"""
统一返回体 + 所有路由共用的 Pydantic 请求/响应模型。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from .models import DocumentStatus

T = TypeVar("T")


# ---------- 统一返回体 ----------
class ApiResponse(BaseModel, Generic[T]):
    """所有接口都套这一层，code=0 表示成功"""
    code: int = 0
    message: str = "ok"
    data: Optional[T] = None


def ok(data: Any = None, message: str = "ok") -> dict:
    """快捷构造成功响应"""
    return {"code": 0, "message": message, "data": data}


def err(code: int, message: str, data: Any = None) -> dict:
    """快捷构造失败响应"""
    return {"code": code, "message": message, "data": data}


# ---------- 认证 ----------
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: Optional[str] = None
    role: str
    created_at: datetime


# ---------- 单据 ----------
class DocumentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="单据标题")
    content: str = Field(..., min_length=1, description="单据正文")
    doc_type: str = Field(default="general", max_length=32)


class DocumentUpdate(BaseModel):
    """只允许编辑期修改的字段"""
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    content: Optional[str] = Field(default=None, min_length=1)
    doc_type: Optional[str] = Field(default=None, max_length=32)


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str
    doc_type: str
    status: DocumentStatus
    submitter_id: int
    current_approver_id: Optional[int] = None
    summary: Optional[str] = None
    agent_validated: bool
    agent_check_result: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    submitted_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None


class DocumentListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    doc_type: str
    status: DocumentStatus
    submitter_id: int
    summary: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ---------- 审批 ----------
class ApprovalRequest(BaseModel):
    comment: Optional[str] = Field(default=None, max_length=2000)


class ApprovalLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    approver_id: int
    action: str
    comment: Optional[str] = None
    created_at: datetime


# ---------- Agent 接口 ----------
class AgentChatRequest(BaseModel):
    """SSE 对话：question 必填，可带上下文 session_id 与当前单据 claim_id"""
    question: str = Field(..., min_length=1, max_length=4000)
    session_id: Optional[str] = None
    claim_id: Optional[str] = Field(default=None, description="当前打开的申领单 id；提供时把单据内容注入提示词")
    model_key: Optional[str] = None           # 可选指定厂商
    timeout_seconds: int = Field(default=5, ge=1, le=60)


class AgentDocSummaryRequest(BaseModel):
    """对单据做摘要"""
    document_id: int


class AgentDocValidateRequest(BaseModel):
    """对单据做合规校验"""
    document_id: int
    rules: Optional[list[str]] = Field(default=None, description="自定义校验规则列表")


class AgentResultOut(BaseModel):
    """非流式 Agent 返回"""
    summary: Optional[str] = None
    validation: Optional[str] = None
    degraded: bool = False           # 是否降级兜底
    fallback_reason: Optional[str] = None
