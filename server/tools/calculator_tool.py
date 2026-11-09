from langchain.tools import tool

@tool("calculator", return_direct=False)
def calculator(query: str) -> str:
    """
    用于数学计算，输入只能是纯数学表达式，例如：3+5*2、(100-23)/7
    """
    try:
        result = eval(query)
        return f"计算结果：{result}"
    except Exception as e:
        return f"计算出错：{str(e)}"
