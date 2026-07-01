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
        real_name (str): 真实姓名
        role (str): 用户角色（admin / user）
        allowed_agents (List[str]): 允许使用的智能体名称列表
        created_at (str): 创建时间
        updated_at (str): 更新时间
    """
    id: int
    username: str
    real_name: str
    role: str
    allowed_agents: List[str] = []
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


class ProfileUpdateRequest(BaseModel):
    """
    用户资料更新请求模型

    Attributes:
        phone (str): 手机号
        email (str): 邮箱
        department (str): 部门
        position (str): 职位
        allowed_agents (List[str]): 允许使用的智能体名称列表
    """
    phone: str
    email: str
    department: str
    position: str
    allowed_agents: List[str] = []


class UserCreateRequest(BaseModel):
    """
    Admin 创建用户请求模型

    Attributes:
        username (str): 用户名
        password (str): 密码
        role (str): 角色，默认为 'user'
        real_name (str): 真实姓名
        phone (str): 手机号
        email (str): 邮箱
        department (str): 部门
        position (str): 职位
        allowed_agents (List[str]): 允许使用的智能体名称列表
    """
    username: str
    password: str
    role: str = 'user'
    real_name: str = ''
    phone: str = ''
    email: str = ''
    department: str = ''
    position: str = ''
    allowed_agents: List[str] = []


class UserUpdateRequest(BaseModel):
    """
    Admin 更新用户请求模型

    Attributes:
        real_name (str): 真实姓名
        phone (str): 手机号
        email (str): 邮箱
        department (str): 部门
        position (str): 职位
        role (str): 角色
        allowed_agents (List[str]): 允许使用的智能体名称列表
    """
    real_name: str = ''
    phone: str = ''
    email: str = ''
    department: str = ''
    position: str = ''
    role: str = 'user'
    allowed_agents: List[str] = []


class UserProfileResponse(BaseModel):
    """
    用户个人资料响应模型

    Attributes:
        id (int): 用户ID
        username (str): 用户名
        role (str): 用户角色
        real_name (str): 真实姓名
        phone (str): 手机号
        email (str): 邮箱
        department (str): 部门
        position (str): 职位
        allowed_agents (List[str]): 允许使用的智能体名称列表
        created_at (str): 创建时间
        updated_at (str): 更新时间
    """
    id: int
    username: str
    role: str
    real_name: str
    phone: str
    email: str
    department: str
    position: str
    allowed_agents: List[str] = []
    created_at: str
    updated_at: str


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
            real_name=u.get('real_name', ''),
            role=u.get('role', 'user'),
            allowed_agents=u.get('allowed_agents', []),
            created_at=str(u['created_at']),
            updated_at=str(u['updated_at'])
        )
        for u in users
    ]


@router.post('', dependencies=[Depends(require_admin)])
async def create_user_admin(request: UserCreateRequest, req: Request):
    """
    Admin 创建用户（复用注册核心逻辑）

    Args:
        request (UserCreateRequest): 包含用户名、密码、角色等信息的请求对象
        req (Request): FastAPI 请求对象

    Returns:
        dict: 创建结果
    """
    import re
    from app.shared.utils.auth.user_db import UserDB
    from app.shared.utils.auth.audit_log import AuditLog

    # 校验用户名长度
    if len(request.username) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名长度不能少于3位"
        )

    # 校验密码长度
    if len(request.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码长度不能少于6位"
        )

    # 校验手机号格式
    if request.phone and not re.match(r'^1[3-9]\d{9}$', request.phone):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请输入有效的中国大陆手机号"
        )

    # 校验邮箱格式
    if request.email and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', request.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请输入有效的邮箱地址"
        )

    # 校验角色
    if request.role not in ('admin', 'user'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="角色必须是 admin 或 user"
        )

    try:
        user_id = await UserDB.create_user(
            request.username,
            request.password,
            role=request.role,
            real_name=request.real_name,
            phone=request.phone,
            email=request.email,
            department=request.department,
            position=request.position,
            allowed_agents=request.allowed_agents
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # 写入审计日志
    client_ip = req.client.host if req.client else "unknown"
    admin_username = getattr(req.state, 'username', 'unknown')
    await AuditLog.write_log(
        action='admin_create_user',
        username=admin_username,
        detail=f'Admin 创建用户 {request.username}，角色 {request.role}',
        ip_address=client_ip
    )

    return {"message": "创建成功", "user_id": user_id}


@router.get('/online', dependencies=[Depends(require_admin)])
async def get_online_users():
    """
    查询在线用户列表（admin 专用）

    在线判定逻辑：用户持有任一有效 Token（主 refresh_token 或 portal_refresh_token）
    或最近 30 分钟内有活跃 Session，即视为在线。
    返回结构保持前端兼容。

    Returns:
        dict: 在线用户列表
    """
    from app.shared.utils.auth.session_db import SessionDB
    from app.shared.utils.auth.refresh_token_db import RefreshTokenDB
    from app.shared.utils.auth.portal_refresh_token_db import PortalRefreshTokenDB
    from app.shared.utils.auth.user_db import UserDB

    online_map = {}

    # 1. 有活跃 Session 的用户（原有逻辑，作为活跃基础）
    session_users = await SessionDB.get_all_active_sessions(minutes=30)
    for u in session_users:
        uid = u['user_id']
        online_map[uid] = {
            'user_id': uid,
            'username': u['username'],
            'session_count': u.get('session_count', 0),
            'last_active_at': str(u.get('last_active_at')) if u.get('last_active_at') else None,
        }

    # 2. 有有效 portal_refresh_token 的用户（补充去重）
    portal_users = await PortalRefreshTokenDB.get_users_with_valid_tokens()
    for u in portal_users:
        uid = u['user_id']
        if uid in online_map:
            continue
        online_map[uid] = {
            'user_id': uid,
            'username': u.get('username', ''),
            'session_count': 0,
            'last_active_at': None,
        }

    # 3. 有有效主 refresh_token 的用户（补充去重）
    refresh_users = await RefreshTokenDB.get_users_with_valid_tokens()
    for u in refresh_users:
        uid = u['user_id']
        if uid in online_map:
            continue
        user = await UserDB.get_user_by_id(uid)
        online_map[uid] = {
            'user_id': uid,
            'username': user['username'] if user else str(uid),
            'session_count': 0,
            'last_active_at': None,
        }

    return {"online_users": list(online_map.values())}


@router.put('/{user_id}', dependencies=[Depends(require_admin)])
async def update_user_admin(user_id: int, request: UserUpdateRequest, req: Request):
    """
    Admin 更新用户资料

    Args:
        user_id (int): 用户ID
        request (UserUpdateRequest): 包含用户资料更新信息的请求对象
        req (Request): FastAPI 请求对象

    Returns:
        dict: 更新结果
    """
    import re
    from app.shared.utils.auth.user_db import UserDB
    from app.shared.utils.auth.audit_log import AuditLog

    user = await UserDB.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    # 校验手机号格式
    if request.phone and not re.match(r'^1[3-9]\d{9}$', request.phone):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请输入有效的中国大陆手机号"
        )

    # 校验邮箱格式
    if request.email and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', request.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请输入有效的邮箱地址"
        )

    # 校验角色
    if request.role not in ('admin', 'user'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="角色必须是 admin 或 user"
        )

    success = await UserDB.update_user_info(
        user_id,
        real_name=request.real_name,
        phone=request.phone,
        email=request.email,
        department=request.department,
        position=request.position,
        role=request.role,
        allowed_agents=request.allowed_agents
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="更新失败")

    # 写入审计日志
    client_ip = req.client.host if req.client else "unknown"
    admin_username = getattr(req.state, 'username', 'unknown')
    await AuditLog.write_log(
        action='admin_update_user',
        username=admin_username,
        detail=f'Admin 更新用户 {user["username"]}(ID:{user_id}) 资料',
        ip_address=client_ip
    )

    return {"message": "更新成功"}


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
    from app.shared.utils.Session.SessionCache import session_cache

    user = await UserDB.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    # 清除该用户所有 Refresh Token（强制重新登录）
    deleted_count = await RefreshTokenDB.delete_user_tokens(user_id)

    # 将该用户所有 Session 标记为 kicked（使其从在线列表中消失，但保留会话记录）
    kicked_sessions = await session_cache.kick_user_sessions(user_id)

    # 删除该用户所有 Portal Refresh Token（防止第三方 iframe 继续换 token）
    from app.shared.utils.auth.portal_refresh_token_db import PortalRefreshTokenDB
    deleted_portal_tokens = await PortalRefreshTokenDB.delete_user_tokens(user_id)

    # 记录审计日志
    client_ip = req.client.host if req.client else "unknown"
    admin_username = getattr(req.state, 'username', 'unknown')
    await AuditLog.write_log(
        action='admin_kick_user',
        username=admin_username,
        detail=f'强制用户 {user["username"]}(ID:{user_id}) 下线，清除 {deleted_count} 个 Refresh Token，删除 {deleted_portal_tokens} 个 Portal Token，标记 {kicked_sessions} 个 Session 为 kicked',
        ip_address=client_ip
    )

    return {
        "message": f"用户 {user['username']} 已被强制下线",
        "deleted_tokens": deleted_count,
        "deleted_portal_tokens": deleted_portal_tokens,
        "kicked_sessions": kicked_sessions
    }


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

    # 密码修改后同时删除该用户所有 Portal Refresh Token
    from app.shared.utils.auth.portal_refresh_token_db import PortalRefreshTokenDB
    deleted_portal = await PortalRefreshTokenDB.delete_user_tokens(user_id)
    print(f"[密码修改] 已清除用户 {user_id} 的 {deleted_count} 个 Refresh Token，删除 {deleted_portal} 个 Portal Token")

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


@router.get('/{user_id}/profile', response_model=UserProfileResponse)
async def get_user_profile(user_id: int, req: Request):
    """
    获取用户个人资料

    仅允许用户查看自己的资料。

    Args:
        user_id (int): 用户ID
        req (Request): FastAPI 请求对象

    Returns:
        UserProfileResponse: 用户个人资料

    Raises:
        HTTPException: 用户不存在或无权查看时抛出
    """
    from app.shared.utils.auth.user_db import UserDB

    current_user_id = getattr(req.state, 'user_id', None)
    if current_user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能查看自己的资料"
        )

    user = await UserDB.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    return UserProfileResponse(
        id=user['id'],
        username=user['username'],
        role=user.get('role', 'user'),
        real_name=user.get('real_name', ''),
        phone=user.get('phone', ''),
        email=user.get('email', ''),
        department=user.get('department', ''),
        position=user.get('position', ''),
        allowed_agents=user.get('allowed_agents', []),
        created_at=str(user['created_at']),
        updated_at=str(user['updated_at'])
    )


@router.put('/{user_id}/profile')
async def update_user_profile(user_id: int, request: ProfileUpdateRequest, req: Request):
    """
    更新用户个人资料

    仅允许用户修改自己的资料。
    会对手机号和邮箱格式进行校验。

    Args:
        user_id (int): 用户ID
        request (ProfileUpdateRequest): 包含手机、邮箱、部门、职位的请求
        req (Request): FastAPI 请求对象

    Returns:
        dict: 更新结果

    Raises:
        HTTPException: 参数校验失败或无权修改时抛出
    """
    import re
    from app.shared.utils.auth.user_db import UserDB

    current_user_id = getattr(req.state, 'user_id', None)
    if current_user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能修改自己的资料"
        )

    user = await UserDB.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    phone = request.phone.strip()
    email = request.email.strip()
    department = request.department.strip()
    position = request.position.strip()

    if phone and not re.match(r'^1[3-9]\d{9}$', phone):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请输入有效的中国大陆手机号"
        )

    if email and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请输入有效的邮箱地址"
        )

    success = await UserDB.update_profile(
        user_id, phone, email, department, position, allowed_agents=request.allowed_agents
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="更新失败")

    return {"message": "资料更新成功"}
