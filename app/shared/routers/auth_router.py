#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
认证路由模块

本模块定义了认证相关的API路由。
主要功能包括：
- 用户注册（含确认密码）
- 用户登录（含验证码校验）
- 验证码获取
- 用户登出

Date: 2026/2/6
Author: 张镒谱
"""
from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from app.shared.utils.auth.Safety import jwt_auth
from app.core.database import DatabasePool


class LoginRequest(BaseModel):
    """
    登录请求模型

    Attributes:
        username (str): 用户名
        password (str): 密码
        captcha_key (str): 验证码 key
        captcha_code (str): 验证码输入值
    """
    username: str
    password: str
    captcha_key: str
    captcha_code: str


class ApiLoginRequest(BaseModel):
    """
    API 程序化登录请求模型（免验证码）

    Attributes:
        username (str): 用户名
        password (str): 密码
    """
    username: str
    password: str


class RegisterRequest(BaseModel):
    """
    注册请求模型

    Attributes:
        username (str): 用户名
        password (str): 密码
        confirm_password (str): 确认密码
    """
    username: str
    password: str
    confirm_password: str


class LoginResponse(BaseModel):
    """
    登录响应模型

    Attributes:
        access_token (str): JWT访问令牌
        token_type (str): 令牌类型
        expires_in (int): 令牌过期时间（分钟）
        role (str): 用户角色
        username (str): 用户名
        user_id (Optional[int]): 用户ID
    """
    access_token: str
    token_type: str
    expires_in: int
    role: str
    username: str
    user_id: Optional[int] = None


class CaptchaResponse(BaseModel):
    """
    验证码响应模型

    Attributes:
        captcha_key (str): 验证码 key，用于登录时校验
        captcha_image (str): base64 编码的验证码图片
    """
    captcha_key: str
    captcha_image: str


# 创建API路由实例，设置前缀和标签
router = APIRouter(prefix='/api/auth', tags=['Authentication'])


@router.get('/captcha', response_model=CaptchaResponse)
async def get_captcha():
    """
    获取验证码接口

    生成图形验证码，返回验证码 key 和 base64 图片。

    Returns:
        CaptchaResponse: 验证码 key 和图片
    """
    from app.shared.utils.auth.captcha import captcha_manager
    key, image_base64 = captcha_manager.generate()
    return CaptchaResponse(captcha_key=key, captcha_image=image_base64)


@router.post('/register')
async def register(request: RegisterRequest):
    """
    用户注册API端点

    注册新用户，默认角色为 'user'。

    Args:
        request: 包含用户名、密码和确认密码的请求对象

    Returns:
        dict: 注册结果

    Raises:
        HTTPException: 参数校验失败或用户名已存在时抛出400错误
    """
    from app.shared.utils.auth.user_db import UserDB

    # 校验确认密码
    if request.password != request.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="两次输入的密码不一致"
        )

    # 校验密码长度
    if len(request.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码长度不能少于6位"
        )

    # 校验用户名长度
    if len(request.username) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名长度不能少于3位"
        )

    try:
        await UserDB.create_user(request.username, request.password, role='user')
        return {"message": "注册成功"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post('/login', response_model=LoginResponse)
async def login(request: LoginRequest, req: Request, response: Response):
    """
    用户登录API端点

    验证验证码、用户凭据，返回 Access Token（JSON body）
    并通过 Set-Cookie 设置 Refresh Token（HttpOnly）。
    登录成功/失败均记录审计日志。

    Args:
        request (LoginRequest): 包含用户名、密码、验证码 key 和验证码的请求对象
        req (Request): FastAPI 请求对象，用于获取客户端 IP
        response (Response): FastAPI 响应对象，用于设置 Cookie

    Returns:
        LoginResponse: 包含访问令牌、令牌类型、过期时间、角色和用户名的响应对象

    Raises:
        HTTPException: 验证码错误、用户名或密码错误时抛出
    """
    from app.shared.utils.auth.captcha import captcha_manager
    from app.shared.utils.auth.audit_log import AuditLog

    # 获取客户端 IP
    client_ip = req.client.host if req.client else "unknown"

    # 校验验证码
    if not captcha_manager.verify(request.captcha_key, request.captcha_code):
        await AuditLog.write_log(
            action='login_failure',
            username=request.username,
            detail='验证码错误',
            ip_address=client_ip
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码错误或已过期"
        )

    # 验证用户凭据
    if DatabasePool.is_enabled():
        from app.shared.utils.auth.user_db import UserDB
        is_valid = await UserDB.verify_credentials(request.username, request.password)
    else:
        is_valid = await jwt_auth.verify_credentials(request.username, request.password)

    if not is_valid:
        await AuditLog.write_log(
            action='login_failure',
            username=request.username,
            detail='用户名或密码错误',
            ip_address=client_ip
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )

    # Memory 模式下自动创建用户记录
    if not DatabasePool.is_enabled():
        from app.shared.utils.auth.user_db import UserDB
        if not await UserDB.get_user_by_username(request.username):
            await UserDB.create_user(request.username, request.password)

    # 获取用户角色
    from app.shared.utils.auth.user_db import UserDB
    user = await UserDB.get_user_by_username(request.username)
    role = user.get('role', 'user') if user else 'user'
    user_id = user.get('id') if user else None

    # 生成 Access Token（JSON body 返回）
    access_token = await jwt_auth.generate_token(request.username)

    # 生成 Refresh Token（HttpOnly Cookie 传递）
    from app.shared.utils.auth.refresh_token_db import RefreshTokenDB
    refresh_token = await jwt_auth.generate_refresh_token(request.username)
    token_hash = RefreshTokenDB.hash_token(refresh_token)
    expires_at = datetime.utcnow() + timedelta(hours=24)
    await RefreshTokenDB.store_token(token_hash, user_id, expires_at)

    # 通过 Set-Cookie 设置 Refresh Token
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        samesite="strict",
        path="/api/auth",
        max_age=86400
    )

    # 记录登录成功日志
    await AuditLog.write_log(
        action='login_success',
        username=request.username,
        user_id=user_id,
        ip_address=client_ip
    )

    return LoginResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=30,
        role=role,
        username=request.username,
        user_id=user_id
    )


@router.post('/login-api', response_model=LoginResponse)
async def login_api(request: ApiLoginRequest, req: Request, response: Response):
    """
    API 程序化登录接口（免验证码）

    用于非浏览器场景的服务间调用，直接验证用户名密码后返回 Token。
    与现有 login 接口行为保持一致，但跳过验证码校验。

    Args:
        request (ApiLoginRequest): 包含用户名和密码的请求对象
        req (Request): FastAPI 请求对象，用于获取客户端 IP
        response (Response): FastAPI 响应对象，用于设置 Cookie

    Returns:
        LoginResponse: 包含访问令牌、令牌类型、过期时间、角色和用户名的响应对象

    Raises:
        HTTPException: 用户名或密码错误时抛出 401
    """
    from app.shared.utils.auth.audit_log import AuditLog

    # 获取客户端 IP
    client_ip = req.client.host if req.client else "unknown"

    # 验证用户凭据
    if DatabasePool.is_enabled():
        from app.shared.utils.auth.user_db import UserDB
        is_valid = await UserDB.verify_credentials(request.username, request.password)
    else:
        is_valid = await jwt_auth.verify_credentials(request.username, request.password)

    if not is_valid:
        await AuditLog.write_log(
            action='login_failure',
            username=request.username,
            detail='用户名或密码错误',
            ip_address=client_ip
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )

    # Memory 模式下自动创建用户记录
    if not DatabasePool.is_enabled():
        from app.shared.utils.auth.user_db import UserDB
        if not await UserDB.get_user_by_username(request.username):
            await UserDB.create_user(request.username, request.password)

    # 获取用户角色
    from app.shared.utils.auth.user_db import UserDB
    user = await UserDB.get_user_by_username(request.username)
    role = user.get('role', 'user') if user else 'user'
    user_id = user.get('id') if user else None

    # 生成 Access Token（JSON body 返回）
    access_token = await jwt_auth.generate_token(request.username)

    # 生成 Refresh Token（HttpOnly Cookie 传递）
    from app.shared.utils.auth.refresh_token_db import RefreshTokenDB
    refresh_token = await jwt_auth.generate_refresh_token(request.username)
    token_hash = RefreshTokenDB.hash_token(refresh_token)
    expires_at = datetime.utcnow() + timedelta(hours=24)
    await RefreshTokenDB.store_token(token_hash, user_id, expires_at)

    # 通过 Set-Cookie 设置 Refresh Token
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        samesite="strict",
        path="/api/auth",
        max_age=86400
    )

    # 记录登录成功日志
    await AuditLog.write_log(
        action='login_success',
        username=request.username,
        user_id=user_id,
        ip_address=client_ip
    )

    return LoginResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=30,
        role=role,
        username=request.username,
        user_id=user_id
    )


@router.post('/refresh')
async def refresh_token(request: Request):
    """
    刷新 Access Token 接口

    从 HttpOnly Cookie 中读取 Refresh Token，验证后返回新的 Access Token。
    Refresh Token 不自动续期（保留原有效期）。

    Returns:
        dict: 包含新的 access_token 和 expires_in

    Raises:
        HTTPException: Refresh Token 无效或过期时返回 401
    """
    from app.shared.utils.auth.refresh_token_db import RefreshTokenDB

    # 从 Cookie 中读取 refresh_token
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 Refresh Token"
        )

    # 验证 JWT 签名 + type=refresh
    payload = await jwt_auth.verify_refresh_token(refresh_token)

    # 计算哈希，查询数据库存在性
    token_hash = RefreshTokenDB.hash_token(refresh_token)
    record = await RefreshTokenDB.verify_token(token_hash)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh Token 已失效，请重新登录"
        )

    # 生成新的 Access Token
    username = payload.get("username")
    access_token = await jwt_auth.generate_token(username)

    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 30
    }


@router.get('/validate')
async def validate_token(request: Request):
    """
    验证 Access Token 有效性接口

    读取 Authorization 头中的 Access Token，验证签名和有效期。
    用于前端页面加载时检查当前 Token 是否有效。

    Returns:
        dict: 包含 username 和 role

    Raises:
        HTTPException: Token 无效或过期时返回 401
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少有效的认证信息"
        )

    token = auth_header.split(" ")[1]
    payload = await jwt_auth.verify_token(token)

    # 拒绝 Refresh Token
    if payload.get("type") == "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的令牌类型"
        )

    # 查询角色和用户ID
    from app.shared.utils.auth.user_db import UserDB
    user = await UserDB.get_user_by_username(payload["username"])
    role = user.get('role', 'user') if user else 'user'
    user_id = user.get('id') if user else None

    return {
        "username": payload["username"],
        "role": role,
        "user_id": user.get('id') if user else None
    }


