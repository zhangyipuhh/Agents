#!/usr/bin/python
# -*- coding:utf-8 -*-

"""
TAGENT 测试配置文件

该模块定义了 TAgentConfig 数据类，用于封装测试 Agent 的所有配置参数。
支持配置模型参数、检查点器、存储库、系统提示词等核心功能。
使用 field() 处理默认值，解决了 dataclass 的类属性共享陷阱问题。

Date: 2026-03-10
Author: 张镒谱
"""


from dataclasses import dataclass, field
from langgraph.prebuilt import ToolNode
from api.agents.agent.AgentConfig import ConfigurableConfig as BaseConfigurableConfig, AgentState as BaseAgentState, AgentContext as BaseAgentContext, AgentConfig as BaseAgentConfig, ExecuteConfig as BaseExecuteConfig

class TConfigurableConfig(BaseConfigurableConfig):
    """
    可配置参数，如 thread_id（线程ID，用于区分不同会话）等
    """

class TExecuteConfig(BaseExecuteConfig):
    """
    LangGraph 可运行配置结构

    用于配置 LangGraph 运行时的各种参数，如线程ID、回调等。
    与 LangGraph 的 invoke 方法的 config 参数兼容。
    """

    configurable: TConfigurableConfig 
    """可配置参数，如 thread_id（线程ID，用于区分不同会话）等"""

class TAgentState(BaseAgentState):
    """
    状态类，需要传入一个继承自 MessagesState 的 TypedDict 类型，用于管理对话状态，在会话中是可被操作的值
    具体实现的agent需要继承该类
    """
 

class TAgentContext(BaseAgentContext):
    """
    上下文类，需要传入一个 TypedDict 类型，定义对话上下文结构，不可变
    上下文类是一个 TypedDict 类型，用于定义对话上下文的结构。
    上下文类的字段会被添加到状态类中，用于在会话中传递上下文信息。
    """
 


@dataclass(kw_only=True)
class TAgentConfig(BaseAgentConfig):
    """
    TAgent 配置类
    
    封装 Agent 的所有配置参数，用于初始化和管理 Agent 实例。
    该类使用数据类实现，支持默认值配置，便于灵活创建 Agent。
    支持继承，子类可重写默认值或添加新字段。
    """
 
    
    state_class: type[TAgentState] = field(default=None)
    """
    状态类，需要传入一个继承自 AgentState 的 TypedDict 类型，用于管理对话状态，在会话中是可被操作的值   
    """
    
    context_class: type[TAgentContext] = field(default=None)
    

    
    
    def get_tools(self) -> tuple[list[str], ToolNode]:
        """
        获取所有审计文档工具名称列表

        返回:
            tuple[list[str], ToolNode]: 工具名称列表和对应的 ToolNode 对象

        注意:
            此方法需要子类重写，在子类中添加工具到 tools 列表
        """
        tools: list[str] = []

        return tools, ToolNode(tools)
