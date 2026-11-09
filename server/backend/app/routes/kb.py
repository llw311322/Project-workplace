"""
制度知识库接口 —— 把 server/rag 的检索能力暴露给前端。

设计要点
--------
1. 只读接口，不改任何业务数据；检索结果按**当前登录人**做密级与车间门控。
2. rag 包导入失败（比如部署时漏拷目录）不影响主服务启动，接口返回 degraded，
   前端提示「知识库未加载」，而不是整个工作台起不来。
3. `/kb/search` 额外返回 `suppressed_docs`：本次因密级被拦下的制度份数。
   这个数字是给审批人看的——说明系统不是查不到，而是有意不给看。
"""
from __future__ import annotations

import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..dependencies import get_current_user
from ..models import User
from ..schemas import ok

router = APIRouter(prefix="/kb", tags=["knowledge-base"])

# 知识库不可用时的统一提示
_DEGRADED_HINT = "知识库未加载：请确认 server/rag/corpus 目录存在且依赖已安装"


# ============================================================ 内部工具


def _load_rag():
    """惰性导入 rag 包，失败返回 None（不让知识库拖垮主服务）"""
    try:
        from rag import RetrieverFactory, Viewer, can_read, inventory, load_all  # noqa: F401
        from rag.splitter import split_document

        return {
            "RetrieverFactory": RetrieverFactory,
            "Viewer": Viewer,
            "can_read": can_read,
            "inventory": inventory,
            "load_all": load_all,
            "split_document": split_document,
        }
    except Exception:  # pragma: no cover - 部署兜底
        return None


def _viewer_for(user: User):
    """把登录用户映射成检索身份"""
    rag = _load_rag()
    if rag is None:
        return None
    return rag["Viewer"](user_id=user.id, roles=[user.role])


def _chunk_count(body: str, title: str, version: str) -> int:
    rag = _load_rag()
    if rag is None:
        return 0
    return len(rag["split_document"](body, title=title, version=version))


# ============================================================ 请求模型


class SearchBody(BaseModel):
    query: str = Field(..., min_length=1, max_length=200, description="自然语言问题")
    top_k: int = Field(6, ge=1, le=20, description="返回条款数")


# 密级中文名，用于 403 提示（让人知道自己缺什么，而不是只看到「无权限」）
_CONF_LABEL = {
    "public": "公开",
    "internal": "内部",
    "restricted": "受限",
    "secret": "涉密",
}

_ROLE_LABEL = {
    "submitter": "员工",
    "approver": "审批人",
    "admin": "管理员",
}


# ============================================================ 接口


@router.get("/stats")
async def kb_stats(user: User = Depends(get_current_user)) -> dict[str, Any]:
    """知识库体检：覆盖率、条款块数、分类分布"""
    rag = _load_rag()
    if rag is None:
        return ok({"available": False, "message": _DEGRADED_HINT})

    inv = rag["inventory"]()
    docs = rag["load_all"]()

    # 分类分布：份数 + 条款块数
    by_cat: dict[str, dict[str, Any]] = {}
    chunks_total = 0
    for d in docs:
        n = _chunk_count(d.body, d.meta.title, d.meta.version)
        chunks_total += n
        bucket = by_cat.setdefault(
            d.meta.category or "未分类",
            {"category": d.meta.category or "未分类", "docs": 0, "chunks": 0},
        )
        bucket["docs"] += 1
        bucket["chunks"] += n

    # 当前身份可见份数（密级门控）
    viewer = _viewer_for(user)
    visible = 0
    if viewer is not None:
        for d in docs:
            meta = {
                "confidentiality": d.meta.confidentiality.value,
                "acl_roles": d.meta.acl_roles,
            }
            if rag["can_read"](meta, viewer):
                visible += 1

    return ok(
        {
            "available": True,
            "total_expected": inv.get("total_expected", len(docs)),
            "total_loaded": inv.get("total_loaded", len(docs)),
            "coverage": inv.get("coverage", 100.0),
            "chunks": inv.get("chunks", chunks_total),
            "missing": inv.get("missing", []),
            "stale": inv.get("stale", []),
            "categories": sorted(by_cat.values(), key=lambda x: x["category"]),
            "visible_docs": visible,
            "total_docs": len(docs),
            # 三道门控的说明，前端直接展示，避免"为什么查不到"变成黑箱
            "gates": [
                {"key": "时效", "desc": "只检索已生效且未废止的制度版本"},
                {"key": "密级", "desc": "按登录人角色过滤，配方类对提交人不可见"},
                {"key": "车间", "desc": "车间专属参数不跨车间检索"},
            ],
        }
    )


