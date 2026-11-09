"""
流式对话消费层：只负责把 AgentExecutor 吐出的流式事件格式化并输出。
Agent 如何组装、模型如何选择都不在这一层，交由 agent_builder / model_scheduler。

三种用法：
  run_sync_stream(executor, question)   → 同步步骤级流（stream）
  run_async_stream(executor, question)  → 异步步骤级流（astream）
  run_token_stream(executor, question)  → 异步 token 级流（astream_events）
"""
from __future__ import annotations

from typing import Any, Optional

from utils.logger import logger


def _chunk_text(chunk: Any) -> str:
    """从 ChatOpenAI 的 chunk 里抠出纯文本（兼容 str / content blocks 两种形态）"""
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
    return str(content)


def _extract_final(output: Any) -> Optional[str]:
    """从 on_chain_end 的 output 里取最终答案"""
    if output is None:
        return None
    if isinstance(output, dict):
        return output.get("output")
    return str(output)


def run_sync_stream(executor, question: str) -> Optional[str]:
    """
    同步步骤级流。每调用一个工具 / 决定最终答案就吐一个 chunk。
    思考与工具日志由 AgentThoughtCallback 负责，这里只取最终答案。
    """
    final: Optional[str] = None
    for chunk in executor.stream({"input": question}):
        if "output" in chunk:
            final = chunk["output"]
    return final


async def run_async_stream(executor, question: str) -> Optional[str]:
    """异步步骤级流，与 run_sync_stream 行为一致，只是改成 async 迭代"""
    final: Optional[str] = None
    async for chunk in executor.astream({"input": question}):
        if "output" in chunk:
            final = chunk["output"]
    return final


async def run_token_stream(executor, question: str) -> Optional[str]:
    """
    异步 token 级流：模型生成一个字就打印一个字。
    注意：ReAct 模式下先吐出的是 Thought/Action 这类脚手本文本，
    最终答案在末尾，属于正常现象。
    """
    final: Optional[str] = None
    started = False

    async for event in executor.astream_events({"input": question}, version="v2"):
        kind = event["event"]

        if kind == "on_chat_model_stream":
            if not started:
                print("\n🧠 流式输出：", end="", flush=True)
                started = True
            print(_chunk_text(event["data"].get("chunk")), end="", flush=True)

        elif kind == "on_chain_end" and event.get("name") == "AgentExecutor":
            final = _extract_final(event["data"].get("output"))

    if started:
        print()  # 收尾换行
    logger.info("✅ 流式输出完成")
    return final
