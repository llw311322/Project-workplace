"""
知识库门控自测 —— 验证"该拦的真的拦住了"。

制度库最大的风险不是检索不到，而是**检索到了不该看到的**：
废止条文、别人的车间参数、客户配方。这几条必须能自动验证，
否则每次改 filters.py 都得靠人肉回归。

跑法：
    cd server && ./.venv/Scripts/python.exe -m pytest tests/test_rag_gates.py -v
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from rag.filters import Viewer, can_read, post_filter
from rag.loader import load_all
from rag.retriever import KeywordRetriever
from rag.splitter import split_document

TODAY = date(2026, 11, 4)
PAST = TODAY - timedelta(days=30)
FUTURE = TODAY + timedelta(days=30)


def _doc(
    doc_id: str,
    *,
    title: str = "测试制度",
    status: str = "active",
    effective: date = PAST,
    expire: date | None = None,
    conf: str = "internal",
    acl: list[str] | None = None,
    workshops: list[str] | None = None,
    body: str = (
        "### 第 1.1 条 内容\n"
        "审批人应当在四小时内完成首审，全部环节累计不超过八小时。\n"
        "超时未处理的，系统自动提醒并升级至上级审批人，同时在列表中标红。\n"
    ),
) -> str:
    acl_s = ", ".join(acl or [])
    ws_s = ", ".join(workshops or [])
    return f"""---
doc_id: {doc_id}
title: {title}
version: v1.0
doc_type: regulation
category: 01_制度流程
effective_date: {effective.isoformat()}
expire_date: {expire.isoformat() if expire else ''}
status: {status}
department: 生产部
confidentiality: {conf}
acl_roles: [{acl_s}]
related_workshops: [{ws_s}]
---

# {title}

{body}
"""


@pytest.fixture()
def corpus(tmp_path: Path) -> Path:
    d = tmp_path / "01_制度流程"
    d.mkdir(parents=True)
    files = {
        "ok.md": _doc("MO-T-001", title="审批时限规定"),
        "future.md": _doc("MO-T-002", title="审批时限规定新版", effective=FUTURE),
        "old.md": _doc("MO-T-003", title="审批时限规定旧版", status="superseded"),
        "expired.md": _doc("MO-T-004", title="审批时限规定过期版", expire=PAST),
        "secret.md": _doc("MO-T-005", title="配方保密规定", conf="secret"),
        "restricted.md": _doc(
            "MO-T-006", title="限岗查看规定", conf="restricted", acl=["admin"]
        ),
        "fz.md": _doc("MO-T-007", title="冻干曲线规定", workshops=["FZ-02"]),
        "draft.md": _doc("MO-T-008", title="未生效草案", status="draft"),
    }
    for name, content in files.items():
        (d / name).write_text(content, encoding="utf-8")
    return tmp_path


def _retriever(corpus: Path) -> KeywordRetriever:
    return KeywordRetriever(docs=load_all(corpus))


def _ids(hits) -> set[str]:
    return {h["metadata"]["doc_id"] for h in hits}


def test_only_active_and_effective_docs_are_retrieved(corpus: Path):
    hits = _retriever(corpus).retrieve("审批时限", Viewer(1, ["approver"]), today=TODAY)
    ids = _ids(hits)
    assert "MO-T-001" in ids
    # 未生效、已废止、已过期、草案 全部不出现
    assert not ids & {"MO-T-002", "MO-T-003", "MO-T-004", "MO-T-008"}


def test_secret_hidden_from_submitter_visible_to_approver(corpus: Path):
    """涉密制度：员工/提交人不可见，审批人与管理员可见（审批人按业务要求全开）"""
    r = _retriever(corpus)
    q = "配方保密"
    as_submitter = _ids(r.retrieve(q, Viewer(1, ["submitter"]), today=TODAY))
    as_approver = _ids(r.retrieve(q, Viewer(2, ["approver"]), today=TODAY))
    as_admin = _ids(r.retrieve(q, Viewer(3, ["admin"]), today=TODAY))
    assert "MO-T-005" not in as_submitter
    assert "MO-T-005" in as_approver
    assert "MO-T-005" in as_admin


def test_restricted_needs_matching_acl_role(corpus: Path):
    r = _retriever(corpus)
    q = "限岗查看"
    as_approver = _ids(r.retrieve(q, Viewer(1, ["approver"]), today=TODAY))
    as_admin = _ids(r.retrieve(q, Viewer(2, ["admin"]), today=TODAY))
    assert "MO-T-006" not in as_approver
    assert "MO-T-006" in as_admin


def test_workshop_scoped_doc_filtered_out(corpus: Path):
    r = _retriever(corpus)
    q = "冻干曲线"
    in_fz = _ids(r.retrieve(q, Viewer(1, ["approver"]), today=TODAY, workshops=["FZ-02"]))
    in_ex = _ids(r.retrieve(q, Viewer(1, ["approver"]), today=TODAY, workshops=["EX-01"]))
    assert "MO-T-007" in in_fz
    assert "MO-T-007" not in in_ex


def test_can_read_matrix():
    internal = {"confidentiality": "internal", "acl_roles": []}
    secret = {"confidentiality": "secret", "acl_roles": ["admin"]}
    restricted = {"confidentiality": "restricted", "acl_roles": ["admin", "approver"]}

    assert can_read(internal, Viewer(1, ["submitter"]))
    # 审批人 clearance=3，可读涉密（演示要求：李四拥有全部制度查看权）
    assert can_read(secret, Viewer(1, ["approver"]))
    assert can_read(secret, Viewer(1, ["admin"]))
    assert can_read(restricted, Viewer(1, ["approver"]))
    assert not can_read(restricted, Viewer(1, ["submitter"]))


def test_post_filter_drops_future_effective():
    hit = {
        "document": "x",
        "metadata": {"status": "active", "effective_int": 20991231, "conf_level": 1},
    }
    assert post_filter([hit], Viewer(1, ["admin"]), today=TODAY) == []


def test_splitter_keeps_clause_and_chapter():
    text = """
## 第四章 审批流程

### 第 4.2 条 审批结论
审批人可作出同意或驳回两种结论。作出驳回时必须填写驳回意见，说明原因及修改要求。

### 第 4.3 条 驳回后处理
被驳回的单据退回提交人，状态变为已驳回。提交人修改后可直接重新提交。
""".strip()
    chunks = split_document(text, title="单据提交流程规定", version="v1.0")
    clauses = [c.clause for c in chunks]
    assert "第 4.2 条 审批结论" in clauses[0]
    assert all("第四章 审批流程" in c.section for c in chunks)
    assert "《单据提交流程规定》v1.0" in chunks[0].breadcrumb


def test_splitter_keeps_table_intact():
    text = """
### 第 2.1 条 权限矩阵
| 金额 | 审批人 |
|---|---|
| ≤2000 | 车间主管 |
| 2000-10000 | 生产经理 |
""".strip()
    chunks = split_document(text, min_chars=1)
    body = "\n".join(c.text for c in chunks)
    assert "| 2000-10000 | 生产经理 |" in body


def test_front_matter_required(corpus: Path, tmp_path: Path):
    bad = tmp_path / "01_制度流程" / "bad.md"
    bad.write_text("# 没有 front-matter 的文档\n正文", encoding="utf-8")
    docs = load_all(corpus)          # strict=False：跳过坏文件，其他照常
    assert all(d.meta.doc_id != "MO-T-999" for d in docs)
    with pytest.raises(ValueError):
        load_all(corpus, strict=True)  # strict=True：直接报错，供入库前校验
