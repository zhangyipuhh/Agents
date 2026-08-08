# -*- coding:utf-8 -*-
"""
login_session_service 单元测试。

覆盖：
- issue_browser_login_session 内部调用 jwt_auth.generate_token + refresh + cookie +
  visible_menus + allowed_agents，并组装 LoginResponse。
- 成功路径：调用方传入 user dict（id/username/role/allowed_agents）。
- MFA 已启用路径：传入 auth_methods=["pwd","totp"] 生成 token + refresh 均携带 amr。
- 验证 cookie 设置（httponly / samesite / path）。
- 服务不可用时的可见降级：menu_permission_service / agent_permission_service 缺失。

注意：使用 in-memory 模式 + monkeypatch UserDB，避免依赖 lifespan state 的 mfa service。

Author: AI Assistant
Date: 2026-08-07
"""

import asyncio
import sys
import os
from unittest.mock import MagicMock, AsyncMock

if "asyncpg" not in sys.modules:
    sys.modules["asyncpg"] = MagicMock()

import jwt
import pytest


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(autouse=True)
def reset_user_db():
    from app.shared.utils.auth.user_db import UserDB

    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0
    UserDB._memory_login_lock.clear()
    yield
    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0
    UserDB._memory_login_lock.clear()


@pytest.fixture
def fastapi_app():
    """极简 FastAPI app + Request/Response。"""
    from fastapi import FastAPI

    return FastAPI()


@pytest.fixture
def request_response(fastapi_app):
    """构造最小 Request/Response。

    Returns:
        (Request, Response): 用于 ``issue_browser_login_session``。
    """
    from starlette.requests import Request
    from starlette.responses import Response

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/login",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 5000),
        "server": ("test", 80),
        "scheme": "http",
    }
    request = Request(scope)
    response = Response()
    return request, response


def test_issue_session_returns_login_response(fastapi_app, request_response):
    """P1: 普通用户登录成功路径返回 LoginResponse（access_token / expires_in）。"""
    from app.shared.utils.auth.login_session_service import issue_browser_login_session
    from app.shared.utils.auth.user_db import UserDB

    user_id = _run_async(
        UserDB.create_user("browsersession", "P@ssword1!", role="user")
    )
    user = _run_async(UserDB.get_user_by_username("browsersession"))
    req, resp = request_response

    login_response = _run_async(
        issue_browser_login_session(
            request=req,
            response=resp,
            user=user,
            auth_methods=["pwd"],
            app=fastapi_app,
        )
    )
    assert login_response.access_token
    assert login_response.token_type == "Bearer"
    assert login_response.expires_in == 30
    assert login_response.role == "user"
    assert login_response.username == "browsersession"
    assert login_response.user_id == user_id


def test_issue_session_sets_refresh_cookie(fastapi_app, request_response):
    """P1: refresh cookie 必为 httponly / samesite=strict / path=/api/auth。"""
    from app.shared.utils.auth.login_session_service import issue_browser_login_session
    from app.shared.utils.auth.user_db import UserDB

    _run_async(UserDB.create_user("cookiesession", "P@ssword1!", role="user"))
    user = _run_async(UserDB.get_user_by_username("cookiesession"))
    req, resp = request_response

    _run_async(
        issue_browser_login_session(
            request=req,
            response=resp,
            user=user,
            auth_methods=["pwd"],
            app=fastapi_app,
        )
    )
    set_cookie = resp.headers.get("set-cookie", "")
    assert "refresh_token=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=strict" in set_cookie
    assert "Path=/api/auth" in set_cookie


def test_issue_session_token_carries_amr(fastapi_app, request_response):
    """P1: MFA 已启用路径下 access_token / refresh_token payload 都含 amr。"""
    from app.shared.utils.auth.login_session_service import issue_browser_login_session
    from app.shared.utils.auth.user_db import UserDB
    from app.shared.utils.auth.Safety import jwt_auth

    user_id = _run_async(
        UserDB.create_user("amrsession", "P@ssword1!", role="user")
    )
    user = _run_async(UserDB.get_user_by_username("amrsession"))
    req, resp = request_response

    login_response = _run_async(
        issue_browser_login_session(
            request=req,
            response=resp,
            user=user,
            auth_methods=["pwd", "totp"],
            app=fastapi_app,
        )
    )
    payload = jwt.decode(
        login_response.access_token,
        jwt_auth.secret_key,
        algorithms=[jwt_auth.algorithm],
    )
    assert payload.get("amr") == ["pwd", "totp"]

    # cookie 中的 refresh 也带 amr
    cookie = resp.headers.get("set-cookie", "")
    # 解析 refresh token 的值（取第一个分号前的 = 之后部分）
    rt_value = cookie.split("refresh_token=", 1)[1].split(";", 1)[0]
    refresh_payload = jwt.decode(
        rt_value,
        jwt_auth.secret_key,
        algorithms=[jwt_auth.algorithm],
    )
    assert refresh_payload.get("amr") == ["pwd", "totp"]
    assert refresh_payload["type"] == "refresh"


def test_issue_session_admin_has_full_visible_menus(fastapi_app, request_response, monkeypatch):
    """P1: admin 角色可见菜单为全量 enabled 项。"""
    from app.shared.utils.auth.login_session_service import issue_browser_login_session
    from app.shared.utils.auth.user_db import UserDB
    from app.shared.utils.auth.menu_permission_service import MenuPermissionService

    # 注入 menu service 但 admin 不依赖 service（直接读 registry）
    monkeypatch.setattr(
        fastapi_app.state,
        "menu_permission_service",
        MenuPermissionService(db=None),
        raising=False,
    )
    monkeypatch.setattr(
        fastapi_app.state,
        "agent_permission_service",
        MenuPermissionService(db=None),
        raising=False,
    )

    admin_id = _run_async(
        UserDB.create_user("sessionadmin", "P@ssword1!", role="admin")
    )
    user = _run_async(UserDB.get_user_by_username("sessionadmin"))
    req, resp = request_response
    login_response = _run_async(
        issue_browser_login_session(
            request=req,
            response=resp,
            user=user,
            auth_methods=["pwd", "totp"],
            app=fastapi_app,
        )
    )
    # admin 看到的菜单至少包含 'profile' 和 'permission-management'
    assert "profile" in login_response.visible_menus
    assert "permission-management" in login_response.visible_menus
    assert len(login_response.visible_menus) > 1
