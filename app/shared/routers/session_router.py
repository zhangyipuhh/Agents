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
from fastapi import APIRouter, HTTPException, Request, Depends, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import quote
from app.shared.utils.files.fileTransfer import FileTransfer
from app.shared.utils.files.session_path_manager import register_session_upload_date
from app.shared.utils.Session.SessionCache import session_cache
from app.shared.utils.auth.session_db import SessionDB
from app.shared.utils.files.attachment_db import AttachmentDB
from app.shared.utils.memory.conversation_db import ConversationDB
from app.shared.utils.memory.checkpoint_history import CheckpointHistoryService
from app.shared.utils.memory.checkpoint import get_async_checkpointer
from app.shared.utils.auth.Safety import require_admin
from app.shared.utils.project.project_db import ProjectDB


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


class SessionCreateRequest(BaseModel):
    """会话创建请求体（2026-06-30 新增 project_id）

    Attributes:
        project_id: 关联的项目 ID；None = 不使用文件夹（默认行为）
    """
    project_id: Optional[int] = None


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


class AdminBatchDeleteRequest(BaseModel):
    """
    Admin 批量删除会话请求模型

    Attributes:
        session_ids (List[str]): 要删除的会话 ID 列表
    """
    session_ids: List[str]


class AdminBatchDeleteResponse(BaseModel):
    """
    Admin 批量删除会话响应模型

    Attributes:
        success (bool): 整体是否成功（只要存在成功删除即视为 True）
        deleted_count (int): 成功删除的数量
        total (int): 请求删除的总数量
        failed (List[Dict[str, str]]): 删除失败的会话及原因
    """
    success: bool
    deleted_count: int
    total: int
    failed: List[Dict[str, str]]


# 创建文件传输工具实例
file_transfer = FileTransfer()

# 创建API路由实例，设置前缀和标签
router = APIRouter(prefix='/api/session', tags=['Session Management'])


