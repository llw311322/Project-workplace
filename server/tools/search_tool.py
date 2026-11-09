from langchain.tools import tool

@tool("web_search", return_direct=False)
def web_search(query: str) -> str:
    """
    联网查询实时信息、新闻、常识；当问题超出模型知识时使用
    参数：query=搜索关键词
    """
    return f"【模拟搜索结果】关键词：{query}，查到对应信息内容。"
