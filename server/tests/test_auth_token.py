"""登录态回归测试 —— 钉住「签发与校验必须是同一把钥匙」这个坑。

背景：
    线上曾出现「刚登录就提示登录已过期」。根因不是 token 过期，而是签名密钥
    来自环境变量，托管平台多副本各自拿到不同值，登录请求与校验请求落在不同
    副本上，签名必然对不上。修复方式是把签名密钥固化为模块级常量。

本测试守住三件事：
    1. 自己签发的 token 能被自己校验（同进程一致性）
    2. 环境变量里出现 JWT_SECRET 也不影响签名结果（密钥不再受环境摆布）
    3. 完整链路 login → /auth/me 能拿到当前用户
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

from backend.app.config import JWT_SIGNING_KEY  # noqa: E402
from backend.app.dependencies import _decode_token, create_access_token  # noqa: E402
from backend.app.main import app  # noqa: E402


def test_token_roundtrip():
    """自签自验必须通过，且能取回原来的 sub"""
    token, expire_ts = create_access_token(2)
    assert _decode_token(token) == "2"
    assert expire_ts > 0


def test_signing_key_isolation_from_env(monkeypatch):
    """即使环境里塞了一个假的 JWT_SECRET，签名结果也不该改变"""
    baseline, _ = create_access_token(1)

    monkeypatch.setenv("JWT_SECRET", "a-totally-different-secret-from-platform")
    # 密钥在模块导入时已确定，无关的 JWT_SECRET 字段不应改写它
    assert isinstance(JWT_SIGNING_KEY, str) and len(JWT_SIGNING_KEY) >= 32
    assert _decode_token(baseline) == "1"


@pytest.mark.parametrize("username,expected_role", [("0001", "submitter"), ("1001", "approver")])
def test_login_then_me(username, expected_role):
    """登录拿到的 token 立刻用于 /auth/me 必须 200，这是线上故障的回归点"""
    with TestClient(app) as client:
        resp = client.post("/api/v1/auth/login", json={"username": username, "password": "123456"})
        assert resp.status_code == 200, resp.text
        token = resp.json()["data"]["access_token"]

        me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200, me.text
        data = me.json()["data"]
        assert data["username"] == username
        assert data["role"] == expected_role


def test_x_auth_token_survives_gateway_injection():
    """托管平台网关会用自己的内部凭据改写 Authorization 头。

    回归点：客户端 token 走自定义头 X-Auth-Token，即使 Authorization 被
    网关注入成别人的值，鉴权也必须成功。
    """
    with TestClient(app) as client:
        resp = client.post("/api/v1/auth/login", json={"username": "1001", "password": "123456"})
        assert resp.status_code == 200
        token = resp.json()["data"]["access_token"]

        # 只带自定义头
        me = client.get("/api/v1/auth/me", headers={"X-Auth-Token": token})
        assert me.status_code == 200, me.text
        assert me.json()["data"]["username"] == "1001"

        # 模拟网关注入：Authorization 是别人的垃圾值，自定义头仍是我们的 token
        me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer gateway-injected-junk", "X-Auth-Token": token},
        )
        assert me.status_code == 200, me.text
        assert me.json()["data"]["username"] == "1001"
