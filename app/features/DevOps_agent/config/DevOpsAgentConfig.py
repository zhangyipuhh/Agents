#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
DevOps Agent 配置文件

该模块定义了 DevOpsAgentConfig 数据类，用于封装 DevOps Agent 的所有配置参数。
支持配置模型参数、检查点器、存储库、系统提示词等核心功能。

Date: 2026-03-30
"""

from dataclasses import dataclass, field
from typing import Optional, Any
from langgraph.prebuilt import ToolNode
from app.core.agent.AgentConfig import (
    ConfigurableConfig as BaseConfigurableConfig,
    AgentState as BaseAgentState,
    AgentConfig as BaseAgentConfig,
    ExecuteConfig as BaseExecuteConfig,
)
from app.features.DevOps_agent.config.DevOpsAgentContext import DevOpsAgentContext


class DevOpsConfigurableConfig(BaseConfigurableConfig):
    """
    可配置参数，如 thread_id（线程ID，用于区分不同会话）等
    """


class DevOpsExecuteConfig(BaseExecuteConfig):
    """
    LangGraph 可运行配置结构，继承自 BaseExecuteConfig

    用于配置 LangGraph 运行时的各种参数，如线程ID、回调等。
    与 LangGraph 的 invoke 方法的 config 参数兼容。
    """


class DevOpsAgentState(BaseAgentState):
    """
    状态类，需要传入一个继承自 MessagesState 的 TypedDict 类型，用于管理对话状态，在会话中是可被操作的值
    具体实现的agent需要继承该类
    """
    server_type: str = "linux"
    """服务器类型，用于判断使用 bash 还是 PowerShell"""


@dataclass(kw_only=True)
class DevOpsAgentConfig(BaseAgentConfig):
    """
    DevOpsAgent 配置类

    封装 Agent 的所有配置参数，用于初始化和管理 Agent 实例。
    该类使用数据类实现，支持默认值配置，便于灵活创建 Agent。
    支持继承，子类可重写默认值或添加新字段。
    """

    name: str = field(default="DevOps_agent")
    """DevOpsAgent 在 skill 系统中的注册名（与 app/features/DevOps_agent/ 目录名一致），
    用于子智能体维度 skill 与 bootstrap 覆盖。"""

    state_class: type[DevOpsAgentState] = field(default=None)
    """
    状态类，需要传入一个继承自 AgentState 的 TypedDict 类型，用于管理对话状态，在会话中是可被操作的值
    """

    context_class: type[DevOpsAgentContext] = field(default=None)

    default_timeout: int = field(default=30)
    """命令执行默认超时（秒）"""

    max_history: int = field(default=100)
    """命令历史最大条数"""

    encoding: str = field(default="utf-8")
    """命令输出编码"""

    def get_tools(self) -> tuple[list[str], ToolNode]:
        """
        获取所有 DevOps 工具名称列表

        返回:
            tuple[list[str], ToolNode]: 工具名称列表和对应的 ToolNode 对象
        """
        from app.features.DevOps_agent.tools.SSHTools import (
            execute_command,
            execute_batch_commands,
        )

        base_tools, base_tool_node = super().get_tools()
        tools = list(base_tools) + [execute_command, execute_batch_commands]

        return tools, ToolNode(tools)
