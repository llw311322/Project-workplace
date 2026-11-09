"""
向量化客户端 —— 通义 text-embedding-v3（OpenAI 兼容协议）。

为什么选它：
    · 全站只接一家厂商（百炼）：对话与向量化共用一把 Key、一个预算开关
    · 32 份制度 ≈ 603 个 chunk，一次性入库成本可忽略
    · 与 Agent 的 LLM 走同一个厂商通道，运维面最小

要点：
    · DashScope 兼容模式下 embeddings 单次请求最多 10 条文本，按批切分
    · 查询时只需 embed 一条，延迟 ~200ms（检索路径的主要开销）
    · 失败重试 3 次（429 / 5xx 指数退避），仍失败抛 RuntimeError 降级
"""
from __future__ import annotations

import os
import time
from typing import Any

import httpx
from dotenv import load_dotenv

# 与 agent/ 模块同一套做法：命令行直接跑（rebuild 脚本）也能读到 .env
load_dotenv()

# ---------- 配置（全部可被环境变量覆盖） ----------
API_KEY = os.getenv("QWEN_API_KEY", "")
BASE_URL = (os.getenv("QWEN_BASE_URL") or "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")
EMBED_MODEL = os.getenv("QWEN_EMBED_MODEL", "text-embedding-v3")
EMBED_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))
BATCH_SIZE = 10          # DashScope 兼容模式单次请求上限
MAX_RETRY = 3


class EmbedderError(RuntimeError):
    """embedding 调用失败（重试耗尽）"""


def _request_batch(client: httpx.Client, texts: list[str]) -> list[list[float]]:
    payload: dict[str, Any] = {"model": EMBED_MODEL, "input": texts}
    if EMBED_DIM:
        payload["dimensions"] = EMBED_DIM
    headers = {"Authorization": f"Bearer {API_KEY}"}

    last_err: Exception | None = None
    for attempt in range(MAX_RETRY):
        try:
            resp = client.post("/embeddings", json=payload, headers=headers, timeout=30)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise httpx.HTTPStatusError(f"transient {resp.status_code}", request=resp.request, response=resp)
            resp.raise_for_status()
            data = resp.json()["data"]
            # 兼容模式按 input 顺序返回（index 字段兜底排序）
            data.sort(key=lambda item: item.get("index", 0))
            return [item["embedding"] for item in data]
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(1.5**attempt)
    raise EmbedderError(f"embedding 请求失败（已重试 {MAX_RETRY} 次）: {last_err}") from last_err


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量向量化。空输入返回空列表；调用方需保证 API_KEY 已配置。"""
    if not texts:
        return []
    if not API_KEY:
        raise EmbedderError("缺少 QWEN_API_KEY，无法向量化")
    out: list[list[float]] = []
    with httpx.Client(base_url=BASE_URL) as client:
        for i in range(0, len(texts), BATCH_SIZE):
            out.extend(_request_batch(client, texts[i : i + BATCH_SIZE]))
    return out


def embed_query(text: str) -> list[float]:
    """单条查询向量化（检索路径热点，单独封装便于统计耗时）"""
    return embed_texts([text])[0]
