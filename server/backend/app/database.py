"""
SQLAlchemy 2.0 异步引擎 + 会话工厂。
DEV_MODE 用 SQLite（aiosqlite），生产用 PostgreSQL（asyncpg）。
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import settings

# ---------- 建 engine ----------
if settings.DEV_MODE:
    # SQLite 模式：没有连接池，参数简单
    # 先确保 data/ 目录存在
    db_path = Path(settings.DEV_SQLITE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine: AsyncEngine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        future=True,
        # SQLite 特殊：单连接 + 禁用连接池（SQLite 不支持多连接并发写）
        connect_args={"check_same_thread": False},
    )
else:
    # PostgreSQL 模式
    engine: AsyncEngine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        future=True,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )

# ---------- 异步 Session 工厂 ----------
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 依赖注入：每个请求一个 session，
    请求结束自动 close（任何异常都能正确释放连接）。
    """
    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """
    DEV_MODE 启动时自动建表 + 种子用户。
    生产模式用 Alembic 迁移，不走这里。
    """
    if not settings.DEV_MODE:
        return

    from . import models  # noqa: F401  确保所有 ORM 模型被注册

    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)

    # 种子用户（bcrypt hash 占位，实际登录用我们写死的校验）
    async with async_session_maker() as session:
        from sqlalchemy import select
        from .models import User

        existing = (await session.execute(select(User).limit(1))).scalar_one_or_none()
        if existing is None:
            import logging
            import os
            import secrets

            log = logging.getLogger("dev_init")
            log.info("🌱 DEV_MODE：首次启动，创建种子用户...")

            # 演示口令不写死在代码里：优先读 DEMO_SEED_PASSWORD；
            # 未设置时随机生成并只在本地日志里打印一次。
            seed_password = os.getenv("DEMO_SEED_PASSWORD", "").strip()
            random_generated = not seed_password
            if random_generated:
                seed_password = secrets.token_urlsafe(8)

            # 用 passlib 生成真实 bcrypt hash
            try:
                from passlib.context import CryptContext
                pwd_ctx = CryptContext(schemes=["bcrypt"])
                hash_submitter = pwd_ctx.hash(seed_password)
                hash_approver = pwd_ctx.hash(seed_password)
            except Exception as exc:
                # passlib 缺失时放弃种子（登录接口会正常报错，而不是留后门）
                log.warning("passlib 不可用，跳过种子用户创建: %s", exc)
                await session.rollback()
                return

            session.add_all([
                User(username="0001", password_hash=hash_submitter,
                     role="submitter", display_name="张三"),
                User(username="1001", password_hash=hash_approver,
                     role="approver", display_name="李四"),
            ])
            await session.commit()
            log.info("✅ 种子用户创建完成（工号 0001 张三 / 1001 李四）")
            if random_generated:
                log.info("🔑 本次随机生成的演示口令: %s （仅限本地演示，重启后重新生成）",
                         seed_password)
            else:
                log.info("🔑 演示口令来自环境变量 DEMO_SEED_PASSWORD")
