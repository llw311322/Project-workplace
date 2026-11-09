"""
Agent 路由 —— SSE 流式对话 / 非流式摘要 / 非流式校验。
统一走 agent_service 做超时 + 降级兜底；限流 5次/分钟。
"""
from __future__ import annotations

import json as _json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agent_service import (
    chat_agent,
    stream_chat_agent,
    summarize_document,
    validate_document,
)
from ..config import settings
from ..database import get_db
from ..dependencies import check_rate_limit, get_current_user
from ..models import Document, User
from ..quota import quota
from ..schemas import (
    AgentChatRequest,
    AgentDocSummaryRequest,
    AgentDocValidateRequest,
    ok,
)

router = APIRouter(prefix="/agent", tags=["agent"])


# ---------- 非流式：摘要 ----------
@router.post("/summary", response_model=dict)
async def agent_summary(
    req: AgentDocSummaryRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # 限流 5次/分钟（每个用户维度）
    await check_rate_limit(f"agent_summary:{user.id}", max_requests=5, window_seconds=60)(request)
    quota.consume(user.id)  # 日配额 / 全局预算护栏

    doc = await _load_doc(db, req.document_id, user)
    text = await summarize_document(doc.content, timeout_seconds=settings.AGENT_TIMEOUT_SECONDS)
    quota.record_usage(len(doc.content), len(text))

    # 回写到单据 summary 字段（异步可忽略失败）
    doc.summary = text
    from datetime import datetime
    doc.updated_at = datetime.utcnow()
    try:
        await db.commit()
    except Exception:
        await db.rollback()

    return ok({"summary": text})


# ---------- 非流式：校验 ----------
@router.post("/validate", response_model=dict)
async def agent_validate(
    req: AgentDocValidateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await check_rate_limit(f"agent_validate:{user.id}", max_requests=5, window_seconds=60)(request)
    quota.consume(user.id)

    doc = await _load_doc(db, req.document_id, user)
    text = await validate_document(
        doc.content, rules=req.rules,
        timeout_seconds=settings.AGENT_TIMEOUT_SECONDS,
    )
    quota.record_usage(len(doc.content), len(text))

    doc.agent_validated = True
    doc.agent_check_result = text
    from datetime import datetime
    doc.updated_at = datetime.utcnow()
    try:
        await db.commit()
    except Exception:
        await db.rollback()

    return ok({"validation": text, "agent_validated": True})


# ---------- SSE 流式对话 ----------
@router.post("/chat/stream")
async def agent_chat_stream(
    req: AgentChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # 限流（5次/分钟），SSE 连接本身占一个“次”
    await check_rate_limit(f"agent_chat_stream:{user.id}", max_requests=5, window_seconds=60)(request)
    quota.consume(user.id)

    doc = await _resolve_claim_doc(db, req.claim_id, user)
    prompt = _with_doc_context(req.question, doc)

    # generator 被 StreamingResponse 消费；Agent 内部异常已在 agent_service 里兜底
    gen = stream_chat_agent(
        prompt,
        model_key=req.model_key,
        timeout_seconds=req.timeout_seconds,
    )
    return StreamingResponse(
        _metered_stream(gen, prompt_chars=len(prompt)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",   # Nginx 关闭缓冲
        },
    )


# ---------- 非流式对话（调试 / 简单场景）----------
@router.post("/chat", response_model=dict)
async def agent_chat(
    req: AgentChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await check_rate_limit(f"agent_chat:{user.id}", max_requests=5, window_seconds=60)(request)
    quota.consume(user.id)

    doc = await _resolve_claim_doc(db, req.claim_id, user)
    prompt = _with_doc_context(req.question, doc)

    result = await chat_agent(
        prompt,
        model_key=req.model_key,
        timeout_seconds=req.timeout_seconds,
    )
    quota.record_usage(len(prompt), len(result))
    return ok({"answer": result})


# ---------- 额度查询（演示护栏是否在工作 / 前端提示剩余次数）----------
@router.get("/quota", response_model=dict)
async def agent_quota(user: User = Depends(get_current_user)):
    return ok(quota.snapshot(user.id))


# ---------- 内部 ----------
def _with_doc_context(question: str, doc: Document | None) -> str:
    """把当前打开的单据注入对话提示词。

    没有这层注入时，模型收到的只有问题本身（如“帮我总结这张单据的要点”），
    只能回答“未提交单据内容”——这是详情页 AI 对话曾经答非所问的根因。
    """
    if doc is None:
        return question
    return (
        "你是工厂申领单审批助手。用户当前打开了一张申领单，完整内容如下"
        "（content 为 JSON 信封：v1、code、workshop、items、urgency、events）。\n"
        f"【单据标题】{doc.title}\n"
        f"【单据内容】{doc.content}\n\n"
        "请只基于以上单据内容与通用业务知识回答；单据里没有的信息不要编造，"
        "明确说明“单据中未包含该信息”。\n"
        f"【用户问题】{question}"
    )


async def _resolve_claim_doc(
    db: AsyncSession, claim_id: str | None, user: User
) -> Document | None:
    """把前端传来的 claim_id 解析成单据（带归属校验）；未传则返回 None。"""
    if not claim_id:
        return None
    try:
        doc_id = int(claim_id)
    except (TypeError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"单据 id 非法：{claim_id}")
    return await _load_doc(db, doc_id, user)


async def _metered_stream(gen, *, prompt_chars: int):
    """包一层流式生成器，统计实际吐出的字符数用于预算估算。

    放在 finally 里保证：客户端中途断开（SSE 被取消）也能记账，
    否则一次长回答的花费会因为断连而漏记。
    """
    answer_chars = 0
    try:
        async for chunk in gen:
            answer_chars += len(chunk)
            yield chunk
    finally:
        quota.record_usage(prompt_chars, answer_chars)


async def _load_doc(db: AsyncSession, doc_id: int, user: User) -> Document:
    res = await db.execute(select(Document).where(Document.id == doc_id))
    doc = res.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"单据不存在 id={doc_id}")
    if not (doc.submitter_id == user.id or user.role in {"admin", "approver"}):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该单据")
    return doc
