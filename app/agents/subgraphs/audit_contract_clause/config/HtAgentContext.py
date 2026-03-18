#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
HtAgentContext 模块

定义合同审批会话上下文的类型结构，用于在 HtAgent 会话中传递和管理上下文信息。
该模块提供上下文类的类型定义，支持多用户会话隔离和上下文共享。

Date: 2026-03-17
Author: 张镒谱
"""

from app.agents.agent.AgentContext import AgentContext as BaseAgentContext


class HtAgentContext(BaseAgentContext):
    """
    合同审批上下文类

    继承自 BaseAgentContext，用于定义合同审批对话上下文的结构。
    上下文类的字段会被添加到状态类中，用于在会话中传递上下文信息。

    Attributes:
        session_id: 会话 ID，用于区分不同用户的对话，相同 session_id 的对话共享记忆
    """
