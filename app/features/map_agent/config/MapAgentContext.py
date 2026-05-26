#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
MapAgentContext 模块

定义地图控制会话上下文的类型结构，用于在 MapAgent 会话中传递和管理上下文信息。
该模块提供上下文类的类型定义，支持多用户会话隔离和上下文共享。

Date: 2026-04-14
Author: AI Assistant
"""

from app.core.agent.AgentContext import AgentContext as BaseAgentContext
from typing import Union
from app.features.map_agent.config.config import ProjectSiteSelectionData

class MapAgentContext(BaseAgentContext):
    """
    地图控制上下文类

    继承自 BaseAgentContext，用于定义地图控制对话上下文的结构。
    上下文类的字段会被添加到状态类中，用于在会话中传递上下文信息。

    Attributes:
        session_id: 会话 ID，用于区分不同用户的对话，相同 session_id 的对话共享记忆
        namespace: 命名空间，用于数据隔离
        store_id: 存储 ID，用于区分不同用户的存储空间
        image_ids: 图片ID列表，用于多模态模型处理图片
        host_session_id: 主机会话 ID，用于多智能体协作时数据隔离
        geometry_data: 地理数据类型，包含点、线、面的几何数据
    """
    system_prompt: str =""
    """系统提示词，默认为空"""
    geometry_data: dict = {}
    """地理数据类型 dict，格式为 {"point": [...], "line": [...], "polygon": [...]}"""
    knowledge_root: str =""
    """知识根目录，默认为空"""
    
    