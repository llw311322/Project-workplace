"""pgvector 迁移的纯逻辑回归测试 —— 不依赖 Postgres / Docker。

覆盖：
    · build_pg_where 的 SQL 门控片段与参数（与 Chroma 版口径一致）
    · embedder 分批调用与缺 key 报错
    · HybridRetriever 的 RRF 融合与双路命中加权
    · 工厂按 RAG_BACKEND 环境变量切换后端
    · 向量字面量格式
真库检索（knn / 索引）由本地起容器后手工验证：python -m rag.pgvector_store stats
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

SERVER_ROOT = Path(__file__).resolve().parents[2] / "server"
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from rag import embedder, pgvector_store  # noqa: E402
from rag.embedder import EmbedderError  # noqa: E402
from rag.filters import Viewer, build_pg_where  # noqa: E402
from rag.retriever import HybridRetriever, PgVectorRetriever, RetrieverFactory  # noqa: E402

TODAY = date(2026, 11, 6)


def _viewer(*roles: str) -> Viewer:
    return Viewer(user_id=1, roles=list(roles), department="生产部")


# ---------------------------------------------------------------- 门控 SQL


def test_pg_where_basic_gates():
    sql, params = build_pg_where(_viewer("submitter"), today=TODAY)
    # 三道闸都在：状态 / 时效 / 密级
    assert "metadata->>'status' = %(status)s" in sql
    assert "COALESCE((metadata->>'effective_int')::int, 0) <= %(stamp)s" in sql
    assert "COALESCE((metadata->>'conf_level')::int, 1) <= %(clearance)s" in sql
    assert params["status"] == "active"
    assert params["stamp"] == 20261106
    assert params["clearance"] == 1  # submitter → 1


def test_pg_where_clearance_follows_role():
    _, params = build_pg_where(_viewer("approver"), today=TODAY)
    assert params["clearance"] == 3  # 审批人全量可见


def test_pg_where_workshops_optional():
    sql, params = build_pg_where(
        _viewer("submitter"), today=TODAY, workshops=["萃取车间", "包装车间"]
    )
    assert "related_workshops" in sql
    assert params["ws_joined"] == "包装车间,萃取车间"  # 排序后拼接，保证确定性

    sql_none, _ = build_pg_where(_viewer("submitter"), today=TODAY)
    assert "related_workshops" not in sql_none  # 不传车间不下推（全厂 ∪ 由 post_filter 兜底）


# ---------------------------------------------------------------- 向量化


def test_embedder_batches_by_api_limit(monkeypatch):
    calls: list[int] = []

    def fake_batch(client, texts):
        calls.append(len(texts))
        return [[0.0] * 4 for _ in texts]

    monkeypatch.setattr(embedder, "API_KEY", "test-key")
    monkeypatch.setattr(embedder, "_request_batch", fake_batch)
    out = embedder.embed_texts([f"t{i}" for i in range(25)])
    assert len(out) == 25
    assert calls == [10, 10, 5]  # DashScope 兼容模式单次上限 10 条


def test_embedder_requires_api_key(monkeypatch):
    monkeypatch.setattr(embedder, "API_KEY", "")
    with pytest.raises(EmbedderError):
        embedder.embed_texts(["任意文本"])


# ---------------------------------------------------------------- 混合检索（RRF）


def _hit(doc_id: str, clause: str, breadcrumb: str) -> dict:
    return {
        "document": f"{doc_id} 的条款正文",
        "metadata": {
            "doc_id": doc_id,
            "title": f"制度{doc_id}",
            "version": "v1.0",
            "clause": clause,
            "breadcrumb": breadcrumb,
            "status": "active",
            "effective_int": 20260101,
            "confidentiality": "internal",
            "conf_level": 1,
            "acl_roles": "",
            "related_workshops": "",
        },
        "score": 999.0,  # 占位：RRF 后应被覆盖
    }


class _FakeRetriever:
    def __init__(self, hits):
        self._hits = hits

    def retrieve(self, query, viewer, top_k=6, **kw):
        return self._hits[:top_k]


def test_hybrid_rrf_fusion_and_bonus():
    shared = _hit("KB-001", "3.2", "领用管理 > 3.2 时限")
    kw_only = _hit("KB-002", "1.1", "总则 > 1.1")
    vec_only = _hit("KB-003", "2.1", "流程 > 2.1")

    hybrid = HybridRetriever(
        keyword=_FakeRetriever([shared, kw_only]),
        vector=_FakeRetriever([shared, vec_only]),
        docs=[],
    )
    hits = hybrid.retrieve("急单时限", _viewer("submitter"), top_k=3)

    assert [h["metadata"]["doc_id"] for h in hits] == ["KB-001", "KB-002", "KB-003"]
    # 分数归一化到 0~1：双路满命中的第一名 = 1.0
    assert hits[0]["score"] == 1.0
    # 双路都命中 KB-001：RRF 得分叠加后 ×1.5，必须显著高于单路命中的（单路第 2 名 ≈ 0.33）
    assert hits[0]["score"] > hits[1]["score"] * 2
    assert all(0 < h["score"] <= 1.0 for h in hits)


def test_hybrid_dedupes_same_chunk():
    same = _hit("KB-001", "3.2", "领用管理 > 3.2 时限")
    hybrid = HybridRetriever(
        keyword=_FakeRetriever([same]), vector=_FakeRetriever([dict(same)]), docs=[]
    )
    hits = hybrid.retrieve("时限", _viewer("submitter"), top_k=6)
    assert len(hits) == 1  # 同一 chunk 不会被两条路重复输出


# ---------------------------------------------------------------- 工厂与工具


def test_factory_switches_by_env(monkeypatch):
    monkeypatch.setenv("RAG_BACKEND", "pgvector")
    RetrieverFactory._cache.clear()
    r = RetrieverFactory.get()  # 不连库，仅在 retrieve 时才需要 Postgres
    assert isinstance(r, PgVectorRetriever)

    monkeypatch.setenv("RAG_BACKEND", "keyword")
    RetrieverFactory._cache.clear()
    assert type(RetrieverFactory.get()).__name__ == "KeywordRetriever"


def test_vec_literal_format():
    lit = pgvector_store._vec_literal([0.123456789, 1.0, -0.5])
    assert lit == "[0.1234568,1,-0.5]"
    assert lit.startswith("[") and lit.endswith("]")
