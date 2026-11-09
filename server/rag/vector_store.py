"""
向量存储 —— Chroma 实现（当前未启用，接口先定好）。

为什么现在不装 Chroma：
    制度文件规模在几十份量级，关键词检索足够；且 Chroma 的 embedding 模型
    需要额外下载权重。等 corpus 内容补齐、真正需要语义泛化时再切，
    retriever.RetrieverFactory.get("vector") 一行即可。

启用步骤（已写进 rag/README.md）：
    1. pip install chromadb
    2. python -m rag.vector_store rebuild
    3. RetrieverFactory.get("vector")

迁移到 pgvector 时只需换这个文件，retriever 不动。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from .loader import CORPUS_DIR, load_all, to_chroma_records

PERSIST_DIR = Path(os.getenv("RAG_CHROMA_DIR", Path(__file__).resolve().parent / "chroma_db"))
COLLECTION = os.getenv("RAG_COLLECTION", "moins_regulations")

_client: Any = None
_collection: Any = None


def get_client():
    global _client
    if _client is None:
        try:
            import chromadb  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "未安装 chromadb。执行 `pip install chromadb -i https://pypi.org/simple` 后重试。"
            ) from exc
        PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(PERSIST_DIR))
    return _client


def get_collection():
    global _collection
    if _collection is None:
        _collection = get_client().get_or_create_collection(
            name=COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def rebuild(corpus_dir: Path = CORPUS_DIR, max_chars: int = 800) -> int:
    """全量重建索引（元数据或文档变更后必须重建，避免新旧版本混存）"""
    client = get_client()
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass  # 集合不存在
    global _collection
    _collection = None
    col = get_collection()

    records = to_chroma_records(load_all(corpus_dir), max_chars=max_chars)
    if not records:
        return 0

    batch = 500
    for i in range(0, len(records), batch):
        part = records[i : i + batch]
        col.add(
            ids=[r["id"] for r in part],
            documents=[r["text"] for r in part],
            metadatas=[r["metadata"] for r in part],
        )
    return len(records)


def stats() -> dict[str, Any]:
    try:
        col = get_collection()
        return {"collection": COLLECTION, "count": col.count(), "dir": str(PERSIST_DIR)}
    except Exception as exc:  # noqa: BLE001
        return {"collection": COLLECTION, "error": str(exc)}


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["rebuild"]:
        print(f"已写入 {rebuild()} 个 chunk → {PERSIST_DIR}")
    else:
        print(stats())
