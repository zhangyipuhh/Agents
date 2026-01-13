#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
主智能体状态定义模块

本模块定义了主智能体的状态数据结构，用于在智能体工作流中传递和管理消息及状态信息。
主要包含消息列表和规则检查计数器，支持消息的累加操作。

Date: 2026-01-13
Author: 张镒谱
"""

from langchain.messages import AnyMessage
from typing_extensions import TypedDict, Annotated
import operator


class MessagesState(TypedDict):
    """
    主智能体状态类

    定义了智能体在工作流中维护的核心状态数据，包括消息历史和规则检查计数。
    使用TypedDict确保类型安全，通过operator.add实现消息列表的累加操作。

    Attributes:
        messages: 消息列表，使用operator.add实现累加操作，支持智能体间的消息传递
        checked_rules_count: 规则检查计数器，记录已检查的规则数量，用于追踪工作流进度
    """
    # 消息列表：使用operator.add实现累加，确保多智能体场景下消息能够正确合并
    messages: Annotated[list[AnyMessage], operator.add]
    # 规则检查计数器：记录已检查的规则数量，用于工作流进度追踪和状态监控
    checked_rules_count: int
