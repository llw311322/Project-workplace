"""
中文制度文档切分器 —— 按「章 / 条 / 款」切，而不是按固定字数切。

为什么不用 RecursiveCharacterTextSplitter 直接切：
    制度文档的语义单元是"条"。按 500 字硬切会把「第 4.2 条」的例外条款
    切到下一块，Agent 检到前半段就容易给出反向结论。审批场景下这类错误
    代价很高，所以按条款边界切，超长条款再降级按段落切。

产出的每个 chunk 自带 breadcrumb：
    《单据提交流程规定》v1.0 > 第四章 审批流程 > 第 4.2 条

约束：
    - markdown 表格块整体不切（权限矩阵、时限表一旦断行就废了）
    - 单块上限 max_chars，超长按空行/句号降级切分
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_RE_CHAPTER = re.compile(r"^第[一二三四五六七八九十百零〇\d]+章")
_RE_CLAUSE = re.compile(r"^第[一二三四五六七八九十百零〇\d]+条")
_RE_NUMBERED = re.compile(r"^(\d+(?:\.\d+)+)\s+")   # 4.2 xxx 这类编号
_TABLE_ROW = re.compile(r"^\s*\|")
_SENTENCE_END = re.compile(r"(?<=[。；！？])")


@dataclass
class Chunk:
    text: str
    clause: str = ""                                  # 第 4.2 条
    section: str = ""                                 # 第四章 审批流程
    breadcrumb: str = ""
    extra: dict = field(default_factory=dict)


def _is_table_block(lines: list[str], i: int) -> int:
    """若第 i 行起是表格块，返回该块行数；否则 0"""
    if not _TABLE_ROW.match(lines[i]):
        return 0
    n = 0
    while i + n < len(lines) and _TABLE_ROW.match(lines[i + n]):
        n += 1
    return n if n >= 2 else 0   # 单行 "|" 可能是正文，不算表


def _hard_split(text: str, max_chars: int) -> list[str]:
    """超长条款降级切分：先按空行，再按句末标点"""
    if len(text) <= max_chars:
        return [text]

    parts: list[str] = []
    buf = ""
    for seg in re.split(r"\n\s*\n", text):
        if len(buf) + len(seg) + 2 <= max_chars:
            buf = f"{buf}\n\n{seg}".strip() if buf else seg
            continue
        if buf:
            parts.append(buf)
        if len(seg) <= max_chars:
            buf = seg
        else:
            cur = ""
            for sent in _SENTENCE_END.split(seg):
                if len(cur) + len(sent) <= max_chars:
                    cur += sent
                else:
                    if cur:
                        parts.append(cur.strip())
                    cur = sent
            buf = cur.strip()
    if buf:
        parts.append(buf)
    return [p for p in parts if p.strip()]


def split_document(
    text: str,
    max_chars: int = 800,
    # 阈值放得很低：制度里的「第 7.2 条 本规定自 X 日起施行」这类短条款
    # 恰恰是 Agent 最常被问到的（生效日期、解释部门），不能当噪声丢掉。
    # 只过滤掉章标题这类空壳（< 12 字）。
    min_chars: int = 12,
    title: str = "",
    version: str = "",
) -> list[Chunk]:
    """把一份制度文档切成条款级 chunk"""
    lines = text.splitlines()
    chunks: list[Chunk] = []

    section = ""
    clause = ""
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        body = "\n".join(buf).strip()
        buf = []
        if len(body) < min_chars:
            return
        head = " > ".join(x for x in (section, clause) if x)
        crumb = " > ".join(x for x in (f"《{title}》{version}".strip(), head) if x)
        for idx, piece in enumerate(_hard_split(body, max_chars)):
            suffix = f"（续{idx + 1}）" if idx else ""
            chunks.append(
                Chunk(
                    text=piece,
                    clause=clause + suffix,
                    section=section,
                    breadcrumb=crumb + suffix,
                )
            )

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # ---- 表格块整体吞入，不切 ----
        tbl = _is_table_block(lines, i)
        if tbl:
            buf.extend(lines[i : i + tbl])
            i += tbl
            continue

        m = _HEADING.match(stripped)
        if m:
            heading = m.group(2)
            if _RE_CHAPTER.match(heading):
                flush()
                section = heading
                clause = ""
            else:
                # 「第X条」或普通小节标题，都当 clause 级，便于引用
                flush()
                clause = heading
            i += 1
            continue

        # ---- 无 markdown 标题的纯文本制度（Word 转出来的常见形态）----
        if _RE_CLAUSE.match(stripped):
            flush()
            clause = stripped.split("　")[0][:40]
            buf.append(stripped)
            i += 1
            continue
        if _RE_CHAPTER.match(stripped):
            flush()
            section = stripped[:40]
            clause = ""
            i += 1
            continue
        if _RE_NUMBERED.match(stripped) and not buf:
            clause = stripped.split()[0]

        buf.append(line)
        i += 1

    flush()
    return chunks


def iter_chunks(docs: Iterable[tuple[str, str, str, str]], max_chars: int = 800):
    """
    docs: (doc_id, title, version, text) 的可迭代对象
    yield: (doc_id, title, version, Chunk)
    """
    for doc_id, title, version, text in docs:
        for ch in split_document(text, max_chars=max_chars, title=title, version=version):
            yield doc_id, title, version, ch
