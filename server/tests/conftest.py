"""测试公共隔离。

限流滑动窗口与日配额都是**进程内状态**，测试共享同一进程、同一客户端 IP，
不重置就会互相污染（前一个测试的调用次数把后一个测试的额度吃掉了）。
这里统一在每个用例前后清空，让每个测试都从干净状态开始。
"""
from __future__ import annotations

import pytest

from backend.app.middleware import AgentRateLimitMiddleware
from backend.app.quota import quota


@pytest.fixture(autouse=True)
def _isolate_inprocess_state():
    AgentRateLimitMiddleware.reset()
    quota.reset()
    yield
    AgentRateLimitMiddleware.reset()
    quota.reset()
