#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Ttools - Agent工具模块
ToolRuntime 只关心 Context 类型，State 和 Config 是它内部自动管理的！

该模块定义了Agent可用的工具函数，包括获取当前时间和数值求和功能。

Date: 2026-03-11
Author: 张镒谱
"""

from datetime import datetime
from app.agents.agent.AgentContext import AgentContext
from langchain.tools import tool, ToolRuntime
from langchain.messages import ToolMessage
from langgraph.types import Command


class Ttools:
    TOOL_NAMES: ClassVar[list[str]] = [
        "add",
    ]

    @staticmethod
    def get_tool_names() -> list[str]:
        return Ttools.TOOL_NAMES    




@tool(description="对列表中的数字进行求和")
def add(numbers: list, runtime: ToolRuntime[AgentContext]) -> float:
    """
    数值求和工具
    
    对输入的数字列表进行求和计算，支持整数和浮点数的混合运算。
    用于Agent执行数学计算任务。
    
    Args:
        numbers (list): 必填，包含数字的列表，支持int或float类型
        runtime (ToolRuntime[TAgentContext]): 工具运行时上下文
        
    Returns:
        float: 列表中所有数字的总和
    """
    # 使用Python内置sum函数对数字列表进行求和计算
    # sum函数内部实现遍历列表元素并累加，算法时间复杂度为O(n)
    
 
    return  f"所有数字的总和为: {sum(numbers)}" 