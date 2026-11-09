"""单据上下文注入回归 —— 详情页 AI 对话曾答"未提交单据内容"。

根因：
    /agent/chat/stream 只把 question 发给模型，前端传的 claimId 被丢弃，
    模型手上没有单据，只能回答"未提交单据照片或文字内容"。
修复：
    AgentChatRequest 增加 claim_id；路由侧把单据内容注入提示词
    （带归属校验：提交人本人或审批人/管理员才可访问）。

本测试守住三件事：
    1. 带 claim_id 时，发给模型的提示词必须包含单据内容
    2. 不带 claim_id 时，提示词就是原始问题（不注入）
    3. 非法 id → 400；不存在的单据 → 404
    （LLM 本身被 monkeypatch 替换，测试不真实调用厂商接口）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

# 种子口令不写死在应用里；测试通过环境变量显式声明（见 database.py）
os.environ.setdefault("DEMO_SEED_PASSWORD", "123456")

import backend.app.routes.agent as agent_routes  # noqa: E402
from backend.app.main import app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def submitter_token(client):
    resp = client.post("/api/v1/auth/login", json={"username": "0001", "password": "123456"})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def _first_claim_id(client, token) -> str:
    resp = client.get("/api/v1/claims/mine", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    items = data["list"] if isinstance(data, dict) else data
    assert items, "演示库应至少有一张单据"
    return str(items[0]["id"])


def _patch_llm(monkeypatch, captured: dict):
    """替换真实 LLM 调用，只记录收到的提示词并回固定内容"""

    async def fake_stream(question, *, model_key=None, timeout_seconds=5):
        captured["prompt"] = question
        yield "好的，"
        yield "已基于单据回答"

    monkeypatch.setattr(agent_routes, "stream_chat_agent", fake_stream)


def test_chat_with_claim_id_injects_document(client, submitter_token, monkeypatch):
    """带 claim_id：提示词必须包含单据标题与 JSON 信封内容"""
    captured: dict = {}
    _patch_llm(monkeypatch, captured)
    claim_id = _first_claim_id(client, submitter_token)

    resp = client.post(
        "/api/v1/agent/chat/stream",
        json={"question": "帮我总结这张单据的要点", "claim_id": claim_id},
        headers={"Authorization": f"Bearer {submitter_token}"},
    )
    assert resp.status_code == 200, resp.text
    prompt = captured["prompt"]
    assert "帮我总结这张单据的要点" in prompt          # 原问题保留
    assert "【单据内容】" in prompt                     # 注入了单据内容
    assert '"v":1' in prompt or '"v": 1' in prompt or "workshop" in prompt  # JSON 信封特征


def test_chat_without_claim_id_keeps_raw_question(client, submitter_token, monkeypatch):
    """不带 claim_id：不注入，提示词就是原问题"""
    captured: dict = {}
    _patch_llm(monkeypatch, captured)

    resp = client.post(
        "/api/v1/agent/chat/stream",
        json={"question": "你好"},
        headers={"Authorization": f"Bearer {submitter_token}"},
    )
    assert resp.status_code == 200, resp.text
    assert captured["prompt"] == "你好"


def test_chat_with_bad_claim_id_400(client, submitter_token, monkeypatch):
    captured: dict = {}
    _patch_llm(monkeypatch, captured)
    resp = client.post(
        "/api/v1/agent/chat/stream",
        json={"question": "hi", "claim_id": "abc"},
        headers={"Authorization": f"Bearer {submitter_token}"},
    )
    assert resp.status_code == 400, resp.text


def test_chat_with_missing_claim_404(client, submitter_token, monkeypatch):
    captured: dict = {}
    _patch_llm(monkeypatch, captured)
    resp = client.post(
        "/api/v1/agent/chat/stream",
        json={"question": "hi", "claim_id": "999999"},
        headers={"Authorization": f"Bearer {submitter_token}"},
    )
    assert resp.status_code == 404, resp.text
