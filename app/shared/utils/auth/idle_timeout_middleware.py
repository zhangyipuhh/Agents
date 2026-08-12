#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Idle 超时中间件（等保三级 §1.5，2026-08-12 新增）

职责：
1. 从请求 Cookie ``login_session_uuid`` 提取会话标识
2. 调用 ``UserLoginSessionService.check_idle`` 校验是否 idle 超时
3. 超时 → 返回 401 + ``{"code": "idle_timeout"}``
4. 通过 → 异步 fire-and-forget 刷新 ``last_active_at``（不阻塞响应）

设计原则：
- 失败路径 fail-loud：``check_idle`` 内部抛异常 → 严格模式拒绝请求；宽松模式放行
- 性能优先：``touch_last_active`` 是异步 fire-and-forget，写库失败仅记 ERROR 日志
- 不触发对未登录路径（白名单）的 DB 查询
- 中间件顺序：session_auth → idle_timeout → auth_middleware
  保证 idle 在 JWT 验签通过后执行，避免无 token 请求触发 DB 查询
"""

import asyncio
import logging
from typing import Awaitable, Callable

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.core.config.settings import settings
from app.shared.utils.auth.Safety import jwt_auth
from app.shared.utils.auth.user_login_session_service import (
    user_login_session_service,
)

logger = logging.getLogger(__name__)


# Cookie 名常量（与 login_session_service 签发处一致）
LOGIN_SESSION_COOKIE_NAME = "login_session_uuid"


def _is_path_exempt(path: str, exempt_paths: list) -> bool:
    """
    检查路径是否在 idle 检测豁免列表中。

    Args:
        path: 请求路径。
        exempt_paths: 豁免路径列表。

    Returns:
        bool: 在豁免列表中返回 True。
    """
    if not exempt_paths:
        return False
    for prefix in exempt_paths:
        if path == prefix or path.startswith(prefix):
            return True
    return False


async def idle_timeout_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable],
):
    """
    FastAPI HTTP 中间件：校验用户登录会话 idle 超时。

    Args:
        request: FastAPI Request。
        call_next: 下一个中间件 / 路由 handler。

    Returns:
        Response: 路由响应 / 401 idle_timeout。
    """
    path = request.url.path

    # 配置读取（每次请求读取；settings 是单例，开销可忽略）
    idle_cfg = settings.auth_idle
    if not idle_cfg.check_enabled:
        # 关闭 idle 检测时直接放行（降级为仅 JWT exp 绝对过期）
        return await call_next(request)

    # 1. JWT 白名单路径不触发 idle 检测（与 session_auth_middleware 一致）
    if jwt_auth.is_whitelisted(path):
        return await call_next(request)

    # 2. 豁免路径（如 /api/auth/login、/api/auth/refresh）不触发 idle 检测
    if _is_path_exempt(path, idle_cfg.check_exempt_paths):
        return await call_next(request)

    # 3. 未携带 session_uuid Cookie → 视为未登录，由下游 auth_middleware 处理
    session_uuid = request.cookies.get(LOGIN_SESSION_COOKIE_NAME)
    if not session_uuid:
        return await call_next(request)

    # 4. 校验 idle
    try:
        is_expired, last_active = await user_login_session_service.check_idle(
            session_uuid, idle_cfg.timeout_seconds
        )
    except RuntimeError as exc:
        # 数据库不可用。fail_loud=True → 拒绝请求；fail_loud=False → 放行（不符合等保）
        if idle_cfg.check_fail_loud:
            logger.exception(
                "[idle_timeout_middleware] 数据库失败且 fail_loud=True, 拒绝请求 path=%s", path
            )
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "detail": "会话状态服务暂时不可用,请稍后重试",
                    "code": "idle_check_unavailable",
                },
            )
        logger.error(
            "[idle_timeout_middleware] 数据库失败且 fail_loud=False, 静默放行 path=%s err=%s",
            path,
            exc,
        )
        return await call_next(request)

    if is_expired:
        logger.info(
            "[idle_timeout_middleware] idle 超时拒绝请求 path=%s session_uuid=%s last_active=%s",
            path,
            session_uuid[:12] + "***",
            last_active,
        )
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "detail": "会话因长时间无操作已过期,请重新登录",
                "code": "idle_timeout",
            },
        )

    # 5. 通过 → 异步刷新 last_active_at（fire-and-forget，不阻塞响应）
    async def _safe_touch():
        try:
            await user_login_session_service.touch_last_active(session_uuid)
        except Exception as exc:  # noqa: BLE001
            # touch 失败仅日志告警，不影响本次响应
            logger.error(
                "[idle_timeout_middleware] 刷新 last_active_at 失败 session_uuid=%s err=%s",
                session_uuid[:12] + "***",
                exc,
            )

    # 调度后台任务；响应已下发后继续执行（FastAPI 后台任务机制）
    asyncio.create_task(_safe_touch())

    return await call_next(request)
