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
from app.agents.agent.AgentConfig import ConfigurableConfig as BaseConfigurableConfig, AgentState as BaseAgentState, AgentConfig as BaseAgentConfig, ExecuteConfig as BaseExecuteConfig
from app.test.Tagent.Ttools import Ttools
from app.test.Tagent.TagentContext import TAgentContext



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
        """
        tools: list[str] = list(super().get_tools()[0])
        tools.extend(Ttools.get_tool_names())

        return tools, ToolNode(tools)
