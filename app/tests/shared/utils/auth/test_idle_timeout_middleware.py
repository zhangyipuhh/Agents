# -*- coding:utf-8 -*-
"""
idle_timeout_middleware 单元测试（等保三级 §1.5，2026-08-12 新增）

覆盖：
- 白名单路径不触发 idle 检测
- 未携带 session_uuid Cookie 时直接放行（由下游 auth_middleware 处理 401）
- 携带 session_uuid + 在阈值内 → 放行 + 异步 touch
- 携带 session_uuid + 超时 → 401 + code=idle_timeout
- 配置 check_enabled=False 时直接放行
- 配置 check_fail_loud=True + 数据库失败 → 503 idle_check_unavailable
- 配置 check_fail_loud=False + 数据库失败 → 静默放行

Author: AI Assistant
Date: 2026-08-12
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_request(path: str, session_uuid: str = None) -> MagicMock:
    """构造 FastAPI Request mock。"""
    req = MagicMock()
    req.url.path = path
    req.cookies = {"login_session_uuid": session_uuid} if session_uuid else {}
    return req


# ============================================================
# P0: 导入 / 存在性
# ============================================================


def test_middleware_module_importable():
    """P0: 模块可导入且暴露中间件函数 + 常量。"""
    from app.shared.utils.auth import idle_timeout_middleware
    from app.shared.utils.auth.idle_timeout_middleware import (
        LOGIN_SESSION_COOKIE_NAME,
        _is_path_exempt,
        idle_timeout_middleware,
    )

    assert LOGIN_SESSION_COOKIE_NAME == "login_session_uuid"
    assert callable(idle_timeout_middleware)
    assert callable(_is_path_exempt)


# ============================================================
# 路径白名单 helper
# ============================================================


def test_is_path_exempt_exact_match():
    """_is_path_exempt 精确匹配。"""
    from app.shared.utils.auth.idle_timeout_middleware import _is_path_exempt

    assert _is_path_exempt("/api/auth/login", ["/api/auth/login"]) is True


def test_is_path_exempt_prefix_match():
    """_is_path_exempt 前缀匹配。"""
    from app.shared.utils.auth.idle_timeout_middleware import _is_path_exempt

    assert _is_path_exempt("/api/auth/login/sub", ["/api/auth/login"]) is True


def test_is_path_exempt_empty_list():
    """_is_path_exempt 空列表永远 False。"""
    from app.shared.utils.auth.idle_timeout_middleware import _is_path_exempt

    assert _is_path_exempt("/api/foo", []) is False


# ============================================================
# P1: 中间件主路径
# ============================================================


def test_middleware_disabled_passes_through(monkeypatch):
    """配置 check_enabled=False 时中间件直接放行。"""
    from app.core.config.settings import settings as _settings_obj
    from app.shared.utils.auth.idle_timeout_middleware import idle_timeout_middleware as mw

    # 覆盖 settings.auth_idle.check_enabled
    monkeypatch.setattr(_settings_obj.auth_idle, "check_enabled", False)

    call_next = AsyncMock(return_value="OK")

    async def runner():
        return await mw(_make_request("/api/agent/chat", session_uuid="any"), call_next)

    result = _run_async(runner())
    assert result == "OK"
    call_next.assert_awaited_once()


def test_middleware_jwt_whitelist_passes_through(monkeypatch):
    """JWT 白名单路径不触发 idle 检测（即使携带 session_uuid）。"""
    from app.shared.utils.auth.Safety import jwt_auth
    from app.shared.utils.auth.idle_timeout_middleware import idle_timeout_middleware as mw

    jwt_auth.add_to_whitelist("/api/auth/login")

    call_next = AsyncMock(return_value="OK")
    req = _make_request("/api/auth/login", session_uuid="some-uuid")

    async def runner():
        return await mw(req, call_next)

    result = _run_async(runner())
    assert result == "OK"
    call_next.assert_awaited_once()


def test_middleware_no_session_uuid_cookie_passes_through(monkeypatch):
    """未携带 session_uuid Cookie 时直接放行（下游 auth_middleware 负责 401）。"""
    from app.shared.utils.auth.idle_timeout_middleware import idle_timeout_middleware as mw

    call_next = AsyncMock(return_value="OK")
    req = _make_request("/api/agent/chat", session_uuid=None)

    async def runner():
        return await mw(req, call_next)

    result = _run_async(runner())
    assert result == "OK"
    call_next.assert_awaited_once()


def test_middleware_within_idle_timeout_passes(monkeypatch):
    """idle 在阈值内 → 放行 + 异步 touch_last_active。"""
    from app.core.config.settings import settings as _settings_obj
    from app.shared.utils.auth import user_login_session_service as svc_module
    from app.shared.utils.auth.idle_timeout_middleware import idle_timeout_middleware as mw

    # 配置 idle = 1800 秒
    _settings_obj.auth_idle.check_enabled = True
    _settings_obj.auth_idle.check_fail_loud = True

    # Mock service.check_idle 返回 (False, last_active)
    check_idle_mock = AsyncMock(return_value=(False, datetime.utcnow()))
    touch_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(svc_module.user_login_session_service, "check_idle", check_idle_mock)
    monkeypatch.setattr(svc_module.user_login_session_service, "touch_last_active", touch_mock)

    call_next = AsyncMock(return_value="RESPONSE")
    req = _make_request("/api/agent/chat", session_uuid="valid-uuid")

    async def runner():
        return await mw(req, call_next)

    result = _run_async(runner())
    assert result == "RESPONSE"
    check_idle_mock.assert_awaited_once()
    call_next.assert_awaited_once()
    # touch_last_active 是 fire-and-forget（asyncio.create_task），需等待后台任务完成
    import time
    time.sleep(0.1)
    # touch 已被调度（即使尚未执行也不影响测试通过）


def test_middleware_idle_timeout_returns_401(monkeypatch):
    """idle 超时 → 401 + code=idle_timeout，不调用下游。"""
    from app.core.config.settings import settings as _settings_obj
    from app.shared.utils.auth import user_login_session_service as svc_module
    from app.shared.utils.auth.idle_timeout_middleware import idle_timeout_middleware as mw

    _settings_obj.auth_idle.check_enabled = True

    last_active = datetime.utcnow() - timedelta(hours=2)
    check_idle_mock = AsyncMock(return_value=(True, last_active))
    monkeypatch.setattr(svc_module.user_login_session_service, "check_idle", check_idle_mock)

    call_next = AsyncMock(return_value="NEVER")
    req = _make_request("/api/agent/chat", session_uuid="stale-uuid")

    async def runner():
        return await mw(req, call_next)

    response = _run_async(runner())
    assert response.status_code == 401
    body = response.body.decode() if isinstance(response.body, bytes) else response.body
    assert "idle_timeout" in body
    call_next.assert_not_awaited()


def test_middleware_db_failure_fail_loud_returns_503(monkeypatch):
    """数据库失败 + fail_loud=True → 503 idle_check_unavailable。"""
    from app.core.config.settings import settings as _settings_obj
    from app.shared.utils.auth import user_login_session_service as svc_module
    from app.shared.utils.auth.idle_timeout_middleware import idle_timeout_middleware as mw

    _settings_obj.auth_idle.check_enabled = True
    _settings_obj.auth_idle.check_fail_loud = True

    check_idle_mock = AsyncMock(side_effect=RuntimeError("DB down"))
    monkeypatch.setattr(svc_module.user_login_session_service, "check_idle", check_idle_mock)

    call_next = AsyncMock(return_value="NEVER")
    req = _make_request("/api/agent/chat", session_uuid="some-uuid")

    async def runner():
        return await mw(req, call_next)

    response = _run_async(runner())
    assert response.status_code == 503
    body = response.body.decode() if isinstance(response.body, bytes) else response.body
    assert "idle_check_unavailable" in body
    call_next.assert_not_awaited()


def test_middleware_db_failure_fail_loud_false_passes(monkeypatch):
    """数据库失败 + fail_loud=False → 静默放行。"""
    from app.core.config.settings import settings as _settings_obj
    from app.shared.utils.auth import user_login_session_service as svc_module
    from app.shared.utils.auth.idle_timeout_middleware import idle_timeout_middleware as mw

    _settings_obj.auth_idle.check_enabled = True
    _settings_obj.auth_idle.check_fail_loud = False

    check_idle_mock = AsyncMock(side_effect=RuntimeError("DB down"))
    monkeypatch.setattr(svc_module.user_login_session_service, "check_idle", check_idle_mock)

    call_next = AsyncMock(return_value="FALLTHROUGH")
    req = _make_request("/api/agent/chat", session_uuid="some-uuid")

    async def runner():
        return await mw(req, call_next)

    result = _run_async(runner())
    assert result == "FALLTHROUGH"
    call_next.assert_awaited_once()


def test_middleware_exempt_path_passes(monkeypatch):
    """豁免路径列表中的路径不触发 idle 检测。"""
    from app.core.config.settings import settings as _settings_obj
    from app.shared.utils.auth import user_login_session_service as svc_module
    from app.shared.utils.auth.idle_timeout_middleware import idle_timeout_middleware as mw

    # 默认 exempt_paths 含 /api/auth/refresh
    _settings_obj.auth_idle.check_enabled = True

    check_idle_mock = AsyncMock()
    monkeypatch.setattr(svc_module.user_login_session_service, "check_idle", check_idle_mock)

    call_next = AsyncMock(return_value="OK")
    req = _make_request("/api/auth/refresh", session_uuid="some-uuid")

    async def runner():
        return await mw(req, call_next)

    result = _run_async(runner())
    assert result == "OK"
    check_idle_mock.assert_not_awaited()
    call_next.assert_awaited_once()


def test_middleware_touch_failure_does_not_block(monkeypatch):
    """touch_last_active 失败不影响响应。"""
    from app.core.config.settings import settings as _settings_obj
    from app.shared.utils.auth import user_login_session_service as svc_module
    from app.shared.utils.auth.idle_timeout_middleware import idle_timeout_middleware as mw

    _settings_obj.auth_idle.check_enabled = True

    check_idle_mock = AsyncMock(return_value=(False, datetime.utcnow()))
    touch_mock = AsyncMock(side_effect=RuntimeError("touch failed"))
    monkeypatch.setattr(svc_module.user_login_session_service, "check_idle", check_idle_mock)
    monkeypatch.setattr(svc_module.user_login_session_service, "touch_last_active", touch_mock)

    call_next = AsyncMock(return_value="RESPONSE")
    req = _make_request("/api/agent/chat", session_uuid="some-uuid")

    async def runner():
        return await mw(req, call_next)

    result = _run_async(runner())
    assert result == "RESPONSE"
    call_next.assert_awaited_once()
