from langchain_core._api.deprecation import suppress_langchain_deprecation_warning


def build_memory():
    # ConversationBufferMemory 在 langchain 0.3.x 可用，
    # 但 import 和实例化都会触发 LangChainDeprecationWarning，用官方 context manager 抑制
    with suppress_langchain_deprecation_warning():
        from langchain.memory import ConversationBufferMemory
        memory = ConversationBufferMemory(
            memory_key="chat_history",
            output_key="output",  # 流式返回的 chunk 会带多个 key，显式指定避免歧义
            return_messages=True  # 必须开启，适配ReAct聊天Agent
        )
    return memory
