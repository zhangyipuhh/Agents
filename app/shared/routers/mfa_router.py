# -*- coding:utf-8 -*-
"""
MFA（TOTP）路由模块（2026-08-07 新增）。

端点（计划契约）：

公开 challenge 端点（仅接受 challenge token，不接受 Access Token，已加入 lifespan 白名单）：

- ``POST /api/auth/mfa/login/verify`` -> 校验 TOTP 或恢复码，成功后签发正式会话
- ``POST /api/auth/mfa/login/enroll/start`` -> 消费 ``login_enroll`` challenge，生成待验证 secret 与新 enrollment challenge
- ``POST /api/auth/mfa/login/enroll/confirm`` -> 验证成功后原子启用 TOTP + 签发会话 + 一次性返回恢复码

已登录端点（Bearer 认证）：

- ``GET  /api/auth/mfa/status`` -> 当前用户的 MFA 状态
- ``POST /api/auth/mfa/totp/enroll/start`` -> 已登录用户绑定 / 轮换
- ``POST /api/auth/mfa/totp/enroll/confirm`` -> 完成启用 / 替换 secret + 撤销 refresh
- ``POST /api/auth/mfa/totp/disable`` -> 仅普通用户可调用；admin 返回 403；撤销 refresh
- ``POST /api/auth/mfa/recovery-codes/regenerate`` -> 重置恢复码（撤销旧码 + 撤销 refresh）

失败响应统一使用 HTTPException(401) / 403 / 503；MFA 服务缺失时所有端点一律 fail-closed
（管理员与已启用用户登录挑战返回 503 / 401）。

所有关键事件通过 ``LogService.emit`` 写入审计日志，字段包括 user / username / ip /
result；不记录 code / secret / challenge / recovery_code 明文。

Author: AI Assistant
Date: 2026-08-07
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.shared.utils.auth.mfa_service import (
    MfaError,
    MfaService,
    MfaStatus,
)
from app.shared.utils.auth.portal_refresh_token_db import PortalRefreshTokenDB
from app.shared.utils.auth.refresh_token_db import RefreshTokenDB
from app.shared.utils.auth.user_db import UserDB

logger = logging.getLogger(__name__)

# ============================================================
# 路由实例
# ============================================================

router = APIRouter(prefix="/api/auth/mfa", tags=["MFA"])

# ============================================================
# 请求 / 响应模型
# ============================================================


class _LoginVerifyRequest(BaseModel):
    challenge_token: str
    code: str
    method: str = Field(pattern="^(totp|recovery_code)$")


class _LoginEnrollStartRequest(BaseModel):
    challenge_token: str


class _LoginEnrollConfirmRequest(BaseModel):
    enrollment_token: str
    code: str


class _LoggedInEnrollStartRequest(BaseModel):
    current_password: str


class _DisableRequest(BaseModel):
    current_password: str
    code: str
    method: str = Field(pattern="^(totp|recovery_code)$")


class _RegenerateRecoveryCodesRequest(BaseModel):
    current_password: str
    code: str
    method: str = Field(pattern="^(totp|recovery_code)$")


# ============================================================
# 内部 helpers
# ============================================================


def _get_mfa_service_or_503(request: Request) -> MfaService:
    """从 ``request.app.state.mfa_service`` 读取 MfaService，缺失时 503 fail-closed。

    Args:
        request: FastAPI request。

    Returns:
        MfaService: 实例。

    Raises:
        HTTPException(503): 服务不可用。
    """
    svc = getattr(request.app.state, "mfa_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MFA 服务不可用，请联系管理员配置 MFA_SECRET_KEY",
        )
    return svc


def _emit_event(
    request: Request,
    action: str,
    result: str,
    level: str,
    message: str,
    username: Optional[str] = None,
    user_id: Optional[int] = None,
) -> None:
    """审计事件 emit（fail-soft，错误仅 warning，不影响业务响应）。

    Args:
        request: FastAPI request。
        action: mfa_enroll / mfa_verify / mfa_disable / mfa_recovery_code。
        result: success / failure。
        level: info / warning。
        message: 业务描述（不含敏感值）。
        username: 可选用户名。
        user_id: 可选用户 ID。

    Returns:
        None。
    """
    try:
        from app.shared.utils.log_service import (
            LogEvent,
            LogLevel,
            LogResult,
            LogService,
            LogType,
            get_log_service,
        )

        svc = get_log_service()
        if svc is None:
            return
        client_ip = getattr(request.client, "host", "unknown") if request.client else "unknown"
        # Map result string → LogResult enum
        result_enum = LogResult.SUCCESS if result == "success" else LogResult.FAILURE
        level_enum = LogLevel.INFO if level == "info" else LogLevel.WARNING
        event = LogEvent(
            action=action,
            log_type=LogType.AUTH,
            result=result_enum,
            level=level_enum,
            source="mfa_router",
            username=username,
            user_id=user_id,
            ip_address=client_ip,
            message=message,
        )
        try:
            svc.emit(event)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[mfa_router] emit %s event failed: %s", action, type(exc).__name__)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[mfa_router] log_service import failed: %s", type(exc).__name__)


def _current_user(request: Request) -> Dict[str, Any]:
    """从 request.state 取得当前用户 dict（admin / 普通用户）。

    Args:
        request: FastAPI request（依赖 auth_middleware 已写入 state）。

    Returns:
        Dict[str, Any]: 用户信息字典（id / username / role）。

    Raises:
        HTTPException 401: 用户身份未识别。
    """
    user_id = getattr(request.state, "user_id", None)
    username = getattr(request.state, "username", None)
    role = getattr(request.state, "role", "user")
    if not user_id or not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无法识别当前用户",
        )
    return {"id": user_id, "username": username, "role": role}


# ============================================================
# 公开 challenge 端点
# ============================================================


@router.post("/login/verify")
async def mfa_login_verify(payload: _LoginVerifyRequest, request: Request, response: Response):
    """校验 TOTP / 恢复码，成功签发正式会话。

    Args:
        payload: ``{"challenge_token", "code", "method"}``。
        request: FastAPI request。
        response: 用于 set_cookie refresh_token。

    Returns:
        LoginResponse（同 /login 成功路径）。

    Raises:
        HTTPException 401 / 503。
    """
    mfa = _get_mfa_service_or_503(request)

    try:
        result = await mfa.verify_login(
            challenge_token=payload.challenge_token,
            code=payload.code,
            method=payload.method,
        )
    except MfaError:
        _emit_event(
            request,
            action="mfa_verify",
            result="failure",
            level="warning",
            message="MFA 校验失败",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MFA 校验失败",
        )

    user_id = int(result["user_id"])
    method_label = result.get("method", payload.method)
    user = await UserDB.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")

    # 完成 MFA 后清零用户失败计数 + 解除锁定
    await UserDB.clear_login_lock(user_id)

    from app.shared.utils.auth.login_session_service import issue_browser_login_session

    # MFA 完成后正式会话：amr=['pwd', method]
    amr = ["pwd", method_label]
    login_response = await issue_browser_login_session(
        request=request,
        response=response,
        user=user,
        auth_methods=amr,
        app=request.app,
    )

    _emit_event(
        request,
        action="mfa_verify",
        result="success",
        level="info",
        message="MFA 校验通过",
        username=user.get("username"),
        user_id=user_id,
    )
    return login_response


@router.post("/login/enroll/start")
async def mfa_login_enroll_start(payload: _LoginEnrollStartRequest, request: Request):
    """消费 ``login_enroll`` challenge，生成待验证 TOTP secret + 新 enrollment challenge。

    Args:
        payload: ``{"challenge_token"}`` (login_enroll 阶段签发的 challenge)。
        request: FastAPI request。

    Returns:
        ``{"enrollment_token", "otpauth_uri", "qr_png_base64", "expires_in"}``。

    Raises:
        HTTPException 401 / 503。
    """
    mfa = _get_mfa_service_or_503(request)

    try:
        enroll = await mfa.start_login_enrollment(
            challenge_token=payload.challenge_token,
        )
    except MfaError:
        raise HTTPException(status_code=401, detail="MFA 校验失败")

    return {
        "enrollment_token": enroll["enrollment_token"],
        "otpauth_uri": enroll["otpauth_uri"],
        "qr_png_base64": enroll["qr_png_base64"],
        "expires_in": enroll["expires_in"],
    }


@router.post("/login/enroll/confirm")
async def mfa_login_enroll_confirm(payload: _LoginEnrollConfirmRequest, request: Request, response: Response):
    """验证 enrollment 阶段 6 位码，成功启用 + 一次性返回恢复码 + 签发正式会话。

    Args:
        payload: ``{"enrollment_token", "code"}``。
        request: FastAPI request。
        response: 用于 set_cookie refresh_token。

    Returns:
        ``{"auth": LoginResponse, "recovery_codes": List[str]}``。

    Raises:
        HTTPException 401 / 503。
    """
    mfa = _get_mfa_service_or_503(request)

    # 公开 API：原子消费 enroll_confirm challenge + 启用 TOTP + 返回恢复码。
    # 任一步骤失败整体回滚，enrollment_token 未被消费，可重试。
    try:
        result = await mfa.confirm_login_enrollment(
            enrollment_token=payload.enrollment_token,
            code=payload.code,
        )
    except MfaError:
        _emit_event(
            request,
            action="mfa_enroll",
            result="failure",
            level="warning",
            message="管理员首次绑定失败",
        )
        raise HTTPException(status_code=401, detail="MFA 校验失败")

    user_id = int(result["user_id"])

    user = await UserDB.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    from app.shared.utils.auth.login_session_service import issue_browser_login_session

    amr = ["pwd", "totp"]
    login_response = await issue_browser_login_session(
        request=request,
        response=response,
        user=user,
        auth_methods=amr,
        app=request.app,
    )

    _emit_event(
        request,
        action="mfa_enroll",
        result="success",
        level="info",
        message="首次绑定 TOTP 成功",
        username=user.get("username"),
        user_id=user_id,
    )

    return {
        "auth": login_response,
        "recovery_codes": result["recovery_codes"],
    }


# ============================================================
# 已登录端点（Bearer 认证）
# ============================================================


async def mfa_status(request: Request) -> MfaStatus:  # noqa: D401
    """获取当前用户的 MFA 状态。"""
    user = _current_user(request)
    mfa = _get_mfa_service_or_503(request)
    return await mfa.get_status(user_id=int(user["id"]), role=user.get("role", "user"))


router.add_api_route(
    path="/status",
    endpoint=mfa_status,
    methods=["GET"],
    response_model=MfaStatus,
)


@router.post("/totp/enroll/start")
async def mfa_totp_enroll_start(
    payload: _LoggedInEnrollStartRequest, request: Request
):
    """已登录用户绑定 / 轮换 TOTP。

    Args:
        payload: ``{"current_password"}``（用于校验）。
        request: FastAPI request。

    Returns:
        ``{"enrollment_token", "otpauth_uri", "qr_png_base64", "secret", "expires_in"}``。
    """
    user = _current_user(request)
    mfa = _get_mfa_service_or_503(request)

    valid = await UserDB.verify_credentials(user["username"], payload.current_password)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="当前密码错误",
        )

    enroll = await mfa.start_enrollment(user_id=int(user["id"]), username=user["username"])
    return {
        "secret": enroll["secret"],
        "enrollment_token": enroll["enrollment_token"],
        "otpauth_uri": enroll["otpauth_uri"],
        "qr_png_base64": enroll["qr_png_base64"],
        "expires_in": enroll["expires_in"],
    }


@router.post("/totp/enroll/confirm")
async def mfa_totp_enroll_confirm(
    payload: _LoginEnrollConfirmRequest, request: Request
):
    """已登录用户确认启用 / 轮换，撤销旧 refresh + 返回恢复码。

    Args:
        payload: ``{"enrollment_token", "code"}``。
        request: FastAPI request。

    Returns:
        ``{"recovery_codes": List[str]}``。
    """
    user = _current_user(request)
    mfa = _get_mfa_service_or_503(request)

    # 公开 API：原子消费 enroll_confirm challenge + 启用 TOTP。
    # 已登录路径同样必须保证原子化（避免错误码后 challenge 被消费但 secret 未启用）。
    try:
        result = await mfa.confirm_login_enrollment(
            enrollment_token=payload.enrollment_token,
            code=payload.code,
        )
    except MfaError:
        _emit_event(
            request,
            action="mfa_enroll",
            result="failure",
            level="warning",
            message="用户绑定 TOTP 失败",
            username=user["username"],
            user_id=int(user["id"]),
        )
        raise HTTPException(status_code=401, detail="MFA 校验失败")

    # 校验返回 user_id 与当前用户匹配（防止 enrollment_token 跨用户复用）
    if int(result.get("user_id", -1)) != int(user["id"]):
        _emit_event(
            request,
            action="mfa_enroll",
            result="failure",
            level="warning",
            message="用户绑定 TOTP 失败：user_id 不匹配",
            username=user["username"],
            user_id=int(user["id"]),
        )
        raise HTTPException(status_code=401, detail="MFA 校验失败")

    # 撤销旧 refresh tokens（主表 + 门户子表）
    await RefreshTokenDB.delete_user_tokens(user_id=int(user["id"]))
    await PortalRefreshTokenDB.delete_user_tokens(user_id=int(user["id"]))

    _emit_event(
        request,
        action="mfa_enroll",
        result="success",
        level="info",
        message="TOTP 启用 / 轮换成功",
        username=user["username"],
        user_id=int(user["id"]),
    )

    return {"recovery_codes": result["recovery_codes"]}


@router.post("/totp/disable")
async def mfa_totp_disable(payload: _DisableRequest, request: Request):
    """禁用 TOTP。仅普通用户可调用；admin 必须返 403。

    Args:
        payload: ``{"current_password", "code", "method"}``。
        request: FastAPI request。

    Returns:
        ``{"success": True}``。
    """
    user = _current_user(request)
    if user.get("role") == "admin":
        # 管理员不能禁用 MFA（强制策略）
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理员账户不允许禁用双因素认证",
        )

    mfa = _get_mfa_service_or_503(request)

    valid = await UserDB.verify_credentials(user["username"], payload.current_password)
    if not valid:
        # 当前密码失败不应写登录失败计数（disable 流程不能因为密码错误把用户锁掉）
        raise HTTPException(status_code=401, detail="当前密码错误")

    # 第二因素校验：必须走公开 API（一次性消费 recovery code，TOTP 不阻塞登录）。
    # 失败不应写登录失败计数（这是 MFA 操作，不是 /login 路径）。
    try:
        await mfa.verify_and_consume_management_factor(
            user_id=int(user["id"]),
            code=payload.code,
            method=payload.method,
            operation="disable",
        )
    except MfaError:
        raise HTTPException(status_code=401, detail="MFA 校验失败")

    await mfa.disable(int(user["id"]))
    # 撤销 refresh（主表 + 门户子表）
    await RefreshTokenDB.delete_user_tokens(user_id=int(user["id"]))
    await PortalRefreshTokenDB.delete_user_tokens(user_id=int(user["id"]))

    _emit_event(
        request,
        action="mfa_disable",
        result="success",
        level="info",
        message="禁用 TOTP 成功",
        username=user["username"],
        user_id=int(user["id"]),
    )
    return {"success": True}


@router.post("/recovery-codes/regenerate")
async def mfa_recovery_codes_regenerate(
    payload: _RegenerateRecoveryCodesRequest, request: Request
):
    """重新生成恢复码（旧码立即失效，撤销 refresh）。

    Args:
        payload: ``{"current_password", "code", "method"}``。
        request: FastAPI request。

    Returns:
        ``{"recovery_codes": List[str]}``。
    """
    user = _current_user(request)
    mfa = _get_mfa_service_or_503(request)

    valid = await UserDB.verify_credentials(user["username"], payload.current_password)
    if not valid:
        # 当前密码失败不应写登录失败计数
        raise HTTPException(status_code=401, detail="当前密码错误")

    # 第二因素校验：必须走公开 API（一次性消费 recovery code，TOTP 不阻塞登录）。
    # 失败不应写登录失败计数。
    try:
        await mfa.verify_and_consume_management_factor(
            user_id=int(user["id"]),
            code=payload.code,
            method=payload.method,
            operation="regenerate_recovery_codes",
        )
    except MfaError:
        raise HTTPException(status_code=401, detail="MFA 校验失败")

    _, plain = await mfa.regenerate_recovery_codes(user_id=int(user["id"]))
    # 撤销 refresh tokens（主表 + 门户子表）
    await RefreshTokenDB.delete_user_tokens(user_id=int(user["id"]))
    await PortalRefreshTokenDB.delete_user_tokens(user_id=int(user["id"]))

    _emit_event(
        request,
        action="mfa_recovery_code",
        result="success",
        level="info",
        message="恢复码重新生成",
        username=user["username"],
        user_id=int(user["id"]),
    )
    return {"recovery_codes": plain}
