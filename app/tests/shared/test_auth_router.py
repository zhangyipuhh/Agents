# -*- coding:utf-8 -*-
"""
认证路由测试模块

测试 auth_router 提供的验证码、注册、登录、验证和登出接口。
"""
import sys
from unittest.mock import MagicMock

# 环境可能未安装 asyncpg，预先 mock 以避免 Safety -> database 导入链失败
if "asyncpg" not in sys.modules:
    sys.modules["asyncpg"] = MagicMock()

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="function")
def app():
    """
    创建仅包含 auth_router 的 FastAPI 应用实例

    避免加载项目中其他缺失依赖的路由模块。
    """
    from app.core.server import create_app
    from app.shared.routers.auth_router import router as auth_router

    _app = create_app()
    _app.include_router(auth_router)
    return _app


@pytest.fixture(scope="function")
def client(app):
    """
    提供 FastAPI TestClient

    Args:
        app: 仅含 auth_router 的 FastAPI 应用实例

    Yields:
        TestClient: HTTP 测试客户端
    """
    with TestClient(app) as c:
        yield c


def test_get_captcha(client):
    """
    测试 GET /api/auth/captcha 返回 200 和包含 key、image 的 JSON

    Args:
        client: FastAPI TestClient

    Returns:
        None
    """
    response = client.get("/api/auth/captcha")
    assert response.status_code == 200
    data = response.json()
    assert "captcha_key" in data
    assert "captcha_image" in data
    assert isinstance(data["captcha_key"], str)
    assert isinstance(data["captcha_image"], str)


