#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
AgentContext 模块

定义对话上下文的类型结构，用于在 Agent 会话中传递和管理上下文信息。
该模块提供上下文类的类型定义，支持多用户会话隔离和上下文共享。

Date: 2026-03-13
Author: 张镒谱
"""

from typing_extensions import TypedDict


class AgentContext(TypedDict):
    """
    上下文类

    继承自 TypedDict，用于定义对话上下文的结构。
    上下文类的字段会被添加到状态类中，用于在会话中传递上下文信息。

    Attributes:
        session_id: 会话 ID，用于区分不同用户的对话，相同 session_id 的对话共享记忆

    Example:
        >>> context = AgentContext(session_id="user_123")
        >>> # 在 Agent 状态中使用上下文
    """

    session_id: str = "default"
    """会话 ID，用于区分不同用户的对话，相同 session_id 的对话共享记忆，默认 "default"""
    namespace: dict
