"""
统一配置层 —— 基于 pydantic-settings，
所有敏感项从 .env / 环境变量读取，类型自动校验。
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


# ========== JWT 签名密钥 ==========
# 签名密钥对「同一次部署的所有进程/副本」必须是同一把，否则会出现
# 「刚登录就提示登录已过期」——签发与校验落在不同副本上，签名验不过。
# 因此密钥必须显式配置：生产环境通过环境变量 JWT_SIGNING_KEY 下发统一值
# （正确做法是接 KMS/密钥管理服务）。未配置时进程内随机生成兜底，
# 仅适合单进程本地演示，且重启后已有登录态全部失效。
import os
import secrets

JWT_SIGNING_KEY = os.getenv("JWT_SIGNING_KEY", "")
if not JWT_SIGNING_KEY:
    JWT_SIGNING_KEY = secrets.token_hex(32)


class Settings(BaseSettings):
    # ========== Dev 模式开关 ==========
    # true 时用 SQLite + FakeRedis 替代 PostgreSQL/Redis，快速本地跑通全链路
    DEV_MODE: bool = True
    DEV_SQLITE_PATH: str = "./data/dev.db"

    # ========== PostgreSQL ==========
    POSTGRES_HOST: str = "127.0.0.1"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "agent_app"

    # ========== Redis ==========
    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # ========== JWT ==========
    # 注意：签名实际使用下方模块级常量 JWT_SIGNING_KEY，不再读这个字段。
    # 保留字段只为兼容旧配置，避免 pydantic 因未知键报错。
    JWT_SECRET: str = ""                    # 已弃用，见 JWT_SIGNING_KEY
    JWT_EXPIRE_MINUTES: int = 10080         # 7 天（演示环境，避免介绍过程中掉线）

    # ========== Agent 超时 ==========
    AGENT_TIMEOUT_SECONDS: int = 5           # Agent 调用硬性超时

    # ========== Agent 成本护栏（公网部署必需）==========
    # 单用户每日调用次数上限，0 表示不限。演示环境 30 次足够体验完整流程
    AGENT_DAILY_QUOTA_PER_USER: int = 30
    # 全局每日预算上限（元），超过后所有 AI 调用熔断，0 表示不限
    AGENT_DAILY_BUDGET_YUAN: float = 3.0
    # 每千 token 单价（元），用于估算花费。按所用厂商的输入/输出均价取一个偏保守值
    AGENT_PRICE_PER_1K_TOKENS: float = 0.002

    # pydantic-settings 会自动加载项目根目录的 .env
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ---------- 便捷派生 ----------
    @property
    def DATABASE_URL(self) -> str:
        """DEV_MODE 用 SQLite，生产用 PostgreSQL asyncpg"""
        if self.DEV_MODE:
            # aiosqlite 异步驱动，SQLite 文件式存储
            return f"sqlite+aiosqlite:///{self.DEV_SQLITE_PATH}"
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def REDIS_URL(self) -> str:
        """aioredis 连接串"""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """单例，整个进程共享"""
    return Settings()


settings = get_settings()
