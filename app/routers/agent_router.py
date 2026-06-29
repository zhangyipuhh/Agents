#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
统一 Agent Router 模块

提供 /api/agent/chat 统一聊天接口、/api/agent/list 智能体列表、
/api/agent/{name}/agents-md 获取 AGENTS.md 内容。

Date: 2026-06-23
Author: AI Assistant
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.shared.utils.agent.agent_config_service import (
    AgentConfigService,
    AgentNotFoundError,
)
from app.routers._stream_helper import generate_stream_response


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["Agent"])


class ChatRequest(BaseModel):
    """统一聊天请求体。

    注意：attachments 字段暂未实现，预留供后续版本使用。

    Attributes:
        message: 用户输入文本
        session_id: 会话 ID（缺省时使用 "default"）
        agent_name: 目标智能体名称（默认 map_agent）
        attachments: 附件列表（暂未实现，预留字段）
        resume: HITL 恢复参数（从中断处恢复执行时传入）
        context_overrides: 上下文字段覆盖（注入到 context_class 构造参数，
            其中的保留字段如 session_id / store_id 会被自动过滤）
    """
    message: str
    session_id: Optional[str] = None
    agent_name: Optional[str] = None
    attachments: List[Any] = []
    resume: Optional[Dict[str, Any]] = None
    context_overrides: Dict[str, Any] = {}


def _get_service(request: Request) -> AgentConfigService:
    """从 app.state 获取 AgentConfigService。

    参数:
        request: FastAPI Request 对象

    返回:
        AgentConfigService: 服务实例

    异常:
        HTTPException: 服务未初始化时抛出 500
    """
    service = getattr(request.app.state, "agent_config_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AgentConfigService not initialized",
        )
    return service


@router.post("/chat")
async def chat(request: Request, chat_request: ChatRequest) -> StreamingResponse:
    """统一智能体聊天接口。

    2026-06-29 重构：Agent 构造流程下沉到
    AgentConfigService.build_agent_instance()，router 仅保留 HTTP 适配层职责
    （参数提取、错误转换、SSE 响应包装、session.agent_type 自动绑定）。

    参数:
        request: FastAPI Request（用于服务获取与断开检测）
        chat_request: 聊天请求体

    返回:
        StreamingResponse: SSE 流式响应

    异常:
        HTTPException: agent 不存在时抛出 404；Agent 初始化失败时抛出 500
    """
    service = _get_service(request)
    session_id = chat_request.session_id or "default"
    agent_name = chat_request.agent_name

    # 2026-06-26 新增：若当前 session 尚未绑定非 default 智能体，且请求传入了有效的 agent_name，
    # 则将 agent_type + agent_display_name 持久化到 session（内存 + 数据库）。
    # 此段属于 HTTP 适配层职责（响应客户端首次选 agent 的语义），保留在 router 层。
    if agent_name and agent_name != "default":
        from app.shared.utils.auth.session_db import SessionDB
        session = await SessionDB.get_session(session_id)
        if session and session.get("agent_type", "default") in ("default", "", None):
            try:
                preview_config = await service.get_agent_config(agent_name)
                display_name = preview_config.display_name or agent_name
            except AgentNotFoundError:
                display_name = agent_name
            await SessionDB.update_session_agent(session_id, agent_name, display_name)

    # 统一构造入口（封装取配置 → 构造 context/state → AgentConfig → Agent.__ainit__）
    try:
        agent, context_instance, input_state = await service.build_agent_instance(
            agent_name=agent_name,
            session_id=session_id,
            message=chat_request.message,
            context_overrides=chat_request.context_overrides,
            resume=chat_request.resume,
        )
    except AgentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Agent initialization failed for %s: %s",
            agent_name or "default", e,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent initialization failed: {str(e)}",
        )

    return StreamingResponse(
        generate_stream_response(agent, input_state, context_instance, session_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/list")
async def list_agents(request: Request) -> List[Dict[str, Any]]:
    """列出所有启用的智能体。

    参数:
        request: FastAPI Request

    返回:
        List[Dict[str, Any]]: 智能体摘要列表
    """
    service = _get_service(request)
    return await service.list_agents()


@router.get("/{agent_name}/agents-md")
async def get_agents_md(request: Request, agent_name: str) -> Dict[str, str]:
    """获取指定 agent 的 AGENTS.md 内容。

    参数:
        request: FastAPI Request
        agent_name: 智能体名称

    返回:
        Dict[str, str]: 包含 content 字段的字典（system_prompt 内容）

    异常:
        HTTPException: agent 不存在时抛出 404
    """
    service = _get_service(request)
    try:
        config = await service.get_agent_config(agent_name)
    except AgentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return {"content": config.system_prompt}
