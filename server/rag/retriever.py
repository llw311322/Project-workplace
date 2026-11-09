"""
检索器 —— 统一入口，多种后端：

    KeywordRetriever  零依赖，中文 2-gram + IDF 打分，**现在就能用**。
                      制度文件总共就几十份，关键词检索的召回已经够审批场景用，
                      而且结果完全可解释（能说清"命中哪几个词"），适合做验收。
    VectorRetriever   Chroma 语义检索，依赖 chromadb，接口已对齐，尚未启用。
    PgVectorRetriever PostgreSQL + pgvector 语义检索（通义 embedding），
                      需本地起 postgres 容器并重建索引。
    HybridRetriever   关键词 + 向量双路召回，RRF（倒数排名融合）合并，
                      兼顾"术语精确命中"与"口语化语义泛化"。

切换后端只改环境变量 RAG_BACKEND（keyword / vector / pgvector / hybrid），
上层（Agent / FastAPI）不用动。
门控（时效 + 密级 + 车间）在所有后端里共用同一份 post_filter 兜底，口径一致。
"""
from __future__ import annotations

import logging
import math
import os
import re
from collections import Counter
from datetime import date
from typing import Any, Optional

from .filters import Viewer, build_citation_block, post_filter
from .loader import CORPUS_DIR, LoadedDoc, _int_date, load_all
from .splitter import split_document

logger = logging.getLogger(__name__)

_TOKEN = re.compile(r"[a-zA-Z]+|\d+|[\u4e00-\u9fa5]")
_STOP = set("的了是在和与及或对为不有等该其此这那个一我你他")

# 领域同义词归一：把口语词映射到制度用词，纯关键词检索的必需品
_SYNONYM = {
    "加急": "紧急 加急 优先",
    "急单": "紧急 加急",
    "退料": "退料 退回 退库",
    "领料": "领料 申领 领用",
    "撤销": "撤销 撤回",
    "驳回": "驳回 拒绝 不通过",
    "审批": "审批 审核 批准",
    "多久": "时限 工作日 小时",
    "谁批": "审批权限 审批人 终审",
    "清线": "清线 换型 清洗",
    "过敏原": "过敏原 致敏",
    "冻干": "冻干 真空冷冻干燥",
    "冷萃": "冷萃 冷萃液",
    "闪萃": "闪萃 浓缩液",
}


def _gram(text: str) -> list[str]:
    """中文按 2-gram 切，英文数字按词切 —— 零依赖的中文检索基线"""
    tokens: list[str] = []
    for seg in _TOKEN.findall(text or ""):
        if seg.isascii():
            tokens.append(seg.lower())
        else:
            tokens.extend(seg)
    chars = "".join(t for t in tokens if not t.isascii())
    grams = [chars[i : i + 2] for i in range(max(0, len(chars) - 1))]
    words = [t for t in tokens if t.isascii()]
    return [g for g in grams if g[0] not in _STOP] + words


def _expand(query: str) -> str:
    out = [query]
    for k, v in _SYNONYM.items():
        if k in query:
            out.append(v)
    return " ".join(out)