@router.post('/logout')
async def logout(req: Request, response: Response):
    """
    用户登出API端点

    删除服务端 Refresh Token 数据库记录 + 清除 Cookie + 删除 Session。
    记录审计日志。

    Args:
        req (Request): FastAPI 请求对象
        response (Response): FastAPI 响应对象，用于清除 Cookie

    Returns:
        dict: 登出结果
    """
    from app.shared.utils.auth.audit_log import AuditLog
    from app.shared.utils.Session.SessionCache import session_cache
    from app.shared.utils.auth.refresh_token_db import RefreshTokenDB

    username = getattr(req.state, 'username', None)
    session_id = req.headers.get('X-Session-ID')
    client_ip = req.client.host if req.client else "unknown"

    # 删除服务端 Refresh Token
    refresh_token = req.cookies.get("refresh_token")
    if refresh_token:
        token_hash = RefreshTokenDB.hash_token(refresh_token)
        await RefreshTokenDB.delete_token(token_hash)

    # 清除 Refresh Token Cookie
    response.delete_cookie(
        key="refresh_token",
        path="/api/auth",
        httponly=True,
        samesite="strict"
    )

    # 删除 Session
    if session_id:
        await session_cache.delete_session(session_id)

    # 记录登出日志
    if username:
        await AuditLog.write_log(
            action='logout',
            username=username,
            detail=f'Session {session_id} 已销毁' if session_id else None,
            ip_address=client_ip
        )

    return {"message": "登出成功"}
