"""
单据 CRUD + 状态变更路由。
创建/编辑/删除/提交/重提/撤销 都走这里；
审批动作单独在 approvals.py，查询在 queries.py。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..dependencies import get_current_user
from ..models import ApprovalLog, Document, DocumentStatus, User
from ..schemas import (
    DocumentCreate,
    DocumentOut,
    DocumentUpdate,
)
from ..state_machine import can_edit, validate_transition
from ..schemas import ok

router = APIRouter(prefix="/documents", tags=["documents"])


# ---------- 创建 ----------
@router.post("", response_model=dict, status_code=201)
async def create_document(
    req: DocumentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = Document(
        title=req.title,
        content=req.content,
        doc_type=req.doc_type,
        status=DocumentStatus.DRAFT,
        submitter_id=user.id,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return ok(DocumentOut.model_validate(doc).model_dump())


# ---------- 详情 ----------
@router.get("/{doc_id}", response_model=dict)
async def get_document(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = await _get_owned_or_permitted(db, doc_id, user)
    return ok(DocumentOut.model_validate(doc).model_dump())


# ---------- 更新（仅编辑期允许）----------
@router.put("/{doc_id}", response_model=dict)
async def update_document(
    doc_id: int,
    req: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = await _get_owned_or_permitted(db, doc_id, user)
    if doc.submitter_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权修改他人单据")
    if not can_edit(doc.status):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"当前状态 {doc.status.value} 不允许编辑")

    patch = req.model_dump(exclude_unset=True)
    for k, v in patch.items():
        setattr(doc, k, v)
    doc.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(doc)
    return ok(DocumentOut.model_validate(doc).model_dump())


# ---------- 删除（仅草稿/驳回，且只能本人或 admin）----------
@router.delete("/{doc_id}", response_model=dict)
async def delete_document(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = await _get_owned_or_permitted(db, doc_id, user)
    if doc.submitter_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权删除")
    if not can_edit(doc.status):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"当前状态 {doc.status.value} 不允许删除")

    # 先清理审批留痕，否则 approval_logs.document_id 外键会阻止删除（500）
    await db.execute(delete(ApprovalLog).where(ApprovalLog.document_id == doc.id))
    await db.delete(doc)
    await db.commit()
    return ok({"deleted": doc_id})


# ---------- 通用状态变更：submit / resubmit / cancel ----------
@router.post("/{doc_id}/transition/{target}", response_model=dict)
async def transition_document(
    doc_id: int,
    target: DocumentStatus,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = await _get_owned_or_permitted(db, doc_id, user)

    # 只有 submitter / admin 能发起 submit / resubmit / cancel
    if doc.submitter_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只有发起人或 admin 能变更单据状态")

    # 严格状态机校验（非法流转会抛 ValueError → 被全局 handler 转 400）
    action = validate_transition(doc.status, target, actor=user.username)

    # 执行流转
    doc.status = target
    doc.updated_at = datetime.utcnow()

    if action == "submit":
        doc.submitted_at = datetime.utcnow()
        # TODO: 实际项目里这里可按 doc_type 查一条审批链，填上 current_approver_id
    elif action == "resubmit":
        doc.submitted_at = datetime.utcnow()
        doc.current_approver_id = None
    elif action == "cancel":
        doc.closed_at = datetime.utcnow()

    await db.commit()
    await db.refresh(doc)
    return ok(DocumentOut.model_validate(doc).model_dump())


# ---------- 内部辅助 ----------
async def _get_owned_or_permitted(
    db: AsyncSession, doc_id: int, user: User
) -> Document:
    """取单据：本人所有单据 / approver / admin 都能看"""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"单据不存在 id={doc_id}")

    is_owner = doc.submitter_id == user.id
    is_admin = user.role == "admin"
    is_pending_me = (
        doc.status == DocumentStatus.PENDING
        and doc.current_approver_id == user.id
    )
    if not (is_owner or is_admin or is_pending_me):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该单据")
    return doc
