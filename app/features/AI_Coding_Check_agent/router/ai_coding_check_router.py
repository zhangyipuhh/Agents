#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
AI辅助编程效果评审智能体路由模块

本模块定义了AI辅助编程效果评审智能体相关的 API 路由。
主要功能包括：
- 非流式评审服务：评审开发者数据，返回完整 JSON 结果

Date: 2026-04-21
Author: 张镒谱
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from app.features.AI_Coding_Check_agent.AICodingCheckAgent import AICodingCheckAgent

# 获取当前模块的日志记录器
logger = logging.getLogger(__name__)

# 初始化 MemorySaver 和 InMemoryStore，用于保存会话检查点和内存数据
_checkpointer = MemorySaver()
store = InMemoryStore()
store_id = "ai_coding_check_store"

# 创建 API 路由实例，设置路由前缀和标签
router = APIRouter(prefix='/api/ai-coding-check', tags=['AI Coding Check'])

# 初始化 AICodingCheckAgent 实例，传入检查点存储器和内存存储
agent = AICodingCheckAgent(
    checkpointer=_checkpointer,
    store=store,
    store_id=store_id,
)


class ReviewRequest(BaseModel):
    """
    评审请求模型

    定义用户发送给评审智能体的请求数据结构。

    Attributes:
        developer_data: 开发者数据字典，包含 name、content、code、task 等字段
    """
    developer_data: Dict[str, Any]


class ReviewResponse(BaseModel):
    """
    评审响应模型

    定义评审智能体返回的响应数据结构。

    Attributes:
        code: 状态码，200 表示成功
        message: 状态信息
        data: 评审结果数据
    """
    code: int = 200
    message: str = "success"
    data: Dict[str, Any] = {}


@router.post('/review', response_model=ReviewResponse)
async def review(request: ReviewRequest) -> ReviewResponse:
    """
    评审开发者数据（非流式 JSON API）

    接收开发者数据，调用 AICodingCheckAgent 进行评审，返回完整的评审结果 JSON。

    工作流程：
    1. 接收 POST 请求，解析为 ReviewRequest
    2. 调用 AICodingCheckAgent.review() 获取评审结果
    3. 返回 JSON 响应

    Args:
        request: 评审请求，包含 developer_data

    Returns:
        ReviewResponse: 评审结果

    Raises:
        HTTPException: 评审失败时抛出
    """
    try:
        # 调用智能体评审方法，传入开发者数据进行评审
        result = await agent.review(request.developer_data)
        # 评审成功，返回 200 状态码和评审结果
        return ReviewResponse(code=200, message="success", data=result)
    except Exception as e:
        # 评审过程中出现异常，记录错误日志并抛出 HTTP 500 错误
        logger.error(f"评审失败: {e}")
        raise HTTPException(status_code=500, detail=f"评审失败: {str(e)}")
