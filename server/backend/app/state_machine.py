"""
单据状态机 —— 严格校验，任何非法流转直接抛 ValueError（
由 exceptions.py 捕获转成 400）。

合法流转图：

    编辑期:  DRAFT ──提交──▶ PENDING
              DRAFT ──撤销──▶ CANCELLED

    审批期:  PENDING ──通过──▶ APPROVED
              PENDING ──驳回──▶ REJECTED
              PENDING ──撤销──▶ CANCELLED

    驳回后:  REJECTED ──重新提交──▶ PENDING    （内容已修订）
              REJECTED ──撤销──▶ CANCELLED

终态：APPROVED / CANCELLED 不可再变
"""
from __future__ import annotations

from typing import Optional

from .models import DocumentStatus


# ---------- 合法流转表 ----------
# current_status → { target_status: "触发动作名" }
_TRANSITIONS: dict[DocumentStatus, dict[DocumentStatus, str]] = {
    DocumentStatus.DRAFT: {
        DocumentStatus.PENDING: "submit",
        DocumentStatus.CANCELLED: "cancel",
    },
    DocumentStatus.PENDING: {
        DocumentStatus.APPROVED: "approve",
        DocumentStatus.REJECTED: "reject",
        DocumentStatus.CANCELLED: "cancel",
    },
    DocumentStatus.REJECTED: {
        DocumentStatus.PENDING: "resubmit",
        DocumentStatus.CANCELLED: "cancel",
    },
    # APPROVED / CANCELLED 是终态，没有可出边
    DocumentStatus.APPROVED: {},
    DocumentStatus.CANCELLED: {},
}

# 终态集合
_TERMINAL = {DocumentStatus.APPROVED, DocumentStatus.CANCELLED}


def validate_transition(
    current: DocumentStatus,
    target: DocumentStatus,
    *,
    actor: Optional[str] = None,
) -> str:
    """
    校验 current → target 是否合法。

    :return: 触发动作名（submit / approve / reject / resubmit / cancel）
    :raises ValueError: 非法流转，附带可读错误信息
    """
    if current == target:
        raise ValueError(f"状态未变化：已是 {current.value}")

    allowed = _TRANSITIONS.get(current, {})
    if target not in allowed:
        hint = f"（当前为终态，不可再变更）" if current in _TERMINAL else ""
        raise ValueError(
            f"非法状态流转：{current.value} → {target.value} {hint}"
            f"{f' 操作者={actor}' if actor else ''}"
        )
    return allowed[target]


def is_terminal(status: DocumentStatus) -> bool:
    """终态判断"""
    return status in _TERMINAL


def can_edit(status: DocumentStatus) -> bool:
    """哪些状态允许修改单据正文：草稿 / 驳回后"""
    return status in {DocumentStatus.DRAFT, DocumentStatus.REJECTED}
