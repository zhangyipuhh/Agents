#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Agent继续执行判断模块

本模块提供Agent执行流程的条件判断逻辑，用于决定Agent是否需要继续执行。
主要功能包括：
- 检查Agent的最后一条消息是否包含工具调用
- 根据工具调用情况决定下一步执行路径
- 实现LangGraph图中的条件边（conditional edge）逻辑

使用场景：
在LangGraph构建的Agent执行图中，此函数作为条件节点，
用于判断Agent是否需要调用工具来完成任务。
"""
from typing import Literal
from langgraph.graph import END
from app.agents.states.mainstates import MessagesState


def should_continue(state: MessagesState) -> Literal["tool_node", END]:
    """
    判断Agent是否需要继续执行
    
    此函数是LangGraph图中的条件判断节点，用于决定Agent的执行流程。
    通过检查最后一条消息是否包含工具调用，决定下一步是执行工具调用
    还是结束对话。
    
    判断逻辑：
    1. 从状态中获取消息列表
    2. 提取最后一条消息
    3. 检查最后一条消息是否包含tool_calls属性且不为空
    4. 如果有工具调用，返回"tool_node"节点名称
    5. 如果没有工具调用，返回END结束节点
    
    Args:
        state (MessagesState): Agent的当前状态，包含消息历史记录
            - state["messages"]: 消息列表，包含对话历史和Agent的响应
    
    Returns:
        Literal["tool_node", END]: 下一步执行的目标节点
            - "tool_node": 需要执行工具调用，跳转到工具节点
            - END: 不需要工具调用，结束对话流程
    """
    # 从状态中获取消息列表
    messages = state["messages"]
    
    # 获取最后一条消息，这是Agent的最新响应
    last_message = messages[-1]

    # 检查最后一条消息是否包含工具调用
    # tool_calls属性存在且不为空表示Agent请求调用工具
    if last_message.tool_calls:
        # 返回工具节点名称，指示图流程跳转到工具执行节点
        return "tool_node"
    
    # 没有工具调用，返回END结束对话流程
    return END