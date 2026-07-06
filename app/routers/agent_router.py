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
from pydantic import BaseModel, Field

from app.core.database import DatabasePool
from app.shared.utils.agent.agent_config_service import (
    AgentConfigService,
    AgentNotFoundError,
)
from app.routers._stream_helper import generate_stream_response
from app.core.tools._stop_signal import trigger_abort


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
        context_overrides: 上下文字段覆盖；作为通用通道注入到目标 agent 的
            ``context_class(**overrides)``，供任意子智能体的 context 扩展字段使用
            （如 map_agent 的 ``geometry_data``、audit_document_agent 的 ``audit_root``）。
            值语义：
              - 非空 dict/list/str/None（保留）→ 透传到 service.build_agent_instance
              - 空值（None / "" / [] / {}）→ 由 router 自动过滤，避免覆盖 agent 默认值
            注：本字段是**通用字段通道**，不针对具体 agent 硬编码键名。
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

    # 按用户 allowed_agents 校验目标智能体访问权限
    if agent_name and agent_name != "default":
        allowed_agents = getattr(request.state, 'allowed_agents', [])
        if agent_name not in allowed_agents:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"无权使用智能体 '{agent_name}'"
            )

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
        # 过滤 context_overrides 中的空值键（None / "" / [] / {}），
        # 避免覆盖 agent context_class 字段默认值（如 MapAgentContext.geometry_data = {}）。
        # 设计为通用机制，不针对任何具体 agent 或字段硬编码键名 —— 任意子智能体的
        # context 扩展字段（如 geometry_data / audit_root / project_id）都能通过 context_overrides
        # 注入；仅当值"实际为空"时才过滤，service 层负责保留字段与关键字参数的最终管控。
        # 注意：仅过滤容器型空值；bool False / 数字 0 不在过滤范围（避免误杀业务字段）。
        _EMPTY_VALUES = (None, "", [], {})
        merged_overrides = {
            k: v for k, v in (chat_request.context_overrides or {}).items()
            if v not in _EMPTY_VALUES
        }

        agent, context_instance, input_state = await service.build_agent_instance(
            agent_name=agent_name,
            session_id=session_id,
            message=chat_request.message,
            context_overrides=merged_overrides,
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
    """列出当前用户有权使用的启用的智能体。

    参数:
        request: FastAPI Request

    返回:
        List[Dict[str, Any]]: 按用户 allowed_agents 过滤后的智能体摘要列表

    说明（2026-07-XX 新增）：
        本端点**不依赖 session_id 隔离**，仅读 ``request.state.allowed_agents``（来自 JWT 注入）。
        因此后端 ``session_auth_middleware`` 把 ``/api/agent/list`` 加入 ``SESSION_WHITELIST_PREFIXES``，
        首次进入页面 / 按需建 session 阶段 localStorage.session_id 为空时仍能正常返回 200。
        注意：``/api/agent/chat`` 仍命中 ``SESSION_REQUIRED_PREFIXES``（``/api/agent/``）保留校验。
    """
    service = _get_service(request)
    agents = await service.list_agents()
    allowed_agents = getattr(request.state, 'allowed_agents', [])
    if not allowed_agents:
        return []
    allowed_set = set(allowed_agents)
    return [a for a in agents if a.get('name') in allowed_set]


@router.post("/{session_id}/abort")
async def abort_session(session_id: str) -> Dict[str, str]:
    """
    主动中止指定 session 的流式响应（2026-07-06 新增）。

    核心机制：
    - 前端调此端点后，trigger_abort(session_id) 设置 abort_event
    - 工具函数（sandbox / explore）下次 is_set() 检查时感知，主动构造
      ToolMessage 返回（stopped_by_user 分支）→ 避免 orphan tool_calls
    - 后端 _stream_helper 的延迟中断机制继续生效，等 tools 节点完成
    - LangGraph 正常推进 → yield tools update + end 事件 → SSE 自然关闭

    Args:
        session_id: 会话 ID（即 thread_id）

    Returns:
        Dict[str, str]: 包含 status 与 session_id 字段
            - status="aborted": 找到 abort event 并 set
            - status="not_found": session 未注册（可能未启动或已结束），调用方可忽略

    设计要点：
    - 永远 idempotent：多次调用或对未注册 session 都不抛错
    - 不依赖 SSE 连接状态：abort_event 走全局 dict，与 reader 无关
    - 不阻塞：仅 set event，毫秒级返回
    """
    success = trigger_abort(session_id)
    if success:
        logger.info(
            f"[abort] session_id={session_id} 收到主动 abort 请求，abort_event 已 set"
        )
        return {"status": "aborted", "session_id": session_id}
    logger.info(
        f"[abort] session_id={session_id} 收到 abort 请求但 session 未注册（可能已结束），忽略"
    )
    return {"status": "not_found", "session_id": session_id}


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


# ============================================================================
# 2026-07-02 新增：AI 回复的赞/踩反馈入库
# 路由前缀 /api/agent + /message-feedback = /api/agent/message-feedback
# 该接口为本次新增的**唯一**新增端点；/chat、/list、/{name}/agents-md 保持原样
# ============================================================================


class MessageFeedbackRequest(BaseModel):
    """AI 回复反馈（赞/踩）的请求体。

    Attributes:
        session_id: 会话 ID
        message_id: 前端消息 ID（与 ChatArea 中 message.id 对齐）
        feedback_type: 'like'（赞）或 'dislike'（踩）
        problem_type: 踩时的问题类型，事实错误 / 逻辑不通 / 答非所问 / 其他；赞/不填写原因时为 None
        problem_description: 踩时用户填写的"问题描述"
        expected_answer: 踩时用户填写的"期望的样子"
        message_content: 消息内容快照（便于回溯上下文）
        ai_reply: AI 回复内容快照
        agent_name: 当前绑定的 Agent 名称
    """

    session_id: str
    message_id: str
    feedback_type: str
    problem_type: Optional[str] = None
    problem_description: Optional[str] = None
    expected_answer: Optional[str] = None
    message_content: Optional[str] = None
    ai_reply: Optional[str] = None
    agent_name: Optional[str] = None


@router.post("/message-feedback", status_code=status.HTTP_201_CREATED)
async def post_message_feedback(
    request: Request, payload: MessageFeedbackRequest
) -> Dict[str, Any]:
    """提交 AI 回复的赞/踩反馈。

    2026-07-02 新增接口：
      * 赞（feedback_type='like'）直接入库，不要求任何附加内容
      * 踩（feedback_type='dislike'）携带 problem_type / problem_description / expected_answer
      * 同一用户对同一条 message_id 已有反馈时，更新为最新反馈，保证 like/dislike 互斥
      * 数据库模式未启用（`AUTH_STORAGE_MODE=memory`）时返回 503
      * 非法 feedback_type 返回 400

    参数:
        request: FastAPI Request（用于获取当前 user_id 与 User-Agent）
        payload: MessageFeedbackRequest 请求体

    返回:
        Dict[str, Any]: ``{"id": 新记录 ID, "created_at": 入库时间 ISO 字符串}``

    异常:
        HTTPException: 未登录 401 / 非法 feedback_type 400 / 库模式关闭 503 / DB 异常 500
    """
    # 1) 当前用户必须已登录（auth_middleware 已注入 request.state.user_id）
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录，无法提交反馈",
        )

    # 2) feedback_type 合法性校验（CHECK 约束是兜底，这里给前端友好错误）
    if payload.feedback_type not in ("like", "dislike"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="feedback_type 必须是 like 或 dislike",
        )

    # 3) 数据库模式未启用 → 503
    if not DatabasePool.is_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="反馈功能仅在数据库模式下可用",
        )

    # 4) 写入 message_feedback 表（使用 upsert，保证同一用户同一条消息只有一种反馈）
    user_agent = request.headers.get("user-agent", "")[:255] or None
    try:
        row = await DatabasePool.fetchrow(
            """
            INSERT INTO message_feedback (
                user_id, session_id, message_id, feedback_type,
                problem_type, problem_description, expected_answer,
                message_content, ai_reply, agent_name, user_agent
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (user_id, session_id, message_id) DO UPDATE SET
                feedback_type = EXCLUDED.feedback_type,
                problem_type = EXCLUDED.problem_type,
                problem_description = EXCLUDED.problem_description,
                expected_answer = EXCLUDED.expected_answer,
                message_content = EXCLUDED.message_content,
                ai_reply = EXCLUDED.ai_reply,
                agent_name = EXCLUDED.agent_name,
                user_agent = EXCLUDED.user_agent,
                created_at = NOW()
            RETURNING id, created_at
            """,
            user_id,
            payload.session_id,
            payload.message_id,
            payload.feedback_type,
            payload.problem_type,
            payload.problem_description,
            payload.expected_answer,
            payload.message_content,
            payload.ai_reply,
            payload.agent_name,
            user_agent,
        )
    except Exception as e:
        logger.exception("写入 message_feedback 失败: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"反馈入库失败: {e}",
        )

    created_at = row["created_at"]
    return {
        "id": row["id"],
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
    }
