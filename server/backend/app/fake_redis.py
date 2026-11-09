"""
FakeRedis — DEV_MODE 下替代 aioredis 的极简实现。
只支持 get/set/incr/exists/expire 这几个我们限流场景用到的方法。
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional


class FakeRedis:
    """单进程内存 dict，thread-safe 用 asyncio.Lock"""

    def __init__(self):
        self._data: dict[str, tuple[str, float | None]] = {}  # key → (value, expire_at_or_None)
        self._lock = asyncio.Lock()

    def _is_expired(self, key: str) -> bool:
        if key not in self._data:
            return True
        _, expire_at = self._data[key]
        if expire_at is not None and time.time() > expire_at:
            self._data.pop(key, None)
            return True
        return False

    async def get(self, key: str) -> Optional[str]:
        async with self._lock:
            if self._is_expired(key):
                return None
            return self._data[key][0]

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        async with self._lock:
            expire_at = (time.time() + ex) if ex else None
            self._data[key] = (value, expire_at)
            return True

    async def incr(self, key: str) -> int:
        async with self._lock:
            if self._is_expired(key):
                self._data[key] = ("0", None)
            val = int(self._data[key][0]) + 1
            self._data[key] = (str(val), self._data[key][1])
            return val

    async def expire(self, key: str, seconds: int) -> bool:
        async with self._lock:
            if key not in self._data:
                return False
            val, _ = self._data[key]
            self._data[key] = (val, time.time() + seconds)
            return True

    async def delete(self, key: str) -> int:
        async with self._lock:
            return 1 if self._data.pop(key, None) else 0


# ---------- 单例 ----------
_fake_redis: Optional[FakeRedis] = None


def get_fake_redis() -> FakeRedis:
    global _fake_redis
    if _fake_redis is None:
        _fake_redis = FakeRedis()
    return _fake_redis
