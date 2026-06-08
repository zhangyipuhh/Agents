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
- 颁发门户子 refresh_token（issue-portal-refresh-token）
- 扩展 refresh 接口支持 body/header 读取（兼容第三方 iframe 调用）

Date: 2026/2/6
Author: 张镒谱
"""
import secrets
from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from app.shared.utils.auth.Safety import jwt_auth
from app.core.config.settings import settings
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
        real_name (str): 真实姓名
        phone (str): 手机号
        email (str): 邮箱
        department (str): 部门（选填）
        position (str): 职位（选填）
        captcha_key (str): 验证码 key
        captcha_code (str): 验证码输入值
    """
    username: str
    password: str
    confirm_password: str
    real_name: str
    phone: str
    email: str
    department: str = ""
    position: str = ""
    captcha_key: str
    captcha_code: str


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


class IssuePortalRefreshTokenRequest(BaseModel):
    """
    申请门户子 refresh_token 请求模型

    Attributes:
        _: 占位字段，请求体可为空；实际鉴权依赖 Authorization 头中的 access_token
    """
    # 空请求体；保留 Pydantic 类仅为保持 OpenAPI 文档一致性


class IssuePortalRefreshTokenResponse(BaseModel):
    """
    申请门户子 refresh_token 响应模型

    Attributes:
        portal_refresh_token (str): 子 refresh_token 明文（仅此一次返回，需在父页 JS 中保存并 postMessage 给第三方 iframe）
        expires_in (int): 有效期（秒）
        expires_at (str): ISO8601 格式的过期时间字符串
    """
    portal_refresh_token: str
    expires_in: int
    expires_at: str


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
        request: 包含用户名、密码、确认密码、真实姓名、手机号、邮箱、部门、职位和验证码的请求对象

    Returns:
        dict: 注册结果

    Raises:
        HTTPException: 参数校验失败或用户名已存在时抛出400错误
    """
    import re
    from app.shared.utils.auth.user_db import UserDB
    from app.shared.utils.auth.captcha import captcha_manager

    # 校验验证码
    if not captcha_manager.verify(request.captcha_key, request.captcha_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码错误或已过期"
        )

    # 校验确认密码
    if request.password != request.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="两次输入的密码不一致"
        )

    # 校验密码复杂度：至少6位，包含大写、小写、数字、特殊字符
    if len(request.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码长度不能少于6位"
        )
    if not re.search(r'[A-Z]', request.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码必须包含大写字母"
        )
    if not re.search(r'[a-z]', request.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码必须包含小写字母"
        )
    if not re.search(r'\d', request.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码必须包含数字"
        )
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]', request.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码必须包含特殊字符"
        )

    # 校验用户名长度
    if len(request.username) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名长度不能少于3位"
        )

    # 校验真实姓名长度
    if len(request.real_name) < 2 or len(request.real_name) > 20:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="真实姓名长度应为2-20个字符"
        )

    # 校验手机号格式
    if not re.match(r'^1[3-9]\d{9}$', request.phone):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请输入有效的中国大陆手机号"
        )

    # 校验邮箱格式
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', request.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请输入有效的邮箱地址"
        )

    try:
        await UserDB.create_user(
            request.username,
            request.password,
            role='user',
            real_name=request.real_name,
            phone=request.phone,
            email=request.email,
            department=request.department,
            position=request.position
        )
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

    读取顺序（优先级从高到低）：
    1. 请求头 `X-Refresh-Token: <token>` —— 第三方 iframe 调用时使用
    2. 请求体 `{"refresh_token": "<token>"}` —— 第三方 iframe 调用时使用
    3. HttpOnly Cookie `refresh_token` —— 父页主应用调用时使用（保持原行为）

    验证流程：
    - 校验 JWT 签名与 `type=refresh` 类型
    - 计算 SHA256 哈希后，依次查询 `refresh_tokens` 与 `portal_refresh_tokens` 两张表
      （任一表中未撤销且未过期即视为有效）
    - 返回新的 Access Token（Refresh Token 不自动续期，保留原有效期）

    Returns:
        dict: 包含新的 access_token、token_type 与 expires_in

    Raises:
        HTTPException: 缺少 Refresh Token 或其无效 / 过期时返回 401
    """
    from app.shared.utils.auth.refresh_token_db import RefreshTokenDB
    from app.shared.utils.auth.portal_refresh_token_db import PortalRefreshTokenDB

    # 1) 优先从 X-Refresh-Token 头读取
    refresh_token = request.headers.get("X-Refresh-Token")

    # 2) 次选从请求体读取（POST JSON body）
    if not refresh_token:
        try:
            body = await request.json()
        except Exception:
            body = None
        if isinstance(body, dict):
            refresh_token = body.get("refresh_token")

    # 3) 最后回落到 HttpOnly Cookie（父页主应用场景，原行为不变）
    if not refresh_token:
        refresh_token = request.cookies.get("refresh_token")

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 Refresh Token"
        )

    # 验证 JWT 签名 + type=refresh
    payload = await jwt_auth.verify_refresh_token(refresh_token)

    # 计算哈希后，依次查主表与门户子表
    token_hash = RefreshTokenDB.hash_token(refresh_token)
    record = await RefreshTokenDB.verify_token(token_hash)
    if not record:
        # 主表未命中，查门户子表
        record = await PortalRefreshTokenDB.verify_token(token_hash)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh Token 已失效，请重新登录"
        )

    # 生成新的 Access Token（从记录中取 username，优先于 JWT payload，确保与存储一致）
    username = record.get("username") or payload.get("username")
    access_token = await jwt_auth.generate_token(username)

    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 30
    }


