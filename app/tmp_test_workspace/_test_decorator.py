"""临时测试 @tool 装饰器行为（执行后可删除）"""
from langchain.tools import tool


@tool(description="test desc")
def f1(x: str) -> str:
    """docstring"""
    return x


@tool
def f2(x: str) -> str:
    """docstring"""
    return x


print("=== @tool(description=...) ===")
print("type:", type(f1).__name__)
print("has name:", hasattr(f1, "name"))
print("has description:", hasattr(f1, "description"))
print("callable:", callable(f1))
if hasattr(f1, "name"):
    print("name:", f1.name)
if hasattr(f1, "description"):
    print("description:", f1.description)
print("repr:", repr(f1)[:200])
print()
print("=== @tool（无参） ===")
print("type:", type(f2).__name__)
print("has name:", hasattr(f2, "name"))
print("callable:", callable(f2))
