"""
依赖注入集合 —— get_db / get_current_user / rate_limiter。
FastAPI 路由里用 Depends(...) 引用即可。
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Optional

from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import JWT_SIGNING_KEY, settings
from .database import get_db
from .models import User


# ---------- 密码校验 ----------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain: str, hashed: str) -> bool:
    """统一走 bcrypt 校验，不做任何明码后门。

    种子用户的口令由 DEMO_SEED_PASSWORD 环境变量控制（见 database.py），
    这里只负责核对哈希，不认识任何具体口令。
    """
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


# ---------- JWT ----------
def create_access_token(sub: str | int) -> tuple[str, int]:
    """返回 (token, 过期时间戳秒)"""
    expire_ts = int(time.time()) + settings.JWT_EXPIRE_MINUTES * 60
    payload = {"sub": str(sub), "exp": expire_ts}
    token = jwt.encode(payload, JWT_SIGNING_KEY, algorithm="HS256")
    return token, expire_ts


def _decode_token(token: str) -> str:
    try:
        payload = jwt.decode(token, JWT_SIGNING_KEY, algorithms=["HS256"])
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "无效 token")
        return sub
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"token 解析失败: {e}") from e


# ---------- 当前用户 ----------
async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """从请求头取出用户。

    优先读自定义头 ``X-Auth-Token``，再回退标准 ``Authorization: Bearer``。
    为什么需要自定义头：托管平台的反向代理会用自己的内部凭据**改写**
    Authorization 头（带 sharecode 的网关注入了自己的 Bearer），客户端的
    token 根本到不了后端，所有请求都会 401"登录已过期"。绕开的办法就是
    换一个网关不会碰的头名。
    """
    token = (request.headers.get("X-Auth-Token") or "").strip()
    if not token:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "缺少 Authorization")
        token = auth.split(" ", 1)[1].strip()
    sub = _decode_token(token)

    result = await db.execute(select(User).where(User.id == int(sub)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在")
    return user


def require_role(*roles: str):
    """
    角色守卫工厂：路由里写 Depends(require_role("approver", "admin"))
    返回一个 FastAPI 可用的 async callable。
    """
    async def _guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"需要角色之一: {roles}")
        return user
    return _guard


# ---------- 限流（slowapi）----------
# 默认按 IP 限流；Agent 路由单独 5/min
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["60/minute"],
    storage_uri="memory://",     # 单机内存；多实例可换 redis://
)


# ---------- 轻量内存限流器（给 SSE/WebSocket 补位，slowapi 对 StreamingResponse 支持一般）----------
@dataclass
class _SlidingWindow:
    """简易滑动窗口：按 key 记录时间戳"""
    window_seconds: int = field(default=60)
    max_requests: int = field(default=60)
    _timestamps: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))

    def allow(self, key: str) -> bool:
        now = time.time()
        ts_list = self._timestamps[key]
        # 淘汰窗口外的旧时间戳
        cutoff = now - self.window_seconds
        self._timestamps[key] = [t for t in ts_list if t > cutoff]
        if len(self._timestamps[key]) >= self.max_requests:
            return False
        self._timestamps[key].append(now)
        return True


_mem_limiter = _SlidingWindow(window_seconds=60, max_requests=60)


def check_rate_limit(
    key: str,
    *,
    max_requests: int = 60,
    window_seconds: int = 60,
) -> Callable[[Request], None]:
    """
    返回一个 FastAPI 依赖，5 秒令牌桶。
    用法：Depends(check_rate_limit(f"agent:{user.id}", max_requests=5))
    """
    async def _dep(request: Request):
        # 动态刷新窗口参数
        _mem_limiter.window_seconds = window_seconds
        _mem_limiter.max_requests = max_requests
        if not _mem_limiter.allow(key):
            raise HTTPException(
                status_code=429,
                detail=f"请求过于频繁，{max_requests}次/{window_seconds}s",
                headers={"Retry-After": str(window_seconds)},
            )
    return _dep
