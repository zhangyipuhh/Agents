# -*- coding:utf-8 -*-
"""
会话路由测试模块

测试 app.shared.routers.session_router 的核心端点，
包括创建会话、获取列表和删除会话。
"""
import asyncio
from unittest.mock import patch, AsyncMock

import pytest

from app.shared.utils.auth.user_db import UserDB


@pytest.fixture(autouse=True)
def reset_user_db():
    """
    每个测试前重置 UserDB 内存状态并创建 admin 用户。

    Returns:
        None
    """
    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0
    asyncio.run(UserDB.create_user("admin", "admin123", role="admin"))
    yield
    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0


def test_create_session(client, admin_headers):
    """
    测试 POST /api/session/create 创建会话成功。

    Args:
        client: FastAPI TestClient fixture。
        admin_headers: 包含 admin Bearer token 的请求头 fixture。

    Returns:
        None

    Raises:
        AssertionError: 响应状态码非 200 或缺少 session_id 时抛出。
    """
    response = client.post("/api/session/create", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert data["message"] == "会话创建成功"


def test_list_sessions(client, admin_headers):
    """
    测试 GET /api/session/list 获取当前用户的会话列表。

    由于 create_session 将数据写入 session_cache_original，而 list_sessions
    查询的是 SessionDB._memory_cache，因此测试中直接通过 SessionDB 准备数据。

    Args:
        client: FastAPI TestClient fixture。
        admin_headers: 包含 admin Bearer token 的请求头 fixture。

    Returns:
        None

    Raises:
        AssertionError: 响应状态码非 200 或会话列表格式不正确时抛出。
    """
    from app.shared.utils.auth.session_db import SessionDB

    SessionDB._memory_cache.clear()
    asyncio.run(SessionDB.add_session("sess-list-001", 1, "admin"))

    response = client.get("/api/session/list", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert "sessions" in data
    assert isinstance(data["sessions"], list)
    assert len(data["sessions"]) >= 1


def test_delete_session(client, admin_headers):
    """
    测试 DELETE /api/session/delete/{id} 删除会话。

    先调用 create_session 创建会话，再 mock 文件系统删除操作后执行删除，
    验证返回 success=True。

    Args:
        client: FastAPI TestClient fixture。
        admin_headers: 包含 admin Bearer token 的请求头 fixture。

    Returns:
        None

    Raises:
        AssertionError: 响应状态码非 200 或删除未成功时抛出。
    """
    resp = client.post("/api/session/create", headers=admin_headers)
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]

    with patch(
        "app.shared.routers.session_router.file_transfer.delete_session",
        AsyncMock(return_value=True),
    ):
        response = client.delete(
            f"/api/session/delete/{session_id}", headers=admin_headers
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "删除成功" in data["message"] or data["message"] == "会话删除成功"
