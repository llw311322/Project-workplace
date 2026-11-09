"""
SQLAlchemy 2.0 ORM 模型 —— 用户 / 单据 / 审批历史 / Agent 会话。
所有字段带中文注释，业务状态枚举集中定义避免魔法字符串。
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ---------- 业务状态枚举（和 state_machine.py 保持一致）----------
class DocumentStatus(str, PyEnum):
    DRAFT = "draft"                 # 草稿（编辑中）
    PENDING = "pending"             # 已提交，待审批
    APPROVED = "approved"           # 审批通过
    REJECTED = "rejected"           # 驳回，可修改后重提
    CANCELLED = "cancelled"         # 发起人主动撤销


class ApprovalAction(str, PyEnum):
    APPROVE = "approve"
    REJECT = "reject"


# ---------- Base ----------
class Base(DeclarativeBase):
    pass


# ---------- 用户 ----------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="submitter")  # submitter / approver / admin
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # 反向引用
    documents: Mapped[list["Document"]] = relationship(
        back_populates="submitter",
        foreign_keys="Document.submitter_id",
    )
    approvals: Mapped[list["ApprovalLog"]] = relationship(
        back_populates="approver",
        foreign_keys="ApprovalLog.approver_id",
    )


# ---------- 单据 ----------
class Document(Base):
    """一张业务单据：申请 / 报销 / 请假 等通用结构"""
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)          # 富文本 / JSON 串
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False, default="general")
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status"),
        nullable=False,
        default=DocumentStatus.DRAFT,
        index=True,
    )

    submitter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    current_approver_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )

    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)          # Agent 生成的摘要
    agent_validated: Mapped[bool] = mapped_column(default=False, nullable=False)  # Agent 是否已校验
    agent_check_result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    submitter: Mapped["User"] = relationship(
        back_populates="documents",
        foreign_keys=[submitter_id],
    )
    approvals: Mapped[list["ApprovalLog"]] = relationship(
        back_populates="document", order_by="ApprovalLog.created_at"
    )


# ---------- 审批历史 ----------
class ApprovalLog(Base):
    """一次审批动作的流水日志"""
    __tablename__ = "approval_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    approver_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    action: Mapped[ApprovalAction] = mapped_column(
        Enum(ApprovalAction, name="approval_action"), nullable=False
    )
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    document: Mapped["Document"] = relationship(back_populates="approvals")
    approver: Mapped["User"] = relationship(back_populates="approvals")


# ---------- Agent 对话会话（可选预留）----------
class AgentConversation(Base):
    """用户和 Agent 的多轮对话归档"""
    __tablename__ = "agent_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="新会话")
    agent_session_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


__all__ = [
    "Base",
    "User",
    "Document",
    "ApprovalLog",
    "AgentConversation",
    "DocumentStatus",
    "ApprovalAction",
]