@router.get("/docs")
async def kb_docs(user: User = Depends(get_current_user)) -> dict[str, Any]:
    """制度清单：含不可见的条目（标 readable=false，前端显示为受限）"""
    rag = _load_rag()
    if rag is None:
        return ok({"available": False, "message": _DEGRADED_HINT, "list": [], "total": 0})

    viewer = _viewer_for(user)
    docs = rag["load_all"]()
    items: list[dict[str, Any]] = []

    for d in docs:
        m = d.meta
        readable = True
        if viewer is not None:
            readable = rag["can_read"](
                {"confidentiality": m.confidentiality.value, "acl_roles": m.acl_roles},
                viewer,
            )
        items.append(
            {
                "doc_id": m.doc_id,
                "title": m.title,
                "version": m.version,
                "category": m.category,
                "doc_type": m.doc_type.value,
                "department": m.department,
                "confidentiality": m.confidentiality.value,
                "effective_date": m.effective_date.isoformat() if m.effective_date else None,
                "expire_date": m.expire_date.isoformat() if m.expire_date else None,
                "status": m.status.value,
                "chunks": _chunk_count(d.body, m.title, m.version),
                "related_claims": m.related_claims,
                "readable": readable,
            }
        )

    items.sort(key=lambda x: (x["category"], x["doc_id"]))
    return ok(
        {
            "available": True,
            "list": items,
            "total": len(items),
            "visible": sum(1 for i in items if i["readable"]),
        }
    )


@router.get("/doc/{doc_id}")
async def kb_doc_detail(doc_id: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    """制度全文预览：按密级判定是否放行，无权限时 403 并说明原因"""
    rag = _load_rag()
    if rag is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _DEGRADED_HINT)

    viewer = _viewer_for(user)
    target = None
    for d in rag["load_all"]():
        if d.meta.doc_id == doc_id:
            target = d
            break

    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"未找到制度 {doc_id}")

    m = target.meta
    if viewer is not None and not rag["can_read"](
        {"confidentiality": m.confidentiality.value, "acl_roles": m.acl_roles}, viewer
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"《{m.title}》密级为「{_CONF_LABEL.get(m.confidentiality.value, m.confidentiality.value)}」，"
            f"当前身份（{_ROLE_LABEL.get(user.role, user.role)}）无权查看全文",
        )

    return ok(
        {
            "doc_id": m.doc_id,
            "title": m.title,
            "version": m.version,
            "category": m.category,
            "doc_type": m.doc_type.value,
            "department": m.department,
            "confidentiality": m.confidentiality.value,
            "effective_date": m.effective_date.isoformat() if m.effective_date else None,
            "expire_date": m.expire_date.isoformat() if m.expire_date else None,
            "status": m.status.value,
            "owner": m.owner,
            "related_claims": m.related_claims,
            "keywords": m.keywords,
            "body": target.body,
            "char_count": len(target.body),
        }
    )


@router.post("/search")
async def kb_search(body: SearchBody, user: User = Depends(get_current_user)) -> dict[str, Any]:
    """制度检索：返回命中条款 + 引用路径 + 被密级拦下的份数"""
    rag = _load_rag()
    if rag is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _DEGRADED_HINT)

    viewer = _viewer_for(user)
    factory = rag["RetrieverFactory"]
    retriever = factory.get()

    started = time.perf_counter()
    hits = retriever.retrieve(body.query, viewer, top_k=body.top_k)
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    results = []
    for h in hits:
        meta = h.get("metadata") or {}
        results.append(
            {
                "score": round(float(h.get("score", 0.0)), 1),
                "doc_id": meta.get("doc_id"),
                "title": meta.get("title"),
                "version": meta.get("version"),
                "category": meta.get("category"),
                "department": meta.get("department"),
                "confidentiality": meta.get("confidentiality"),
                "effective_date": meta.get("effective_date").isoformat()
                if hasattr(meta.get("effective_date"), "isoformat")
                else meta.get("effective_date"),
                "clause": meta.get("clause"),
                "section": meta.get("section"),
                "breadcrumb": meta.get("breadcrumb"),
                "text": (h.get("document") or "").strip(),
            }
        )

    # 对比管理员视角，算出「因密级被拦下」的份数——演示时最有说服力的一个数字
    suppressed_docs = 0
    try:
        wide = retriever.retrieve(body.query, rag["Viewer"](0, ["admin"]), top_k=max(body.top_k * 3, 12))
        shown_ids = {r["doc_id"] for r in results}
        blocked = {h["metadata"]["doc_id"] for h in wide if h["metadata"]["doc_id"] not in shown_ids}
        # 只统计确实因密级/ACL 被拦的，不是单纯没进 top_k
        suppressed_docs = sum(1 for doc_id in blocked if _is_blocked_by_clearance(rag, doc_id, viewer))
    except Exception:
        suppressed_docs = 0

    return ok(
        {
            "query": body.query,
            "hits": results,
            "total": len(results),
            "elapsed_ms": elapsed_ms,
            "suppressed_docs": suppressed_docs,
            "viewer_role": user.role,
        }
    )


def _is_blocked_by_clearance(rag: dict[str, Any], doc_id: Optional[str], viewer) -> bool:
    """确认某份制度是「密级不够」而不是「单纯没排进前列」"""
    if not doc_id or viewer is None:
        return False
    for d in rag["load_all"]():
        if d.meta.doc_id != doc_id:
            continue
        return not rag["can_read"](
            {"confidentiality": d.meta.confidentiality.value, "acl_roles": d.meta.acl_roles},
            viewer,
        )
    return False
