# -*- coding:utf-8 -*-
"""
文件路由测试模块

测试 app.shared.routers.file_router 的核心端点，
包括列出文件和删除文件（mock 文件系统操作）。
"""
import asyncio
from unittest.mock import patch, AsyncMock

import pytest

from app.shared.utils.auth.user_db import UserDB
from app.shared.utils.Session.SessionCacheOriginal import session_cache_original


@pytest.fixture(autouse=True)
def reset_user_db():
    """
    每个测试前重置 UserDB 和会话缓存，并创建 admin 用户。

    Returns:
        None
    """
    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0
    session_cache_original._cache.clear()
    asyncio.run(UserDB.create_user("admin", "admin123", role="admin"))
    yield
    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0
    session_cache_original._cache.clear()


def test_list_files(client, admin_headers):
    """
    测试 GET /api/files/list 列出文件。

    需要携带 X-Session-ID 请求头，并 mock file_transfer.list_files
    以避免真实文件系统操作。

    Args:
        client: FastAPI TestClient fixture。
        admin_headers: 包含 admin Bearer token 的请求头 fixture。

    Returns:
        None

    Raises:
        AssertionError: 响应状态码非 200 或文件列表格式不正确时抛出。
    """
    session_id = "test-file-session"
    session_cache_original.add_session(session_id, "admin")
    headers = {**admin_headers, "X-Session-ID": session_id}

    with patch(
        "app.shared.routers.file_router.file_transfer.list_files",
        AsyncMock(return_value=[]),
    ):
        response = client.get("/api/files/list", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert "files" in data
    assert "count" in data
    assert data["count"] == 0


def test_delete_files(client, admin_headers):
    """
    测试 DELETE /api/files/delete 删除文件。

    需要携带 X-Session-ID 请求头，并 mock file_transfer.delete_files
    以避免真实文件系统操作。

    Args:
        client: FastAPI TestClient fixture。
        admin_headers: 包含 admin Bearer token 的请求头 fixture。

    Returns:
        None

    Raises:
        AssertionError: 响应状态码非 200 或删除结果不符合预期时抛出。
    """
    session_id = "test-file-session"
    session_cache_original.add_session(session_id, "admin")
    headers = {**admin_headers, "X-Session-ID": session_id}

    # TestClient.delete 显式不暴露 json/content/data 关键字，因此
    # 这里改用 client.request("DELETE", ...) 直接发送 JSON body。
    with patch(
        "app.shared.routers.file_router.file_transfer.delete_files",
        AsyncMock(return_value={"success": ["uuid-1"], "failed": []}),
    ):
        response = client.request(
            "DELETE",
            "/api/files/delete",
            headers=headers,
            json={"uuids": ["uuid-1"]},
        )

    assert response.status_code == 200
    data = response.json()
    assert "success" in data
    assert data["success"] == ["uuid-1"]
    assert data["failed"] == []
