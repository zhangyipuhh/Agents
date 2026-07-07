# -*- coding:utf-8 -*-
"""
Project 路由测试（2026-06-30 新增）

测试 app.shared.routers.project_router 的：
  * POST /api/project/create
  * GET  /api/project/list
  * GET  /api/project/{id}/info
  * PUT  /api/project/session/bind
  * PUT  /api/project/session/unbind
"""

import asyncio

import pytest

from app.shared.utils.auth.user_db import UserDB
from app.shared.utils.auth.session_db import SessionDB
from app.shared.utils.project.project_db import ProjectDB


@pytest.fixture(autouse=True)
def reset_state():
    """每个测试前重置所有相关内存状态。"""
    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0
    SessionDB._memory_cache.clear()
    ProjectDB._memory_cache.clear()
    asyncio.run(UserDB.create_user("admin", "admin123", role="admin"))
    asyncio.run(SessionDB.add_session("sess-001", 1, "admin"))
    yield
    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0
    SessionDB._memory_cache.clear()
    ProjectDB._memory_cache.clear()


def test_create_project(client, admin_headers):
    """测试创建项目成功。"""
    response = client.post(
        "/api/project/create",
        json={"name": "Daily-work", "uuid": "sess-001"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["project"]["name"] == "Daily-work"
    assert data["project"]["uuid"] == "sess-001"


def test_create_project_empty_name(client, admin_headers):
    """空项目名应返回 400。"""
    response = client.post(
        "/api/project/create",
        json={"name": "  ", "uuid": "sess-001"},
        headers=admin_headers,
    )
    assert response.status_code == 400


def test_create_project_without_uuid(client, admin_headers):
    """不传 uuid 时后端应自动生成独立 uuid 并创建成功。"""
    response = client.post(
        "/api/project/create",
        json={"name": "Auto-uuid-project"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["project"]["name"] == "Auto-uuid-project"
    assert data["project"]["uuid"]
    assert len(data["project"]["uuid"]) > 0


def test_create_project_empty_uuid(client, admin_headers):
    """空 uuid 应视为未提供，后端自动生成并返回 200。"""
    response = client.post(
        "/api/project/create",
        json={"name": "test", "uuid": ""},
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["project"]["uuid"]
    assert len(data["project"]["uuid"]) > 0


def test_list_projects_empty(client, admin_headers):
    """无项目时返回空列表。"""
    response = client.get("/api/project/list", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert "projects" in data
    assert isinstance(data["projects"], list)


def test_list_projects_with_data(client, admin_headers):
    """有项目时返回项目列表。"""
    asyncio.run(ProjectDB.create_project(user_id=1, name="Project-A", uuid="uuid-a"))
    asyncio.run(ProjectDB.create_project(user_id=1, name="Project-B", uuid="uuid-b"))

    response = client.get("/api/project/list", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["projects"]) == 2
    names = {p["name"] for p in data["projects"]}
    assert "Project-A" in names
    assert "Project-B" in names


def test_get_project_info(client, admin_headers):
    """测试按 ID 获取项目详情。"""
    p = asyncio.run(ProjectDB.create_project(user_id=1, name="test", uuid="uuid-test"))

    response = client.get(f"/api/project/{p['id']}/info", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["project"]["id"] == p["id"]
    assert data["project"]["name"] == "test"


def test_get_project_info_not_found(client, admin_headers):
    """不存在的项目 ID 返回 404。"""
    response = client.get("/api/project/9999/info", headers=admin_headers)
    assert response.status_code == 404


def test_bind_session_to_project(client, admin_headers):
    """测试会话绑定到项目。"""
    p = asyncio.run(ProjectDB.create_project(user_id=1, name="test", uuid="uuid-1"))

    response = client.put(
        "/api/project/session/bind",
        json={"session_id": "sess-001", "project_id": p["id"]},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

    # 验证 session.project_id 已更新
    session = asyncio.run(SessionDB.get_session("sess-001"))
    assert session["project_id"] == p["id"]


def test_unbind_session_from_project(client, admin_headers):
    """测试解除会话项目关联。"""
    p = asyncio.run(ProjectDB.create_project(user_id=1, name="test", uuid="uuid-1"))
    asyncio.run(SessionDB.update_session_project("sess-001", p["id"]))

    response = client.put(
        "/api/project/session/unbind",
        json={"session_id": "sess-001"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

    # 验证 session.project_id 已置 None
    session = asyncio.run(SessionDB.get_session("sess-001"))
    assert session["project_id"] is None


def test_delete_project_success(client, admin_headers):
    """测试删除项目成功，关联会话解除绑定。"""
    p = asyncio.run(ProjectDB.create_project(user_id=1, name="ToDelete", uuid="uuid-del"))
    asyncio.run(SessionDB.update_session_project("sess-001", p["id"]))

    response = client.delete(
        f"/api/project/{p['id']}/delete",
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True

    # 验证项目已删除
    assert asyncio.run(ProjectDB.get_project_by_id(p["id"], user_id=1)) is None
    # 验证关联会话已解绑
    session = asyncio.run(SessionDB.get_session("sess-001"))
    assert session["project_id"] is None


def test_delete_project_not_found(client, admin_headers):
    """删除不存在的项目返回 404。"""
    response = client.delete("/api/project/9999/delete", headers=admin_headers)
    assert response.status_code == 404


def test_rename_project_success(client, admin_headers):
    """测试重命名项目成功。"""
    p = asyncio.run(ProjectDB.create_project(user_id=1, name="Old", uuid="uuid-rename"))

    response = client.put(
        f"/api/project/{p['id']}/rename",
        json={"name": "New"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["project"]["name"] == "New"

    # 验证数据库/缓存已更新
    updated = asyncio.run(ProjectDB.get_project_by_id(p["id"], user_id=1))
    assert updated["name"] == "New"


def test_rename_project_empty_name(client, admin_headers):
    """空项目名称返回 400。"""
    p = asyncio.run(ProjectDB.create_project(user_id=1, name="Old", uuid="uuid-empty"))

    response = client.put(
        f"/api/project/{p['id']}/rename",
        json={"name": "  "},
        headers=admin_headers,
    )
    assert response.status_code == 400


def test_rename_project_not_found(client, admin_headers):
    """重命名不存在的项目返回 404。"""
    response = client.put(
        "/api/project/9999/rename",
        json={"name": "New"},
        headers=admin_headers,
    )
    assert response.status_code == 404
