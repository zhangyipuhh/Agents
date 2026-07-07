# -*- coding:utf-8 -*-
"""
会话路由测试模块

测试 app.shared.routers.session_router 的核心端点，
包括创建会话、获取列表和删除会话。
"""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.shared.utils.auth.user_db import UserDB
from app.shared.utils.auth.session_db import SessionDB


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


def test_create_session_with_project_id(client, admin_headers):
    """2026-06-30 新增：create_session 接受 project_id body 并把会话绑定到项目。"""
    from app.shared.utils.project.project_db import ProjectDB
    from app.shared.utils.Session.SessionCache import session_cache

    p = asyncio.run(ProjectDB.create_project(user_id=1, name="test", uuid="uuid-1"))

    response = client.post(
        "/api/session/create",
        json={"project_id": p["id"]},
        headers=admin_headers,
    )
    assert response.status_code == 200
    session_id = response.json()["session_id"]

    # 验证 session.project_id 已绑定（兼容 Memory / DB 两种模式，从 session_cache 读）
    session = asyncio.run(session_cache.get_session(session_id))
    assert session is not None
    assert session.get("project_id") == p["id"]


def test_create_session_without_project_id(client, admin_headers):
    """2026-06-30 新增：不传 project_id 时按默认行为（不绑定项目）。"""
    from app.shared.utils.Session.SessionCache import session_cache

    response = client.post(
        "/api/session/create",
        json={},
        headers=admin_headers,
    )
    assert response.status_code == 200
    session_id = response.json()["session_id"]
    session = asyncio.run(session_cache.get_session(session_id))
    assert session is not None
    assert session.get("project_id") is None


# ===== 导出 Markdown 测试 =====

TestAIMessage = type("AIMessage", (object,), {})
TestHumanMessage = type("HumanMessage", (object,), {})


def _msg(type_cls, content=None, **kwargs):
    """构造用于测试的动态消息实例。"""
    inst = type_cls.__new__(type_cls)
    inst.content = content
    for k, v in kwargs.items():
        setattr(inst, k, v)
    return inst


def _build_mock_agent_graph(main_messages):
    """构造 graph.aget_state 返回主消息列表的 mock agent。"""
    state = SimpleNamespace(values={"messages": main_messages})
    graph = MagicMock()
    graph.aget_state = AsyncMock(return_value=state)
    agent = MagicMock()
    agent.graph = graph
    return agent


def _build_mock_checkpointer(thread_states):
    """构造根据 thread_id 返回 state 的 mock checkpointer。"""
    cp = MagicMock()

    async def fake_aget(config):
        tid = config["configurable"]["thread_id"]
        return thread_states.get(tid)

    cp.aget = AsyncMock(side_effect=fake_aget)
    return cp


def test_export_markdown_success(client, admin_headers):
    """导出 Markdown 应包含主消息与子智能体消息，并返回 text/markdown。"""
    create_resp = client.post("/api/session/create", headers=admin_headers)
    assert create_resp.status_code == 200, create_resp.text
    session_id = create_resp.json()["session_id"]
    headers = {**admin_headers, "X-Session-ID": session_id}

    h1 = _msg(TestHumanMessage, content="你好")
    ai1 = _msg(
        TestAIMessage,
        content="好的",
        tool_calls=[{"id": "call_x", "name": "sandbox", "args": {}}],
        id="m-ai-1",
    )
    main_messages = [h1, ai1]

    sub_state = {
        "channel_values": {
            "messages": [
                _msg(TestHumanMessage, content="子任务输入"),
                _msg(TestAIMessage, content="子任务输出"),
            ]
        }
    }
    cp = _build_mock_checkpointer({"call_x": sub_state})
    map_agent = _build_mock_agent_graph(main_messages)

    with patch(
        "app.shared.routers.session_router.get_async_checkpointer",
        AsyncMock(return_value=cp),
    ), patch(
        "app.routers.knowledge_router.get_map_agent",
        AsyncMock(return_value=map_agent),
    ):
        resp = client.get(
            f"/api/session/{session_id}/export/markdown",
            headers=headers,
        )

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "text/markdown; charset=utf-8"
    body = resp.text
    assert "# 新对话" in body
    assert "## 用户" in body
    assert "你好" in body
    assert "## Assistant" in body
    assert "## 子智能体" in body
    assert "子任务输出" in body


