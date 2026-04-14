#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
地图智能体路由模块

本模块定义了地图智能体相关的 API 路由。
主要功能包括：
- 流式聊天对话服务：与地图AI助手进行多轮对话，支持实时流式输出

Date: 2026-04-14
Author: AI Assistant
"""

import logging
import json
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator, Optional
from pydantic import BaseModel

from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from langchain_core.messages import ToolMessage

from app.features.map_agent.MapAgent import MapAgent

logger = logging.getLogger(__name__)

# 初始化 MemorySaver 和 InMemoryStore
_checkpointer = MemorySaver()
store = InMemoryStore()
store_id = "map_agent_store"

# 创建 API 路由实例
router = APIRouter(prefix='/api/map', tags=['Map Agent'])

# 初始化 MapAgent 实例
map_agent = MapAgent(
    checkpointer=_checkpointer,
    store=store,
    store_id=store_id,
)


class ChatRequest(BaseModel):
    """
    聊天请求模型

    定义用户发送给地图智能体的请求数据结构。

    Attributes:
        message (str): 用户输入的消息内容
        session_id (Optional[str]): 会话ID，用于标识和恢复会话状态
    """
    message: str
    session_id: Optional[str] = None


async def generate_stream_response(
    user_input: str,
    session_id: str
) -> AsyncGenerator[str, None]:
    """
    生成流式响应的异步生成器

    此函数负责处理用户请求，通过 MapAgent 生成流式响应。
    使用 stream_mode=["updates", "custom", "messages"] 组合模式，
    实时获取节点状态更新、自定义数据和 LLM token，
    并通过 SSE 格式发送给前端。

    处理流程：
    1. 调用 MapAgent 的 stream 方法，使用组合模式
    2. 根据不同的流式数据类型（updates、custom、messages）进行处理
    3. 将每个数据块转换为 SSE 格式发送给前端
    4. 发送结束信号或错误信息

    Args:
        user_input (str): 用户输入内容
        session_id (str): 会话ID

    Yields:
        str: SSE 格式的响应数据，包含 type 字段和对应的数据
    """
    try:
        # 调用 MapAgent 的 stream 方法，使用组合模式
        async for chunk in map_agent.stream(
            user_input=user_input,
            session_id=session_id,
            stream_mode=["updates", "custom", "messages"]
        ):
            # 处理组合模式的输出
            # chunk 的格式为 (mode, data)
            if isinstance(chunk, tuple) and len(chunk) == 2:
                mode, data = chunk

                if mode == "updates":
                    # 节点状态更新
                    # data 格式: {node_name: {state_updates}}
                    yield f"data: {json.dumps({'type': 'update', 'data': data}, ensure_ascii=False, default=str)}\n\n"

                elif mode == "custom":
                    # 自定义数据
                    # data 格式: 自定义的数据结构
                    yield f"data: {json.dumps({'type': 'custom', 'data': data}, ensure_ascii=False, default=str)}\n\n"

                elif mode == "messages":
                    if isinstance(data, tuple) and len(data) == 2:
                        message_chunk, metadata = data
                        if isinstance(message_chunk, ToolMessage):
                            continue
                        content = getattr(message_chunk, 'content', str(message_chunk))
                        if not content:
                            continue
                        yield f"data: {json.dumps({'type': 'message', 'content': content, 'metadata': metadata}, ensure_ascii=False, default=str)}\n\n"
                    else:
                        # 如果数据格式不符合预期，直接序列化
                        yield f"data: {json.dumps({'type': 'message', 'data': data}, ensure_ascii=False, default=str)}\n\n"
            else:
                # 处理非组合模式的输出（向后兼容）
                yield f"data: {json.dumps({'type': 'unknown', 'data': chunk}, ensure_ascii=False, default=str)}\n\n"

        # 发送结束信号
        yield f"data: {json.dumps({'type': 'end', 'message': '会话结束'}, ensure_ascii=False)}\n\n"

    except Exception as e:
        # 捕获异常并将错误信息转换为 SSE 格式发送给前端
        import traceback
        logger.error(f"[ERROR] generate_stream_response 异常: {e}")
        logger.error(f"[ERROR] 异常堆栈: {traceback.format_exc()}")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"


@router.post('/chat')
async def chat(
    request: Request,
    chat_request: ChatRequest
):
    """
    地图智能体流式聊天接口

    与地图AI助手进行对话，支持多轮对话和地图操作。
    使用 SSE (Server-Sent Events) 协议实时返回 Agent 的思考过程和响应结果。

    工作流程：
    1. 接收 POST 请求，解析为 ChatRequest 对象
    2. 获取 session_id，优先使用请求体中的，否则从 request.state 获取
    3. 调用 generate_stream_response 生成流式响应
    4. 通过 StreamingResponse 以 SSE 格式返回数据
    5. 设置适当的响应头以确保流式传输正常工作

    Args:
        request: FastAPI 请求对象
        chat_request: 聊天请求，包含用户消息和可选的会话ID

    Returns:
        StreamingResponse: 流式响应对象，使用 text/event-stream 媒体类型
    """
    try:
        # 获取 session_id，优先使用请求体中的，否则从 request.state 获取
        session_id = chat_request.session_id or getattr(request.state, "session_id", "default")

        logger.debug(f"[DEBUG] chat 请求: message={chat_request.message}, session_id={session_id}")

        # 返回流式响应
        return StreamingResponse(
            generate_stream_response(
                user_input=chat_request.message,
                session_id=session_id
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # 禁用 nginx 缓冲
            }
        )

    except Exception as e:
        import traceback
        logger.error(f"[ERROR] chat 异常: {e}")
        logger.error(f"[ERROR] 异常堆栈: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"对话处理失败：{str(e)}")
