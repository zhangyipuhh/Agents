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
from app.test.Tagent.TagentContext import TAgentContext
from langchain.tools import tool, ToolRuntime
from langchain.messages import ToolMessage
from langgraph.types import Command

@tool(description="获取当前时间") 
def get_current_time(runtime: ToolRuntime[TAgentContext]) -> str:
    """
    获取当前时间工具
    
    返回当前系统时间字符串，格式为 YYYY-MM-DD HH:MM:SS，并附带会话ID。
    用于Agent了解当前时间上下文，支持时间敏感的任务处理。
    
    Args:
        runtime (ToolRuntime[TAgentContext]): 工具运行时上下文，包含会话信息
        
    Returns:
        str: 格式化的时间字符串，格式 "YYYY-MM-DD HH:MM:SS (session_id: xxx)"
    """
    # 获取当前系统时间并格式化为字符串
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
 
 
    # 会话ID用于追踪和调试，将session_id附加到返回结果中
    return  current_time + f" (session_id: {runtime.context.get('session_id', 'default')}) "  



@tool(description="对列表中的数字进行求和")
def add(numbers: list, runtime: ToolRuntime[TAgentContext]) -> float:
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