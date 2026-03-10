#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Agent 配置模块

该模块定义了 AgentConfig 数据类，用于封装 Agent 的所有配置参数。
支持配置模型参数、检查点器、存储库、系统提示词等核心功能。
使用 field() 处理默认值，解决了 dataclass 的类属性共享陷阱问题。

Date: 2026-03-10
Author: 张镒谱
"""

from typing import TypedDict, Optional, Any
from dataclasses import dataclass, field
from langgraph.graph import MessagesState
from langgraph.store.base import BaseStore
from langgraph.prebuilt import ToolNode

@dataclass(kw_only=True)
class AgentConfig:
    """
    Agent 配置类
    
    封装 Agent 的所有配置参数，用于初始化和管理 Agent 实例。
    该类使用数据类实现，支持默认值配置，便于灵活创建 Agent。
    支持继承，子类可重写默认值或添加新字段。
    """

    model_type: str
    """模型类型，如 "ollama"、"deepseek"、"openai" 等，指定使用的模型服务商"""
    
    model_name: str
    """模型名称，如 "llama3.2"、"deepseek-chat"、"gpt-4" 等，指定具体的模型"""
    
    state_class: type[MessagesState] = field(default=None)
    """状态类，需要传入一个继承自 MessagesState 的 TypedDict 类型，用于管理对话状态"""
    
    context_class: type[TypedDict] = field(default=None)
    """上下文类，需要传入一个 TypedDict 类型，定义对话上下文结构"""
    
    temperature: float = field(default=0)
    """模型温度参数，控制生成多样性。取值范围 0-1，越高越随机，默认 0"""
    
    api_key: Optional[str] = field(default=None)
    """API 密钥，用于访问远程模型服务。如果为 None，则使用环境变量或本地模型"""
    
    base_url: Optional[str] = field(default=None)
    """API 基础 URL，指定模型服务的地址。如果为 None，则使用默认地址"""
    
    max_tokens: int = field(default=256)
    """最大 token 数，限制单次生成的最大长度，防止生成过长响应，默认 256"""
    
    max_tokens_before_summary: int = field(default=256)
    """触发摘要的 token 阈值，当消息历史超过此值时触发摘要操作，默认 256"""
    
    max_summary_tokens: int = field(default=128)
    """摘要后的最大 token 数，控制摘要的长度，避免摘要过于冗长，默认 128"""
    
    checkpointer: Any = field(default=None)
    """检查点器，用于持久化对话状态，支持断点续训和状态恢复，默认 None"""
    
    store: Optional[BaseStore] = field(default=None)
    """存储库，用于长期跨会话记忆存储，支持跨会话上下文共享，默认 None"""
    
    system_prompt: Optional[str] = field(default=None)
    """系统提示词，用于设置 AI 的行为角色、性格和约束条件，默认 None"""
    
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
