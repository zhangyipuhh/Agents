# -*- coding:utf-8 -*-
"""
session_auth_middleware / SessionDB.get_user_sessions 关于 ops-detect: 临时会话的测试（2026-08-17 新增）。

覆盖：
  - session_auth_middleware 在 /api/agent/ 前缀下，自动供给 ops-detect: 合成 session 行；
  - 非 /api/agent/ 前缀或非 ops-detect: 前缀保持原 401 行为；
  - add_session 失败时回落到 401（fail-loud）；
  - SessionDB.get_user_sessions 过滤 ops-detect:% 不污染主侧边栏。
"""
import asyncio
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

if "asyncpg" not in sys.modules:
    sys.modules["asyncpg"] = MagicMock()

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

from app.shared.utils.auth import Safety as safety_module
from app.shared.utils.auth.Safety import session_auth_middleware


def _run_async(coro):
    """辅助函数：在新的事件循环中运行异步协程"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_request(path: str, session_id: str | None, username: str | None,
                  user_id: int | None = 1):
    """构造 session_auth_middleware 所需的 mock Request。"""
    request = MagicMock(spec=Request)
    request.url.path = path
    request.headers.get.return_value = session_id
    request.state.username = username
    request.state.user_id = user_id
    request.state.role = "admin" if username == "admin" else "user"
    return request


# -----------------------------------------------------------------------------
# session_auth_middleware: ops-detect 自动供给
# -----------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/api/agent/chat", "/api/agent/{}/abort".format("ops-detect:1:123")])
def test_session_auth_middleware_auto_provisions_ops_detect_session(path):
    """ops-detect: 合成 session_id 在 /api/agent/ 前缀下自动建行后放行。"""
    username = "admin"
    ops_session = "ops-detect:42:1700000000000"

    with patch("app.shared.utils.Session.SessionCache.session_cache") as mock_cache, \
         patch("app.shared.utils.auth.Safety.session_cache", mock_cache):
        mock_cache.verify_session = AsyncMock(return_value=False)
        mock_cache.add_session = AsyncMock(return_value=True)

        async def fake_call_next(_request):
            return JSONResponse(content={"ok": True})

        request = _make_request(path, ops_session, username)
        response = _run_async(session_auth_middleware(request, fake_call_next))

        assert response.status_code == 200
        mock_cache.verify_session.assert_awaited_once_with(ops_session, username)
        mock_cache.add_session.assert_awaited_once()
        call_args = mock_cache.add_session.await_args
        # 绑定当前用户与请求 user_id（第三个参数为 user_id 整数）
        assert call_args.args[0] == ops_session
        assert call_args.args[1] == username
        assert call_args.args[2] == 1
        assert call_args.kwargs.get("project_id") is None
        # request.state.session_id 写入中间件供下游使用
        assert request.state.session_id == ops_session


def test_session_auth_middleware_rejects_unknown_non_ops_detect_session():
    """非 ops-detect: 前缀的未知 session 仍按原契约返回 401。"""
    username = "admin"
    bogus = "session-deadbeef"

    with patch("app.shared.utils.Session.SessionCache.session_cache") as mock_cache, \
         patch("app.shared.utils.auth.Safety.session_cache", mock_cache):
        mock_cache.verify_session = AsyncMock(return_value=False)
        mock_cache.add_session = AsyncMock()

        async def fake_call_next(_request):
            return JSONResponse(content={"ok": True})

        request = _make_request("/api/agent/chat", bogus, username)
        response = _run_async(session_auth_middleware(request, fake_call_next))

        assert response.status_code == 401
        body = json.loads(response.body)
        assert "无权访问该会话" in body["detail"]
        mock_cache.add_session.assert_not_called()


def test_session_auth_middleware_ops_detect_only_for_agent_prefix():
    """ops-detect: 前缀仅在 /api/agent/ 路径生效；其他前缀（如 /api/core）仍 401。"""
    username = "admin"
    ops_session = "ops-detect:42:1700000000000"

    with patch("app.shared.utils.Session.SessionCache.session_cache") as mock_cache, \
         patch("app.shared.utils.auth.Safety.session_cache", mock_cache):
        mock_cache.verify_session = AsyncMock(return_value=False)
        mock_cache.add_session = AsyncMock()

        async def fake_call_next(_request):
            return JSONResponse(content={"ok": True})

        request = _make_request("/api/core/uploadfile", ops_session, username)
        response = _run_async(session_auth_middleware(request, fake_call_next))

        assert response.status_code == 401
        mock_cache.add_session.assert_not_called()


def test_session_auth_middleware_add_session_failure_returns_401():
    """add_session 抛异常时按 fail-loud 返回 401，绝不静默放行。"""
    username = "admin"
    ops_session = "ops-detect:42:1700000000000"

    with patch("app.shared.utils.Session.SessionCache.session_cache") as mock_cache, \
         patch("app.shared.utils.auth.Safety.session_cache", mock_cache):
        mock_cache.verify_session = AsyncMock(return_value=False)
        mock_cache.add_session = AsyncMock(side_effect=RuntimeError("db down"))
        mock_cache.get_session = AsyncMock(return_value=None)

        async def fake_call_next(_request):
            return JSONResponse(content={"ok": True})

        request = _make_request("/api/agent/chat", ops_session, username)
        response = _run_async(session_auth_middleware(request, fake_call_next))

        assert response.status_code == 401
        body = json.loads(response.body)
        assert "无权访问该会话" in body["detail"]


# -----------------------------------------------------------------------------
# SessionDB.get_user_sessions: 过滤 ops-detect: 前缀
# -----------------------------------------------------------------------------


def test_get_user_sessions_sql_excludes_ops_detect_prefix():
    """SQL 路径必须包含 NOT LIKE 'ops-detect:%' 守卫。"""
    from app.shared.utils.auth.session_db import SessionDB

    captured_sql: dict[str, str] = {}

    async def fake_fetch(sql, *args, **kwargs):
        captured_sql["sql"] = sql
        return []

    with patch("app.shared.utils.auth.session_db.SessionDB.is_enabled", return_value=True), \
         patch("app.shared.utils.auth.session_db.DatabasePool.fetch", new=fake_fetch):
        _run_async(SessionDB.get_user_sessions(7))

    assert "ops-detect:%" in captured_sql["sql"]
    assert "NOT LIKE" in captured_sql["sql"]


def test_get_user_sessions_memory_mode_excludes_ops_detect_prefix():
    """Memory 模式同样过滤 ops-detect: 前缀会话。"""
    from app.shared.utils.auth.session_db import SessionDB

    user_id = 9
    SessionDB._memory_cache.clear()
    SessionDB._memory_cache["real-session-1"] = {
        "user_id": user_id, "username": "u", "created_at": "2026-08-17",
    }
    SessionDB._memory_cache["ops-detect:1:1700000000000"] = {
        "user_id": user_id, "username": "u", "created_at": "2026-08-17",
    }
    SessionDB._memory_cache["other-user-session"] = {
        "user_id": 999, "username": "other", "created_at": "2026-08-17",
    }

    with patch("app.shared.utils.auth.session_db.SessionDB.is_enabled", return_value=False):
        sessions = _run_async(SessionDB.get_user_sessions(user_id))

    ids = {s["session_id"] for s in sessions}
    assert "real-session-1" in ids
    assert "ops-detect:1:1700000000000" not in ids
    assert "other-user-session" not in ids