def test_export_markdown_empty(client, admin_headers):
    """会话无消息时导出仅包含标题。"""
    create_resp = client.post("/api/session/create", headers=admin_headers)
    assert create_resp.status_code == 200
    session_id = create_resp.json()["session_id"]
    headers = {**admin_headers, "X-Session-ID": session_id}

    cp = _build_mock_checkpointer({})
    map_agent = _build_mock_agent_graph([])

    with patch(
        "app.shared.routers.session_router.get_async_checkpointer",
        AsyncMock(return_value=cp),
    ), patch(
        "app.routers.knowledge_router.get_map_agent",
        AsyncMock(return_value=map_agent),
    ):
        resp = client.get(
            f"/api/session/{session_id}/export/markdown",
            headers=headers,
        )

    assert resp.status_code == 200, resp.text
    assert "# 新对话" in resp.text


def test_export_markdown_unauthorized(client):
    """未登录访问导出接口返回 401。"""
    resp = client.get("/api/session/any/export/markdown")
    assert resp.status_code == 401


def test_export_markdown_forbidden(client, admin_headers):
    """非本人会话返回 403。"""
    create_resp = client.post("/api/session/create", headers=admin_headers)
    assert create_resp.status_code == 200
    session_id = create_resp.json()["session_id"]
    headers = {**admin_headers, "X-Session-ID": session_id}

    with patch(
        "app.shared.routers.session_router.session_cache.verify_session",
        AsyncMock(return_value=False),
    ):
        resp = client.get(
            f"/api/session/{session_id}/export/markdown",
            headers=headers,
        )
    assert resp.status_code in (401, 403), f"unexpected status {resp.status_code}"


# ===== 会话文件空间测试（2026-07-01 新增） =====

def _make_fake_path(name, suffix=".txt"):
    """构造一个仅用于 resolve_session_file_path 返回的 Path-like 对象。"""
    from pathlib import Path
    return Path(f"/tmp/fake/{name}{suffix}")


def test_get_session_files_tree_success(client, admin_headers):
    """GET /api/session/{id}/files/tree 返回文件树。"""
    create_resp = client.post("/api/session/create", headers=admin_headers)
    assert create_resp.status_code == 200
    session_id = create_resp.json()["session_id"]
    headers = {**admin_headers, "X-Session-ID": session_id}

    fake_tree = {
        "name": "会话文件",
        "type": "folder",
        "path": "/tmp/fake",
        "children": [
            {
                "name": "原文件",
                "type": "folder",
                "path": "/tmp/fake/orig",
                "children": [
                    {"name": "test.txt", "type": "file", "path": "/tmp/fake/orig/test.txt", "size": 12}
                ],
            }
        ],
    }

    with patch(
        "app.shared.routers.session_router.file_transfer.build_session_file_tree",
        AsyncMock(return_value=fake_tree),
    ):
        resp = client.get(f"/api/session/{session_id}/files/tree", headers=headers)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["tree"]["name"] == "会话文件"
    assert data["tree"]["children"][0]["children"][0]["name"] == "test.txt"


def test_get_session_files_tree_unauthorized(client):
    """未登录访问文件树接口返回 401。"""
    resp = client.get("/api/session/any/files/tree")
    assert resp.status_code == 401


def test_get_session_files_tree_forbidden(client, admin_headers):
    """非本人会话访问文件树返回 403。"""
    create_resp = client.post("/api/session/create", headers=admin_headers)
    assert create_resp.status_code == 200
    session_id = create_resp.json()["session_id"]
    headers = {**admin_headers, "X-Session-ID": session_id}

    with patch(
        "app.shared.routers.session_router.session_cache.verify_session",
        AsyncMock(return_value=False),
    ):
        resp = client.get(
            f"/api/session/{session_id}/files/tree",
            headers=headers,
        )
    assert resp.status_code in (401, 403), f"unexpected status {resp.status_code}"


