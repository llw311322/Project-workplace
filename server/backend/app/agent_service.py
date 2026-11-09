"""
Agent 服务层 —— 对上层路由屏蔽 LangChain 细节，
同时统一做 try/except + 超时降级（5 秒硬超时），
任何异常都不阻断主业务。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import AsyncGenerator, Optional

from utils.logger import logger

# ====== 关键：把项目根目录塞进 sys.path，这样 backend/ 可以 import 到 agent/ ======
_PROJECT_ROOT = Path(__file__).resolve().parents[2]   # backend/app → backend → 项目根
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 复用项目已有能力
from agent.agent_builder import build_agent_executor
from agent.stream_runner import run_token_stream


def _fallback(reason: str) -> str:
    """统一降级提示文案，前端看到 '🤖 Agent 暂时不可用…' 就知道要重试或走人工"""
    return f"🤖 Agent 暂时不可用（原因: {reason}）。请稍后重试或联系人工处理。"


async def chat_agent(
    question: str,
    *,
    model_key: Optional[str] = None,
    timeout_seconds: int = 5,
) -> str:
    """
    非流式 Agent 对话。超时 / 异常 → 返回降级文案，绝不 raise。
    """
    try:
        executor = build_agent_executor(model_key=model_key, streaming=False)
        # 用 asyncio.wait_for 做硬超时
        result = await asyncio.wait_for(
            asyncio.to_thread(_run_sync_wrapper, executor, question),
            timeout=timeout_seconds,
        )
        return result or _fallback("空响应")
    except asyncio.TimeoutError:
        logger.warning(f"[Agent] 对话超时 {timeout_seconds}s")
        return _fallback(f"响应超时（>{timeout_seconds}s）")
    except Exception as e:
        logger.exception(f"[Agent] 对话异常: {e}")
        return _fallback(type(e).__name__)


def _run_sync_wrapper(executor, question: str) -> Optional[str]:
    """
    build_agent_executor 产出的 executor 既支持 .stream() 也支持 .invoke()。
    同步调用最稳，丢到 asyncio.to_thread 里跑。
    """
    try:
        # invoke 一次拿最终答案，比 stream 再聚合简单
        out = executor.invoke({"input": question})
        return out.get("output") if isinstance(out, dict) else str(out)
    except Exception as e:
        logger.exception(f"[Agent.executor.invoke] 崩了: {e}")
        return None


async def summarize_document(content: str, *, timeout_seconds: int = 5) -> str:
    """对单据正文做摘要，失败返回降级文案"""
    prompt = (
        "请用 1-3 句话概括下面这段业务单据的核心信息："
        "\n\n---\n"
        f"{content[:3500]}"   # 截断防爆 token
        "\n---"
    )
    return await chat_agent(prompt, timeout_seconds=timeout_seconds)


async def validate_document(
    content: str,
    rules: Optional[list[str]] = None,
    *,
    timeout_seconds: int = 5,
) -> str:
    """
    合规校验：默认检查是否包含敏感词、金额前后矛盾、日期非法，
    调用方也可以自定义 rules。
    """
    rule_block = "\n".join(f"- {r}" for r in (rules or [])) or "- 无明显语法错误\n- 无前后矛盾\n- 金额/日期字段自洽"
    prompt = (
        "你是一名业务合规审核员。请根据以下规则对单据做校验，"
        "逐条给出 合规 / 风险 + 说明，最后一句输出【整体结论：通过 / 不通过】。"
        f"\n\n校验规则：\n{rule_block}"
        "\n\n单据正文：\n"
        f"{content[:3500]}"
    )
    return await chat_agent(prompt, timeout_seconds=timeout_seconds)


async def stream_chat_agent(
    question: str,
    *,
    model_key: Optional[str] = None,
    timeout_seconds: int = 5,
) -> AsyncGenerator[str, None]:
    """
    SSE 用的 token 级流：每吐一个字 yield 一个 data: 事件块。
    异常时只 yield 一个降级块就结束，不向前端抛错。
    """
    # yield 一个“开始”帧
    yield _sse_event(event="start", data={"message": "streaming started"})

    final_text_parts: list[str] = []

    try:
        executor = build_agent_executor(model_key=model_key, streaming=True)

        async for event in executor.astream_events({"input": question}, version="v2"):
            kind = event["event"]

            if kind == "on_chat_model_stream":
                chunk = _extract_chunk_text(event["data"].get("chunk"))
                if chunk:
                    final_text_parts.append(chunk)
                    yield _sse_event(event="token", data=chunk)

            elif kind == "on_chain_end" and event.get("name") == "AgentExecutor":
                final = _extract_final(event["data"].get("output"))
                if final and not final_text_parts:
                    # 极少数情况下没有 token 流但有 final，补齐一下
                    yield _sse_event(event="token", data=final)

    except asyncio.TimeoutError:
        logger.warning(f"[Agent SSE] 超时 {timeout_seconds}s")
        yield _sse_event(event="error", data=_fallback(f"超时（>{timeout_seconds}s）"))
        yield _sse_event(event="done", data={"degraded": True})
        return
    except Exception as e:
        logger.exception(f"[Agent SSE] 异常: {e}")
        yield _sse_event(event="error", data=_fallback(type(e).__name__))
        yield _sse_event(event="done", data={"degraded": True})
        return

    yield _sse_event(event="done", data={"degraded": False})


# ---------- 私有工具 ----------
def _extract_chunk_text(chunk) -> str:
    """从 ChatOpenAI chunk 里抠纯文本（和 stream_runner._chunk_text 逻辑对齐）"""
    if chunk is None:
        return ""
    content = getattr(chunk, "content", chunk)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content) if content is not None else ""


def _extract_final(output) -> Optional[str]:
    if output is None:
        return None
    if isinstance(output, dict):
        return output.get("output")
    return str(output)


def _sse_event(*, event: str, data) -> str:
    """标准 SSE 帧：event: xxx\\ndata: json\\n\\n"""
    import json as _json
    payload = _json.dumps({"event": event, "data": data}, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"
