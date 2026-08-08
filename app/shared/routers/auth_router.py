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
import logging
import secrets
import time
from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
from app.shared.utils.auth.Safety import jwt_auth
from app.core.config.settings import settings
from app.core.database import DatabasePool

logger = logging.getLogger(__name__)


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
        visible_menus (List[str]): 2026-07-23 新增：该用户可见的菜单 id 列表
            - admin：所有 enabled 项的 id（按 sort_order 升序）
            - 普通用户：menu_permission_service 计算结果（含强制 profile）
            - 前端一次拿，无需单独请求菜单接口
        allowed_agents (List[str]): 2026-07-24 新增：该用户授权的 agent_name 列表
            - admin：返 []（前端 InputBox 通过 isAdmin prop 走全量旁路）
            - 普通用户：agent_permission_service 缓存值；service 不可用时
              fallback 到 users.allowed_agents 旧字段（迁移兼容）
    """
    access_token: str
    token_type: str
    expires_in: int
    role: str
    username: str
    user_id: Optional[int] = None
    visible_menus: List[str] = []
    # 2026-07-24 新增：当前用户授权的 agent_name 列表（来自 user_agent_acl）。
    # admin 返 []（前端 InputBox 通过 isAdmin prop 走全量旁路）。
    # 普通用户返 agent_permission_service.get_user_agent_grants_sync(user_id) 缓存值；
    # service 不可用时 fallback 到 users.allowed_agents 旧字段（迁移兼容）。
    allowed_agents: List[str] = []


class MfaChallengeResponse(BaseModel):
    """2026-08-07 新增：MFA challenge 响应（仅 /login 用）。

    与 ``LoginResponse`` 互斥：
    - ``auth_stage == "mfa_required"``：已绑定 TOTP，等待 /api/auth/mfa/login/verify
    - ``auth_stage == "mfa_enrollment_required"``：管理员首次绑定，等待 enroll/start + confirm

    两阶段均**不**签发 access_token / refresh cookie；客户端拿到 challenge_token
    单独走 MFA 流程。
    """

    auth_stage: str
    challenge_token: str
    challenge_expires_in: int = 300
    mfa_methods: List[str] = []
    username: str


async def _compute_visible_menus(req: Request, user_id: Optional[int], role: str) -> List[str]:
    """计算该用户的 visible_menus 列表。

    - admin：所有 enabled 项的 id（按 sort_order 升序）
    - 普通用户：通过 menu_permission_service 计算（含强制 profile）
    - menu_permission_service 不可用（lifespan 未初始化）：普通用户 fail-secure 仅 ['profile']

    Args:
        req: FastAPI Request 对象（用于取 app.state.menu_permission_service）
        user_id: 用户 ID；admin 也接受 None
        role: 用户角色

    Returns:
        List[str]: 可见菜单 id 列表
    """
    from app.core.menu_registry import get_enabled_items

    if role == "admin":
        return [m.id for m in sorted(get_enabled_items(), key=lambda m: m.sort_order)]
    svc = getattr(req.app.state, "menu_permission_service", None)
    if svc is None:
        # fail-secure：service 不可用时仅 ['profile']
        return ["profile"]
    uid = user_id if user_id is not None else 0
    return await svc.get_visible_menu_ids(user_id=uid, is_admin=False)


async def _compute_allowed_agents(
    req: Request,
    user_id: Optional[int],
    role: str,
    fallback: Optional[List[str]] = None,
) -> List[str]:
    """计算该用户的 allowed_agents 列表。

    2026-07-24 改造：数据源从 users.allowed_agents (JSONB) 切换到 user_agent_acl 表。
    - admin：返 []（前端 InputBox 与 isAdmin 旁路配合，全量可见）
    - 普通用户：通过 agent_permission_service 读 ACL
    - service 不可用：返 fallback（兼容极端情况：DB 还没迁完时的最后一道防线）
    - db=None / preload_all 失败：fail-secure 返 []

    Args:
        req: FastAPI Request 对象
        user_id: 用户 ID
        role: 用户角色
        fallback: service 不可用时的兜底（一般是 users.allowed_agents 字段）

    Returns:
        List[str]: 已授权 agent_name 列表
    """
    if role == "admin":
        # admin 不受 ACL 限制；前端 InputBox 通过 isAdmin 旁路显示全量，
        # 直接返 [] 让前端代码走 isAdmin 分支。
        return []
    if user_id is None:
        return []
    svc = getattr(req.app.state, "agent_permission_service", None)
    if svc is None:
        # service 不可用（lifespan 未初始化或初始化失败）：fallback 到 users.allowed_agents
        return list(fallback) if fallback else []
    granted = svc.get_user_agent_grants_sync(user_id)
    if not granted and fallback:
        # 极端情况：DB 迁移未完成 / preload 异常，回退到旧字段
        # 防止新用户第一次登录时 authorized 列表突然变空
        return list(fallback)
    return sorted(granted)


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
    from app.shared.utils.auth.password_policy import validate_password

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

    # 2026-08-07 改造：统一密码规则由 password_policy 提供（最小长度 8 + 大小写 + 数字 + 特殊字符）。
    # 注：保留 import re 以兼容其他路由模块的副作用，但实际校验全部委托给 password_policy。
    is_valid, err_msg = validate_password(request.password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err_msg,
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


@router.post('/login')
async def login(request: LoginRequest, req: Request, response: Response):
    """浏览器登录（2026-08-07 改造：支持 MFA 两阶段）。

    响应类型：
    - 成功（普通用户未启用 MFA）：``LoginResponse``
    - MFA 已启用：``MfaChallengeResponse(auth_stage="mfa_required")``
    - 管理员未绑定 MFA：``MfaChallengeResponse(auth_stage="mfa_enrollment_required")``

    返回字典而非 Pydantic 实例以便 FastAPI 不强制按 LoginResponse 校验（不同阶段 schema 不同）。

    验证流程（2026-08-07 改造）：
    1. 校验图形验证码；
    2. 验证用户凭据（失败累计登录锁定）；
    3. 查询 MFA 状态：已绑定 → mfa_required；role=admin 未绑定 → mfa_enrollment_required；
       否则直接签发正式会话（保持原 /login 行为）。

    Args:
        request (LoginRequest): 包含用户名、密码、验证码 key 和验证码的请求对象
        req (Request): FastAPI 请求对象，用于获取客户端 IP
        response (Response): FastAPI 响应对象，用于设置 Cookie

    Returns:
        dict: LoginResponse 或 MfaChallengeResponse（FastAPI 接受 dict 自动序列化）。

    Raises:
        HTTPException: 验证码错误、用户名或密码错误、用户被锁定时抛出
    """
    from app.shared.utils.auth.captcha import captcha_manager
    from app.shared.utils.log_service import (
        LogEvent,
        LogLevel,
        LogResult,
        LogService,
        LogType,
        get_log_service,
    )

    # 简易登录审计事件 emit（fail-soft，emit 失败不影响业务响应）。
    # 迁移自历史审计写入：login_success/login_failure 统一为 action='login'，
    # 通过 result（success/failure）与 level（info/warning）区分；source='auth_router'。
    def _emit_login_event(
        username: str,
        result: LogResult,
        level: LogLevel,
        message: str,
        user_id: Optional[int] = None,
    ) -> None:
        """统一 audit 'login' 事件（fail-soft，emit 失败仅 warning）。

        参数:
            username: 触发登录的用户名（失败时仍记录，便于定位爆破来源）。
            result: success / failure。
            level: info / warning。
            message: 业务描述信息，将写入 ``LogEvent.message``。
            user_id: 已知用户 ID（成功路径取得），失败时为 None。

        返回:
            None。
        """
        svc = get_log_service()
        if svc is None:
            return
        event = LogEvent(
            action="login",
            log_type=LogType.AUTH,
            result=result,
            level=level,
            source="auth_router",
            username=username,
            user_id=user_id,
            ip_address=client_ip,
            message=message,
        )
        try:
            svc.emit(event)
        except Exception as exc:  # pragma: no cover - 防御性 fail-soft
            import logging
            logging.getLogger(__name__).warning(
                "[auth_router] emit login event failed: %s", type(exc).__name__
            )

    client_ip = req.client.host if req.client else "unknown"

    # 校验验证码
    if not captcha_manager.verify(request.captcha_key, request.captcha_code):
        _emit_login_event(
            username=request.username,
            result=LogResult.FAILURE,
            level=LogLevel.WARNING,
            message='验证码错误',
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码错误或已过期"
        )

    # 验证用户凭据
    # 2026-08-07 改造：统一通过 UserDB.verify_credentials 校验；memory 模式与 PG 模式一致。
    # 旧实现依赖 jwt_auth.verify_credentials 的硬编码 admin/123456，仅适合开发态硬编码；
    # 本计划要求"用户可任意创建并登录"，因此改走 UserDB（该方法内部已根据 is_enabled
    # 自动适配 db / memory 路径）。
    from app.shared.utils.auth.user_db import UserDB

    is_valid = await UserDB.verify_credentials(request.username, request.password)

    # 2026-08-07 改造：提前校验锁定状态。锁定期间即使密码正确也必须拒绝（fail-closed）。
    # 仅在已知用户上读取 locked_until；不存在的用户名仍按"凭据错误"处理以避免账号枚举。
    if is_valid:
        existing = await UserDB.get_user_by_username(request.username)
        if existing is not None:
            lock_state = await UserDB.get_login_lock_state(int(existing.get("id")))
            if lock_state.get("locked_until") is not None and lock_state["locked_until"] > time.time():
                _emit_login_event(
                    username=request.username,
                    result=LogResult.FAILURE,
                    level=LogLevel.WARNING,
                    message='用户被锁定',
                    user_id=existing.get("id"),
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="登录失败次数过多，账号已临时锁定",
                )

    # 2026-08-07 批次硬化：MFA 服务不可用时浏览器 /login 一律 fail-closed（503），
    # 即使密码错误也直接 503，避免暴露账号是否存在（反枚举）。
    # 仅在已知用户走 password-OK 路径时把 fail-closed 推到下面；这里在 password-FAIL 路径上
    # 也保证 mfa_service 缺失时不会泄露"账号不存在"信息。
    if not is_valid and getattr(req.app.state, "mfa_service", None) is None:
        _emit_login_event(
            username=request.username,
            result=LogResult.FAILURE,
            level=LogLevel.WARNING,
            message="MFA 服务不可用，fail-closed 拒绝返回凭据错误",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MFA 服务不可用，请联系管理员",
        )

    if not is_valid:
        # 2026-08-07 新增：累计失败计数（5 次后锁 30 分钟，由 ``UserDB.record_failed_login`` 内部处理）。
        # 这里仅在已存在的 user 上累计；不区分 username 是否存在，避免暴露账号是否存在。
        try:
            from app.shared.utils.auth.user_db import UserDB as _UserDB

            try:
                _existing = await _UserDB.get_user_by_username(request.username)
            except Exception:  # noqa: BLE001
                _existing = None
            if _existing is not None:
                # 注意：max_attempts/lockout_seconds 与 mfa_service._settings 优先级一致
                mfa_service_ref = getattr(req.app.state, "mfa_service", None)
                lockout_seconds = (
                    getattr(mfa_service_ref, "_settings", None)
                    and mfa_service_ref._settings.lockout_seconds
                ) or 1800
                max_attempts = (
                    getattr(mfa_service_ref, "_settings", None)
                    and mfa_service_ref._settings.max_attempts
                ) or 5
                # 2026-08-08 修复：早期版本使用 ``DatabasePool.fetchval`` 调用，
                # 而 ``DatabasePool`` 没有 ``fetchval`` 方法导致 ``AttributeError`` 被
                # 外层 ``except Exception: pass`` 静默吞掉，整条登录失败计数链路
                # 静默失效（密码错 12 次后 ``users.failed_login_count`` 仍为 0），
                # 用户表现"几次不锁定"。现改为 fetchrow + 兜底 + 路由层二次判定。
                new_count = await _UserDB.record_failed_login(
                    int(_existing.get("id")),
                    max_attempts=max_attempts,
                    lockout_seconds=lockout_seconds,
                )
                # 兜底二次判定：即便 ``record_failed_login`` 主路径 SQL CASE 漂移
                # 未触发 locked_until 写入，路由层仍基于 new_count 显式拒绝锁定。
                # 同步检查 DB 状态以避免误报（用户已存在 locked_until > now 时
                # 立即短路返回）。
                lock_state = await _UserDB.get_login_lock_state(int(_existing.get("id")))
                now_ts = time.time()
                is_locked = (
                    (lock_state.get("locked_until") is not None
                     and lock_state["locked_until"] > now_ts)
                    or new_count >= max_attempts
                )
                if is_locked:
                    _emit_login_event(
                        username=request.username,
                        result=LogResult.FAILURE,
                        level=LogLevel.WARNING,
                        message='用户被锁定',
                    )
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="登录失败次数过多，账号已临时锁定",
                    )
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            # 2026-08-08 修复：原 ``except Exception: pass`` 完全吞掉失败
            # 累计异常，已被验证导致登录锁定机制彻底静默失效。现改为
            # ``logger.exception``：记录堆栈便于排障，但仍然不能让登录
            # 接口因此返回 5xx（凭据错误本身仍返回 401，避免反枚举特性改变）。
            logger.exception(
                "[auth_router.login] record_failed_login raised: %s", exc
            )

        _emit_login_event(
            username=request.username,
            result=LogResult.FAILURE,
            level=LogLevel.WARNING,
            message='用户名或密码错误',
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

    # 2026-08-07 新增：MFA 两阶段分支。
    # - 普通用户未启用 MFA → 直接签发会话
    # - 普通用户已启用 / 管理员未绑定 → 返回 challenge，不签发 token / cookie
    # - 管理员已绑定：与普通用户走同一 mfa_required 流程
    # 2026-08-07 批次硬化：当 MfaService 不可用（None）或 get_status 抛异常时，
    # 浏览器 /login 必须 fail-closed（503），绝不能签发 access / refresh。
    # 这是普通用户无法判断自己是否"已启用 MFA"的安全门；admin 同样必须 503
    # （强制策略不可被旁路）。
    mfa_service = getattr(req.app.state, "mfa_service", None)
    mfa_status = None
    mfa_service_unavailable = False
    if mfa_service is None:
        mfa_service_unavailable = True
    else:
        try:
            mfa_status = await mfa_service.get_status(user_id=int(user_id), role=role)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[auth_router.login] get_status 异常，按 fail-closed 处理: %s",
                type(exc).__name__,
            )
            mfa_service_unavailable = True

    if mfa_status is not None and mfa_status.enabled:
        # 已绑定 → 验证阶段
        try:
            challenge_token, ttl = await mfa_service.create_login_challenge(
                user_id=int(user_id), purpose="login_verify"
            )
        except Exception:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MFA 服务不可用，请联系管理员",
            )
        _emit_login_event(
            username=request.username,
            result=LogResult.SUCCESS,
            level=LogLevel.INFO,
            message="login mfa_required",
            user_id=user_id,
        )
        return MfaChallengeResponse(
            auth_stage="mfa_required",
            challenge_token=challenge_token,
            challenge_expires_in=ttl,
            mfa_methods=list(mfa_status.methods),
            username=request.username,
        )

    # 已绑定路径不命中；若服务不可用则 fail-closed（避免给未启用用户签发 token）
    if mfa_service_unavailable:
        _emit_login_event(
            username=request.username,
            result=LogResult.FAILURE,
            level=LogLevel.WARNING,
            message="MFA 服务不可用，fail-closed 拒绝签发会话",
            user_id=user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MFA 服务不可用，请联系管理员",
        )

    if mfa_status is not None and mfa_status.required:
        # 管理员未绑定 → 强制绑定的 enrollment challenge
        try:
            challenge_token, ttl = await mfa_service.create_login_challenge(
                user_id=int(user_id), purpose="login_enroll"
            )
        except Exception:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MFA 服务不可用，请联系管理员",
            )
        _emit_login_event(
            username=request.username,
            result=LogResult.SUCCESS,
            level=LogLevel.INFO,
            message="login mfa_enrollment_required",
            user_id=user_id,
        )
        return MfaChallengeResponse(
            auth_stage="mfa_enrollment_required",
            challenge_token=challenge_token,
            challenge_expires_in=ttl,
            mfa_methods=[],
            username=request.username,
        )

    # 成功登录：清零失败计数与锁定状态（覆盖密码路径的成功）
    try:
        await UserDB.clear_login_lock(int(user_id) if user_id else 0)
    except Exception:  # noqa: BLE001
        pass

    # 通过 login_session_service 统一签发完整会话（含 amr）
    from app.shared.utils.auth.login_session_service import issue_browser_login_session

    login_response = await issue_browser_login_session(
        request=req,
        response=response,
        user=user,
        auth_methods=["pwd"],
        app=req.app,
    )

    # 记录登录成功日志
    _emit_login_event(
        username=request.username,
        result=LogResult.SUCCESS,
        level=LogLevel.INFO,
        message='login success',
        user_id=user_id,
    )

    return login_response


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
    from app.shared.utils.log_service import (
        LogEvent,
        LogLevel,
        LogResult,
        LogService,
        LogType,
        get_log_service,
    )

    # 与 login 共用：login_success / login_failure 统一为 action='login'；
    # fail-soft：emit 失败不影响业务 401 响应。
    def _emit_login_api_event(
        username: str,
        result: LogResult,
        level: LogLevel,
        message: str,
        user_id: Optional[int] = None,
    ) -> None:
        """程序化登录场景的审计事件 emit（fail-soft）。

        参数:
            username: 触发登录的用户名。
            result: success / failure。
            level: info / warning。
            message: 业务描述。
            user_id: 用户 ID（成功时为已知值，失败时 None）。

        返回:
            None。
        """
        svc = get_log_service()
        if svc is None:
            return
        event = LogEvent(
            action="login",
            log_type=LogType.AUTH,
            result=result,
            level=level,
            source="auth_router",
            username=username,
            user_id=user_id,
            ip_address=client_ip,
            message=message,
        )
        try:
            svc.emit(event)
        except Exception as exc:  # pragma: no cover - 防御性 fail-soft
            import logging
            logging.getLogger(__name__).warning(
                "[auth_router.login_api] emit login event failed: %s",
                type(exc).__name__,
            )

    client_ip = req.client.host if req.client else "unknown"

    # 验证用户凭据
    if DatabasePool.is_enabled():
        from app.shared.utils.auth.user_db import UserDB
        is_valid = await UserDB.verify_credentials(request.username, request.password)
    else:
        is_valid = await jwt_auth.verify_credentials(request.username, request.password)

    if not is_valid:
        _emit_login_api_event(
            username=request.username,
            result=LogResult.FAILURE,
            level=LogLevel.WARNING,
            message='用户名或密码错误',
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
    cookie_cfg = settings.auth_cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        samesite="strict",
        secure=cookie_cfg.secure,
        path="/api/auth",
        max_age=86400
    )

    # 通过 Set-Cookie 下发 Access Token（HttpOnly，前端 JS 不可读）
    response.set_cookie(
        key=cookie_cfg.access_token_name,
        value=access_token,
        httponly=True,
        samesite=cookie_cfg.samesite,
        secure=cookie_cfg.secure,
        path=cookie_cfg.access_token_path,
        max_age=cookie_cfg.access_token_max_age_seconds,
    )

    # 记录登录成功日志
    _emit_login_api_event(
        username=request.username,
        result=LogResult.SUCCESS,
        level=LogLevel.INFO,
        message='login success',
        user_id=user_id,
    )

    visible_menus = await _compute_visible_menus(req, user_id, role)
    # 2026-07-24 新增：把 allowed_agents 也透传到 LoginResponse
    allowed_agents = await _compute_allowed_agents(
        req,
        user_id,
        role,
        fallback=user.get('allowed_agents', []) if user else [],
    )

    return LoginResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=30,
        role=role,
        username=request.username,
        user_id=user_id,
        visible_menus=visible_menus,
        allowed_agents=allowed_agents,
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
    # 2026-08-07 新增：透传 amr。如果旧 refresh token 携带 amr（如 admin 完成 MFA 后签发），
    # 新 access token 同样携带；旧 token 无 amr 时保持原行为（不写入 amr 字段）。
    amr = payload.get("amr") if isinstance(payload, dict) else None
    access_token = await jwt_auth.generate_token(
        username,
        auth_methods=amr if isinstance(amr, list) else None,
    )

    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 30,
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
    from app.shared.utils.auth.refresh_token_db import RefreshTokenDB

    # 从 request.state 取鉴权信息（auth_middleware 已写入）
    username = getattr(req.state, 'username', None)
    user_id = getattr(req.state, 'user_id', None)
    if not username or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无法识别当前用户"
        )

    # 检查该用户是否仍持有有效的 refresh_token（被踢后会被删除）
    has_refresh = await RefreshTokenDB.has_valid_token(user_id)
    if not has_refresh:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户会话已失效，请重新登录"
        )

    # 先删除该用户所有旧的 portal refresh_token，确保一个用户只有一条记录
    await PortalRefreshTokenDB.delete_user_tokens(user_id)

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

    visible_menus = await _compute_visible_menus(request, user_id, role)

    # 2026-07-24：allowed_agents 改读 user_agent_acl（通过 agent_permission_service），
    # fallback 到 users.allowed_agents 字段（迁移兼容）。
    allowed_agents = await _compute_allowed_agents(
        request,
        user_id,
        role,
        fallback=user.get('allowed_agents', []) if user else [],
    )

    return {
        "username": payload["username"],
        "role": role,
        "user_id": user.get('id') if user else None,
        "allowed_agents": allowed_agents,
        "visible_menus": visible_menus,
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
    from app.shared.utils.Session.SessionCache import session_cache
    from app.shared.utils.auth.refresh_token_db import RefreshTokenDB
    from app.shared.utils.auth.portal_refresh_token_db import PortalRefreshTokenDB
    from app.shared.utils.log_service import (
        LogEvent,
        LogLevel,
        LogResult,
        LogService,
        LogType,
        get_log_service,
    )

    username = getattr(req.state, 'username', None)
    user_id = getattr(req.state, 'user_id', None)
    session_id = req.headers.get('X-Session-ID')
    client_ip = req.client.host if req.client else "unknown"

    # 删除服务端 Refresh Token
    refresh_token = req.cookies.get("refresh_token")
    if refresh_token:
        token_hash = RefreshTokenDB.hash_token(refresh_token)
        await RefreshTokenDB.delete_token(token_hash)

    # 删除该用户所有门户子 refresh_token（防止子 token 残留被第三方利用）
    if user_id:
        await PortalRefreshTokenDB.delete_user_tokens(user_id)

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

    # 记录登出日志（fail-soft，emit 失败不影响业务 200 响应）
    if username:
        svc = get_log_service()
        if svc is not None:
            event = LogEvent(
                action="logout",
                log_type=LogType.AUTH,
                result=LogResult.SUCCESS,
                level=LogLevel.INFO,
                source="auth_router",
                username=username,
                user_id=user_id,
                ip_address=client_ip,
                session_id=session_id,
                message=(
                    f'Session {session_id} 已销毁'
                    if session_id else 'logout'
                ),
            )
            try:
                svc.emit(event)
            except Exception as exc:  # pragma: no cover - 防御性 fail-soft
                import logging
                logging.getLogger(__name__).warning(
                    "[auth_router.logout] emit logout event failed: %s",
                    type(exc).__name__,
                )

    return {"message": "登出成功"}
