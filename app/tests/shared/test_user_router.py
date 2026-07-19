# -*- coding:utf-8 -*-
"""
用户管理路由测试模块

测试 user_router 提供的用户列表查询、创建和删除接口，验证 admin 权限控制。
"""
import sys
from unittest.mock import MagicMock

# 环境可能未安装 asyncpg，预先 mock 以避免 Safety -> database 导入链失败
if "asyncpg" not in sys.modules:
    sys.modules["asyncpg"] = MagicMock()

import pytest
from datetime import datetime
from fastapi.testclient import TestClient


@pytest.fixture(scope="function")
def app():
    """
    创建仅包含 user_router 的 FastAPI 应用实例

    避免加载项目中其他缺失依赖的路由模块。
    """
    from app.core.server import create_app
    from app.shared.routers.user_router import router as user_router

    _app = create_app()
    _app.include_router(user_router)
    return _app


@pytest.fixture(scope="function")
def client(app):
    """
    提供 FastAPI TestClient

    Args:
        app: 仅含 user_router 的 FastAPI 应用实例

    Yields:
        TestClient: HTTP 测试客户端
    """
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="function", autouse=True)
def setup_users():
    """
    为每个测试函数准备内存中的 admin 和普通用户数据

    直接操作 UserDB 的内存存储，确保 auth_middleware 能正确识别用户角色。
    """
    from app.shared.utils.auth.user_db import UserDB

    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0

    now = datetime.utcnow()
    UserDB._memory_users["admin"] = {
        "id": 1,
        "username": "admin",
        "password_hash": "",
        "role": "admin",
        "real_name": "Admin",
        "phone": "",
        "email": "",
        "department": "",
        "position": "",
        "created_at": now,
        "updated_at": now,
    }
    UserDB._memory_users["testuser"] = {
        "id": 2,
        "username": "testuser",
        "password_hash": "",
        "role": "user",
        "real_name": "Test User",
        "phone": "",
        "email": "",
        "department": "",
        "position": "",
        "created_at": now,
        "updated_at": now,
    }
    UserDB._memory_id_counter = 2


