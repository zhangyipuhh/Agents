#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
DevOpsAgentContext 模块

定义 DevOps 会话上下文的类型结构，用于在 DevOpsAgent 会话中传递和管理上下文信息。
该模块提供上下文类的类型定义，支持 SSH 配置和命令黑名单的注入。

Date: 2026-03-30
"""

from typing import Optional, Any
from app.core.agent.AgentContext import AgentContext as BaseAgentContext


class DevOpsAgentContext(BaseAgentContext):
    """
    DevOps 上下文类

    继承自 BaseAgentContext，用于定义 DevOps 对话上下文的结构。
    上下文类的字段会被添加到状态类中，用于在会话中传递上下文信息。

    Attributes:
        session_id: 会话 ID，用于区分不同用户的对话，相同 session_id 的对话共享记忆
        ssh_config: SSH 连接配置，从配置文件加载
        command_blacklist: 命令黑名单列表
    """

    ssh_config: Optional[str] = None
    """SSH 连接配置（JSON 字符串），包含 host, username, password, private_key_path 等"""

    command_blacklist: list[str] = []
    """命令黑名单列表，用于拦截高危命令"""
