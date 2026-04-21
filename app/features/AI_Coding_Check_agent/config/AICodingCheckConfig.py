#!/usr/bin/python
# -*- coding:utf-8 -*-

"""
AICodingCheckAgent 配置文件

该模块定义了 AICodingCheckConfig 数据类，用于封装 AI 辅助编程效果评审 Agent 的所有配置参数。
支持配置模型参数、检查点器、存储库、系统提示词等核心功能。
使用 field() 处理默认值，解决了 dataclass 的类属性共享陷阱问题。

Date: 2026-04-21
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

from app.features.AI_Coding_Check_agent.config.AICodingCheckContext import AICodingCheckContext


class AICodingCheckConfigurableConfig(BaseConfigurableConfig):
    """
    可配置参数，如 thread_id（线程ID，用于区分不同会话）等
    """


class AICodingCheckExecuteConfig(BaseExecuteConfig):
    """
    LangGraph 可运行配置结构，继承自 BaseExecuteConfig

    用于配置 LangGraph 运行时的各种参数，如线程ID、回调等。
    与 LangGraph 的 invoke 方法的 config 参数兼容。
    """


class AICodingCheckState(BaseAgentState):
    """
    状态类，需要传入一个继承自 MessagesState 的 TypedDict 类型，用于管理对话状态，在会话中是可被操作的值
    具体实现的agent需要继承该类
    """

    developer_data: dict = {}
    """开发者数据，存储待评审的开发者信息，如姓名、提交记录等"""

    review_result: dict = {}
    """评审结果，存储 AI 评审后的结构化输出，包含各维度评分和检测结果"""


@dataclass(kw_only=True)
class AICodingCheckConfig(BaseAgentConfig):
    """
    AICodingCheckAgent 配置类

    封装 Agent 的所有配置参数，用于初始化和管理 Agent 实例。
    该类使用数据类实现，支持默认值配置，便于灵活创建 Agent。
    支持继承，子类可重写默认值或添加新字段。
    """

    state_class: type[AICodingCheckState] = field(default=None)
    """
    状态类，需要传入一个继承自 AgentState 的 TypedDict 类型，用于管理对话状态，在会话中是可被操作的值
    """

    context_class: type[AICodingCheckContext] = field(default=None)
    """上下文类，用于管理会话隔离和上下文信息传递"""

    def get_tools(self) -> tuple[list[str], ToolNode]:
        """
        获取所有评审工具名称列表

        返回:
            tuple[list[str], ToolNode]: 工具名称列表和对应的 ToolNode 对象
        """
        # 本 Agent 直接基于提示词进行评审，不需要绑定工具
        # 工具已由 AICodingCheckAgent.review() 方法直接调用
        return [], None
