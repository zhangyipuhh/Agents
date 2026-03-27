from typing import Union, List, Optional
from pathlib import Path
from langchain.tools import tool
from langgraph.types import Command
from app.core.agent.AgentContext import AgentContext
from app.core.tools.BaseTools import ToolRuntime


def get_current_time(runtime: ToolRuntime[AgentContext]) -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def search_web(query: str, runtime: ToolRuntime[AgentContext]) -> str:
    return f"搜索结果: {query} (模拟)"


TOOLS = [
    get_current_time,
    search_web,
]
