# -*- coding:utf-8 -*-
"""user_router 注册审批端点测试(2026-08-30 新增)

覆盖 /api/users/pending + /api/users/{id}/approve + /api/users/{id}/reject
三个端点的 admin 鉴权、状态码语义与数据库副作用。

测试策略:
- 走真实 JWT 认证(Authorization: Bearer <token>),auth_middleware 解析 token
  并根据 DB 中 username -> role 映射写入 request.state.role
- UserDB 走内存模式(_memory_users / _memory_id_counter),每个测试用例通过
  autouse fixture 清空重建
"""
import asyncio
import sys
from datetime import datetime
from unittest.mock import MagicMock

if "asyncpg" not in sys.modules:
    sys.modules["asyncpg"] = MagicMock()

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="function")
def app():
    """仅含 user_router 的最小 app。

    Returns:
        FastAPI: 通过 create_app() 构造并 include user_router 的应用。
    """
    from app.core.server import create_app
    from app.shared.routers.user_router import router as user_router

    _app = create_app()
    _app.include_router(user_router)
    return _app


@pytest.fixture(scope="function")
def client(app):
    """FastAPI TestClient。

    Args:
        app: 仅含 user_router 的 FastAPI 应用。

    Yields:
        TestClient: HTTP 测试客户端。
    """
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def setup_users():
    """为每个测试函数准备 admin + 普通用户,并清空 UserDB 内存。

    setup_users 与 UserDB 内存表直接初始化,不依赖 lifespan 中的
    ensure_admin_exists 流程。每个测试用例结束后再次清空,避免相互污染。
    """
    from app.shared.utils.auth.user_db import UserDB

    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0
    UserDB._memory_login_lock.clear()

    now = datetime.utcnow()
    base_user = {
        "password_hash": "",
        "phone": "",
        "email": "",
        "department": "",
        "position": "",
        "status": "active",
        "status_reason": None,
        "register_ip": None,
        "approved_by_user_id": None,
        "approved_at": None,
        "allowed_agents": [],
    }
    UserDB._memory_users["admin"] = {
        **base_user,
        "id": 1,
        "username": "admin",
        "role": "admin",
        "real_name": "Admin",
        "created_at": now,
        "updated_at": now,
    }
    UserDB._memory_users["testuser"] = {
        **base_user,
        "id": 2,
        "username": "testuser",
        "role": "user",
        "real_name": "Test User",
        "created_at": now,
        "updated_at": now,
    }
    UserDB._memory_id_counter = 2

    yield

    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0
    UserDB._memory_login_lock.clear()


def _build_token(username: str) -> dict:
    """生成指定 username 的 Bearer JWT 请求头。

    Args:
        username: 要注入 token 的用户名。

    Returns:
        dict: 含 Authorization 头的字典。
    """
    import jwt
    from app.shared.utils.auth.Safety import JWTAuth
    from datetime import timedelta

    payload = {
        "username": username,
        "type": "access",
        "exp": datetime.utcnow() + timedelta(minutes=30),
        "iat": datetime.utcnow(),
    }
    token = jwt.encode(payload, JWTAuth().secret_key, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_get_pending_users_requires_admin(client):
    """GET /api/users/pending 非 admin 返回 403。

    Args:
        client: FastAPI TestClient。

    Returns:
        None
    """
    response = client.get("/api/users/pending", headers=_build_token("testuser"))
    assert response.status_code == 403


def test_get_pending_users_returns_list(client):
    """GET /api/users/pending 返回 status=pending_approval 的用户列表。

    Args:
        client: FastAPI TestClient。

    Returns:
        None
    """
    from app.shared.utils.auth.user_db import UserDB

    asyncio.run(UserDB.create_user("p1", "Test@123", status="pending_approval"))
    asyncio.run(UserDB.create_user("p2", "Test@123", status="pending_approval"))
    asyncio.run(UserDB.create_user("a1", "Test@123", status="active"))

    response = client.get("/api/users/pending", headers=_build_token("admin"))
    assert response.status_code == 200
    data = response.json()
    usernames = {u["username"] for u in data}
    assert usernames == {"p1", "p2"}


def test_approve_user_success(client):
    """POST /api/users/{id}/approve 成功路径:status 改为 active。

    Args:
        client: FastAPI TestClient。

    Returns:
        None
    """
    from app.shared.utils.auth.user_db import UserDB

    pending_id = asyncio.run(
        UserDB.create_user("approve_target", "Test@123", status="pending_approval")
    )

    response = client.post(
        f"/api/users/{pending_id}/approve",
        json={},
        headers=_build_token("admin"),
    )
    assert response.status_code == 200

    user = asyncio.run(UserDB.get_user_by_id(pending_id))
    assert user["status"] == "active"


def test_approve_user_not_found(client):
    """approve 不存在的 user_id 返回 404。

    Args:
        client: FastAPI TestClient。

    Returns:
        None
    """
    response = client.post(
        "/api/users/99999/approve",
        json={},
        headers=_build_token("admin"),
    )
    assert response.status_code == 404


def test_approve_user_already_active_returns_409(client):
    """approve 已激活用户返回 409(并发守卫,update_user_status 仅允许 pending_approval)。

    Args:
        client: FastAPI TestClient。

    Returns:
        None
    """
    from app.shared.utils.auth.user_db import UserDB

    active_id = asyncio.run(UserDB.create_user("active", "Test@123"))

    response = client.post(
        f"/api/users/{active_id}/approve",
        json={},
        headers=_build_token("admin"),
    )
    assert response.status_code == 409


def test_reject_user_success(client):
    """POST /api/users/{id}/reject 成功路径:status=rejected, status_reason 写入。

    Args:
        client: FastAPI TestClient。

    Returns:
        None
    """
    from app.shared.utils.auth.user_db import UserDB

    pending_id = asyncio.run(
        UserDB.create_user("reject_target", "Test@123", status="pending_approval")
    )

    response = client.post(
        f"/api/users/{pending_id}/reject",
        json={"reason": "信息不实,需补充材料"},
        headers=_build_token("admin"),
    )
    assert response.status_code == 200

    user = asyncio.run(UserDB.get_user_by_id(pending_id))
    assert user["status"] == "rejected"
    assert user["status_reason"] == "信息不实,需补充材料"


def test_reject_user_missing_reason(client):
    """reject 缺 reason 返回 400。

    Args:
        client: FastAPI TestClient。

    Returns:
        None
    """
    from app.shared.utils.auth.user_db import UserDB

    pending_id = asyncio.run(
        UserDB.create_user("reject_no_reason", "Test@123", status="pending_approval")
    )

    response = client.post(
        f"/api/users/{pending_id}/reject",
        json={"reason": ""},
        headers=_build_token("admin"),
    )
    assert response.status_code == 400
    assert "reason" in response.json()["detail"]