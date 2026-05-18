#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
会话管理路由模块

本模块定义了会话管理相关的API路由。
主要功能包括：
- 生成新会话
- 删除会话

Date: 2026/2/6
Author: 张镒谱
"""
import uuid
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel  
from app.shared.utils.files.fileTransfer import FileTransfer
from app.shared.utils.Session.SessionCache import session_cache


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


# 创建文件传输工具实例
file_transfer = FileTransfer()

# 创建API路由实例，设置前缀和标签
# prefix='/api/session': 所有路由路径将以/api/session开头
# tags=['Session Management']: 用于API文档分组，便于在Swagger UI中查看
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
        #print(f"[诊断-session_router] create_session: username={username}")
        if not username:
            raise HTTPException(status_code=401, detail="未认证")

        from app.shared.utils.auth.user_db import UserDB
        from app.shared.utils.Session.SessionCache import session_cache
        from app.core.database import DatabasePool

        #print(f"[诊断-session_router] create_session: DatabasePool.is_enabled()={DatabasePool.is_enabled()}")
        user = await UserDB.get_user_by_username(username)
        #print(f"[诊断-session_router] create_session: UserDB.get_user_by_username('{username}') -> {user}")
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在")

        session_id = str(uuid.uuid4())
        session_dir = file_transfer._get_session_dir(session_id)

        # 添加 session（传入 user_id）
        session_cache.add_session(session_id, username, user['id'])

        return SessionCreateResponse(
            session_id=session_id,
            message="会话创建成功"
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        #print(f"[诊断-session_router] create_session 异常: {e}")
        #print(f"[诊断-session_router] 堆栈: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"创建会话失败: {str(e)}")


@router.delete('/delete/{session_id}', response_model=SessionDeleteResponse)
async def delete_session(session_id: str, request: Request):
    """
    删除会话API端点
    
    删除指定会话的整个目录及其所有文件。
    需要提供有效的 JWT token。
    
    工作流程：
    1. 从请求头获取 JWT token
    2. 验证 token 并获取用户名
    3. 验证 session_id 是否属于该用户
    4. 删除该会话目录及其所有文件
    5. 从缓存中删除 session_id
    6. 返回删除结果
    
    Args:
        session_id (str): 要删除的会话ID
        request (Request): FastAPI 请求对象
        
    Returns:
        SessionDeleteResponse: 包含删除结果的响应对象
        
    Raises:
        HTTPException: 当删除过程中发生错误时抛出500错误
    """
    try:
        # 从 request.state 获取用户名（由 JWT 中间件设置）
        username = request.state.username
        
        if not username:
            raise HTTPException(status_code=401, detail="未认证")
        
        # 验证 session_id 是否属于该用户
        is_valid = session_cache.verify_session(session_id, username)
        
        if not is_valid:
            raise HTTPException(status_code=403, detail="无权删除该会话")
        
        # 删除会话目录
        success = await file_transfer.delete_session(session_id)
        
        # 从缓存中删除 session_id
        session_cache.delete_session(session_id)
        
        return SessionDeleteResponse(
            success=success,
            message="会话删除成功" if success else "会话不存在"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除会话失败: {str(e)}")
