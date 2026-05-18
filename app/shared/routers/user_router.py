#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
用户管理路由模块

提供用户管理相关的API路由。
主要功能包括：
- 查询用户列表
- 删除用户
- 修改密码

Date: 2026/5/15
Author: 张镒谱
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import List

router = APIRouter(prefix='/api/users', tags=['User Management'])


class UserResponse(BaseModel):
    """
    用户响应模型

    Attributes:
        id (int): 用户ID
        username (str): 用户名
        created_at (str): 创建时间
        updated_at (str): 更新时间
    """
    id: int
    username: str
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


@router.get('', response_model=List[UserResponse])
async def list_users():
    """
    查询用户列表

    Returns:
        List[UserResponse]: 用户列表
    """
    from app.shared.utils.auth.user_db import UserDB
    users = await UserDB.list_users()
    return [
        UserResponse(
            id=u['id'],
            username=u['username'],
            created_at=str(u['created_at']),
            updated_at=str(u['updated_at'])
        )
        for u in users
    ]


@router.delete('/{user_id}')
async def delete_user(user_id: int):
    """
    删除用户

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

    user = await UserDB.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    if not UserDB.verify_password(request.old_password, user['password_hash']):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="旧密码错误")

    success = await UserDB.update_password(user_id, request.new_password)
    if not success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="修改失败")

    return {"message": "密码修改成功"}