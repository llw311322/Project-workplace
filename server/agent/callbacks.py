from langchain.callbacks.base import BaseCallbackHandler
from loguru import logger

class AgentThoughtCallback(BaseCallbackHandler):
    """打印Agent每一步思考、动作、观察"""
    def on_agent_action(self, action, **kwargs):
        logger.info(f"【思考动作】{action.log}")

    def on_tool_end(self, output, **kwargs):
        logger.info(f"【工具返回结果】{output}")
