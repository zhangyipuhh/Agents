#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
会话管理路由模块

本模块定义了会话管理相关的API路由。
主要功能包括：
- 生成新会话
- 删除会话
- 获取会话列表
- 获取会话详情
- 更新会话标题
- 获取会话附件列表

Date: 2026/2/6
Author: 张镒谱
"""
import uuid
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from pydantic import BaseModel
from typing import Optional
from app.shared.utils.files.fileTransfer import FileTransfer
from app.shared.utils.Session.SessionCache import session_cache
from app.shared.utils.auth.session_db import SessionDB
from app.shared.utils.files.attachment_db import AttachmentDB
from app.shared.utils.memory.conversation_db import ConversationDB
from app.shared.utils.memory.checkpoint_history import CheckpointHistoryService
from app.shared.utils.memory.checkpoint import get_async_checkpointer
from app.shared.utils.auth.Safety import require_admin


class SessionCreateResponse(BaseModel):
    """
    会话创建响应模型

    定义创建会话操作后的响应数据结构。

    Attributes:
        session_id (str): 生成的会话ID
        message (str): 操作结果消息
    """
    session_id: str
    message: str


class SessionDeleteResponse(BaseModel):
    """
    会话删除响应模型

    定义删除会话操作后的响应数据结构。

    Attributes:
        success (bool): 删除是否成功
        message (str): 操作结果消息
    """
    success: bool
    message: str


class SessionTitleUpdateRequest(BaseModel):
    """
    会话标题更新请求模型

    Attributes:
        title (str): 新标题
    """
    title: str


# 创建文件传输工具实例
file_transfer = FileTransfer()

# 创建API路由实例，设置前缀和标签
router = APIRouter(prefix='/api/session', tags=['Session Management'])


@router.post('/create', response_model=SessionCreateResponse)
async def create_session(request: Request):
    """
    创建新会话API端点

    生成一个新的会话ID，用于隔离不同用户的文件。
    需要提供有效的 JWT token。
    """
    try:
        username = request.state.username
        if not username:
            raise HTTPException(status_code=401, detail="未认证")

        from app.shared.utils.auth.user_db import UserDB

        user = await UserDB.get_user_by_username(username)
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在")

        session_id = str(uuid.uuid4())
        session_dir = file_transfer._get_session_dir(session_id)

        # 添加 session（传入 user_id）
        await session_cache.add_session(session_id, username, user['id'])

        return SessionCreateResponse(
            session_id=session_id,
            message="会话创建成功"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建会话失败: {str(e)}")


@router.delete('/delete/{session_id}', response_model=SessionDeleteResponse)
async def delete_session(session_id: str, request: Request):
    """
    删除会话API端点

    删除指定会话的整个目录及其所有文件，同时清理关联的对话记录和附件记录。
    需要提供有效的 JWT token。

    Args:
        session_id (str): 要删除的会话ID
        request (Request): FastAPI 请求对象

    Returns:
        SessionDeleteResponse: 包含删除结果的响应对象

    Raises:
        HTTPException: 当删除过程中发生错误时抛出500错误
    """
    try:
        username = request.state.username

        if not username:
            raise HTTPException(status_code=401, detail="未认证")

        # 验证 session_id 是否属于该用户
        is_valid = await session_cache.verify_session(session_id, username)

        if not is_valid:
            raise HTTPException(status_code=403, detail="无权删除该会话")

        # 删除关联的对话记录
        await ConversationDB.delete_session_records(session_id)

        # 删除关联的附件记录
        await AttachmentDB.delete_session_attachments(session_id)

        # 删除会话目录
        success = await file_transfer.delete_session(session_id)

        # 删除 LangGraph Checkpoint 中的对话状态
        # 2026-06-16 改造：先收集主 thread 下所有子智能体 thread_id，逐个清理后再删主 thread
        try:
            checkpointer = await get_async_checkpointer()
            sub_thread_ids = await CheckpointHistoryService.collect_subagent_thread_ids_for_cleanup(
                checkpointer=checkpointer,
                session_id=session_id,
            )
            for sub_tid in sub_thread_ids:
                try:
                    await checkpointer.adelete_thread(sub_tid)
                except Exception as e_sub:
                    import logging
                    logging.getLogger(__name__).warning(
                        f"删除子智能体 checkpoint 失败: sub_thread_id={sub_tid}, error={e_sub}"
                    )
            await checkpointer.adelete_thread(session_id)
        except Exception as e:
            # 记录日志但不阻断删除流程，因为 checkpoint 可能不存在
            import logging
            logging.getLogger(__name__).warning(
                f"删除 checkpoint 失败: session_id={session_id}, error={e}"
            )

        # 从缓存中删除 session_id
        await session_cache.delete_session(session_id)

        return SessionDeleteResponse(
            success=success,
            message="会话删除成功" if success else "会话不存在"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除会话失败: {str(e)}")


@router.get('/list')
async def list_sessions(request: Request):
    """
    获取当前用户的会话列表

    返回用户的所有会话，按最后活跃时间倒序排列。

    Returns:
        list: 会话列表，每项包含 session_id、title、last_active_at、status、agent_type、created_at
    """
    try:
        username = request.state.username
        if not username:
            raise HTTPException(status_code=401, detail="未认证")

        from app.shared.utils.auth.user_db import UserDB
        user = await UserDB.get_user_by_username(username)
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在")

        sessions = await SessionDB.get_user_sessions(user['id'])
        return {"sessions": sessions}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取会话列表失败: {str(e)}")


@router.get('/{session_id}/detail')
async def get_session_detail(session_id: str, request: Request):
    """
    获取会话详情（含附件列表）

    Args:
        session_id (str): 会话 ID

    Returns:
        dict: 会话详情，包含基本信息和附件列表
    """
    try:
        username = request.state.username
        if not username:
            raise HTTPException(status_code=401, detail="未认证")

        # 验证 session 归属
        is_valid = await session_cache.verify_session(session_id, username)
        if not is_valid:
            raise HTTPException(status_code=403, detail="无权访问该会话")

        detail = await SessionDB.get_session_detail(session_id)
        if not detail:
            raise HTTPException(status_code=404, detail="会话不存在")

        return detail
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取会话详情失败: {str(e)}")


@router.put('/{session_id}/title')
async def update_session_title(session_id: str, request: Request, body: SessionTitleUpdateRequest):
    """
    更新会话标题

    Args:
        session_id (str): 会话 ID
        body (SessionTitleUpdateRequest): 包含新标题的请求体

    Returns:
        dict: 更新结果
    """
    try:
        username = request.state.username
        if not username:
            raise HTTPException(status_code=401, detail="未认证")

        # 验证 session 归属
        is_valid = await session_cache.verify_session(session_id, username)
        if not is_valid:
            raise HTTPException(status_code=403, detail="无权修改该会话")

        await SessionDB.update_session_title(session_id, body.title)
        return {"success": True, "message": "标题更新成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新标题失败: {str(e)}")


@router.get('/{session_id}/attachments')
async def get_session_attachments(session_id: str, request: Request):
    """
    获取会话附件列表

    Args:
        session_id (str): 会话 ID

    Returns:
        dict: 附件列表
    """
    try:
        username = request.state.username
        if not username:
            raise HTTPException(status_code=401, detail="未认证")

        # 验证 session 归属
        is_valid = await session_cache.verify_session(session_id, username)
        if not is_valid:
            raise HTTPException(status_code=403, detail="无权访问该会话")

        attachments = await AttachmentDB.get_session_attachments(session_id)
        return {"attachments": attachments}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取附件列表失败: {str(e)}")


@router.get('/{session_id}/messages')
async def get_session_messages(
    session_id: str,
    limit: Optional[int] = 50,
    request: Request = None
):
    """
    获取会话的历史消息（从 LangGraph Checkpoint）

    从 LangGraph 的 Checkpoint 中恢复指定会话的对话历史，
    用于前端切换会话时还原聊天界面。

    2026-06-16 改造：
        - 在返回的 messages 列表中，**按时序**合并子智能体（sandbox / explore 等）消息流
        - 子智能体消息以 `type: "subagent"` 元素出现，紧跟在其触发的 AIMessage 之后
        - 子智能体消息流来自全局 checkpointer，thread_id == 父 LLM tool_call_id
        - 老客户端忽略未知 type/字段，前端渐进升级支持渲染
        - 返回的 messages 顺序严格：M1(user) → M2(ai 含 tool_call=sandbox) →
          [subagent: call_xxx 完整轨迹] → M3(user) → M4(ai) → ...

    Args:
        session_id: 会话 ID
        limit: 返回消息数量限制，默认 50 条，设为 0 表示返回所有（按合并后总数限制）

    Returns:
        dict: 包含 messages 列表和元数据
        {
            "session_id": str,
            "messages": [
                {"id": ..., "type": "user"/"ai"/"tool", "role": ..., "content": ...},
                {"type": "subagent", "thread_id": ..., "tool": ...,
                 "parent_message_id": ..., "messages": [...]},
                ...
            ],
            "total": int  # 合并后的总消息数
        }
    """
    try:
        username = request.state.username
        if not username:
            raise HTTPException(status_code=401, detail="未认证")

        # 验证 session 归属
        is_valid = await session_cache.verify_session(session_id, username)
        if not is_valid:
            raise HTTPException(status_code=403, detail="无权访问该会话")

        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"[History] get_session_messages session_id={session_id}")

        # 统一从 checkpointer 获取主消息流（确保子智能体反查基于同一 checkpointer 实例）
        checkpointer = await get_async_checkpointer()

        # 优先尝试通过 graph.aget_state() 获取（更可靠，且能拿到原始 LangChain 消息对象）
        raw_messages_data: list = []
        use_graph_state = False
        try:
            from app.features.map_agent.router.map_router import get_map_agent
            map_agent = await get_map_agent()
            agent = await map_agent.get_agent()
            graph_config = {"configurable": {"thread_id": session_id}}
            state = await agent.graph.aget_state(graph_config)
            values = getattr(state, "values", None) or {}
            raw_messages_data = values.get("messages", []) if isinstance(values, dict) else []
            use_graph_state = True

            logger.warning(
                f"[History] graph.get_state() succeeded, raw_messages_count={len(raw_messages_data)}"
            )
        except Exception as e:
            logger.warning(f"[History] graph.get_state() 失败，回退到 checkpointer.aget: {e}")
            try:
                config = {"configurable": {"thread_id": session_id}}
                raw_state = await checkpointer.aget(config)
                if raw_state:
                    channel_values = raw_state.get("channel_values", {}) if hasattr(raw_state, "get") else {}
                    raw_messages_data = channel_values.get("messages", []) if isinstance(channel_values, dict) else []
            except Exception as e2:
                logger.warning(f"[History] checkpointer.aget() 失败: {e2}")
                raw_messages_data = []

        if not raw_messages_data:
            return {
                "session_id": session_id,
                "messages": [],
                "total": 0,
            }

        # 1) 主消息转换（过滤 tool）
        main_messages: list = []
        for msg in raw_messages_data:
            msg_dict = CheckpointHistoryService._convert_message_to_dict(msg)
            if msg_dict and msg_dict.get("type") != "tool":
                main_messages.append(msg_dict)

        # 2) 合并子智能体消息（按时序）
        #    仅在 use_graph_state 路径下 raw_messages_data 含 LangChain 对象，
        #    回退路径下 raw_messages_data 也来自 checkpointer 转换，对象可能是 dict，
        #    merge_main_and_subagent_messages 内部用 isinstance(AIMessage) 防御，dict 会被忽略。
        merged_messages = await CheckpointHistoryService.merge_main_and_subagent_messages(
            checkpointer=checkpointer,
            main_messages=main_messages,
            raw_main_messages=raw_messages_data if use_graph_state else None,
            subagent_limit=None,
        )

        # 3) 应用 limit（基于合并后总数）
        if limit and limit > 0:
            merged_messages = merged_messages[-limit:]

        logger.warning(
            f"[History] 返回 messages 总数={len(merged_messages)} "
            f"(main={len(main_messages)}, use_graph_state={use_graph_state})"
        )

        return {
            "session_id": session_id,
            "messages": merged_messages,
            "total": len(merged_messages),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取历史消息失败: {str(e)}")


@router.delete('/admin/{session_id}', dependencies=[Depends(require_admin)])
async def admin_delete_session(session_id: str, request: Request):
    """
    Admin 强制删除任意会话（踢特定会话）

    不需要验证 session 归属，admin 特权操作。
    执行与普通删除相同的清理逻辑：对话记录、附件、文件目录、checkpoint、缓存。

    Args:
        session_id (str): 要删除的会话ID
        request (Request): FastAPI 请求对象

    Returns:
        SessionDeleteResponse: 删除结果
    """
    from app.shared.utils.auth.audit_log import AuditLog

    try:
        # 删除关联的对话记录
        await ConversationDB.delete_session_records(session_id)

        # 删除关联的附件记录
        await AttachmentDB.delete_session_attachments(session_id)

        # 删除会话目录
        file_transfer = FileTransfer()
        success = await file_transfer.delete_session(session_id)

        # 删除 LangGraph Checkpoint 中的对话状态
        # 2026-06-16 改造：先收集主 thread 下所有子智能体 thread_id，逐个清理后再删主 thread
        try:
            checkpointer = await get_async_checkpointer()
            sub_thread_ids = await CheckpointHistoryService.collect_subagent_thread_ids_for_cleanup(
                checkpointer=checkpointer,
                session_id=session_id,
            )
            for sub_tid in sub_thread_ids:
                try:
                    await checkpointer.adelete_thread(sub_tid)
                except Exception as e_sub:
                    import logging
                    logging.getLogger(__name__).warning(
                        f"删除子智能体 checkpoint 失败: sub_thread_id={sub_tid}, error={e_sub}"
                    )
            await checkpointer.adelete_thread(session_id)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"删除 checkpoint 失败: session_id={session_id}, error={e}"
            )

        # 从缓存中删除 session_id
        await session_cache.delete_session(session_id)

        # 记录审计日志
        admin_username = getattr(request.state, 'username', 'unknown')
        client_ip = request.client.host if request.client else "unknown"
        await AuditLog.write_log(
            action='admin_delete_session',
            username=admin_username,
            detail=f'Admin 删除会话 {session_id}',
            ip_address=client_ip
        )

        return {
            "success": success,
            "message": "会话删除成功" if success else "会话不存在"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除会话失败: {str(e)}")


@router.get('/admin/search', dependencies=[Depends(require_admin)])
async def admin_search_sessions(username: str = Query(..., description="用户名关键字")):
    """
    Admin 按用户名搜索会话

    支持模糊匹配用户名，返回匹配的会话列表。

    Args:
        username (str): 用户名关键字

    Returns:
        dict: 会话列表
    """
    sessions = await SessionDB.search_sessions_by_username(username)
    return {"sessions": sessions}
