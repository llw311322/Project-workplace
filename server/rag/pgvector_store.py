"""
向量存储 —— PostgreSQL + pgvector 实现。

与 vector_store.py（Chroma，未启用）职责相同、接口对齐：
    rebuild()   全量重建索引（TRUNCATE 后重灌，制度版本变更后必须重建）
    stats()     chunk 数 / 覆盖文档数
    search()    语义近邻检索（带 SQL 门控）

设计取舍：
    · 用 psycopg（同步）直连，不经 SQLAlchemy：RAG 存储是独立关注点，
      不占用业务库的 async 连接池；量级小（几百 chunk），同步开销可忽略
    · 门控条件全部下推到 SQL（见 filters.build_pg_where），
      与 Chroma / keyword 版共用同一份 post_filter 兜底
    · embedding 用通义 text-embedding-v3（1024 维），见 embedder.py

依赖：
    pip install "psycopg[binary]"      # 仅本地 pgvector 模式需要
    docker compose up -d postgres      # pgvector/pgvector:pg16 镜像
"""
from __future__ import annotations

import os
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Any, Optional

from .embedder import embed_query, embed_texts
from .filters import Viewer, build_pg_where, post_filter
from .loader import CORPUS_DIR, load_all, to_chroma_records

TABLE = os.getenv("RAG_PG_TABLE", "knowledge_chunks")
FETCH_FACTOR = 4  # 先取 top_k * FETCH_FACTOR，post_filter 后再截断


def _conn_kwargs() -> dict[str, Any]:
    """与 docker-compose.yml / .env 的 POSTGRES_* 对齐"""
    return {
        "host": os.getenv("POSTGRES_HOST", "127.0.0.1"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB", "agent_app"),
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
        "connect_timeout": 5,
    }


def _connect():
    try:
        import psycopg  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "未安装 psycopg。执行 `pip install \"psycopg[binary]\"` 后重试。"
        ) from exc
    return psycopg.connect(**_conn_kwargs())


def _vec_literal(vec: list[float]) -> str:
    """pgvector 的文本字面量：'[0.1,0.2,...]'，SQL 里 ::vector 显式转换"""
    return "[" + ",".join(f"{x:.7g}" for x in vec) + "]"


def rebuild(corpus_dir: Path = CORPUS_DIR, max_chars: int = 800) -> int:
    """全量重建：TRUNCATE + 重灌。制度 front-matter 变更后必须执行。"""
    records = to_chroma_records(load_all(corpus_dir), max_chars=max_chars)
    if not records:
        return 0

    # 分批向量化（embedder 内部再按 API 限制切批）
    vectors = embed_texts([r["text"] for r in records])
    if len(vectors) != len(records):
        raise RuntimeError(f"向量数 {len(vectors)} 与 chunk 数 {len(records)} 不一致")

    with closing(_connect()) as conn, conn.cursor() as cur:
        cur.execute(f"TRUNCATE {TABLE}")
        for r, vec in zip(records, vectors):
            cur.execute(
                f"INSERT INTO {TABLE} (content, embedding, metadata) "
                "VALUES (%s, %s::vector, %s::jsonb)",
                (r["text"], _vec_literal(vec), psycopg_json(r["metadata"])),
            )
        conn.commit()
    return len(records)


def psycopg_json(obj: Any) -> str:
    """metadata dict → jsonb 字面量（避免引入 psycopg.types.json 的注册步骤）"""
    import json

    return json.dumps(obj, ensure_ascii=False)


def search(
    query: str,
    viewer: Viewer,
    top_k: int = 6,
    today: Optional[date] = None,
    workshops: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """语义近邻检索：SQL 门控下推 + post_filter 兜底"""
    qvec = embed_query(query)
    where_sql, params = build_pg_where(viewer, today=today, workshops=workshops)
    params = {**params, "qvec": _vec_literal(qvec), "limit": max(top_k * FETCH_FACTOR, 10)}

    with closing(_connect()) as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT content, metadata, 1 - (embedding <=> %(qvec)s::vector) AS score "
            f"FROM {TABLE} WHERE {where_sql} "
            f"ORDER BY embedding <=> %(qvec)s::vector LIMIT %(limit)s",
            params,
        )
        rows = cur.fetchall()

    hits = [
        {"document": content, "metadata": dict(meta), "score": round(float(score), 4)}
        for content, meta, score in rows
    ]
    return post_filter(hits, viewer, today=today, workshops=workshops)[:top_k]


def stats() -> dict[str, Any]:
    try:
        with closing(_connect()) as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT count(*), count(DISTINCT metadata->>'doc_id') FROM {TABLE}"
            )
            chunks, docs = cur.fetchone()  # type: ignore[misc]
        return {"backend": "pgvector", "chunks": chunks, "docs": docs, "table": TABLE}
    except Exception as exc:  # noqa: BLE001
        return {"backend": "pgvector", "error": str(exc)}


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["rebuild"]:
        print(f"已写入 {rebuild()} 个 chunk → pgvector ({TABLE})")
    else:
        print(stats())
