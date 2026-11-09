"""
认证路由 —— 登录发 JWT、当前用户资料。
密码用 passlib[bcrypt] 校验，签名密钥从 config 读。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..dependencies import create_access_token, get_current_user, verify_password
from ..models import User
from ..schemas import LoginRequest, TokenResponse, UserProfile, ok

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=dict)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """用户名密码换 JWT"""
    stmt = select(User).where(User.username == req.username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None or not verify_password(req.password, user.password_hash):
        # 故意模糊错误信息，避免枚举用户名
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")

    token, expire_ts = create_access_token(user.id)
    return ok(TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_at=datetime.utcfromtimestamp(expire_ts),
    ).model_dump())


@router.get("/me", response_model=dict)
async def me(current_user: User = Depends(get_current_user)):
    """取当前登录用户资料（测试 token 用）"""
    return ok(UserProfile.model_validate(current_user).model_dump())