class BaseRetriever:
    def __init__(self, docs: Optional[list[LoadedDoc]] = None, max_chars: int = 800):
        self.docs = docs if docs is not None else load_all()
        self.max_chars = max_chars
        self._records = self._build()

    def _build(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def retrieve(
        self,
        query: str,
        viewer: Viewer,
        top_k: int = 6,
        today: Optional[date] = None,
        workshops: Optional[list[str]] = None,
        doc_ids: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    def as_context(
        self, query: str, viewer: Viewer, top_k: int = 6, **kw: Any
    ) -> tuple[str, list[dict[str, Any]]]:
        """返回 (注入 Prompt 的上下文块, 命中列表)"""
        hits = self.retrieve(query, viewer, top_k=top_k, **kw)
        return build_citation_block(hits), hits


class KeywordRetriever(BaseRetriever):
    """中文 2-gram + IDF 打分。适合几十~几百份文档的规模。"""

    def _build(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for d in self.docs:
            m = d.meta
            base = {
                "doc_id": m.doc_id,
                "title": m.title,
                "version": m.version,
                "category": m.category,
                "status": m.status.value,
                "confidentiality": m.confidentiality.value,
                "acl_roles": m.acl_roles,
                "department": m.department,
                "related_workshops": ",".join(m.related_workshops),
                "related_claims": ",".join(m.related_claims),
                "effective_int": _int_date(m.effective_date),
                "expire_int": _int_date(m.expire_date),
                "effective_date": m.effective_date,
                "expire_date": m.expire_date,
            }
            for ch in split_document(
                d.body, max_chars=self.max_chars, title=m.title, version=m.version
            ):
                records.append(
                    {
                        "document": ch.text,
                        "metadata": {
                            **base,
                            "clause": ch.clause,
                            "section": ch.section,
                            "breadcrumb": ch.breadcrumb,
                        },
                        "_grams": Counter(_gram(ch.text + ch.breadcrumb)),
                    }
                )

        # 文档频率 → IDF
        n = len(records) or 1
        df: Counter = Counter()
        for r in records:
            df.update(set(r["_grams"]))
        self._idf = {g: math.log((n + 1) / (c + 0.5)) for g, c in df.items()}
        return records

    def retrieve(
        self,
        query: str,
        viewer: Viewer,
        top_k: int = 6,
        today: Optional[date] = None,
        workshops: Optional[list[str]] = None,
        doc_ids: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        q = Counter(_gram(_expand(query)))
        if not q:
            return []

        scored: list[dict[str, Any]] = []
        for r in self._records:
            if doc_ids and r["metadata"]["doc_id"] not in doc_ids:
                continue
            hit = 0.0
            for g, qc in q.items():
                tf = r["_grams"].get(g, 0)
                if tf:
                    hit += qc * (1 + math.log(tf)) * self._idf.get(g, 1.0)
            if hit <= 0:
                continue
            # 标题命中加权：制度名本身就是最强的意图信号
            if any(g in r["metadata"]["title"] for g in q):
                hit *= 1.35
            scored.append({**r, "score": round(hit, 4)})

        scored.sort(key=lambda x: x["score"], reverse=True)
        # 同 doc 内最多取 3 块，避免一份文档刷屏挤掉其他规定
        picked: list[dict[str, Any]] = []
        per_doc: Counter = Counter()
        for h in scored:
            did = h["metadata"]["doc_id"]
            if per_doc[did] >= 3:
                continue
            per_doc[did] += 1
            picked.append(h)
            if len(picked) >= top_k * 3:
                break

        return post_filter(picked, viewer, today=today, workshops=workshops)[:top_k]


class VectorRetriever(BaseRetriever):
    """Chroma 语义检索。接口已对齐，启用前需 pip install chromadb + 建集合。"""

    def __init__(self, collection: Any = None, **kw: Any):
        self._collection = collection
        super().__init__(**kw)

    def _build(self) -> list[dict[str, Any]]:
        # Chroma 自带切分入库，这里不预切
        return []

    def retrieve(self, query: str, viewer: Viewer, top_k: int = 6, **kw: Any):
        from .filters import build_chroma_where

        if self._collection is None:
            raise RuntimeError(
                "VectorRetriever 未绑定 collection。请先执行 rag/vector_store.py 里的 index_all()。"
            )
        where = build_chroma_where(
            viewer, today=kw.get("today"), workshops=kw.get("workshops")
        )
        raw = self._collection.query(
            query_texts=[query], n_results=max(top_k * 2, 10), where=where
        )
        hits = []
        for text, meta, dist in zip(
            raw["documents"][0], raw["metadatas"][0], raw["distances"][0]
        ):
            hits.append({"document": text, "metadata": meta, "score": 1 - dist})
        return post_filter(hits, viewer, today=kw.get("today"), workshops=kw.get("workshops"))[
            :top_k
        ]


# ---------------------------------------------------------------- 工厂

RRF_K = 60  # 经典取值：抑制头部排名的独占效应，让两路结果都有发言权


class PgVectorRetriever(BaseRetriever):
    """PostgreSQL + pgvector 语义检索。需先 `python -m rag.pgvector_store rebuild`。"""

    def _build(self) -> list[dict[str, Any]]:
        # chunk 存在 pgvector 表里，内存不预载
        return []

    def retrieve(self, query: str, viewer: Viewer, top_k: int = 6, **kw: Any):
        from .pgvector_store import search

        return search(
            query,
            viewer,
            top_k=top_k,
            today=kw.get("today"),
            workshops=kw.get("workshops"),
        )


class HybridRetriever(BaseRetriever):
    """关键词 + 向量双路召回，RRF 融合。

    为什么两路都要：
        · 关键词路对制度术语精确命中（"氮气铝罐""过敏原"这类专有词，向量容易泛化过头）
        · 向量路接住口语化提问（"急单怎么办" vs 制度里的"紧急申领"）
    """

    def __init__(self, keyword: KeywordRetriever, vector: BaseRetriever, **kw: Any):
        self._keyword = keyword
        self._vector = vector
        super().__init__(**kw)

    def _build(self) -> list[dict[str, Any]]:
        return []

    def retrieve(self, query: str, viewer: Viewer, top_k: int = 6, **kw: Any):
        recall_k = max(top_k * 2, 8)
        kw_hits = self._keyword.retrieve(query, viewer, top_k=recall_k, **kw)
        vec_hits = self._vector.retrieve(query, viewer, top_k=recall_k, **kw)

        # RRF：score = Σ 1/(k + rank)，rank 从 1 计
        fused: dict[tuple, dict[str, Any]] = {}
        for source, hits in (("kw", kw_hits), ("vec", vec_hits)):
            for rank, hit in enumerate(hits, 1):
                meta = hit.get("metadata") or {}
                key = (meta.get("doc_id"), meta.get("clause"), meta.get("breadcrumb"))
                rrf_score = 1.0 / (RRF_K + rank)
                if key in fused:
                    fused[key]["score"] += rrf_score
                    fused[key]["sources"].add(source)
                else:
                    fused[key] = {
                        **hit,
                        "score": rrf_score,
                        "sources": {source},
                    }

        merged = sorted(fused.values(), key=lambda h: h["score"], reverse=True)
        # 双路都命中的说明是强相关，加分凸显
        for h in merged:
            if len(h["sources"]) == 2:
                h["score"] = round(h["score"] * 1.5, 4)
        merged.sort(key=lambda h: h["score"], reverse=True)

        # 归一化到 0~1：以"双路都排第 1"为满分（2/(K+1)*1.5），
        # 单路第 1 名 ≈ 0.33，双路命中会明显高于单路，用户看到的相关度才有区分度
        perfect = 2.0 / (RRF_K + 1) * 1.5
        for h in merged:
            h["score"] = round(min(h["score"] / perfect, 1.0), 3)

        return post_filter(merged, viewer, today=kw.get("today"), workshops=kw.get("workshops"))[
            :top_k
        ]


class RetrieverFactory:
    """
    backend="keyword"  零依赖，默认
    backend="vector"   需 chromadb
    backend="pgvector" 需本地 postgres 容器 + `python -m rag.pgvector_store rebuild`
    backend="hybrid"   keyword + pgvector 双路 RRF

    默认后端由环境变量 RAG_BACKEND 决定（见 .env），切形态不改代码。
    """

    _cache: dict[str, BaseRetriever] = {}

    @classmethod
    def get(cls, backend: Optional[str] = None, corpus_dir=CORPUS_DIR) -> BaseRetriever:
        backend = backend or os.getenv("RAG_BACKEND", "keyword")
        if backend in cls._cache:
            return cls._cache[backend]
        docs = load_all(corpus_dir)
        try:
            if backend == "vector":
                from .vector_store import get_collection

                r: BaseRetriever = VectorRetriever(collection=get_collection(), docs=docs)
            elif backend == "pgvector":
                r = PgVectorRetriever(docs=docs)
            elif backend == "hybrid":
                r = HybridRetriever(keyword=KeywordRetriever(docs=docs), vector=PgVectorRetriever(docs=docs))
            else:
                r = KeywordRetriever(docs=docs)
        except Exception as exc:  # noqa: BLE001
            # 配了语义/混合检索但运行环境不具备（缺 psycopg、容器没起、旧库维度不符），
            # 退回关键词检索而不是让整个知识库接口 500 —— 降级要可见，所以打日志。
            logger.warning(
                f"⚠️ 检索后端 '{backend}' 初始化失败，已降级为 keyword：{type(exc).__name__}: {exc}"
            )
            r = KeywordRetriever(docs=docs)
            backend = "keyword"
        cls._cache[backend] = r
        return r

    @classmethod
    def reload(cls) -> None:
        cls._cache.clear()


if __name__ == "__main__":
    # 手工验证：python -m rag.retriever "加急单谁能批"
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "加急单谁能批"
    viewer = Viewer(user_id=1, roles=["approver"], department="生产部")
    ctx, hits = RetrieverFactory.get().as_context(q, viewer, top_k=5)
    print(f"查询：{q}\n命中 {len(hits)} 条\n" + "=" * 60)
    for h in hits:
        print(f"[{h['score']}] {h['metadata']['breadcrumb']}")
        print(h["document"][:120].replace("\n", " ") + "\n")