def test_preview_session_file_text(client, admin_headers):
    """GET /api/session/{id}/files/preview 文本文件返回 content。"""
    create_resp = client.post("/api/session/create", headers=admin_headers)
    assert create_resp.status_code == 200
    session_id = create_resp.json()["session_id"]
    headers = {**admin_headers, "X-Session-ID": session_id}

    fake_path = _make_fake_path("test", ".txt")

    with patch(
        "app.shared.routers.session_router.file_transfer.resolve_session_file_path",
        return_value=fake_path,
    ), patch(
        "app.shared.routers.session_router.file_transfer._get_preview_mode",
        return_value="text",
    ), patch(
        "app.shared.routers.session_router.file_transfer.read_session_file_content",
        AsyncMock(return_value="hello world"),
    ):
        resp = client.get(
            f"/api/session/{session_id}/files/preview?stored_path=/tmp/fake/test.txt",
            headers=headers,
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["content"] == "hello world"
    assert data["preview_mode"] == "text"
    assert data["file_name"] == "test.txt"


def test_preview_session_file_image(client, admin_headers):
    """GET /api/session/{id}/files/preview 图片文件返回 file_url。"""
    create_resp = client.post("/api/session/create", headers=admin_headers)
    assert create_resp.status_code == 200
    session_id = create_resp.json()["session_id"]
    headers = {**admin_headers, "X-Session-ID": session_id}

    fake_path = _make_fake_path("image", ".png")

    with patch(
        "app.shared.routers.session_router.file_transfer.resolve_session_file_path",
        return_value=fake_path,
    ), patch(
        "app.shared.routers.session_router.file_transfer._get_preview_mode",
        return_value="image",
    ):
        resp = client.get(
            f"/api/session/{session_id}/files/preview?stored_path=/tmp/fake/image.png",
            headers=headers,
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["preview_mode"] == "image"
    assert data["file_url"].startswith(f"/api/session/{session_id}/files/download")
    assert "stored_path" in data["file_url"]


def test_preview_session_file_forbidden(client, admin_headers):
    """resolve_session_file_path 抛 403 时预览接口返回 403。"""
    create_resp = client.post("/api/session/create", headers=admin_headers)
    assert create_resp.status_code == 200
    session_id = create_resp.json()["session_id"]
    headers = {**admin_headers, "X-Session-ID": session_id}

    with patch(
        "app.shared.routers.session_router.file_transfer.resolve_session_file_path",
        side_effect=HTTPException(status_code=403, detail="无权访问该文件路径"),
    ):
        resp = client.get(
            f"/api/session/{session_id}/files/preview?stored_path=../../etc/passwd",
            headers=headers,
        )

    assert resp.status_code == 403, resp.text


def test_download_session_file_success(client, admin_headers, tmp_path):
    """GET /api/session/{id}/files/download 成功下载文件。"""
    create_resp = client.post("/api/session/create", headers=admin_headers)
    assert create_resp.status_code == 200
    session_id = create_resp.json()["session_id"]
    headers = {**admin_headers, "X-Session-ID": session_id}

    # 在临时目录创建真实文件供 FileResponse 读取
    test_file = tmp_path / "download.txt"
    test_file.write_text("download content", encoding="utf-8")

    with patch(
        "app.shared.routers.session_router.file_transfer.resolve_session_file_path",
        return_value=test_file,
    ):
        resp = client.get(
            f"/api/session/{session_id}/files/download?stored_path=/tmp/fake/download.txt",
            headers=headers,
        )

    assert resp.status_code == 200, resp.text
    assert resp.content.decode("utf-8") == "download content"
    assert resp.headers.get("content-disposition", "").startswith("attachment")


def test_download_session_file_unauthorized(client):
    """未登录访问下载接口返回 401。"""
    resp = client.get("/api/session/any/files/download?stored_path=x")
    assert resp.status_code == 401


# ===== Admin 批量删除/历史消息/导出 Markdown 测试 =====

def test_admin_batch_delete_sessions_success(client, admin_headers):
    """Admin 批量删除接口应成功删除多个会话并返回统计。"""
    session_ids = []
    for _ in range(3):
        create_resp = client.post("/api/session/create", headers=admin_headers)
        assert create_resp.status_code == 200, create_resp.text
        session_ids.append(create_resp.json()["session_id"])

    headers = {**admin_headers, "Content-Type": "application/json"}
    with patch(
        "app.shared.routers.session_router.FileTransfer.delete_session",
        AsyncMock(return_value=True),
    ):
        resp = client.request(
            "DELETE",
            "/api/session/admin/batch",
            content=json.dumps({"session_ids": session_ids}),
            headers=headers,
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    assert data["deleted_count"] == 3
    assert data["total"] == 3
    assert data["failed"] == []


def test_admin_batch_delete_sessions_partial_failure(client, admin_headers):
    """Admin 批量删除接口应返回部分失败结果。"""
    create_resp = client.post("/api/session/create", headers=admin_headers)
    assert create_resp.status_code == 200, create_resp.text
    existing_session_id = create_resp.json()["session_id"]
    non_existent_session_id = "non-existent-session-id"

    async def _fake_delete_session(session_id):
        if session_id == non_existent_session_id:
            raise RuntimeError("会话目录不存在")
        return True

    headers = {**admin_headers, "Content-Type": "application/json"}
    with patch(
        "app.shared.routers.session_router.FileTransfer.delete_session",
        AsyncMock(side_effect=_fake_delete_session),
    ):
        resp = client.request(
            "DELETE",
            "/api/session/admin/batch",
            content=json.dumps({"session_ids": [existing_session_id, non_existent_session_id]}),
            headers=headers,
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    assert data["deleted_count"] == 1
    assert data["total"] == 2
    assert len(data["failed"]) == 1
    assert data["failed"][0]["session_id"] == non_existent_session_id
    assert "会话目录不存在" in data["failed"][0]["reason"]


def test_admin_batch_delete_sessions_unauthorized(client):
    """未登录访问 Admin 批量删除接口返回 401。"""
    resp = client.request(
        "DELETE",
        "/api/session/admin/batch",
        content=json.dumps({"session_ids": ["any-session-id"]}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 401


def test_admin_get_session_messages_success(client, admin_headers):
    """Admin 历史消息接口应返回含子智能体的合并消息。"""
    create_resp = client.post("/api/session/create", headers=admin_headers)
    assert create_resp.status_code == 200, create_resp.text
    session_id = create_resp.json()["session_id"]

    h1 = _msg(TestHumanMessage, content="你好")
    ai1 = _msg(
        TestAIMessage,
        content="好的",
        tool_calls=[{"id": "call_x", "name": "sandbox", "args": {}}],
        id="m-ai-1",
    )
    main_messages = [h1, ai1]

    sub_state = {
        "channel_values": {
            "messages": [
                _msg(TestHumanMessage, content="子任务输入"),
                _msg(TestAIMessage, content="子任务输出"),
            ]
        }
    }
    cp = _build_mock_checkpointer({"call_x": sub_state})
    map_agent = _build_mock_agent_graph(main_messages)

    with patch(
        "app.shared.routers.session_router.get_async_checkpointer",
        AsyncMock(return_value=cp),
    ), patch(
        "app.routers.knowledge_router.get_map_agent",
        AsyncMock(return_value=map_agent),
    ):
        resp = client.get(
            f"/api/session/admin/{session_id}/messages",
            headers=admin_headers,
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["session_id"] == session_id
    assert "messages" in data
    assert "total" in data
    assert any(msg.get("type") == "subagent" for msg in data["messages"])


def test_admin_export_session_markdown_success(client, admin_headers):
    """Admin 导出 Markdown 接口应包含主消息与子智能体消息。"""
    create_resp = client.post("/api/session/create", headers=admin_headers)
    assert create_resp.status_code == 200, create_resp.text
    session_id = create_resp.json()["session_id"]

    h1 = _msg(TestHumanMessage, content="你好")
    ai1 = _msg(
        TestAIMessage,
        content="好的",
        tool_calls=[{"id": "call_x", "name": "sandbox", "args": {}}],
        id="m-ai-1",
    )
    main_messages = [h1, ai1]

    sub_state = {
        "channel_values": {
            "messages": [
                _msg(TestHumanMessage, content="子任务输入"),
                _msg(TestAIMessage, content="子任务输出"),
            ]
        }
    }
    cp = _build_mock_checkpointer({"call_x": sub_state})
    map_agent = _build_mock_agent_graph(main_messages)

    with patch(
        "app.shared.routers.session_router.get_async_checkpointer",
        AsyncMock(return_value=cp),
    ), patch(
        "app.routers.knowledge_router.get_map_agent",
        AsyncMock(return_value=map_agent),
    ):
        resp = client.get(
            f"/api/session/admin/{session_id}/export/markdown",
            headers=admin_headers,
        )

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "text/markdown; charset=utf-8"
    body = resp.text
    assert "# 新对话" in body
    assert "## 用户" in body
    assert "你好" in body
    assert "## Assistant" in body
    assert "## 子智能体" in body
    assert "子任务输出" in body


def test_admin_export_session_markdown_not_found(client, admin_headers):
    """Admin 导出 Markdown 接口对不存在的会话返回 404。"""
    resp = client.get(
        "/api/session/admin/non-existent-session/export/markdown",
        headers=admin_headers,
    )
    assert resp.status_code == 404
