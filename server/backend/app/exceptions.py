"""
全局异常处理器 —— 把各种异常转成统一返回体格式，
前端只需要看 code/message/data 三字段。
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .schemas import err


def register_exception_handlers(app: FastAPI) -> None:
    """在 main.py 的 create_app 里调一次即可"""

    @app.exception_handler(HTTPException)
    async def _handle_http(_, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=err(code=exc.status_code, message=str(exc.detail) or "http error"),
            headers=exc.headers,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_starlette(_, exc: StarletteHTTPException):
        # 兼容 Starlette 原生异常（404/405 等）
        return JSONResponse(
            status_code=exc.status_code,
            content=err(code=exc.status_code, message=exc.detail or "http error"),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_, exc: RequestValidationError):
        # 请求体字段校验失败，把 pydantic errors 转成可读字符串
        detail = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        return JSONResponse(
            status_code=422,
            content=err(code=422, message=f"参数校验失败: {detail}"),
        )

    @app.exception_handler(ValueError)
    async def _handle_value_error(_, exc: ValueError):
        # 状态机 / 业务校验错误 → 400
        return JSONResponse(
            status_code=400,
            content=err(code=400, message=str(exc)),
        )

    @app.exception_handler(Exception)
    async def _handle_any(_, exc: Exception):
        # 兜底：未知异常 → 500，message 里不暴露敏感信息
        from utils.logger import logger
        logger.exception(f"[Unhandled] {exc}")
        return JSONResponse(
            status_code=500,
            content=err(code=500, message=f"服务内部错误: {type(exc).__name__}"),
        )
