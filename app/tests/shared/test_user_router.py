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