def test_register_success(client, monkeypatch):
    """
    测试正常注册流程

    使用 monkeypatch mock CaptchaManager.verify 返回 True，避免真实验证码校验失败。

    Args:
        client: FastAPI TestClient
        monkeypatch: pytest monkeypatch fixture

    Returns:
        None
    """
    monkeypatch.setattr(
        "app.shared.utils.auth.captcha.captcha_manager.verify",
        lambda key, code: True,
    )

    payload = {
        "username": "newuser001",
        "password": "Test@123",
        "confirm_password": "Test@123",
        "real_name": "张三",
        "phone": "13800138000",
        "email": "test@example.com",
        "department": "测试部",
        "position": "工程师",
        "captcha_key": "mock_key",
        "captcha_code": "ABCD",
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 200
    assert response.json()["message"] == "注册成功"


def test_register_duplicate_username(client, monkeypatch):
    """
    测试重复用户名注册失败

    先注册一次，再次使用相同用户名注册应返回 400。

    Args:
        client: FastAPI TestClient
        monkeypatch: pytest monkeypatch fixture

    Returns:
        None
    """
    monkeypatch.setattr(
        "app.shared.utils.auth.captcha.captcha_manager.verify",
        lambda key, code: True,
    )

    payload = {
        "username": "dupuser001",
        "password": "Test@123",
        "confirm_password": "Test@123",
        "real_name": "李四",
        "phone": "13900139000",
        "email": "dup@example.com",
        "department": "",
        "position": "",
        "captcha_key": "mock_key",
        "captcha_code": "ABCD",
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 200

    response2 = client.post("/api/auth/register", json=payload)
    assert response2.status_code == 400
    assert "用户名已存在" in response2.json()["detail"]


def test_login_api_success(client):
    """
    测试 POST /api/auth/login-api 免验证码登录成功并返回 access_token

    memory 模式下使用硬编码凭据 admin/123456 可直接登录。

    Args:
        client: FastAPI TestClient

    Returns:
        None
    """
    payload = {
        "username": "admin",
        "password": "123456",
    }
    response = client.post("/api/auth/login-api", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "Bearer"
    assert data["username"] == "admin"


def test_validate_token(client, admin_headers):
    """
    测试 GET /api/auth/validate 验证有效 token 返回用户信息

    Args:
        client: FastAPI TestClient
        admin_headers: admin 认证请求头（来自 conftest）

    Returns:
        None
    """
    response = client.get("/api/auth/validate", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "admin"
    assert "allowed_agents" in data
    assert isinstance(data["allowed_agents"], list)


def test_logout(client, admin_headers):
    """
    测试 POST /api/auth/logout 登出成功

    Args:
        client: FastAPI TestClient
        admin_headers: admin 认证请求头（来自 conftest）

    Returns:
        None
    """
    response = client.post("/api/auth/logout", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["message"] == "登出成功"


class TestIssuePortalRefreshToken:
    """测试 issue-portal-refresh-token 接口"""

    def test_issue_portal_refresh_token_exists(self):
        """
        验证 issue_portal_refresh_token 函数存在且可导入
        """
        from app.shared.routers.auth_router import issue_portal_refresh_token

        assert callable(issue_portal_refresh_token)

    def test_issue_portal_refresh_token_rejects_kicked_user(self, monkeypatch):
        """
        测试场景：用户被踢后（refresh_token 被删除）调用 issue-portal-refresh-token

        参数:
            monkeypatch: pytest monkeypatch fixture

        预期结果:
            抛出 HTTPException，状态码 401
        """
        import asyncio
        from unittest.mock import AsyncMock
        from fastapi import Request, HTTPException
        from app.shared.routers.auth_router import issue_portal_refresh_token

        # 构造 mock request，模拟 auth_middleware 已写入用户信息
        mock_request = AsyncMock(spec=Request)
        mock_request.state.username = 'testuser'
        mock_request.state.user_id = 1

        # Mock RefreshTokenDB.has_valid_token 返回 False（模拟被踢）
        from app.shared.utils.auth import refresh_token_db

        monkeypatch.setattr(
            refresh_token_db.RefreshTokenDB,
            'has_valid_token',
            AsyncMock(return_value=False)
        )

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(issue_portal_refresh_token(mock_request))

        assert exc_info.value.status_code == 401
        assert '用户会话已失效' in exc_info.value.detail

    def test_issue_portal_refresh_token_accepts_valid_user(self, monkeypatch):
        """
        测试场景：正常用户调用 issue-portal-refresh-token

        参数:
            monkeypatch: pytest monkeypatch fixture

        预期结果:
            成功返回 portal_refresh_token
        """
        import asyncio
        from unittest.mock import AsyncMock
        from fastapi import Request
        from app.shared.routers.auth_router import issue_portal_refresh_token

        # 构造 mock request
        mock_request = AsyncMock(spec=Request)
        mock_request.state.username = 'testuser'
        mock_request.state.user_id = 1

        # Mock RefreshTokenDB.has_valid_token 返回 True
        from app.shared.utils.auth import refresh_token_db

        monkeypatch.setattr(
            refresh_token_db.RefreshTokenDB,
            'has_valid_token',
            AsyncMock(return_value=True)
        )

        # Mock PortalRefreshTokenDB 相关操作
        from app.shared.utils.auth import portal_refresh_token_db

        monkeypatch.setattr(
            portal_refresh_token_db.PortalRefreshTokenDB,
            'delete_user_tokens',
            AsyncMock(return_value=0)
        )
        monkeypatch.setattr(
            portal_refresh_token_db.PortalRefreshTokenDB,
            'hash_token',
            staticmethod(lambda x: 'hash123')
        )
        monkeypatch.setattr(
            portal_refresh_token_db.PortalRefreshTokenDB,
            'store_token',
            AsyncMock(return_value=True)
        )

        # Mock jwt_auth.generate_refresh_token
        from app.shared.utils.auth import Safety

        monkeypatch.setattr(
            Safety.jwt_auth,
            'generate_refresh_token',
            AsyncMock(return_value='portal_token_123')
        )

        result = asyncio.run(issue_portal_refresh_token(mock_request))

        assert result.portal_refresh_token == 'portal_token_123'