@router.post('/create', response_model=SessionCreateResponse)
async def create_session(request: Request, body: Optional[SessionCreateRequest] = None):
    """
    创建新会话API端点

    生成一个新的会话ID，用于隔离不同用户的文件。
    需要提供有效的 JWT token。

    2026-06-30 改造：接受可选的 project_id body，将 session 关联到指定项目。
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
        project_id = body.project_id if body else None

        # 注册 session 上传日期索引，确保后续文件上传、沙箱、explore 等工具能定位日期化目录
        # 注意：项目目录不走日期化路径，不受影响
        register_session_upload_date(session_id)

        # 添加 session（传入 user_id 和 project_id）
        await session_cache.add_session(session_id, username, user['id'], project_id=project_id)

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


async def _load_merged_session_messages(session_id: str) -> List[Dict[str, Any]]:
    """
    加载指定会话的完整合并消息（含子智能体）

    复用 graph.get_state() / checkpointer.aget 逻辑，返回已合并的 dict 列表。
    导出与 /messages 端点共享此 helper，避免重复实现。

    Args:
        session_id: 会话 ID

    Returns:
        List[Dict[str, Any]]: 合并后的消息列表
    """
    import logging
    logger = logging.getLogger(__name__)

    checkpointer = await get_async_checkpointer()

    raw_messages_data: list = []
    use_graph_state = False
    try:
        from app.routers.knowledge_router import get_map_agent
        agent = await get_map_agent()
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

    # 1) 主消息转换（过滤 tool）
    main_messages: list = []
    for msg in raw_messages_data:
        msg_dict = CheckpointHistoryService._convert_message_to_dict(msg)
        if msg_dict and msg_dict.get("type") != "tool":
            main_messages.append(msg_dict)

    # 2) 合并子智能体消息（按时序）
    merged_messages = await CheckpointHistoryService.merge_main_and_subagent_messages(
        checkpointer=checkpointer,
        main_messages=main_messages,
        raw_main_messages=raw_messages_data if use_graph_state else None,
        subagent_limit=None,
    )

    return merged_messages


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

        merged_messages = await _load_merged_session_messages(session_id)

        # 应用 limit（基于合并后总数）
        if limit and limit > 0:
            merged_messages = merged_messages[-limit:]

        logger.warning(f"[History] 返回 messages 总数={len(merged_messages)}")

        return {
            "session_id": session_id,
            "messages": merged_messages,
            "total": len(merged_messages),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取历史消息失败: {str(e)}")


def _messages_to_markdown(messages: List[Dict[str, Any]], level: int = 2) -> str:
    """
    将合并后的消息列表递归渲染为 Markdown 文本

    Args:
        messages: 合并后的消息字典列表
        level: 当前标题级别（用于递归子智能体时加深）

    Returns:
        str: Markdown 文本
    """
    lines: List[str] = []
    heading = '#'
    for _ in range(level - 1):
        heading += '#'

    for msg in messages:
        msg_type = msg.get('type')
        if msg_type == 'tool':
            continue

        if msg_type == 'subagent':
            tool = msg.get('tool') or 'subagent'
            meta = msg.get('meta') or {}
            display_name = meta.get('display_name') or tool
            lines.append(f"{heading} 子智能体: {display_name}\n")
            sub_messages = msg.get('messages', [])
            if sub_messages:
                lines.append(_messages_to_markdown(sub_messages, level + 1))
            continue

        if msg_type == 'user':
            role_label = '用户'
        elif msg_type == 'ai':
            role_label = 'Assistant'
        else:
            role_label = msg.get('role') or msg_type or '消息'

        content = msg.get('content') or ''
        if not isinstance(content, str):
            content = str(content)
        lines.append(f"{heading} {role_label}\n\n{content}\n")

    return '\n'.join(lines)


@router.get('/{session_id}/export/markdown')
async def export_session_markdown(session_id: str, request: Request):
    """
    导出会话为 Markdown 文件

    返回当前会话的完整对话（含子智能体轨迹）作为 Markdown 文本，
    浏览器可通过 Content-Disposition 触发下载。

    Args:
        session_id: 会话 ID

    Returns:
        Response: text/markdown 响应，附带下载文件名
    """
    try:
        username = request.state.username
        if not username:
            raise HTTPException(status_code=401, detail="未认证")

        is_valid = await session_cache.verify_session(session_id, username)
        if not is_valid:
            raise HTTPException(status_code=403, detail="无权访问该会话")

        session = await session_cache.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")

        title = session.get('title') or '新对话'
        merged_messages = await _load_merged_session_messages(session_id)
        markdown_body = _messages_to_markdown(merged_messages, level=2)
        markdown = f"# {title}\n\n{markdown_body}"

        filename = f"{title}.md"
        encoded_filename = quote(filename, safe='')
        return Response(
            content=markdown,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出 Markdown 失败: {str(e)}")


async def _delete_session_core(session_id: str, admin_username: str = "unknown", client_ip: str = "unknown") -> bool:
    """
    执行会话数据清理，供 Admin 单条/批量删除复用。

    清理内容包括：对话记录、附件记录、文件目录、LangGraph Checkpoint（含子智能体 thread）、缓存。
    每条删除都会记录审计日志。

    Args:
        session_id (str): 要删除的会话 ID
        admin_username (str): 执行删除的管理员用户名
        client_ip (str): 管理员客户端 IP

    Returns:
        bool: 文件目录删除是否成功（会话是否存在）
    """
    from app.shared.utils.auth.audit_log import AuditLog

    # 删除关联的对话记录
    await ConversationDB.delete_session_records(session_id)

    # 删除关联的附件记录
    await AttachmentDB.delete_session_attachments(session_id)

    # 删除会话目录
    _file_transfer = FileTransfer()
    success = await _file_transfer.delete_session(session_id)

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
    await AuditLog.write_log(
        action='admin_delete_session',
        username=admin_username,
        detail=f'Admin 删除会话 {session_id}',
        ip_address=client_ip
    )

    return success


@router.delete('/admin/batch', dependencies=[Depends(require_admin)])
async def admin_batch_delete_sessions(request: Request, body: AdminBatchDeleteRequest):
    """
    Admin 批量删除会话

    不需要验证 session 归属，admin 特权操作。
    对每个 session_id 执行与单条删除相同的清理逻辑，返回成功/失败统计。

    Args:
        request (Request): FastAPI 请求对象
        body (AdminBatchDeleteRequest): 包含 session_ids 列表的请求体

    Returns:
        AdminBatchDeleteResponse: 批量删除结果
    """
    admin_username = getattr(request.state, 'username', 'unknown')
    client_ip = request.client.host if request.client else "unknown"

    deleted_count = 0
    failed: List[Dict[str, str]] = []

    for session_id in body.session_ids:
        try:
            await _delete_session_core(session_id, admin_username, client_ip)
            deleted_count += 1
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"批量删除会话失败: session_id={session_id}, error={e}"
            )
            failed.append({
                "session_id": session_id,
                "reason": f"删除失败: {str(e)}"
            })

    return {
        "success": deleted_count > 0,
        "deleted_count": deleted_count,
        "total": len(body.session_ids),
        "failed": failed
    }


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
    try:
        admin_username = getattr(request.state, 'username', 'unknown')
        client_ip = request.client.host if request.client else "unknown"
        success = await _delete_session_core(session_id, admin_username, client_ip)
        return {
            "success": success,
            "message": "会话删除成功" if success else "会话不存在"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除会话失败: {str(e)}")


@router.get('/admin/{session_id}/messages', dependencies=[Depends(require_admin)])
async def admin_get_session_messages(session_id: str, limit: Optional[int] = 50):
    """
    Admin 获取任意会话的历史消息

    不需要验证 session 归属，admin 特权操作。
    从 LangGraph Checkpoint 恢复指定会话的对话历史，包含子智能体轨迹。

    Args:
        session_id (str): 会话 ID
        limit (Optional[int]): 返回消息数量限制，默认 50 条，设为 0 表示返回所有

    Returns:
        dict: 包含 messages 列表和元数据
    """
    try:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"[History] admin_get_session_messages session_id={session_id}")

        merged_messages = await _load_merged_session_messages(session_id)

        # 应用 limit（基于合并后总数）
        if limit and limit > 0:
            merged_messages = merged_messages[-limit:]

        logger.warning(f"[History] 返回 messages 总数={len(merged_messages)}")

        return {
            "session_id": session_id,
            "messages": merged_messages,
            "total": len(merged_messages),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取历史消息失败: {str(e)}")


@router.get('/admin/{session_id}/export/markdown', dependencies=[Depends(require_admin)])
async def admin_export_session_markdown(session_id: str):
    """
    Admin 导出任意会话为 Markdown 文件

    不需要验证 session 归属，admin 特权操作。
    返回指定会话的完整对话（含子智能体轨迹）作为 Markdown 文本。

    Args:
        session_id (str): 会话 ID

    Returns:
        Response: text/markdown 响应，附带下载文件名
    """
    try:
        session = await session_cache.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")

        title = session.get('title') or '新对话'
        merged_messages = await _load_merged_session_messages(session_id)
        markdown_body = _messages_to_markdown(merged_messages, level=2)
        markdown = f"# {title}\n\n{markdown_body}"

        filename = f"{title}.md"
        encoded_filename = quote(filename, safe='')
        return Response(
            content=markdown,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出 Markdown 失败: {str(e)}")


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


async def _get_session_project_info(session_id: str) -> Tuple[Optional[int], Optional[str]]:
    """
    获取会话关联的项目信息。

    Args:
        session_id: 会话 ID。

    Returns:
        Tuple[Optional[int], Optional[str]]: (project_id, project_relative_path)。
            未关联项目时返回 (None, None)。
    """
    session = await SessionDB.get_session(session_id)
    if not session:
        return None, None
    project_id = session.get('project_id')
    if not project_id:
        return None, None
    project = ProjectDB._memory_cache.get(project_id)
    if not project and ProjectDB.is_enabled():
        project = await ProjectDB.get_project_by_id(project_id)
        if project:
            with ProjectDB._lock:
                ProjectDB._memory_cache[project_id] = project
    if project:
        return project_id, project.get('relative_path')
    return project_id, None


@router.get('/{session_id}/files/tree')
async def get_session_files_tree(session_id: str, request: Request):
    """
    获取会话文件空间的树形结构。

    返回当前会话/项目对应的原文件目录与解析缓存目录的完整层级结构，
    供前端 FolderTree 组件渲染。

    Args:
        session_id: 会话 ID。

    Returns:
        dict: { tree: {...} }

    Raises:
        HTTPException: 401 未认证 / 403 无权访问 / 500 扫描失败。
    """
    try:
        username = request.state.username
        if not username:
            raise HTTPException(status_code=401, detail="未认证")

        is_valid = await session_cache.verify_session(session_id, username)
        if not is_valid:
            raise HTTPException(status_code=403, detail="无权访问该会话")

        project_id, relative_path = await _get_session_project_info(session_id)
        tree = await file_transfer.build_session_file_tree(
            session_id,
            project_id=project_id,
            project_relative_path=relative_path
        )
        return {"tree": tree}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取会话文件树失败: {str(e)}")


@router.get('/{session_id}/files/preview')
async def preview_session_file(
    session_id: str,
    stored_path: str = Query(..., description="文件存储路径"),
    request: Request = None
):
    """
    预览会话文件空间中的单个文件。

    根据文件扩展名决定 preview_mode：文本/Markdown 直接返回 content；
    Office/PDF/图片返回可下载的 file_url。

    Args:
        session_id: 会话 ID。
        stored_path: 文件存储路径（相对或绝对）。

    Returns:
        dict: 预览数据，包含 path/content/type/preview_mode/file_url/file_name。

    Raises:
        HTTPException: 401 未认证 / 403 无权访问 / 404 文件不存在。
    """
    try:
        username = request.state.username
        if not username:
            raise HTTPException(status_code=401, detail="未认证")

        is_valid = await session_cache.verify_session(session_id, username)
        if not is_valid:
            raise HTTPException(status_code=403, detail="无权访问该会话")

        project_id, relative_path = await _get_session_project_info(session_id)
        file_path = file_transfer.resolve_session_file_path(
            stored_path,
            session_id,
            project_id=project_id,
            project_relative_path=relative_path
        )

        preview_mode = file_transfer._get_preview_mode(file_path)
        file_name = file_path.name
        content = ""
        file_url = ""

        if preview_mode in ("text", "markdown"):
            content = await file_transfer.read_session_file_content(file_path)
        else:
            file_url = f"/api/session/{session_id}/files/download?stored_path={quote(stored_path, safe='')}"

        return {
            "path": stored_path,
            "content": content,
            "type": file_path.suffix.lower().lstrip("."),
            "preview_mode": preview_mode,
            "file_url": file_url,
            "file_name": file_name,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"预览文件失败: {str(e)}")


@router.get('/{session_id}/files/download')
async def download_session_file(
    session_id: str,
    stored_path: str = Query(..., description="文件存储路径"),
    request: Request = None
):
    """
    下载会话文件空间中的单个文件。

    Args:
        session_id: 会话 ID。
        stored_path: 文件存储路径（相对或绝对）。

    Returns:
        FileResponse: 文件下载响应。

    Raises:
        HTTPException: 401 未认证 / 403 无权访问 / 404 文件不存在。
    """
    try:
        username = request.state.username
        if not username:
            raise HTTPException(status_code=401, detail="未认证")

        is_valid = await session_cache.verify_session(session_id, username)
        if not is_valid:
            raise HTTPException(status_code=403, detail="无权访问该会话")

        project_id, relative_path = await _get_session_project_info(session_id)
        file_path = file_transfer.resolve_session_file_path(
            stored_path,
            session_id,
            project_id=project_id,
            project_relative_path=relative_path
        )

        return FileResponse(
            path=str(file_path),
            filename=file_path.name,
            media_type="application/octet-stream"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载文件失败: {str(e)}")
