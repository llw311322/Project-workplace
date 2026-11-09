"""
FastAPI 应用入口 —— 创建 app、挂路由、注册异常处理器、
配置 slowapi 全局限流、生命周期里管 DB/Redis 连接。

启动方式：
    uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .config import settings
from .database import engine
from .exceptions import register_exception_handlers
from .middleware import AgentRateLimitMiddleware

# 路由导入
from .routes.auth import router as auth_router
from .routes.documents import router as documents_router
from .routes.approvals import router as approvals_router
from .routes.queries import router as queries_router
from .routes.agent import router as agent_router

# 货品申领单适配层（把前端 /claims/* 契约映射到通用 Document，不改 models）
from .routes.claims import router as claims_router, agent_router as agent_claims_router

# 制度知识库检索（只读，复用 server/rag）
from .routes.kb import router as kb_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    from utils.logger import logger

    # ---------- 启动 ----------
    logger.info(f"🚀 应用启动：DEV_MODE={settings.DEV_MODE}")
    if settings.DEV_MODE:
        # DEV_MODE：自动建 SQLite 表 + 种子用户
        from .database import init_db
        await init_db()
        logger.info(f"💾 SQLite 数据库文件：{settings.DEV_SQLITE_PATH}")

    yield  # ← 服务运行中

    # ---------- shutdown ----------
    logger.info("🛑 应用关闭：释放资源")
    await engine.dispose()
    try:
        from .redis_client import close_redis
        await close_redis()
    except Exception:
        pass  # DEV_MODE 下 Redis 可能没连，忽略


def create_app() -> FastAPI:
    app = FastAPI(
        title="Agent 业务后端",
        version="0.1.0",
        description="单据 CRUD + 审批流 + Agent 摘要/校验/SSE 对话",
        lifespan=lifespan,
    )

    # ---------- AI 接口独立限流 ----------
    # 每次调用都要打真实 LLM，单次成本远高于普通查询。公网暴露后必须防止被刷。
    # 注意顺序：先加的在内层、后加的在外层，CORS 需要包在最外面才能给 429 补上跨域头。
    app.add_middleware(AgentRateLimitMiddleware, limit=12, window_seconds=60)

    # ---------- CORS ----------
    # 单端口部署时前后端同源，其实不依赖 CORS；保留宽松策略是为了本地用
    # vite dev server（5173）直连方便。鉴权走 Bearer Header 而非 Cookie，
    # 因此关掉 allow_credentials —— 它与 allow_origins=["*"] 同时开启在浏览器侧本就无效。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---------- slowapi 全局 ----------
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["60/minute"],
        storage_uri="memory://",
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ---------- 异常 ----------
    register_exception_handlers(app)

    # ---------- 路由挂载 ----------
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(documents_router, prefix="/api/v1")
    app.include_router(approvals_router, prefix="/api/v1")
    app.include_router(queries_router, prefix="/api/v1")
    app.include_router(agent_router, prefix="/api/v1")
    app.include_router(claims_router, prefix="/api/v1")
    app.include_router(agent_claims_router, prefix="/api/v1")
    app.include_router(kb_router, prefix="/api/v1")

    # ---------- 简单健康检查 ----------
    @app.get("/healthz")
    async def healthz():
        return {"status": "ok", "jwt_expire_minutes": settings.JWT_EXPIRE_MINUTES}

    # ---------- 前端静态托管（单端口部署） ----------
    # 把 vite build 的 dist 交给同一个进程提供，一个端口同时跑页面和 API。
    # 好处：局域网直接访问 http://内网IP:8001，公网只需暴露一个端口，
    # 也不用再管 Vite dev server 与代理。dist 不存在时自动跳过，开发模式照旧。
    _mount_frontend(app)

    return app


def _mount_frontend(app: FastAPI) -> None:
    """挂载打包后的前端；SPA 路由回落到 index.html"""
    here = Path(__file__).resolve()
    candidates = [
        # 部署包结构：<root>/backend/app/main.py → <root>/static
        here.parents[2] / "static",
        # 开发结构：<项目根>/server/backend/app/main.py → <项目根>/dist
        here.parents[3] / "dist",
    ]
    dist_dir = next((p for p in candidates if (p / "index.html").is_file()), None)

    if dist_dir is None:
        from utils.logger import logger

        logger.info("ℹ️ 未找到前端产物（static/ 或 dist/），跳过前端托管；开发模式请用 vite dev server")
        return

    index_file = dist_dir / "index.html"
    from utils.logger import logger

    logger.info(f"🖥️ 前端托管目录：{dist_dir}")

    assets_dir = dist_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    # 这些前缀交给 FastAPI 自己处理，未命中时返回 JSON 404 而不是首页 HTML
    reserved = ("api", "docs", "redoc", "openapi.json", "healthz")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if full_path.split("/", 1)[0] in reserved:
            raise HTTPException(status_code=404, detail="Not Found")
        target = dist_dir / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(index_file)


app = create_app()
