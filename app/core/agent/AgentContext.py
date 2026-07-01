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
from typing import Optional


class AgentContext(TypedDict):
    """
    上下文类

    继承自 TypedDict，用于定义对话上下文的结构。
    上下文类的字段会被添加到状态类中，用于在会话中传递和管理上下文信息。
    该模块提供上下文类的类型定义，支持多用户会话隔离和上下文共享。

    Attributes:
        session_id: 会话 ID，用于区分不同用户的对话，相同 session_id 的对话共享记忆
        host_session_id: 主机会话 ID，用于多智能体协作时数据隔离

    Example:
        >>> context = AgentContext(session_id="user_123")
        >>> # 在 Agent 状态中使用上下文

    说明:
        2026-07-01 删除原 project_id 字段（Optional[int] = None）。
        业务场景需要的上下文键（如 project_id）由调用方通过 context_overrides
        显式注入到 context_class(**kwargs)；AgentContext 是 TypedDict，
        运行时仍允许任意额外键，工具可通过 runtime.context.get("project_id") 读取。
    """

    session_id: str = "default"
    """会话 ID，用于区分不同用户的对话，相同 session_id 的对话共享记忆，默认 "default" """
    namespace: dict = {}
    store_id: str = "default"
    """存储 ID，用于区分不同用户的存储空间，相同 store_id 的存储空间共享记忆，默认 "default" """
    image_ids: list[str] = []
    """图片ID列表，用于多模态模型处理图片"""
    host_session_id: Optional[str] = None
    """主机会话 ID，用于多智能体协作时数据隔离，默认 None"""
    process_data: dict = {}
    """过程数据字典，用于存储业务逻辑中的临时过程值，默认空字典"""