@router.post('/issue-portal-refresh-token', response_model=IssuePortalRefreshTokenResponse)
async def issue_portal_refresh_token(req: Request):
    """
    颁发门户子 Refresh Token 接口

    由父页（门户导航页）在 iframe 加载完成时调用。生成一张与正常
    refresh_token 等效但独立存储（portal_refresh_tokens 表）的子 token，
    供父页通过 postMessage 推送给第三方 iframe。第三方可像普通 SPA
    一样反复用它换 access_token。

    鉴权：
    - 通过现有 auth_middleware 校验 Authorization 头中的 access_token

    Returns:
        IssuePortalRefreshTokenResponse: 包含 portal_refresh_token（明文，仅此一次返回）、
                                         expires_in、expires_at

    Raises:
        HTTPException: 鉴权失败返回 401；存储失败返回 500
    """
    from app.shared.utils.auth.portal_refresh_token_db import PortalRefreshTokenDB

    # 从 request.state 取鉴权信息（auth_middleware 已写入）
    username = getattr(req.state, 'username', None)
    user_id = getattr(req.state, 'user_id', None)
    if not username or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无法识别当前用户"
        )

    # 生成门户子 refresh_token（与主 token 统一为 JWT 格式）
    ttl_seconds = settings.portal_auth.portal_refresh_token_ttl_seconds
    portal_refresh_token = await jwt_auth.generate_refresh_token(
        username,
        expires_delta=timedelta(seconds=ttl_seconds)
    )

    # 哈希后入库（仍存入 portal_refresh_tokens 表，便于独立撤销与审计）
    token_hash = PortalRefreshTokenDB.hash_token(portal_refresh_token)
    expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
    stored = await PortalRefreshTokenDB.store_token(token_hash, user_id, username, expires_at)
    if not stored:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="门户子 Refresh Token 存储失败"
        )

    return IssuePortalRefreshTokenResponse(
        portal_refresh_token=portal_refresh_token,
        expires_in=ttl_seconds,
        expires_at=expires_at.isoformat() + "Z"
    )


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
    from app.shared.utils.auth.portal_refresh_token_db import PortalRefreshTokenDB

    username = getattr(req.state, 'username', None)
    user_id = getattr(req.state, 'user_id', None)
    session_id = req.headers.get('X-Session-ID')
    client_ip = req.client.host if req.client else "unknown"

    # 删除服务端 Refresh Token
    refresh_token = req.cookies.get("refresh_token")
    if refresh_token:
        token_hash = RefreshTokenDB.hash_token(refresh_token)
        await RefreshTokenDB.delete_token(token_hash)

    # 撤销该用户所有门户子 refresh_token（防止子 token 残留被第三方利用）
    if user_id:
        await PortalRefreshTokenDB.revoke_user_tokens(user_id)

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
