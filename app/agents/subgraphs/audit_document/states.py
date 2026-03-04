#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
状态定义模块

本模块定义了合同审批智能体的状态结构，包含会话ID、文件路径、图片路径、合同数据、成交确认书数据和会议纪要数据。

Date: 2026/3/4
Author: 张镒谱
"""
from typing import List, Dict, Any, Optional
from langgraph.graph import MessagesState


class AuditDocumentState(MessagesState):
    """
    合同审批智能体状态类
    
    包含智能体执行过程中需要的所有状态数据
    """
    
    session_id: str  # 会话 ID，用于长期记忆的命名空间
    file_paths: List[str]  # 存储上传文件的路径，用于解析文件时使用
    image_paths: List[str]  # 存储 PDF 转图片后的路径数组，用于成交确认书解析
    contract_data: List[Dict[str, Any]]  # 合同解析结果数组
    transaction_data: List[Dict[str, Any]]  # 成交确认书解析结果数组
    meeting_data: List[Dict[str, Any]]  # 会议纪要解析结果数组
    file_id: Optional[str] = None  # 文件 ID，用于长期记忆中定位文件
