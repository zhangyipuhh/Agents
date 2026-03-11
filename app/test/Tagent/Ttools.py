from datetime import datetime
from typing import TYPE_CHECKING

from langchain.tools import tool, ToolRuntime

if TYPE_CHECKING:
    from app.test.Tagent.TagentConfig import TAgentState, TAgentContext, TExecuteConfig, TConfigurableConfig

@tool(description="获取当前时间") 
def get_current_time(runtime: "ToolRuntime[TAgentContext,TAgentState,TExecuteConfig]") -> str:
    """获取当前时间"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S") + f" (session_id: {runtime.context.session_id})"


@tool(description="对列表中的数字进行求和")
def add(numbers: list, runtime: "ToolRuntime[TAgentContext,TAgentState,TExecuteConfig]") -> float:
    """
    对列表中的数字进行求和
    Args:
        numbers (list): 必填 包含数字的列表
    Returns:
        float: 列表中数字的总和
    """
    return sum(numbers)
