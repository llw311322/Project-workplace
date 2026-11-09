"""
货品申领单适配层 —— 把前端的「货品申领单契约」（/claims/*）映射到已有的
通用 Document 模型上，**不修改 models.py，也不修改 agent/**。

设计要点
--------
1. 结构化字段统一收在 Document.content 的 JSON 信封里（v=1），不新增数据库列，
   零迁移成本；老数据（纯文本 content）也能读，自动降级。
2. 状态映射：前端 5 态 ↔ 后端 DocumentStatus
       draft      ↔ draft
       submitted  ↔ pending（未指派审批人）
       approving  ↔ pending（已指派审批人）
       approved   ↔ approved
       rejected   ↔ rejected
3. 「撤销提交」按前端语义退回 draft；合法流转集中在 LEGAL 表里，非法流转 400。
4. 审批留痕：approve / reject 写原有 ApprovalLog；submit / withdraw 写进信封
   events（ApprovalAction 枚举只有 approve/reject，不动它）。
5. Agent 摘要 / 校验接受「整张单据」，不要求先落库，贴合表单页用法；
   LLM 不可用时按本地规则兜底，绝不阻断业务。
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agent_service import summarize_document, validate_document
from ..config import settings
from ..database import get_db
from ..dependencies import check_rate_limit, get_current_user, require_role
from ..models import ApprovalAction, ApprovalLog, Document, DocumentStatus, User
from ..schemas import ok

router = APIRouter(prefix="/claims", tags=["claims"])
agent_router = APIRouter(prefix="/agent/claims", tags=["agent-claims"])

ENVELOPE_VERSION = 1

# 前端状态 → 后端状态
_TO_DB_STATUS = {
    "draft": DocumentStatus.DRAFT,
    "submitted": DocumentStatus.PENDING,
    "approving": DocumentStatus.PENDING,
    "approved": DocumentStatus.APPROVED,
    "rejected": DocumentStatus.REJECTED,
}

# 报错文案用的中文状态名（给人看，不是给前端状态机用）
_FROM_DB_STATUS = {
    DocumentStatus.DRAFT: "草稿",
    DocumentStatus.PENDING: "审批中",
    DocumentStatus.APPROVED: "审批通过",
    DocumentStatus.REJECTED: "已驳回",
    DocumentStatus.CANCELLED: "已取消",
}

# 前端可发起的合法流转（防止前端乱传）
_LEGAL = {
    "draft": {"submitted"},
    "submitted": {"approved", "rejected", "draft"},      # draft = 撤销
    "approving": {"approved", "rejected", "draft"},
    "rejected": {"submitted"},
    "approved": set(),
}


# ============================================================ 编码 / 解码


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _now() -> datetime:
    return datetime.utcnow()


def _encode(env: dict[str, Any]) -> str:
    env["v"] = ENVELOPE_VERSION
    return json.dumps(env, ensure_ascii=False)


def _decode(doc: Document) -> dict[str, Any]:
    """把 Document.content 解成信封；兼容历史纯文本数据"""
    try:
        env = json.loads(doc.content)
        if isinstance(env, dict):
            env.setdefault("v", ENVELOPE_VERSION)
            env.setdefault("events", [])
            return env
    except (ValueError, TypeError):
        pass
    return {
        "v": 0,
        "code": f"MO-{doc.id:06d}",
        "remark": doc.content,
        "items": [],
        "events": [],
    }


def _read_status(doc: Document) -> str:
    """后端状态 → 前端状态（pending 再按是否指派审批人细分）"""
    if doc.status == DocumentStatus.PENDING:
        return "approving" if doc.current_approver_id else "submitted"
    return doc.status.value


def _to_claim(doc: Document, approver_name: Optional[str] = None) -> dict[str, Any]:
    env = _decode(doc)
    return {
        "id": str(doc.id),
        "code": env.get("code") or f"MO-{doc.id:06d}",
        "title": doc.title,
        "workshop": env.get("workshop", ""),
        "workshopCode": env.get("workshopCode", ""),
        "applicant": env.get("applicant") or "",
        "applicantTitle": env.get("applicantTitle", ""),
        "phone": env.get("phone", ""),
        "demandDate": env.get("demandDate", ""),
        "urgency": env.get("urgency", "normal"),
        "remark": env.get("remark", ""),
        "status": _read_status(doc),
        "items": env.get("items", []),
        "submittedAt": _iso(doc.submitted_at),
        "createdAt": _iso(doc.created_at),
        "updatedAt": _iso(doc.updated_at),
        "approver": approver_name,
    }


def render_readable(claim: dict[str, Any]) -> str:
    """把单据渲染成自然语言，喂给 LLM（不是直接塞 JSON）"""
    items = claim.get("items") or []
    lines = [
        f"单据标题：{claim.get('title', '')}",
        f"申领车间：{claim.get('workshop', '')}（{claim.get('workshopCode', '')}）",
        f"申领人：{claim.get('applicant', '')}（{claim.get('applicantTitle', '')}）",
        f"联系电话：{claim.get('phone', '')}",
        f"需求日期：{claim.get('demandDate', '')}",
        f"紧急程度：{'加急' if claim.get('urgency') == 'urgent' else '普通'}",
        "货品明细：",
    ]
    if not items:
        lines.append("  （无明细）")
    for i, it in enumerate(items, 1):
        lines.append(
            f"  {i}. {it.get('name', '')} / 规格 {it.get('spec', '')} / "
            f"数量 {it.get('quantity', '')}{it.get('unit', '')} / 用途 {it.get('purpose', '')}"
        )
    lines.append(f"备注说明：{claim.get('remark') or '（无）'}")
    return "\n".join(lines)


# ============================================================ 单号


async def _next_code(db: AsyncSession) -> str:
    today = _now()
    cnt = await db.scalar(
        select(func.count())
        .select_from(Document)
        .where(func.date(Document.created_at) == today.date())
    )
    return f"MO-{today.strftime('%Y%m%d')}-{(cnt or 0) + 1:03d}"


# ============================================================ 取单据（权限）


async def _load(db: AsyncSession, claim_id: str, user: User) -> Document:
    try:
        doc_id = int(claim_id)
    except (TypeError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"单据 id 非法：{claim_id}")

    doc = (
        await db.execute(select(Document).where(Document.id == doc_id))
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"单据不存在 id={doc_id}")

    allowed = (
        doc.submitter_id == user.id
        or user.role in {"approver", "admin"}
    )
    if not allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该单据")
    return doc


async def _approver_name(db: AsyncSession, doc: Document) -> Optional[str]:
    if not doc.current_approver_id:
        return None
    u = (
        await db.execute(select(User).where(User.id == doc.current_approver_id))
    ).scalar_one_or_none()
    return (u.display_name or u.username) if u else None


def _append_event(doc: Document, env: dict[str, Any], **ev: Any) -> None:
    env.setdefault("events", []).append({"at": _iso(_now()), **ev})
    doc.content = _encode(env)


# ============================================================ 创建 / 编辑


@router.post("", response_model=dict, status_code=201)
async def create_claim(
    req: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """新建草稿（body 直接是 Claim 结构）"""
    title = (req.get("title") or "").strip()
    if not title:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "单据标题不能为空")

    env = {
        "code": await _next_code(db),
        "workshop": req.get("workshop", ""),
        "workshopCode": req.get("workshopCode", ""),
        "applicant": req.get("applicant") or (user.display_name or user.username),
        "applicantTitle": req.get("applicantTitle", ""),
        "phone": req.get("phone", ""),
        "demandDate": req.get("demandDate", ""),
        "urgency": req.get("urgency", "normal"),
        "remark": req.get("remark", ""),
        "items": req.get("items", []),
        "events": [],
    }

    doc = Document(
        title=title,
        content=_encode(env),
        doc_type="claim",
        status=DocumentStatus.DRAFT,
        submitter_id=user.id,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return ok(_to_claim(doc))


@router.put("/{claim_id}", response_model=dict)
async def update_claim(
    claim_id: str,
    req: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """保存草稿 / 驳回后修改"""
    doc = await _load(db, claim_id, user)
    if doc.submitter_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权修改他人单据")
    if doc.status not in {DocumentStatus.DRAFT, DocumentStatus.REJECTED}:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"当前状态「{_read_status(doc)}」不允许编辑",
        )

    env = _decode(doc)
    for key in (
        "workshop", "workshopCode", "applicant", "applicantTitle", "phone",
        "demandDate", "urgency", "remark", "items",
    ):
        if key in req:
            env[key] = req[key]
    if req.get("title"):
        doc.title = req["title"]

    doc.content = _encode(env)
    doc.updated_at = _now()
    await db.commit()
    await db.refresh(doc)
    return ok(_to_claim(doc))


# ============================================================ 查询


def _apply_filters(rows: list[Document], q: dict) -> list[Document]:
    st = q.get("status")
    workshop = q.get("workshop")
    keyword = (q.get("keyword") or "").strip()
    start = q.get("startDate")
    end = q.get("endDate")

    out = []
    for doc in rows:
        env = _decode(doc)
        if st and st != "all" and _read_status(doc) != st:
            continue
        if workshop and workshop not in ("", "all", "全部车间") and env.get("workshop") != workshop:
            continue
        if keyword:
            haystack = f"{doc.title}{env.get('code', '')}{env.get('applicant', '')}"
            if keyword not in haystack:
                continue
        d = doc.created_at.strftime("%Y-%m-%d") if doc.created_at else ""
        if start and d and d < start:
            continue
        if end and d and d > end:
            continue
        out.append(doc)
    out.sort(key=lambda x: x.created_at or datetime.min, reverse=True)
    return out


def _paginate(rows: list[Document], page: int, page_size: int) -> dict:
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    total = len(rows)
    start = (page - 1) * page_size
    return {"list": rows[start : start + page_size], "total": total, "page": page, "pageSize": page_size}


@router.get("/mine", response_model=dict)
async def list_mine(
    status_: Optional[str] = Query(default=None, alias="status"),
    workshop: Optional[str] = None,
    keyword: Optional[str] = None,
    startDate: Optional[str] = None,
    endDate: Optional[str] = None,
    page: int = 1,
    pageSize: int = 10,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """我的提交单据列表（分页 + 状态 / 车间 / 关键字 / 日期筛选）"""
    rows = (
        await db.execute(
            select(Document).where(Document.submitter_id == user.id)
        )
    ).scalars().all()

    rows = _apply_filters(
        list(rows),
        {"status": status_, "workshop": workshop, "keyword": keyword,
         "startDate": startDate, "endDate": endDate},
    )
    page_data = _paginate(rows, page, pageSize)
    page_data["list"] = [_to_claim(d) for d in page_data["list"]]
    return ok(page_data)


@router.get("/pending", response_model=dict)
async def list_pending(
    status_: Optional[str] = Query(default=None, alias="status"),
    workshop: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    pageSize: int = 10,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """我的待审批列表；非审批人直接返回空页，避免前端 403"""
    if user.role not in {"approver", "admin"}:
        return ok({"list": [], "total": 0, "page": page, "pageSize": pageSize})

    stmt = select(Document).where(Document.status == DocumentStatus.PENDING)
    if user.role != "admin":
        stmt = stmt.where(
            (Document.current_approver_id == user.id)
            | (Document.current_approver_id.is_(None))
        )
    rows = list((await db.execute(stmt)).scalars().all())
    rows = _apply_filters(
        rows, {"status": status_, "workshop": workshop, "keyword": keyword}
    )

    page_data = _paginate(rows, page, pageSize)
    out = []
    for d in page_data["list"]:
        out.append(_to_claim(d, await _approver_name(db, d)))
    page_data["list"] = out
    return ok(page_data)


@router.get("/{claim_id}", response_model=dict)
async def get_claim(
    claim_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = await _load(db, claim_id, user)
    return ok(_to_claim(doc, await _approver_name(db, doc)))


@router.delete("/{claim_id}", response_model=dict)
async def delete_claim(
    claim_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """删除单据：仅草稿、仅本人（管理员不受限）。

    必须先清理 approval_logs —— 该表 document_id 外键没有级联，
    历史上正是这里导致「删除有审批流水的单据」返回 500。
    """
    doc = await _load(db, claim_id, user)

    if doc.submitter_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只有提交人本人可以删除草稿")
    if doc.status != DocumentStatus.DRAFT:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"当前状态（{_FROM_DB_STATUS.get(doc.status, doc.status.value)}）不允许删除，"
            "请先撤销提交退回草稿",
        )

    await db.execute(delete(ApprovalLog).where(ApprovalLog.document_id == doc.id))
    await db.delete(doc)
    await db.commit()
    return ok({"deleted": doc.id})


@router.get("/{claim_id}/history", response_model=dict)
async def claim_history(
    claim_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """审批历史：建单 → 提交 / 撤销（信封 events）→ 同意 / 驳回（ApprovalLog）"""
    doc = await _load(db, claim_id, user)
    env = _decode(doc)
    entries: list[dict] = []

    submitter = (
        await db.execute(select(User).where(User.id == doc.submitter_id))
    ).scalar_one_or_none()
    submitter_name = (submitter.display_name or submitter.username) if submitter else "提交人"

    entries.append({
        "id": f"c-{doc.id}-create",
        "action": "create",
        "operator": submitter_name,
        "operatorRole": "submitter",
        "comment": "创建单据草稿",
        "createdAt": _iso(doc.created_at),
    })

    for i, ev in enumerate(env.get("events") or []):
        entries.append({
            "id": f"c-{doc.id}-ev-{i}",
            "action": ev.get("action", "submit"),
            "operator": ev.get("operator") or submitter_name,
            "operatorRole": ev.get("operatorRole", "submitter"),
            "comment": ev.get("comment"),
            "createdAt": ev.get("at"),
            "fromStatus": ev.get("from"),
            "toStatus": ev.get("to"),
        })

    logs = (
        await db.execute(
            select(ApprovalLog)
            .where(ApprovalLog.document_id == doc.id)
            .order_by(ApprovalLog.created_at)
        )
    ).scalars().all()

    for log in logs:
        u = (
            await db.execute(select(User).where(User.id == log.approver_id))
        ).scalar_one_or_none()
        entries.append({
            "id": f"log-{log.id}",
            "action": log.action.value,
            "operator": (u.display_name or u.username) if u else f"用户#{log.approver_id}",
            "operatorRole": "approver",
            "comment": log.comment,
            "createdAt": _iso(log.created_at),
            "fromStatus": "submitted",
            "toStatus": "approved" if log.action == ApprovalAction.APPROVE else "rejected",
        })

    if doc.agent_validated:
        entries.append({
            "id": f"c-{doc.id}-ai",
            "action": "ai_validate",
            "operator": "AI 助手",
            "operatorRole": "system",
            "comment": doc.agent_check_result or "AI 已完成内容校验",
            "createdAt": _iso(doc.updated_at),
            "fromAgent": True,
        })

    entries.sort(key=lambda e: e.get("createdAt") or "")
    return ok(entries)


# ============================================================ 状态流转


async def _transition(
    db: AsyncSession, user: User, claim_id: str, target: str, *, comment: str = ""
) -> Document:
    doc = await _load(db, claim_id, user)
    current = _read_status(doc)

    if target not in _LEGAL.get(current, set()):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"非法状态流转：{current} → {target}",
        )

    env = _decode(doc)
    db_status = _TO_DB_STATUS[target]

    if target == "draft":  # 撤销提交
        doc.status = DocumentStatus.DRAFT
        doc.submitted_at = None
        doc.closed_at = _now()
        _append_event(
            doc, env, action="withdraw", operator=user.display_name or user.username,
            operatorRole="submitter", comment=comment or "提交人撤销提交",
            **{"from": current, "to": "draft"},
        )
    elif target == "submitted":
        doc.status = db_status
        doc.submitted_at = _now()
        doc.closed_at = None
        _append_event(
            doc, env, action="resubmit" if current == "rejected" else "submit",
            operator=user.display_name or user.username, operatorRole="submitter",
            comment=comment or None, **{"from": current, "to": "submitted"},
        )

    doc.updated_at = _now()
    await db.commit()
    await db.refresh(doc)
    return doc


@router.post("/{claim_id}/submit", response_model=dict)
async def submit_claim(
    claim_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """提交审批（草稿 / 已驳回可提交）"""
    doc = await _transition(db, user, claim_id, "submitted")
    return ok(_to_claim(doc, await _approver_name(db, doc)))


@router.post("/{claim_id}/withdraw", response_model=dict)
async def withdraw_claim(
    claim_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """撤销提交 → 退回草稿"""
    doc = await _transition(db, user, claim_id, "draft")
    return ok(_to_claim(doc))


@router.post("/{claim_id}/approve", response_model=dict)
async def approve_claim(
    claim_id: str,
    req: Optional[dict] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("approver", "admin")),
):
    doc = await _load(db, claim_id, user)
    current = _read_status(doc)
    if "approved" not in _LEGAL.get(current, set()):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"非法状态流转：{current} → approved"
        )

    comment = ((req or {}).get("comment") or "").strip()
    db.add(ApprovalLog(
        document_id=doc.id, approver_id=user.id,
        action=ApprovalAction.APPROVE, comment=comment or None,
    ))
    doc.status = DocumentStatus.APPROVED
    doc.closed_at = _now()
    doc.updated_at = _now()
    await db.commit()
    await db.refresh(doc)
    return ok(_to_claim(doc, user.display_name or user.username))


@router.post("/{claim_id}/reject", response_model=dict)
async def reject_claim(
    claim_id: str,
    req: Optional[dict] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("approver", "admin")),
):
    """驳回 —— 意见必填（前端已强校验，这里再兜一层）"""
    comment = ((req or {}).get("comment") or "").strip()
    if not comment:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "驳回必须填写驳回意见")

    doc = await _load(db, claim_id, user)
    current = _read_status(doc)
    if "rejected" not in _LEGAL.get(current, set()):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"非法状态流转：{current} → rejected"
        )

    db.add(ApprovalLog(
        document_id=doc.id, approver_id=user.id,
        action=ApprovalAction.REJECT, comment=comment,
    ))
    doc.status = DocumentStatus.REJECTED
    doc.closed_at = None
    doc.updated_at = _now()
    await db.commit()
    await db.refresh(doc)
    return ok(_to_claim(doc, user.display_name or user.username))


# ============================================================ Agent 能力
# 说明：接受整张单据，不要求先落库；LLM 失败一律降级，不阻断业务。


def _is_degraded(text: str) -> bool:
    return text.startswith("🤖 Agent 暂时不可用")


def _local_summary(claim: dict[str, Any]) -> tuple[str, list[str]]:
    items = claim.get("items") or []
    names = [i.get("name", "") for i in items if i.get("name")]
    total = sum(int(i.get("quantity") or 0) for i in items)
    urgency = "加急" if claim.get("urgency") == "urgent" else "普通"
    summary = (
        f"{claim.get('workshop') or '未指定车间'} {claim.get('demandDate') or '未填日期'} 申领："
        f"{len(items)} 项货品（{'、'.join(names[:3])}{'等' if len(names) > 3 else ''}），"
        f"合计 {total} 件，优先级{urgency}。"
    )
    highlights = [
        f"申领车间：{claim.get('workshop') or '未填写'}",
        f"明细 {len(items)} 行，合计 {total} 件",
        "标记为加急，需优先处理" if urgency == "加急" else "普通优先级，按常规排产",
    ]
    return summary, highlights


def _local_validate(claim: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    missing: list[str] = []
    issues: list[str] = []

    for field, label in (
        ("title", "单据标题"),
        ("workshop", "申领车间"),
        ("applicant", "申领人"),
        ("phone", "联系电话"),
        ("demandDate", "需求日期"),
    ):
        if not str(claim.get(field) or "").strip():
            missing.append(label)

    items = claim.get("items") or []
    if not items:
        missing.append("货品明细")
    for idx, it in enumerate(items, 1):
        if not str(it.get("name") or "").strip():
            issues.append(f"第 {idx} 行未填写货品名称")
        if not str(it.get("spec") or "").strip():
            issues.append(f"第 {idx} 行未填写规格")
        try:
            if int(it.get("quantity") or 0) <= 0:
                issues.append(f"第 {idx} 行申领数量必须大于 0")
        except (TypeError, ValueError):
            issues.append(f"第 {idx} 行申领数量不是合法数字")

    dd = str(claim.get("demandDate") or "")
    if dd:
        try:
            if date.fromisoformat(dd) < date.today():
                issues.append("需求日期早于今天，请确认是否仍然有效")
        except ValueError:
            issues.append("需求日期格式应为 YYYY-MM-DD")

    return (not missing and not issues), issues, missing


@agent_router.post("/summary", response_model=dict)
async def agent_claim_summary(
    req: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await check_rate_limit(f"claim_summary:{user.id}", max_requests=30, window_seconds=60)(request)

    fallback_text, highlights = _local_summary(req)
    degraded = False
    summary = fallback_text

    try:
        text = await summarize_document(
            render_readable(req), timeout_seconds=settings.AGENT_TIMEOUT_SECONDS
        )
        if _is_degraded(text):
            degraded = True
        else:
            summary = text
    except Exception:
        degraded = True

    # 已落库的单据顺手把摘要写回去
    claim_id = str(req.get("id") or "")
    if claim_id.isdigit():
        doc = (
            await db.execute(select(Document).where(Document.id == int(claim_id)))
        ).scalar_one_or_none()
        if doc is not None and doc.submitter_id == user.id:
            doc.summary = summary
            doc.updated_at = _now()
            try:
                await db.commit()
            except Exception:
                await db.rollback()

    return ok({"summary": summary, "highlights": highlights, "degraded": degraded})


@agent_router.post("/validate", response_model=dict)
async def agent_claim_validate(
    req: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await check_rate_limit(f"claim_validate:{user.id}", max_requests=30, window_seconds=60)(request)

    passed, issues, missing = _local_validate(req)
    degraded = False

    if passed:
        message = "字段完整：必填项齐全，明细数量与规格自洽，需求日期合法。"
    else:
        parts = []
        if missing:
            parts.append(f"缺失必填项：{'、'.join(missing)}")
        if issues:
            parts.append("；".join(issues))
        message = "；".join(parts)

    # LLM 只做补充说明，结论以本地规则为准（避免模型幻觉影响提交）
    try:
        text = await validate_document(
            render_readable(req), timeout_seconds=settings.AGENT_TIMEOUT_SECONDS
        )
        if _is_degraded(text):
            degraded = True
        else:
            message = f"{message}\n\nAI 复核：{text.strip()}"
    except Exception:
        degraded = True

    claim_id = str(req.get("id") or "")
    if claim_id.isdigit():
        doc = (
            await db.execute(select(Document).where(Document.id == int(claim_id)))
        ).scalar_one_or_none()
        if doc is not None:
            doc.agent_validated = True
            doc.agent_check_result = message[:2000]
            doc.updated_at = _now()
            try:
                await db.commit()
            except Exception:
                await db.rollback()

    return ok({
        "passed": passed,
        "message": message,
        "issues": issues,
        "missingFields": missing,
        "degraded": degraded,
    })
