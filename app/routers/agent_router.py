#!/usr/bin/python
# -*- coding:utf-8 -*-
# File: agent_router.py
# Date: 2026/1/9
# Description: 定义Agent配置相关的API路由，用于创建、查询、编辑和删除Agent配置

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
    """生成流式响应的异步生成器"""
    try:
        inputs = {
            "messages": [HumanMessage(content=request.message)]
        }
        main_agent = MainAgent()
        agent = main_agent.CreateAgent()
        
        # 使用stream获取实时更新
        for event in agent.stream(inputs, stream_mode="values"):
            if "messages" in event and len(event["messages"]) > 0:
                last_msg = event["messages"][-1]
                
                # 根据消息类型生成不同的响应
                if isinstance(last_msg, AIMessage):
                    # 如果是AI消息，返回内容
                    if last_msg.content:
                        yield f"data: {last_msg.content}\n\n"
                    # 如果有工具调用，返回工具调用信息
                    if last_msg.tool_calls:
                        for tool_call in last_msg.tool_calls:
                            yield f"data: [工具调用] {tool_call['name']}\n\n"
                            if tool_call['args']:
                                yield f"data: 参数: {tool_call['args']}\n\n"
                elif isinstance(last_msg, ToolMessage):
                    # 如果是工具响应，返回工具执行结果
                    yield f"data: [工具结果] {last_msg.content}\n\n"
        
        # 发送结束信号
        yield "data: [会话结束]\n\n"
    except Exception as e:
        yield f"data: 错误: {str(e)}\n\n"


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


