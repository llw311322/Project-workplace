"""自定义中间件：AI 接口独立限流

全局限流（slowapi 60/min）保护的是普通查询接口。Agent 接口每次调用要打真实
LLM，单次成本远高于一次查询，公网部署后很容易被脚本刷爆额度，所以单独按 IP
做更严格的滑动窗口限流。

实现上刻意用**纯 ASGI 中间件**而不是 BaseHTTPMiddleware：后者会包裹响应体，
对流式（SSE）响应存在缓冲风险，会让逐字输出变成一次性吐出。
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class AgentRateLimitMiddleware:
    """对 /api/v1/agent/* 按客户端 IP 做滑动窗口限流"""

    # 类级共享：同一进程只有一个应用实例，同时方便测试整体清空窗口
    _hits: dict[str, deque[float]] = defaultdict(deque)

    def __init__(
        self,
        app: ASGIApp,
        *,
        limit: int = 12,
        window_seconds: int = 60,
        prefix: str = "/api/v1/agent",
    ) -> None:
        self.app = app
        self.limit = limit
        self.window = window_seconds
        self.prefix = prefix
        self._last_gc = time.time()

    @classmethod
    def reset(cls) -> None:
        """仅测试用：清空所有窗口计数（测试共享同一进程与同一 IP）"""
        cls._hits.clear()

    # ---------- 内部工具 ----------

    @staticmethod
    def _client_key(scope: Scope) -> str:
        """优先取反向代理转发后的真实 IP"""
        headers = dict(scope.get("headers") or [])
        fwd = headers.get(b"x-forwarded-for")
        if fwd:
            return fwd.decode("latin-1").split(",")[0].strip()
        client = scope.get("client")
        return client[0] if client else "unknown"

    def _gc(self, now: float) -> None:
        """定期清理过期桶，避免内存无上限增长"""
        if now - self._last_gc < 300:
            return
        self._last_gc = now
        for key in list(self._hits):
            q = self._hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if not q:
                self._hits.pop(key, None)

    # ---------- ASGI 入口 ----------

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith(self.prefix):
            await self.app(scope, receive, send)
            return

        now = time.time()
        self._gc(now)

        key = self._client_key(scope)
        q = self._hits[key]
        while q and now - q[0] > self.window:
            q.popleft()

        if len(q) >= self.limit:
            retry_after = max(1, int(self.window - (now - q[0])))
            body: dict[str, Any] = {
                "code": 429,
                "message": (
                    f"AI 接口繁忙：同一访客每分钟最多 {self.limit} 次调用，"
                    f"请 {retry_after} 秒后再试"
                ),
                "data": None,
            }
            response = JSONResponse(
                status_code=429,
                content=body,
                headers={"Retry-After": str(retry_after)},
            )
            await response(scope, receive, send)
            return

        q.append(now)
        await self.app(scope, receive, send)
