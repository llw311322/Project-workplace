"""
制度知识库（RAG）。

当前可用：关键词检索 + 三道门控（时效 / 密级 / 车间）。
向量检索：接口已对齐，装 chromadb 后 `python -m rag.vector_store rebuild` 启用。

典型用法（在 Agent 侧）：
    from rag import Viewer, RetrieverFactory

    viewer = Viewer(user_id=user.id, roles=[user.role], department=user.department)
    retriever = RetrieverFactory.get("keyword")
    context, hits = retriever.as_context(
        "加急单谁能批", viewer, top_k=5, workshops=["EX-01"]
    )
    # context 直接拼进 Prompt；hits 里的 metadata["breadcrumb"] 用于前端展示引用出处

说明：本包采用惰性导入。子模块只在实际用到时才加载，
这样 `python -m rag.loader` / `python -m rag.retriever` 不会触发
"found in sys.modules after import of package" 警告。
"""
from __future__ import annotations

from typing import Any

__all__ = [
    "Viewer",
    "can_read",
    "post_filter",
    "build_citation_block",
    "load_all",
    "inventory",
    "LoadedDoc",
    "split_document",
    "Chunk",
    "KeywordRetriever",
    "VectorRetriever",
    "RetrieverFactory",
    "DocMeta",
    "DocStatus",
    "DocType",
    "Confidentiality",
]

# 导出名 -> (子模块, 模块内属性名)
_EXPORTS: dict[str, tuple[str, str]] = {
    "Viewer": (".filters", "Viewer"),
    "can_read": (".filters", "can_read"),
    "post_filter": (".filters", "post_filter"),
    "build_citation_block": (".filters", "build_citation_block"),
    "load_all": (".loader", "load_all"),
    "inventory": (".loader", "inventory"),
    "LoadedDoc": (".loader", "LoadedDoc"),
    "split_document": (".splitter", "split_document"),
    "Chunk": (".splitter", "Chunk"),
    "KeywordRetriever": (".retriever", "KeywordRetriever"),
    "VectorRetriever": (".retriever", "VectorRetriever"),
    "RetrieverFactory": (".retriever", "RetrieverFactory"),
    "DocMeta": (".schema", "DocMeta"),
    "DocStatus": (".schema", "DocStatus"),
    "DocType": (".schema", "DocType"),
    "Confidentiality": (".schema", "Confidentiality"),
}


def __getattr__(name: str) -> Any:
    """按需导入，避免包初始化时把所有子模块拉进来。"""
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    import importlib

    module_path, attr = _EXPORTS[name]
    module = importlib.import_module(module_path, __name__)
    value = getattr(module, attr)
    globals()[name] = value  # 缓存，后续访问不再走 __getattr__
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
