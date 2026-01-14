#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Agent路由模块

本模块定义了Agent配置相关的API路由，用于处理用户与AI Agent的交互。
主要功能包括：
- 接收用户消息请求
- 通过MainAgent处理请求并生成流式响应
- 使用Server-Sent Events (SSE)协议实时返回Agent的思考过程和响应结果

Date: 2026/1/9 12:07
Author: 张镒谱
"""
import json
from pydantic import BaseModel
from app.agents import MainAgent
from fastapi import (
    APIRouter
)
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
from langchain.messages import HumanMessage, AIMessage, ToolMessage


class AgentRequest(BaseModel):
    """
    Agent请求模型
    
    定义用户发送给Agent的请求数据结构。
    
    Attributes:
        message (str): 用户输入的消息内容，将作为HumanMessage传递给Agent
    """
    message: str

# 创建API路由实例，设置前缀和标签
# prefix='/api/agent': 所有路由路径将以/api/agent开头
# tags=['Agent create']: 用于API文档分组，便于在Swagger UI中查看
router = APIRouter(prefix='/api/agent', tags=['Agent create'])


async def generate_response(request: AgentRequest) -> AsyncGenerator[str, None]:
    """
    生成流式响应的异步生成器
    
    此函数负责处理用户请求，通过MainAgent生成流式响应。
    使用LangChain的astream_events方法实时获取Agent的执行事件，
    包括思考过程、工具调用、最终回答等，并通过SSE格式发送给前端。
    
    处理流程：
    1. 将用户消息转换为HumanMessage格式
    2. 创建MainAgent实例并初始化Agent
    3. 使用astream_events流式获取Agent执行过程中的所有事件
    4. 将每个事件转换为SSE格式发送给前端
    5. 发送结束信号或错误信息
    
    Args:
        request (AgentRequest): 包含用户输入的请求对象
        
    Yields:
        str: SSE格式的响应数据，包含event对象、结束信号或错误信息
    """
    try:
        # 构建输入消息列表，将用户消息转换为HumanMessage对象
        inputs = {
            "messages": [HumanMessage(content=request.message)]
        }
        
        # 创建MainAgent实例
        main_agent = MainAgent()
        
        # 创建Agent实例，该实例将处理用户请求
        agent = main_agent.CreateAgent()
        
        # 使用 astream_events 获取实时更新
        # version="v1": 指定事件流的版本
        # 循环遍历Agent执行过程中的所有事件
        async for event in agent.astream_events(inputs, version="v1", subgraphs=True):
            # 直接将event对象转换为JSON并发送给前端
            # ensure_ascii=False: 支持中文字符
            # default=str: 处理无法序列化的对象
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
        
        # 发送结束信号，通知前端会话已完成
        yield "event: end\ndata: {\"type\": \"end\", \"message\": \"会话结束\"}\n\n"
    except Exception as e:
        # 捕获异常并将错误信息转换为SSE格式发送给前端
        yield f"event: error\ndata: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"


@router.api_route(path='/chat', methods=['POST'])
async def MainAgentApi(request: AgentRequest):
    """
    Agent聊天API端点
    
    处理用户发送的聊天消息，返回流式响应。
    使用POST方法接收用户消息，通过generate_response函数生成SSE流式输出，
    实时返回Agent的思考过程和最终回答。
    
    工作流程：
    1. 接收POST请求，解析为AgentRequest对象
    2. 调用generate_response生成流式响应
    3. 通过StreamingResponse以SSE格式返回数据
    4. 设置适当的响应头以确保流式传输正常工作
    
    Args:
        request (AgentRequest): 包含用户消息的请求对象
        
    Returns:
        StreamingResponse: 流式响应对象，使用text/event-stream媒体类型
    """
    return StreamingResponse(
        # 传入生成器函数，该函数将产生SSE格式的数据流
        generate_response(request),
        # 设置媒体类型为text/event-stream，这是SSE的标准媒体类型
        media_type="text/event-stream",
        # 设置响应头，禁用缓存并保持连接
        headers={
            # 禁用缓存，确保客户端接收到实时数据
            "Cache-Control": "no-cache",
            # 保持连接，支持长连接传输
            "Connection": "keep-alive"
        }
    )


