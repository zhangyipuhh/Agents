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
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from typing import Optional
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
    """
    access_token: str
    token_type: str
    expires_in: int
    role: str
    username: str


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
async def login(request: LoginRequest, req: Request):
    """
    用户登录API端点

    验证验证码、用户凭据，返回JWT令牌和角色信息。
    登录成功/失败均记录审计日志。

    Args:
        request (LoginRequest): 包含用户名、密码、验证码 key 和验证码的请求对象
        req (Request): FastAPI 请求对象，用于获取客户端 IP

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
        # 记录登录失败日志（验证码错误）
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
        # 记录登录失败日志
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

    # 生成 JWT 令牌
    token = await jwt_auth.generate_token(request.username)

    # 记录登录成功日志
    await AuditLog.write_log(
        action='login_success',
        username=request.username,
        user_id=user_id,
        ip_address=client_ip
    )

    return LoginResponse(
        access_token=token,
        token_type="Bearer",
        expires_in=jwt_auth.expiration_minutes,
        role=role,
        username=request.username
    )


@router.post('/logout')
async def logout(req: Request):
    """
    用户登出API端点

    删除服务端 Session，记录审计日志。

    Args:
        req (Request): FastAPI 请求对象

    Returns:
        dict: 登出结果
    """
    from app.shared.utils.auth.audit_log import AuditLog
    from app.shared.utils.Session.SessionCache import session_cache

    username = getattr(req.state, 'username', None)
    session_id = req.headers.get('X-Session-ID')
    client_ip = req.client.host if req.client else "unknown"

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
