"""AI 接口独立限流的验证

不需要真实调用 LLM：中间件在路由匹配之前就计数，所以打到不存在的
/agent/* 路径（返回 404）同样能验证配额是否生效。
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app

LIMIT = 12


def test_agent_quota_blocks_after_limit():
    with TestClient(app) as client:
        codes = [client.post("/api/v1/agent/__ping").status_code for _ in range(LIMIT + 2)]

    # 配额内的请求落到路由层；该路径未注册，POST 会得到 405
    assert codes[:LIMIT] == [405] * LIMIT, codes
    # 超出后由中间件直接拦下
    assert codes[LIMIT:] == [429, 429], codes


def test_agent_quota_message_is_actionable():
    with TestClient(app) as client:
        for _ in range(LIMIT):
            client.post("/api/v1/agent/__ping")
        res = client.post("/api/v1/agent/__ping")

    assert res.status_code == 429
    body = res.json()
    assert body["code"] == 429
    assert "每分钟" in body["message"]
    assert res.headers.get("Retry-After")


def test_normal_endpoints_not_limited():
    """普通接口不受 AI 配额影响"""
    with TestClient(app) as client:
        codes = [client.get("/healthz").status_code for _ in range(20)]
    assert set(codes) == {200}


def test_static_page_served_on_same_port():
    """单端口部署：首页由后端托管"""
    with TestClient(app) as client:
        res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
