# -*- coding:utf-8 -*-
"""
Safety 模块单元测试

测试 JWTAuth 的令牌生成、验证、白名单以及 auth_middleware 对 refresh token 的拦截。
"""
import asyncio
import json
import sys
from unittest.mock import MagicMock

# 环境可能未安装 asyncpg，预先 mock 以避免导入链失败
if "asyncpg" not in sys.modules:
    sys.modules["asyncpg"] = MagicMock()

import jwt
import pytest
from fastapi import Request

from app.shared.utils.auth.Safety import (
    JWTAuth,
    SESSION_WHITELIST_PREFIXES,
    jwt_auth,
    auth_middleware,
)


def _run_async(coro):
    """辅助函数：在新的事件循环中运行异步协程"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_jwt_auth_generate_token(jwt_auth):
    """
    测试 JWTAuth.generate_token 返回非空字符串

    Args:
        jwt_auth: JWTAuth 实例（来自 conftest）

    Returns:
        None
    """
    token = _run_async(jwt_auth.generate_token("testuser"))
    assert isinstance(token, str)
    assert len(token) > 0


def test_jwt_auth_decode_token(jwt_auth):
    """
    测试使用真实 jwt.decode 正确解析 generate_token 生成的 payload

    Args:
        jwt_auth: JWTAuth 实例（来自 conftest）

    Returns:
        None
    """
    token = _run_async(jwt_auth.generate_token("testuser"))
    payload = jwt.decode(token, jwt_auth.secret_key, algorithms=[jwt_auth.algorithm])
    assert payload["username"] == "testuser"
    assert payload["type"] == "access"
    assert "exp" in payload
    assert "iat" in payload


def test_whitelist_add_and_check(jwt_auth):
    """
    测试白名单的添加和检查功能

    Args:
        jwt_auth: JWTAuth 实例（来自 conftest）

    Returns:
        None
    """
    path = "/api/test/whitelist"
    assert not jwt_auth.is_whitelisted(path)
    jwt_auth.add_to_whitelist(path)
    assert jwt_auth.is_whitelisted(path)


def test_verify_credentials_memory_mode(jwt_auth):
    """
    测试 memory 模式下 verify_credentials 验证硬编码凭据（admin/123456）

    Args:
        jwt_auth: JWTAuth 实例（来自 conftest）

    Returns:
        None
    """
    result = _run_async(jwt_auth.verify_credentials("admin", "123456"))
    assert result is True

    result_wrong = _run_async(jwt_auth.verify_credentials("admin", "wrong_password"))
    assert result_wrong is False


def test_refresh_token_rejected_by_auth_middleware(jwt_auth):
    """
    测试 type=refresh 的 token 被 auth_middleware 拒绝

    构造一个携带 refresh token 的 mock Request，验证中间件返回 401。

    Args:
        jwt_auth: JWTAuth 实例（来自 conftest）

    Returns:
        None
    """
    refresh_token = _run_async(jwt_auth.generate_refresh_token("admin"))

    request = MagicMock(spec=Request)
    request.url.path = "/api/protected"
    request.headers.get.return_value = f"Bearer {refresh_token}"

    async def mock_call_next(request):
        from fastapi.responses import JSONResponse
        return JSONResponse(content={"ok": True})

    response = _run_async(auth_middleware(request, mock_call_next))

    assert response.status_code == 401
    body = json.loads(response.body)
    assert "无效的令牌类型" in body["detail"]


def test_authenticate_sets_allowed_agents(jwt_auth, monkeypatch):
    """
    测试 JWTAuth.authenticate 将 allowed_agents 写入 request.state。

    Args:
        jwt_auth: JWTAuth 实例（来自 conftest）
        monkeypatch: pytest monkeypatch fixture

    Returns:
        None
    """
    access_token = _run_async(jwt_auth.generate_token("testuser"))

    async def fake_get_user(username):
        return {
            "id": 2,
            "username": "testuser",
            "role": "user",
            "allowed_agents": ["map_agent"],
        }

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username",
        fake_get_user,
    )

    request = MagicMock(spec=Request)
    request.headers.get.return_value = f"Bearer {access_token}"

    payload = _run_async(jwt_auth.authenticate(request))
    assert payload is not None
    assert request.state.allowed_agents == ["map_agent"]


def test_upload_config_is_in_session_whitelist():
    """2026-07-17 新增：/api/core/upload-config 必须在 Session 白名单中。

    复现：onMounted 阶段 localStorage.session_id 为空时拉取配置，
    强制 X-Session-ID 校验会 400。前端用户每次刷新都看到噪音。
    """
    assert "/api/core/upload-config" in SESSION_WHITELIST_PREFIXES


def test_upload_file_is_not_in_session_whitelist():
    """2026-07-17 新增：/api/core/uploadfile 必须仍要求 X-Session-ID（不能误伤写接口）。"""
    # 用 startswith 检查白名单没有覆盖整个 /api/core 前缀
    for prefix in SESSION_WHITELIST_PREFIXES:
        assert not prefix.startswith("/api/core") or prefix == "/api/core/upload-config"
    # 更直接的断言：白名单不能前缀匹配 /api/core/uploadfile
    matched = [p for p in SESSION_WHITELIST_PREFIXES if "/api/core/uploadfile".startswith(p)]
    assert matched == ["/api/core/upload-config"] or matched == [], (
        "意外白名单: %s 覆盖 /api/core/uploadfile 的前缀" % matched
    )
    # 关键：/api/core/uploadfile 不应仅因 /api/core/upload-config 在白名单就被放行
    # 用 startswith 反向验证
    assert not any(
        p == "/api/core" for p in SESSION_WHITELIST_PREFIXES
    ), "/api/core 不能整段放行（会误伤 uploadfile / merge-chunks 等写接口）"
