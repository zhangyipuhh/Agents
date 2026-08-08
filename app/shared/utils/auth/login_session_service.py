# -*- coding:utf-8 -*-
"""
浏览器登录会话统一签发服务（2026-08-07 新增）。

把 ``/login`` 路径中"密码 + 验证码（+ 可选 MFA）通过后的最终签发流程"
抽离为单一入口，供以下两种调用方复用：

- 浏览器 ``/login`` 一次性成功（普通用户未启用 MFA）
- MFA verify 成功后补发正式会话

职责：

1. 签发 Access Token + Refresh Token（含 amr 标记）
2. 持久化 Refresh Token 到 ``refresh_tokens`` 表（哈希入库）
3. 设置 HttpOnly Refresh Cookie
4. 组装可见菜单 + 已授权智能体（visible_menus / allowed_agents）
5. 返回 ``LoginResponse`` 给调用方

与 ``/login-api`` 不共享：``/login-api`` 在原 ``auth_router`` 保持不动，本服务
仅服务于浏览器 ``/login`` 流程（计划 V1 明确边界）。

Author: AI Assistant
Date: 2026-08-07
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Union

from fastapi import Request, Response

from app.shared.utils.auth.Safety import jwt_auth

logger = logging.getLogger(__name__)


# ============================================================
# 公共入口
# ============================================================


async def issue_browser_login_session(
    request: Request,
    response: Response,
    user: dict,
    auth_methods: Sequence[str],
    app: Any,
) -> Any:
    """为浏览器 ``/login`` 流程签发完整会话。

    Args:
        request: FastAPI Request。
        response: FastAPI Response，用于 set_cookie refresh_token。
        user: 用户信息字典（含 ``id`` / ``username`` / ``role`` / ``allowed_agents`` /
            ``refresh_token ttl``）。
        auth_methods: 认证方法列表（``["pwd"]`` / ``["pwd","totp"]`` /
            ``["pwd","recovery_code"]`` 等）。
        app: FastAPI 应用实例（用于读取 menu/agent service state）。

    Returns:
        LoginResponse（来自 auth_router）。

    Raises:
        RuntimeError: 内部错误（如 RefreshTokenDB.store_token 失败时）。
    """
    from app.shared.utils.auth.refresh_token_db import RefreshTokenDB
    from app.shared.routers.auth_router import LoginResponse

    username: str = user["username"]
    user_id: Optional[int] = user.get("id")
    role: str = user.get("role", "user")
    amr_list: List[str] = list(auth_methods) if auth_methods else []

    # 1) 签发 Access Token（含 amr）
    access_token = await jwt_auth.generate_token(username, auth_methods=amr_list or None)

    # 2) 签发 Refresh Token（含 amr，供 /refresh 透传到新 access_token）
    refresh_token = await jwt_auth.generate_refresh_token(
        username, auth_methods=amr_list or None
    )
    token_hash = RefreshTokenDB.hash_token(refresh_token)
    expires_at = datetime.utcnow() + timedelta(hours=24)
    stored = await RefreshTokenDB.store_token(token_hash, user_id, expires_at)
    if not stored:
        # store_token 已 fail-soft 但仍断言
        raise RuntimeError("refresh_tokens 表写入失败")

    # 3) Set-Cookie（HttpOnly + SameSite=Strict + Path=/api/auth）
    from app.core.config.settings import settings

    cookie_cfg = settings.auth_cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        samesite="strict",
        secure=cookie_cfg.secure,
        path="/api/auth",
        max_age=86400,
    )

    # 同步下发 Access Token Cookie（HttpOnly，前端 JS 不可读）
    # 程序化客户端仍可从 JSON body 取 access_token，二者并存。
    response.set_cookie(
        key=cookie_cfg.access_token_name,
        value=access_token,
        httponly=True,
        samesite=cookie_cfg.samesite,
        secure=cookie_cfg.secure,
        path=cookie_cfg.access_token_path,
        max_age=cookie_cfg.access_token_max_age_seconds,
    )

    # 4) visible_menus
    visible_menus = await _compute_visible_menus_for_session(app, user_id, role)

    # 5) allowed_agents
    allowed_agents = await _compute_allowed_agents_for_session(
        app,
        user_id,
        role,
        fallback=user.get("allowed_agents", []),
    )

    return LoginResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=30,
        role=role,
        username=username,
        user_id=user_id,
        visible_menus=visible_menus,
        allowed_agents=allowed_agents,
    )


# ============================================================
# 内部 helpers（与 auth_router 内联的 _compute_visible_menus / _compute_allowed_agents 契约对齐）
# ============================================================


async def _compute_visible_menus_for_session(
    app: Any,
    user_id: Optional[int],
    role: str,
) -> List[str]:
    """计算 visible_menus：admin 全量；普通用户通过 menu_permission_service。

    Args:
        app: FastAPI app（用于 state.menu_permission_service）。
        user_id: 用户 ID。
        role: 用户角色。

    Returns:
        List[str]: 菜单 id 列表。
    """
    from app.core.menu_registry import get_enabled_items

    if role == "admin":
        return [m.id for m in sorted(get_enabled_items(), key=lambda m: m.sort_order)]
    svc = getattr(app.state, "menu_permission_service", None)
    if svc is None:
        # fail-secure：service 不可用仅返回 ['profile']
        return ["profile"]
    uid = user_id if user_id is not None else 0
    return await svc.get_visible_menu_ids(user_id=uid, is_admin=False)


async def _compute_allowed_agents_for_session(
    app: Any,
    user_id: Optional[int],
    role: str,
    fallback: Optional[Sequence[str]] = None,
) -> List[str]:
    """计算 allowed_agents：admin []；普通用户从 agent_permission_service 读。

    Args:
        app: FastAPI app。
        user_id: 用户 ID。
        role: 用户角色。
        fallback: service 不可用时的兜底（一般是 users.allowed_agents 旧字段）。

    Returns:
        List[str]: 已授权 agent_name 列表。
    """
    if role == "admin":
        return []
    if user_id is None:
        return []
    svc = getattr(app.state, "agent_permission_service", None)
    if svc is None:
        return list(fallback) if fallback else []
    granted = svc.get_user_agent_grants_sync(user_id)
    if not granted and fallback:
        return list(fallback)
    return sorted(granted)
