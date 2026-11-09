"""
审批路由 —— 只有 approver / admin 能调。
approve / reject 同时写 ApprovalLog，状态由 state_machine 严格校验。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..dependencies import get_current_user, require_role
from ..models import ApprovalAction, ApprovalLog, Document, DocumentStatus, User
from ..schemas import ApprovalLogOut, ApprovalRequest, DocumentOut, ok
from ..state_machine import validate_transition

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.post("/{doc_id}/approve", response_model=dict)
async def approve(
    doc_id: int,
    req: ApprovalRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("approver", "admin")),
):
    doc = await _get_pending_doc(db, doc_id, user)

    # 1. 严格状态机校验
    validate_transition(doc.status, DocumentStatus.APPROVED, actor=user.username)

    # 2. 写流水
    log = ApprovalLog(
        document_id=doc.id,
        approver_id=user.id,
        action=ApprovalAction.APPROVE,
        comment=req.comment,
    )
    db.add(log)

    # 3. 改单据状态
    doc.status = DocumentStatus.APPROVED
    doc.updated_at = datetime.utcnow()
    doc.closed_at = datetime.utcnow()

    await db.commit()
    await db.refresh(doc)
    return ok(DocumentOut.model_validate(doc).model_dump())


@router.post("/{doc_id}/reject", response_model=dict)
async def reject(
    doc_id: int,
    req: ApprovalRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("approver", "admin")),
):
    doc = await _get_pending_doc(db, doc_id, user)

    validate_transition(doc.status, DocumentStatus.REJECTED, actor=user.username)

    log = ApprovalLog(
        document_id=doc.id,
        approver_id=user.id,
        action=ApprovalAction.REJECT,
        comment=req.comment,
    )
    db.add(log)

    doc.status = DocumentStatus.REJECTED
    doc.updated_at = datetime.utcnow()
    doc.closed_at = None  # 驳回不关闭，发起人可重提

    await db.commit()
    await db.refresh(doc)
    return ok(DocumentOut.model_validate(doc).model_dump())


# ---------- 内部：取 PENDING 单据 ----------
async def _get_pending_doc(db: AsyncSession, doc_id: int, user: User) -> Document:
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"单据不存在 id={doc_id}")
    if doc.status != DocumentStatus.PENDING:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"单据当前状态 {doc.status.value}，无法审批",
        )

    # 非 admin 且不是指定当前审批人 → 403
    if user.role != "admin" and doc.current_approver_id is not None and doc.current_approver_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "该单据当前不是指派给你审批")
    return doc
