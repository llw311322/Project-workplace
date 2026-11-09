"""LLM 成本护栏测试 —— 日配额、预算熔断、跨天归零、日志脱敏。

为什么值得单独测：公网部署后这层是唯一能阻止"游客刷爆 API Key"的代码护栏，
它失效不会报错、只会安静地烧钱，所以必须有回归测试钉住。
"""
from __future__ import annotations

import logging
import os
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

# 种子口令不写死在应用里；测试通过环境变量显式声明（见 database.py）
os.environ.setdefault("DEMO_SEED_PASSWORD", "123456")

from backend.app.config import settings
from backend.app.quota import DailyQuota, quota
from backend.app.main import app


def _login(client: TestClient, username: str = "0001") -> dict:
    res = client.post("/api/v1/auth/login", json={"username": username, "password": "123456"})
    assert res.status_code == 200, res.text
    return {"X-Auth-Token": res.json()["data"]["access_token"]}


# ---------------------------------------------------------------- 配额


def test_per_user_daily_limit_blocks_after_threshold(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_DAILY_QUOTA_PER_USER", 3)
    q = DailyQuota()
    for _ in range(3):
        q.consume(1)  # 前 3 次通过
    with pytest.raises(HTTPException) as exc:
        q.consume(1)
    assert exc.value.status_code == 429
    assert "额度已用完" in str(exc.value.detail)
    # 另一个用户不受影响（配额是按人计的）
    q.consume(2)


def test_quota_disabled_when_zero(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_DAILY_QUOTA_PER_USER", 0)
    q = DailyQuota()
    for _ in range(50):
        q.consume(1)  # 0 = 不限


# ---------------------------------------------------------------- 预算


def test_global_budget_circuit_breaker(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_DAILY_QUOTA_PER_USER", 0)
    monkeypatch.setattr(settings, "AGENT_DAILY_BUDGET_YUAN", 0.0001)
    monkeypatch.setattr(settings, "AGENT_PRICE_PER_1K_TOKENS", 0.002)
    q = DailyQuota()
    q.consume(1)
    q.record_usage(2000, 2000)  # 4000 字 ≈ 6000 token ≈ 0.012 元，超预算
    with pytest.raises(HTTPException) as exc:
        q.consume(2)  # 换个人来也不给用：预算熔断是全局的
    assert exc.value.status_code == 429
    assert "预算" in str(exc.value.detail)


def test_snapshot_reports_remaining_and_spend(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_DAILY_QUOTA_PER_USER", 10)
    q = DailyQuota()
    q.consume(7)
    q.consume(7)
    q.record_usage(1000, 1000)
    snap = q.snapshot(7)
    assert snap["user_used"] == 2
    assert snap["user_remaining"] == 8
    assert snap["spend_yuan"] > 0
    assert snap["budget_exhausted"] is False


# ---------------------------------------------------------------- 跨天归零


def test_counters_roll_over_next_day(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_DAILY_QUOTA_PER_USER", 1)
    q = DailyQuota()
    q.consume(1)
    with pytest.raises(HTTPException):
        q.consume(1)

    # 模拟"昨天用完了，今天自然恢复"
    q._state.day = date.today() - timedelta(days=1)
    q.consume(1)
    assert q.snapshot(1)["user_used"] == 1
    assert q.snapshot(1)["global_calls"] == 1  # 昨天的计数也一起归零


# ---------------------------------------------------------------- HTTP 层


def test_chat_route_returns_429_with_actionable_message(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_DAILY_QUOTA_PER_USER", 1)

    async def fake_chat(question: str, **_kw):
        return "好的"

    monkeypatch.setattr("backend.app.routes.agent.chat_agent", fake_chat)

    with TestClient(app) as client:
        headers = _login(client)
        first = client.post("/api/v1/agent/chat", json={"question": "领用流程"}, headers=headers)
        assert first.status_code == 200, first.text

        second = client.post("/api/v1/agent/chat", json={"question": "领用流程"}, headers=headers)
        assert second.status_code == 429
        assert "额度已用完" in second.json()["message"]
        assert second.headers.get("Retry-After") == "3600"


def test_quota_endpoint_exposes_remaining(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_DAILY_QUOTA_PER_USER", 20)
    with TestClient(app) as client:
        headers = _login(client, "1001")
        res = client.get("/api/v1/agent/quota", headers=headers)
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["user_limit"] == 20
        assert data["user_remaining"] == 20
        assert data["budget_exhausted"] is False


# ---------------------------------------------------------------- 日志脱敏


def test_api_key_never_appears_in_logs(caplog):
    """密钥一旦进日志，就会被日志收集系统带走——这是低成本但高价值的约束"""
    from agent import model_scheduler as ms

    sched = ms.ModelScheduler()
    caplog.set_level(logging.DEBUG)
    secret = "sk-demo-very-secret-key-should-never-be-logged"
    for key in sched._configs:
        cfg = sched._configs[key]
        cfg.api_keys = [secret]
        cfg.bad_keys = set()
    if sched._configs:
        sched._pick_key_with_fallback(next(iter(sched._configs)))
    sched.mark_key_fail(next(iter(sched._configs)), secret)

    assert secret not in caplog.text
    assert secret[:15] not in caplog.text