def test_list_users_admin_ok(client, admin_headers):
    """
    测试 admin 访问 GET /api/users/ 返回 200

    Args:
        client: FastAPI TestClient
        admin_headers: admin 认证请求头（来自 conftest）

    Returns:
        None
    """
    response = client.get("/api/users/", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_list_users_forbidden_for_normal_user(client, user_headers):
    """
    测试普通用户访问 GET /api/users/ 返回 403

    Args:
        client: FastAPI TestClient
        user_headers: 普通用户认证请求头（来自 conftest）

    Returns:
        None
    """
    response = client.get("/api/users/", headers=user_headers)
    assert response.status_code == 403
    assert "需要管理员权限" in response.json()["detail"]


def test_create_user_admin(client, admin_headers):
    """
    测试 admin 通过 POST /api/users/ 创建用户

    Args:
        client: FastAPI TestClient
        admin_headers: admin 认证请求头（来自 conftest）

    Returns:
        None
    """
    payload = {
        "username": "createduser001",
        "password": "Pass@123",
        "role": "user",
        "real_name": "王五",
        "phone": "13700137000",
        "email": "create@example.com",
        "department": "研发部",
        "position": "开发",
    }
    response = client.post("/api/users/", json=payload, headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "创建成功"
    assert "user_id" in data


def test_delete_user_admin(client, admin_headers):
    """
    测试 admin 通过 DELETE /api/users/{id} 删除用户

    先创建一个用户，再执行删除操作。

    Args:
        client: FastAPI TestClient
        admin_headers: admin 认证请求头（来自 conftest）

    Returns:
        None
    """
    payload = {
        "username": "deleteuser001",
        "password": "Pass@123",
        "role": "user",
        "real_name": "赵六",
        "phone": "13600136000",
        "email": "delete@example.com",
        "department": "",
        "position": "",
    }
    create_resp = client.post("/api/users/", json=payload, headers=admin_headers)
    assert create_resp.status_code == 200
    user_id = create_resp.json()["user_id"]

    response = client.delete(f"/api/users/{user_id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["message"] == "删除成功"


def test_create_user_with_allowed_agents(client, admin_headers):
    """
    测试 admin 创建用户时 allowed_agents 可被写入并返回。

    Args:
        client: FastAPI TestClient
        admin_headers: admin 认证请求头（来自 conftest）

    Returns:
        None
    """
    payload = {
        "username": "agent_user_001",
        "password": "Pass@123",
        "role": "user",
        "real_name": "智能体用户",
        "phone": "13800138000",
        "email": "agent@example.com",
        "department": "测试部",
        "position": "工程师",
        "allowed_agents": ["map_agent", "test_agent"],
    }
    create_resp = client.post("/api/users/", json=payload, headers=admin_headers)
    assert create_resp.status_code == 200
    assert create_resp.json()["message"] == "创建成功"

    list_resp = client.get("/api/users/", headers=admin_headers)
    assert list_resp.status_code == 200
    users = list_resp.json()
    target = next((u for u in users if u["username"] == "agent_user_001"), None)
    assert target is not None
    assert target["allowed_agents"] == ["map_agent", "test_agent"]


def test_update_user_allowed_agents(client, admin_headers):
    """
    测试 admin 更新用户时 allowed_agents 可被修改。

    Args:
        client: FastAPI TestClient
        admin_headers: admin 认证请求头（来自 conftest）

    Returns:
        None
    """
    payload = {
        "username": "agent_user_002",
        "password": "Pass@123",
        "role": "user",
        "real_name": "智能体用户二",
        "phone": "13900139000",
        "email": "agent2@example.com",
        "department": "研发部",
        "position": "开发",
        "allowed_agents": ["map_agent"],
    }
    create_resp = client.post("/api/users/", json=payload, headers=admin_headers)
    assert create_resp.status_code == 200
    user_id = create_resp.json()["user_id"]

    update_payload = {
        "real_name": "智能体用户二",
        "phone": "13900139000",
        "email": "agent2@example.com",
        "department": "研发部",
        "position": "开发",
        "role": "user",
        "allowed_agents": ["map_agent", "audit_document_agent"],
    }
    update_resp = client.put(f"/api/users/{user_id}", json=update_payload, headers=admin_headers)
    assert update_resp.status_code == 200
    assert update_resp.json()["message"] == "更新成功"

    list_resp = client.get("/api/users/", headers=admin_headers)
    assert list_resp.status_code == 200
    users = list_resp.json()
    target = next((u for u in users if u["id"] == user_id), None)
    assert target is not None
    assert target["allowed_agents"] == ["map_agent", "audit_document_agent"]


def test_list_users_returns_200_with_native_list_allowed_agents(
    client, admin_headers, monkeypatch
):
    """
    验证 GET /api/users/ 在 UserDB.list_users 返回 native list 时
    Pydantic 校验通过（allowed_agents 字段类型 List[str]）。

    单元层面 UserDB postgres 分支的 JSONB 字符串解码由
    test_user_db_postgres_jsonb.py 覆盖；本测试验证路由层契约。

    Args:
        client: FastAPI TestClient
        admin_headers: admin 认证请求头（来自 conftest）
        monkeypatch: pytest 内置 fixture，用于替换 UserDB.list_users

    Returns:
        None

    Raises:
        AssertionError: 状态码非 200 或响应结构不符时抛出。
    """
    from app.shared.utils.auth.user_db import UserDB

    async def fake_list_users():
        return [{
            "id": 1, "username": "admin", "role": "admin",
            "real_name": "Admin", "phone": "13800138000", "email": "admin@example.com",
            "department": "研发部", "position": "负责人",
            "allowed_agents": ["map_agent", "audit_document_agent"],
            "created_at": "2026-07-01", "updated_at": "2026-07-01",
        }]

    monkeypatch.setattr(UserDB, "list_users", fake_list_users)
    response = client.get("/api/users/", headers=admin_headers)
    assert response.status_code == 200
    users = response.json()
    assert len(users) == 1
    assert isinstance(users[0]["allowed_agents"], list)
    assert users[0]["allowed_agents"] == ["map_agent", "audit_document_agent"]
    # 2026-07-18 回归断言:编辑用户表单依赖 email/phone/department/position 字段,
    # UserResponse 必须保留它们,否则前端 openEditUser 拿不到值,详情弹窗为空。
    assert users[0]["email"] == "admin@example.com"
    assert users[0]["phone"] == "13800138000"
    assert users[0]["department"] == "研发部"
    assert users[0]["position"] == "负责人"


def test_list_users_response_model_includes_profile_fields(client, admin_headers, monkeypatch):
    """
    2026-07-18 回归测试:GET /api/users 响应模型必须保留 email/phone/department/position。

    根因记录:之前 UserResponse 模型只声明 7 个字段,FastAPI 用 response_model 序列化
    时会把未声明的 email/phone/department/position 字段过滤掉,导致前端
    UserSettingsDialog.vue::openEditUser 拿不到 user.email,被 `|| ''` 兜底为空字符串,
    编辑弹窗里邮箱/手机/部门/职位显示为空。

    Args:
        client: FastAPI TestClient。
        admin_headers: admin 认证请求头。
        monkeypatch: pytest 内置 fixture,替换 UserDB.list_users。

    Returns:
        None

    Raises:
        AssertionError: 响应中缺少任一字段时抛出。
    """
    from app.shared.utils.auth.user_db import UserDB

    async def fake_list_users():
        return [{
            "id": 7, "username": "alice", "role": "user",
            "real_name": "Alice",
            "phone": "13700137000",
            "email": "alice@example.com",
            "department": "运营部",
            "position": "运营",
            "allowed_agents": [],
            "created_at": "2026-07-18",
            "updated_at": "2026-07-18",
        }]

    monkeypatch.setattr(UserDB, "list_users", fake_list_users)
    response = client.get("/api/users/", headers=admin_headers)
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    user = payload[0]
    # 必传字段不应被 response_model 过滤
    assert user["email"] == "alice@example.com"
    assert user["phone"] == "13700137000"
    assert user["department"] == "运营部"
    assert user["position"] == "运营"
    # 同时验证未填充的旧值(空串)不会因字段缺失变成缺失键
    assert "email" in user
    assert "phone" in user
    assert "department" in user
    assert "position" in user
