from .calculator_tool import calculator
from .search_tool import web_search

# 把所有工具放到列表，统一给Agent调用
all_tools = [calculator, web_search]
