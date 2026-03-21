#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
DocAgent 配置模块

该模块定义了 DocAgentConfig 数据类，用于封装文档处理 Agent 的所有配置参数。
支持配置模型参数、检查点器、存储库、系统提示词等核心功能。
使用 field() 处理默认值，解决了 dataclass 的类属性共享陷阱问题。

Date: 2026-03-19
Author: 张镒谱
"""

from dataclasses import dataclass, field
from langgraph.prebuilt import ToolNode
from app.core.agent.AgentConfig import (
    ConfigurableConfig as BaseConfigurableConfig,
    AgentState as BaseAgentState,
    AgentConfig as BaseAgentConfig,
    ExecuteConfig as BaseExecuteConfig,
)
from app.features.contract_document_agent.config.DocAgentContext import DocAgentContext


class DocConfigurableConfig(BaseConfigurableConfig):
    """
    可配置参数，如 thread_id（线程ID，用于区分不同会话）等
    """


class DocExecuteConfig(BaseExecuteConfig):
    """
    LangGraph 可运行配置结构，继承自 BaseExecuteConfig

    用于配置 LangGraph 运行时的各种参数，如线程ID、回调等。
    与 LangGraph 的 invoke 方法的 config 参数兼容。
    """


class DocAgentState(BaseAgentState):
    """
    状态类，需要传入一个继承自 MessagesState 的 TypedDict 类型，用于管理对话状态，在会话中是可被操作的值
    具体实现的agent需要继承该类
    """


@dataclass(kw_only=True)
class DocAgentConfig(BaseAgentConfig):
    """
    DocAgent 配置类

    封装 Agent 的所有配置参数，用于初始化和管理 Agent 实例。
    该类使用数据类实现，支持默认值配置，便于灵活创建 Agent。
    支持继承，子类可重写默认值或添加新字段。
    """

    state_class: type[DocAgentState] = field(default=None)
    """
    状态类，需要传入一个继承自 AgentState 的 TypedDict 类型，用于管理对话状态，在会话中是可被操作的值
    """

    context_class: type[DocAgentContext] = field(default=None)
    """
    上下文类，需要传入一个 AgentContext 类型，定义对话上下文结构，不可变
    """

    def get_tools(self) -> tuple[list[str], ToolNode]:
        """
        获取所有文档处理工具名称列表

        返回:
            tuple[list[str], ToolNode]: 工具名称列表和对应的 ToolNode 对象
        """
        from app.agents.subgraphs.Doc_Agent.tools.DocTools import (
            split_file
        )

        base_tools, base_tool_node = super().get_tools()
        tools = list(base_tools) + [split_file]

        return tools, ToolNode(tools)
