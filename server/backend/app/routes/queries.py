"""
只读查询路由 —— 我的提交 / 待审批 / 详情含审批历史 / 审批历史单独拉。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..dependencies import get_current_user, require_role
from ..models import ApprovalLog, Document, DocumentStatus, User
from ..schemas import ApprovalLogOut, DocumentListOut, DocumentOut, ok

router = APIRouter(prefix="/queries", tags=["queries"])


@router.get("/mine", response_model=dict)
async def my_documents(
    status: Optional[DocumentStatus] = Query(default=None, description="按状态过滤"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """我的提交列表"""
    stmt = select(Document).where(Document.submitter_id == user.id)
    if status is not None:
        stmt = stmt.where(Document.status == status)
    stmt = stmt.order_by(Document.created_at.desc())
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return ok([DocumentListOut.model_validate(r).model_dump() for r in rows])


@router.get("/pending", response_model=dict)
async def pending_approval(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("approver", "admin")),
):
    """
    待我审批：
      - admin 能看所有 PENDING 单据
      - approver 只看指派给自己的 current_approver_id == user.id
    """
    stmt = select(Document).where(Document.status == DocumentStatus.PENDING)
    if user.role != "admin":
        stmt = stmt.where(
            (Document.current_approver_id == user.id)
            | (Document.current_approver_id.is_(None))  # 未指派兜底也让 approver 可见
        )
    stmt = stmt.order_by(Document.submitted_at.desc())
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return ok([DocumentListOut.model_validate(r).model_dump() for r in rows])


@router.get("/detail/{doc_id}", response_model=dict)
async def document_detail_with_history(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """单据详情 + 审批历史一次性返回"""
    doc_res = await db.execute(select(Document).where(Document.id == doc_id))
    doc = doc_res.scalar_one_or_none()
    if doc is None:
        from fastapi import HTTPException, status as st
        raise HTTPException(st.HTTP_404_NOT_FOUND, f"单据不存在 id={doc_id}")

    # 权限：本人 / admin / 当前审批人可看
    if not (
        doc.submitter_id == user.id
        or user.role == "admin"
        or (doc.status == DocumentStatus.PENDING and doc.current_approver_id == user.id)
    ):
        from fastapi import HTTPException, status as st
        raise HTTPException(st.HTTP_403_FORBIDDEN, "无权查看")

    # 审批历史（从旧到新）
    log_res = await db.execute(
        select(ApprovalLog)
        .where(ApprovalLog.document_id == doc_id)
        .order_by(ApprovalLog.created_at)
    )
    logs = log_res.scalars().all()

    return ok({
        "document": DocumentOut.model_validate(doc).model_dump(),
        "approval_history": [ApprovalLogOut.model_validate(l).model_dump() for l in logs],
    })


@router.get("/history/{doc_id}", response_model=dict)
async def approval_history(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """单独拉审批历史（detail 已带，这是便捷接口）"""
    res = await db.execute(
        select(ApprovalLog)
        .where(ApprovalLog.document_id == doc_id)
        .order_by(ApprovalLog.created_at)
    )
    rows = res.scalars().all()
    return ok([ApprovalLogOut.model_validate(r).model_dump() for r in rows])
