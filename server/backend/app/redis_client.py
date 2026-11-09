"""
Redis 客户端封装 —— 单例 + 懒加载。

关键取舍：aioredis 只在真正调用 get_redis() 时才 import。
当前运行模式（SQLite）不使用 Redis 缓存，因此整个项目不依赖任何外部中间件，
可以直接作为一个单端口服务整体部署。需要缓存时再装 aioredis 即可。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from .config import settings

if TYPE_CHECKING:  # 仅供类型检查，运行时不导入
    import aioredis

# 模块级单例，首次使用才实例化
_redis: Optional[Any] = None


async def get_redis() -> Any:
    """懒加载：第一次调用才真正连 Redis"""
    global _redis
    if _redis is None:
        try:
            import aioredis  # noqa: F401 —— 延迟到此处导入
        except ImportError as exc:
            raise RuntimeError(
                "未安装 aioredis。当前运行模式不需要 Redis；如启用缓存请先 pip install aioredis"
            ) from exc

        _redis = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis


async def close_redis() -> None:
    """应用 shutdown 时调用，优雅释放连接池"""
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None
