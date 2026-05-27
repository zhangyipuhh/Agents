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
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from app.shared.utils.files.fileTransfer import FileTransfer
from app.shared.utils.Session.SessionCache import session_cache
from app.shared.utils.auth.session_db import SessionDB
from app.shared.utils.files.attachment_db import AttachmentDB
from app.shared.utils.memory.conversation_db import ConversationDB


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
