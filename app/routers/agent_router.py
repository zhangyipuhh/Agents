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
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from app.shared.utils.agent.agent_config_service import (
    AgentConfigService,
    AgentNotFoundError,
)
from app.shared.utils.agent.dynamic_schema import RESERVED_CONTEXT_FIELDS
from app.shared.utils.memory import get_async_checkpointer
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

    参数:
        request: FastAPI Request（用于服务获取与断开检测）
        chat_request: 聊天请求体

    返回:
        StreamingResponse: SSE 流式响应

    异常:
        HTTPException: agent 不存在时抛出 404；Agent 初始化失败时抛出 500
    """
    service = _get_service(request)

    try:
        config = await service.get_agent_config(chat_request.agent_name)
    except AgentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    # 过滤 context_overrides 中的保留字段，避免与显式传入的 session_id 等
    # 关键字参数冲突（TypeError: got multiple values for keyword argument）
    safe_overrides = {
        k: v for k, v in chat_request.context_overrides.items()
        if k not in RESERVED_CONTEXT_FIELDS
    }
    # 2026-06-24 修复：state_class / context_class 是 _TypedDictWithDefaults 包装器，
    # __call__ 时会自动补全基类保留字段默认值（error_limit=5 / limit=25 /
    # agent_name=None / session_id="default" / store_id="default" / image_ids=[] 等）
    # 以及 state_schema / context_schema 中定义的扩展字段默认值，调用方只需显式
    # 传入必需字段（messages / session_id 等），无需重复传入保留字段。
    # 完整逻辑见 app/shared/utils/agent/dynamic_schema.py:_BASE_STATE_DEFAULTS /
    # _BASE_CONTEXT_DEFAULTS，以及 build_agent_state / build_agent_context。
    context_instance = config.context_class(
        session_id=chat_request.session_id or "default",
        **safe_overrides,
    )

    if chat_request.resume:
        input_state = Command(resume=chat_request.resume)
    else:
        state_class = config.state_class
        input_state = state_class(messages=[HumanMessage(content=chat_request.message)])

    try:
        from app.core.agent.agent import Agent
        from app.core.agent.AgentConfig import AgentConfig

        # 获取全局异步 checkpointer，支持 resume 与多轮对话状态持久化
        checkpointer = await get_async_checkpointer()
        # 2026-06-24 重构：把 config_schema 中 AgentConfig 字段覆盖（如 temperature /
        # model_name / max_tokens 等）解包注入 AgentConfig 构造器。未在 schema 中声明的
        # 字段保留 AgentConfig 默认值（来自 LLM_CONFIG / 环境变量），向后兼容。
        # 保留字段（state_class / context_class / checkpointer / store）已由
        # dynamic_schema.parse_config_schema 在 RESERVED_CONFIG_FIELDS 阶段过滤，
        # 不会出现在 agent_config_overrides 中。
        agent_config_overrides = config.agent_config_overrides or {}
        agent_config = AgentConfig(
            name=config.name,
            system_prompt=config.system_prompt,
            state_class=config.state_class,
            context_class=config.context_class,
            checkpointer=checkpointer,
            tools=config.tools,  # 从 UnifiedAgentConfig 注入工具列表（由 AgentConfigService 从 DB + MCP registry 加载）
            **agent_config_overrides,
        )
        agent = Agent(agent_config)
        await agent.__ainit__()
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Agent initialization failed for %s: %s", chat_request.agent_name or "default", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent initialization failed: {str(e)}",
        )

    session_id = chat_request.session_id or "default"

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
