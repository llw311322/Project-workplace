"""
知识库加载器 —— 扫描 rag/corpus/，解析 front-matter，输出带元数据的文档。

只做"读 + 校验"，不做向量化（向量化在 vector_store.py）。
刻意不依赖 langchain 的 DirectoryLoader：制度文件需要严格的元数据校验，
以及"清单覆盖度"审计（哪些制度还没交上来），这些是通用 loader 不做的。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterator, Optional

import yaml

from .schema import DocMeta

CORPUS_DIR = Path(__file__).resolve().parent / "corpus"

_SKIP = {"_TEMPLATE.md", "_INDEX.md", "README.md", "manifest.yaml"}

_FM = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class LoadedDoc:
    meta: DocMeta
    body: str
    path: Path

    @property
    def ok(self) -> bool:
        return bool(self.body.strip())


def _int_date(d: Optional[date]) -> int:
    """日期转整数，供 Chroma where 做数值比较（Chroma 不支持日期比较）"""
    if not d:
        return 0
    return d.year * 10000 + d.month * 100 + d.day


def parse_front_matter(raw: str, path: Path) -> tuple[dict[str, Any], str]:
    m = _FM.match(raw)
    if not m:
        raise ValueError(f"{path.name}: 缺少 YAML front-matter（文件必须以 --- 开头）")
    meta = yaml.safe_load(m.group(1)) or {}
    if not isinstance(meta, dict):
        raise ValueError(f"{path.name}: front-matter 不是键值对")
    return meta, raw[m.end():]


def load_file(path: Path) -> LoadedDoc:
    raw = path.read_text(encoding="utf-8")
    meta_dict, body = parse_front_matter(raw, path)

    meta_dict.setdefault("category", path.parent.name)
    meta_dict.setdefault("status", "active")

    meta = DocMeta(**meta_dict)
    return LoadedDoc(meta=meta, body=body, path=path)


def iter_files(corpus_dir: Path = CORPUS_DIR) -> Iterator[Path]:
    for p in sorted(corpus_dir.rglob("*.md")):
        if p.name in _SKIP:
            continue
        yield p


def load_all(corpus_dir: Path = CORPUS_DIR, strict: bool = False) -> list[LoadedDoc]:
    """
    strict=False：单份文件有问题只记录，不影响其他文档（生产环境建议如此）
    strict=True ：有任何错误直接抛异常（CI / 入库前校验用）
    """
    docs: list[LoadedDoc] = []
    errors: list[str] = []
    for path in iter_files(corpus_dir):
        try:
            docs.append(load_file(path))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{path.relative_to(corpus_dir)}: {exc}")
    if errors and strict:
        raise ValueError("知识库元数据校验失败：\n" + "\n".join(errors))
    if errors:
        print(f"[rag] 跳过 {len(errors)} 份无效文档：")
        for e in errors:
            print(f"  - {e}")
    return docs


def to_chroma_records(docs: list[LoadedDoc], max_chars: int = 800) -> list[dict[str, Any]]:
    """LoadedDoc → Chroma 入库记录（含冗余的 int 日期字段与密级数值）"""
    from .filters import _LEVEL
    from .splitter import split_document

    records: list[dict[str, Any]] = []
    for d in docs:
        m = d.meta
        base = {
            "doc_id": m.doc_id,
            "title": m.title,
            "version": m.version,
            "doc_type": m.doc_type.value,
            "category": m.category,
            "status": m.status.value,
            "department": m.department,
            "effective_int": _int_date(m.effective_date),
            "expire_int": _int_date(m.expire_date),
            "confidentiality": m.confidentiality.value,
            "conf_level": _LEVEL[m.confidentiality],
            "acl_roles": ",".join(m.acl_roles),
            "related_workshops": ",".join(m.related_workshops),
            "related_claims": ",".join(m.related_claims),
            "keywords": ",".join(m.keywords),
        }
        for ch in split_document(
            d.body, max_chars=max_chars, title=m.title, version=m.version
        ):
            records.append(
                {
                    "id": f"{m.doc_id}:{m.version}:{len(records)}",
                    "text": f"{ch.breadcrumb}\n{ch.text}".strip(),
                    "metadata": {
                        **base,
                        "clause": ch.clause,
                        "section": ch.section,
                        "breadcrumb": ch.breadcrumb,
                    },
                }
            )
    return records


def inventory(corpus_dir: Path = CORPUS_DIR) -> dict[str, Any]:
    """
    知识库盘点：读 manifest.yaml，对比实际已交的文件，输出缺哪些。
    制度文件不是一次能收齐的，得能追踪进度。
    """
    manifest_path = corpus_dir / "manifest.yaml"
    manifest = (
        yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        if manifest_path.exists()
        else {}
    )
    expected = {item["doc_id"]: item for item in manifest.get("docs", [])}

    loaded = load_all(corpus_dir)
    have = {d.meta.doc_id: d for d in loaded}

    missing = [
        {"doc_id": k, "title": v.get("title"), "tier": v.get("tier"), "dir": v.get("dir")}
        for k, v in expected.items()
        if k not in have
    ]
    extra = [k for k in have if k not in expected]
    today = date.today()
    stale = [
        {"doc_id": d.meta.doc_id, "version": d.meta.version, "title": d.meta.title}
        for d in loaded
        if d.meta.status.value == "active" and not d.meta.is_retrievable(today)
    ]

    return {
        "total_expected": len(expected),
        "total_loaded": len(loaded),
        "coverage": round(len(have) / len(expected) * 100, 1) if expected else 0.0,
        "missing": missing,
        "undeclared": extra,
        "not_retrievable": stale,
        "chunks": len(to_chroma_records(loaded)),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(inventory(), ensure_ascii=False, indent=2))
