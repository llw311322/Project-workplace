from dotenv import load_dotenv
import os
from langchain_openai import ChatOpenAI
# ====== 关键导入：执行器+创建Agent的函数（内置传送带）======
from langchain.agents import AgentExecutor, create_react_agent

from .prompt_template import get_react_prompt
from .callbacks import AgentThoughtCallback
from .model_scheduler import scheduler
from tools.tool_registry import all_tools
from memory.memory_config import build_memory
from utils.logger import logger

# 加载环境变量
load_dotenv()

def build_agent_executor(model_key: str | None = None, streaming: bool = False):
    """
    组装 ReAct Agent 执行器。
    :param model_key: 厂商别名（当前只支持 "qwen"，见 model_scheduler.VENDOR_DEFS）。
                     为 None 时使用 .env 里的 AGENT_VENDOR（默认 qwen）。
    :param streaming: 是否开启 LLM 级流式。仅 token 级流式（astream_events）需要 True，
                     步骤级 stream/astream 不需要。
    """
    # 1. 从调度器取 LLM 配置（自动处理多密钥轮询 + 故障降级）
    api_key, base_url, model_name = scheduler.get_llm_config(model_key)
    llm = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model_name,
        temperature=0,
        streaming=streaming,
    )
    logger.info(f"🔑 LLM: [{model_key or scheduler.default_key()}] model={model_name} base_url={base_url}")

    # 2. 获取提示词、工具、记忆
    prompt = get_react_prompt()
    tools = all_tools
    memory = build_memory()
    callbacks = [AgentThoughtCallback()]

    # 3. 组装Agent大脑（llm + prompt + tools）
    agent = create_react_agent(llm=llm, tools=tools, prompt=prompt)

    # 4. 实例化【执行器传送带】AgentExecutor
    # 内部自带循环、解析、异常捕获、终止判断，不用手写while循环
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        memory=memory,
        verbose=False,
        handle_parsing_errors=True,  # 自动捕获LLM输出格式错误
        max_iterations=8,  # 最大思考轮次，防止死循环
        callbacks=callbacks
    )

    logger.info("✅ Agent执行器组装完成")
    return agent_executor
