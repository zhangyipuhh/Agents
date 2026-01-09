#!/usr/bin/python
# -*- coding:utf-8 -*-
# File: agent_router.py
# Date: 2026/1/9
# Description: 定义Agent配置相关的API路由，用于创建、查询、编辑和删除Agent配置

import json
from pydantic import BaseModel
from app.agents import MainAgent
from fastapi import (
    APIRouter
)
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
from langchain.messages import HumanMessage, AIMessage, ToolMessage


# 创建请求模型
class AgentRequest(BaseModel):
    message: str

# 创建API路由实例，设置前缀和标签
router = APIRouter(prefix='/api/agent', tags=['Agent create'])


async def generate_response(request: AgentRequest) -> AsyncGenerator[str, None]:
    """生成流式响应的异步生成器
    
    Args:
        request (AgentRequest): 包含用户输入的请求对象
        
    Yields:
        str: SSE格式的响应数据，直接传递event对象
    """
    try:
        inputs = {
            "messages": [HumanMessage(content=request.message)]
        }
        main_agent = MainAgent()
        agent = main_agent.CreateAgent()
        
        # 使用 astream_events 获取实时更新
        async for event in agent.astream_events(inputs, version="v1"):
            # 直接将event对象转换为JSON并发送给前端
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
        
        # 发送结束信号
        yield "event: end\ndata: {\"type\": \"end\", \"message\": \"会话结束\"}\n\n"
    except Exception as e:
        yield f"event: error\ndata: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"


@router.api_route(path='/chat', methods=['POST'])
async def MainAgentApi(request: AgentRequest):
    """创建Prompt配置并返回流式输出
    
    Args:
        request (AgentRequest): 包含用户输入的消息对象
        
    Returns:
        流式输出 (Server-Sent Events)
    """
    return StreamingResponse(
        generate_response(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )


