#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
用户管理路由模块

提供用户管理相关的API路由。
主要功能包括：
- 查询用户列表
- 删除用户
- 修改密码
- 修改用户名

Date: 2026/5/15
Author: 张镒谱
"""
from fastapi import APIRouter, HTTPException, Request, status, Depends
from pydantic import BaseModel
from typing import List
from app.shared.utils.auth.Safety import require_admin

router = APIRouter(prefix='/api/users', tags=['User Management'])


class UserResponse(BaseModel):
    """
    用户响应模型

    Attributes:
        id (int): 用户ID
        username (str): 用户名
        role (str): 用户角色（admin / user）
        created_at (str): 创建时间
        updated_at (str): 更新时间
    """
    id: int
    username: str
    role: str
    created_at: str
    updated_at: str


class PasswordUpdateRequest(BaseModel):
    """
    密码修改请求模型

    Attributes:
        old_password (str): 旧密码
        new_password (str): 新密码
    """
    old_password: str
    new_password: str


class UsernameUpdateRequest(BaseModel):
    """
    用户名修改请求模型

    Attributes:
        new_username (str): 新用户名
    """
    new_username: str


@router.get('', response_model=List[UserResponse], dependencies=[Depends(require_admin)])
async def list_users():
    """
    查询用户列表（admin 专用）

    Returns:
        List[UserResponse]: 用户列表（含角色信息）
    """
    from app.shared.utils.auth.user_db import UserDB
    users = await UserDB.list_users()
    return [
        UserResponse(
            id=u['id'],
            username=u['username'],
            role=u.get('role', 'user'),
            created_at=str(u['created_at']),
            updated_at=str(u['updated_at'])
        )
        for u in users
    ]


@router.delete('/{user_id}', dependencies=[Depends(require_admin)])
async def delete_user(user_id: int):
    """
    删除用户（admin 专用）

    Args:
        user_id (int): 用户ID

    Returns:
        dict: 删除结果
    """
    from app.shared.utils.auth.user_db import UserDB
    from app.shared.utils.Session.SessionCache import session_cache

    await session_cache.delete_user_sessions(user_id)
    success = await UserDB.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return {"message": "删除成功"}


@router.post('/{user_id}/kick', dependencies=[Depends(require_admin)])
async def kick_user(user_id: int, req: Request):
    """
    强制用户下线（踢人，admin 专用）

    清除该用户的所有 Refresh Token，使其无法刷新 Access Token，被迫重新登录。
    保留该用户的所有 Session 记录，确保 admin 在会话查询中仍可查看历史数据。

    Args:
        user_id (int): 要强制下线的用户ID
        req (Request): FastAPI 请求对象

    Returns:
        dict: 操作结果
    """
    from app.shared.utils.auth.user_db import UserDB
    from app.shared.utils.auth.refresh_token_db import RefreshTokenDB
    from app.shared.utils.auth.audit_log import AuditLog

    user = await UserDB.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    # 清除该用户所有 Refresh Token（强制重新登录）
    deleted_count = await RefreshTokenDB.delete_user_tokens(user_id)

    # 记录审计日志
    client_ip = req.client.host if req.client else "unknown"
    admin_username = getattr(req.state, 'username', 'unknown')
    await AuditLog.write_log(
        action='admin_kick_user',
        username=admin_username,
        detail=f'强制用户 {user["username"]}(ID:{user_id}) 下线，清除 {deleted_count} 个 Refresh Token',
        ip_address=client_ip
    )

    return {
        "message": f"用户 {user['username']} 已被强制下线",
        "deleted_tokens": deleted_count
    }


@router.get('/online', dependencies=[Depends(require_admin)])
async def get_online_users():
    """
    查询在线用户列表（admin 专用）

    基于会话最后活跃时间判断在线状态，返回在线用户及其会话统计。

    Returns:
        dict: 在线用户列表
    """
    from app.shared.utils.auth.session_db import SessionDB

    online_users = await SessionDB.get_all_active_sessions(minutes=30)
    return {"online_users": online_users}


@router.get('/{user_id}/sessions', dependencies=[Depends(require_admin)])
async def get_user_sessions_admin(user_id: int):
    """
    查询指定用户的所有会话（admin 专用）

    Args:
        user_id (int): 用户ID

    Returns:
        dict: 该用户的会话列表
    """
    from app.shared.utils.auth.user_db import UserDB
    from app.shared.utils.auth.session_db import SessionDB

    user = await UserDB.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    sessions = await SessionDB.get_user_sessions(user_id)
    return {"sessions": sessions}


@router.put('/{user_id}/password')
async def update_password(user_id: int, request: PasswordUpdateRequest):
    """
    修改密码

    Args:
        user_id (int): 用户ID
        request (PasswordUpdateRequest): 包含旧密码和新密码的请求

    Returns:
        dict: 修改结果
    """
    from app.shared.utils.auth.user_db import UserDB
    from app.shared.utils.auth.refresh_token_db import RefreshTokenDB

    user = await UserDB.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    if not UserDB.verify_password(request.old_password, user['password_hash']):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="旧密码错误")

    if len(request.new_password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="新密码长度不能少于6位")

    success = await UserDB.update_password(user_id, request.new_password)
    if not success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="修改失败")

    # 密码修改后清除该用户所有 Refresh Token（强制重新登录）
    deleted_count = await RefreshTokenDB.delete_user_tokens(user_id)
    print(f"[密码修改] 已清除用户 {user_id} 的 {deleted_count} 个 Refresh Token")

    return {"message": "密码修改成功"}


@router.put('/{user_id}/username')
async def update_username(user_id: int, request: UsernameUpdateRequest, req: Request):
    """
    修改用户名

    仅允许用户修改自己的用户名。

    Args:
        user_id (int): 用户ID
        request (UsernameUpdateRequest): 包含新用户名的请求
        req (Request): FastAPI 请求对象

    Returns:
        dict: 修改结果

    Raises:
        HTTPException: 用户名已存在或无权修改时抛出
    """
    from app.shared.utils.auth.user_db import UserDB

    # 校验用户名长度
    if len(request.new_username) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名长度不能少于3位"
        )

    # 检查当前用户是否有权修改该用户名
    current_user_id = getattr(req.state, 'user_id', None)
    if current_user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能修改自己的用户名"
        )

    try:
        success = await UserDB.update_username(user_id, request.new_username)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
        return {"message": "用户名修改成功", "new_username": request.new_username}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
