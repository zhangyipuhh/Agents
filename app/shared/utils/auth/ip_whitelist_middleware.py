# -*- coding:utf-8 -*-
"""IP 白名单中间件(注册审批 + IP 白名单,2026-08-30 新增,等保三级 §7.1.3 a)

职责:
1. 仅拦截 POST /api/auth/register(及带斜杠变体)路径
2. 读取 nginx 写入的 X-Real-IP header(**不读** X-Forwarded-For,可被伪造)
3. 缺失 / 非法 / 不在白名单 → 403
4. 通过 → 注入 request.state.client_ip 供下游 register 路由使用
5. 拦截事件写审计日志(register_ip_blocked)

设计原则:
- 配置关闭(enabled=False)时完全放行,行为与现状一致
- X-Real-IP 缺失按 fail-closed 拒绝(不允许绕过 nginx 直连 uvicorn)
- 白名单使用 ipaddress 标准库做 CIDR 匹配
"""
import ipaddress
import logging
from typing import Awaitable, Callable

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.core.config.settings import settings

logger = logging.getLogger(__name__)

# 仅拦注册路径的前缀。login/login-api/refresh 不拦(与设计决策对齐)
_REGISTER_PATH = "/api/auth/register"


def _ip_in_whitelist(client_ip: str, whitelist: list) -> bool:
    """检查 client_ip 是否匹配白名单中任一 CIDR。"""
    try:
        addr = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for cidr in whitelist:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
            if addr in network:
                return True
        except ValueError:
            logger.warning(
                "[ip_whitelist_middleware] 白名单条目非法 CIDR: %r,跳过", cidr
            )
    return False


def _emit_blocked_log(client_ip: str) -> None:
    """IP 被拦截时写审计日志(fail-soft)。"""
    try:
        from app.shared.utils.log_service import (
            LogEvent,
            LogLevel,
            LogResult,
            LogType,
            get_log_service,
        )
        svc = get_log_service()
        if svc is None:
            return
        event = LogEvent(
            action="register_ip_blocked",
            log_type=LogType.AUTH,
            result=LogResult.FAILURE,
            level=LogLevel.WARNING,
            source="ip_whitelist_middleware",
            ip_address=client_ip,
            message=f"注册接口 IP 白名单拦截 client_ip={client_ip}",
        )
        svc.emit(event)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[ip_whitelist_middleware] 审计日志 emit 失败: %s", type(exc).__name__
        )


async def ip_whitelist_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable],
):
    """FastAPI HTTP 中间件:注册路径 IP 白名单校验。"""
    cfg = settings.registration_security
    if not cfg.enabled:
        return await call_next(request)

    path = request.url.path
    if not (path == _REGISTER_PATH or path.startswith(_REGISTER_PATH + "/")):
        return await call_next(request)

    client_ip = request.headers.get("X-Real-IP")
    if not client_ip:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "无法识别客户端来源 IP,请通过反向代理访问"},
        )

    try:
        ipaddress.ip_address(client_ip)
    except ValueError:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "客户端 IP 格式非法"},
        )

    if not _ip_in_whitelist(client_ip, cfg.ip_whitelist):
        _emit_blocked_log(client_ip)
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "当前网络不允许注册,如有疑问请联系管理员"},
        )

    request.state.client_ip = client_ip
    return await call_next(request)
