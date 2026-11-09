"""
检索门控规则 —— 决定"哪些 chunk 有资格被 Agent 看到"。

三道闸门，缺一不可：
    1. 时效闸：status=active 且 effective_date <= today 且未过期
    2. 密级闸：confidentiality 与调用者角色的匹配
    3. 范围闸：文档归口部门 / 适用车间与当前单据是否相关（加分项，不硬拦）

用法：
    where = build_chroma_where(user=user, today=date.today())
    hits = collection.query(query_texts=[q], where=where, n_results=8)
    hits = post_filter(hits, user=user)   # 兜底二次校验，防止 where 语法遗漏
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Optional

from .schema import Confidentiality, DocStatus

# 角色 → 密级上限。角色名与后端 User.role 对齐（submitter/approver/admin）
ROLE_CLEARANCE: dict[str, int] = {
    "employee": 1,     # public + internal（员工只能查员工类制度）
    "submitter": 1,    # 同 employee
    "approver": 3,     # 按业务要求：审批人拥有全部制度的查看权限（含涉密）
    "admin": 3,        # + secret
}

_LEVEL = {
    Confidentiality.PUBLIC: 0,
    Confidentiality.INTERNAL: 1,
    Confidentiality.RESTRICTED: 2,
    Confidentiality.SECRET: 3,
}


@dataclass
class Viewer:
    """检索发起者"""

    user_id: int
    roles: list[str] = field(default_factory=list)
    department: Optional[str] = None
    workshops: list[str] = field(default_factory=list)

    @property
    def clearance(self) -> int:
        if not self.roles:
            return 1
        return max(ROLE_CLEARANCE.get(r, 1) for r in self.roles)


def can_read(meta: dict[str, Any], viewer: Viewer) -> bool:
    """单条 chunk 的读取判定（post_filter 用）"""
    conf = str(meta.get("confidentiality") or Confidentiality.INTERNAL.value)
    level = _LEVEL.get(Confidentiality(conf), 1)

    if level > viewer.clearance:
        return False

    acl = meta.get("acl_roles") or []
    if isinstance(acl, str):
        acl = [s.strip() for s in acl.split(",") if s.strip()]
    # 密级够高即通行；受限文档额外要求命中 acl_roles
    if level == _LEVEL[Confidentiality.RESTRICTED] and acl:
        if not set(acl) & set(viewer.roles):
            return False
    return True


def build_chroma_where(
    viewer: Viewer,
    today: Optional[date] = None,
    category: Optional[str] = None,
    workshops: Optional[Iterable[str]] = None,
) -> dict[str, Any]:
    """
    构造 ChromaDB 的 where 子句。

    注意：Chroma 的 where 不支持"日期字符串比较"，因此 effective_date /
    expire_date 以整数 YYYYMMDD 冗余存一份（见 loader 的 _int_date），
    这里用 $lte / $gte 做数值比较。
    """
    today = today or date.today()
    stamp = today.year * 10000 + today.month * 100 + today.day

    must: list[dict[str, Any]] = [
        {"status": {"$eq": DocStatus.ACTIVE.value}},
        {"effective_int": {"$lte": stamp}},
        {"conf_level": {"$lte": viewer.clearance}},
    ]
    if category:
        must.append({"category": {"$eq": category}})

    where: dict[str, Any] = {"$and": must}

    # 车间过滤：文档 related_workshops 为空表示全厂适用，因此不能用 where 硬过滤，
    # 交给 post_filter 做"全厂 ∪ 命中车间"的并集判断。
    if workshops:
        where = {
            "$and": [
                where,
                {
                    "$or": [
                        {"related_workshops": {"$eq": ""}},
                        {"related_workshops": {"$eq": ",".join(sorted(workshops))}},
                    ]
                },
            ]
        }
    return where


def build_pg_where(
    viewer: Viewer,
    today: Optional[date] = None,
    category: Optional[str] = None,
    workshops: Optional[Iterable[str]] = None,
) -> tuple[str, dict[str, Any]]:
    """
    构造 pgvector 版门控片段（knowledge_chunks.metadata 为 jsonb）。

    与 build_chroma_where 完全同口径：status / 时效 / 密级 /（可选）车间，
    过期与受限文档 ACL 仍交给 post_filter 兜底 —— 三个后端共用一份
    post_filter，保证"密级闸"只有一套实现，不会出现口径漂移。

    返回 (sql_fragment, params)：fragment 以 AND 开头，直接拼进 WHERE。
    """
    today = today or date.today()
    stamp = today.year * 10000 + today.month * 100 + today.day

    params: dict[str, Any] = {
        "status": DocStatus.ACTIVE.value,
        "stamp": stamp,
        "clearance": viewer.clearance,
    }
    parts = [
        "metadata->>'status' = %(status)s",
        "COALESCE((metadata->>'effective_int')::int, 0) <= %(stamp)s",
        "COALESCE((metadata->>'conf_level')::int, 1) <= %(clearance)s",
    ]
    if category:
        params["category"] = category
        parts.append("metadata->>'category' = %(category)s")

    # 车间过滤与 Chroma 版一致：related_workshops 为空表示全厂适用，不在此硬拦
    if workshops:
        params["ws_joined"] = ",".join(sorted(workshops))
        parts.append(
            "(metadata->>'related_workshops' = '' "
            "OR metadata->>'related_workshops' = %(ws_joined)s)"
        )

    return " AND ".join(parts), params


def _stamp(value: Any) -> Optional[int]:
    """把各种形态的日期统一成 YYYYMMDD 整数；无法识别返回 None"""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value or None
    if isinstance(value, date):
        return value.year * 10000 + value.month * 100 + value.day
    if isinstance(value, str):
        try:
            d = date.fromisoformat(value[:10])
        except ValueError:
            return None
        return d.year * 10000 + d.month * 100 + d.day
    return None


def post_filter(
    hits: list[dict[str, Any]],
    viewer: Viewer,
    today: Optional[date] = None,
    workshops: Optional[Iterable[str]] = None,
) -> list[dict[str, Any]]:
    """对检索结果做二次校验 + 时效兜底（防 where 语法表达能力不足）"""
    today = today or date.today()
    stamp = today.year * 10000 + today.month * 100 + today.day
    ws = set(workshops or [])
    out: list[dict[str, Any]] = []

    for hit in hits:
        meta = hit.get("metadata") or {}
        if str(meta.get("status")) != DocStatus.ACTIVE.value:
            continue

        # int 字段优先（Chroma 入库时冗余的那份），date 对象兜底（内存检索）
        eff = _stamp(meta.get("effective_int")) or _stamp(meta.get("effective_date"))
        if eff and eff > stamp:
            continue
        exp = _stamp(meta.get("expire_int")) or _stamp(meta.get("expire_date"))
        if exp and exp < stamp:
            continue

        if not can_read(meta, viewer):
            continue

        doc_ws = meta.get("related_workshops") or ""
        if ws and doc_ws:
            doc_set = {s.strip() for s in str(doc_ws).split(",") if s.strip()}
            if doc_set and not (doc_set & ws):
                continue

        out.append(hit)
    return out


def build_citation_block(hits: list[dict[str, Any]]) -> str:
    """把命中片段拼成注入 Prompt 的上下文块，带条款级引用标记"""
    lines: list[str] = []
    for i, hit in enumerate(hits, 1):
        meta = hit.get("metadata") or {}
        title = meta.get("title", "未命名")
        ver = meta.get("version", "")
        clause = meta.get("clause", "")
        text = (hit.get("document") or hit.get("page_content") or "").strip()
        lines.append(f"[{i}] 《{title}》{ver} {clause}\n{text}")
    return "\n\n".join(lines)
