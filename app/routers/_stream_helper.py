#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
SSE 流式响应辅助模块

从 map_router.py 提取的通用 SSE 生成逻辑，供 agent_router 复用。

Date: 2026-06-23
Author: AI Assistant
"""

import json
import logging
from typing import Any, AsyncGenerator

from fastapi import Request


logger = logging.getLogger(__name__)


async def generate_stream_response(
    agent: Any,
    input_state: Any,
    context: Any,
    session_id: str,
    request: Request,
) -> AsyncGenerator[str, None]:
    """生成 SSE 流式响应。

    参数:
        agent: Agent 实例（需实现 stream 方法）
        input_state: 输入状态（AgentState 或 Command）
        context: AgentContext 实例
        session_id: 会话 ID
        request: FastAPI Request（用于检测客户端断开）

    返回:
        AsyncGenerator[str, None]: SSE 事件流
    """
    from app.core.agent.AgentConfig import ExecuteConfig

    execute_config = ExecuteConfig(
        configurable={"thread_id": session_id},
        recursion_limit=25,
    )

    try:
        async for chunk in agent.stream(
            input_state,
            context=context,
            config=execute_config,
            stream_mode=["updates", "custom", "messages"],
        ):
            if await request.is_disconnected():
                logger.info("Client disconnected, stopping stream for session %s", session_id)
                break

            if isinstance(chunk, tuple) and len(chunk) == 2:
                mode, data = chunk
                event_type = _map_mode_to_event_type(mode, data)
                yield f"data: {json.dumps({'type': event_type, 'mode': mode, 'data': _serialize(data)}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'update', 'data': _serialize(chunk)}, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'end'})}\n\n"
    except Exception as e:
        logger.exception("Stream error for session %s: %s", session_id, e)
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"


def _map_mode_to_event_type(mode: str, data: Any) -> str:
    """将 LangGraph stream mode 映射为 SSE 事件类型。

    参数:
        mode: stream_mode 名称（updates / custom / messages）
        data: 该模式对应的数据块

    返回:
        str: SSE 事件类型（interrupt / update / custom / message）
    """
    if mode == "updates":
        if isinstance(data, dict) and "__interrupt__" in data:
            return "interrupt"
        return "update"
    elif mode == "custom":
        return "custom"
    elif mode == "messages":
        return "message"
    return "update"


def _serialize(data: Any) -> Any:
    """将数据序列化为 JSON 兼容格式。

    参数:
        data: 待序列化的数据

    返回:
        Any: JSON 可序列化的数据（不可序列化时返回 str 表示）
    """
    try:
        json.dumps(data, ensure_ascii=False)
        return data
    except (TypeError, ValueError):
        return str(data)
