# -*- coding:utf-8 -*-
"""
认证路由测试模块

测试 auth_router 提供的验证码、注册、登录、验证和登出接口。
"""
import asyncio
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


def test_login_api_success(client, monkeypatch):
    """
    测试 POST /api/auth/login-api 免验证码登录成功并返回 access_token

    memory 模式下使用环境注入的 bootstrap 凭据 admin/P@ssword1! 可直接登录。

    Args:
        client: FastAPI TestClient
        monkeypatch: pytest monkeypatch fixture

    Returns:
        None
    """
    monkeypatch.setenv("AUTH_DEFAULT_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("AUTH_DEFAULT_ADMIN_PASSWORD", "P@ssword1!")

    # 2026-08-11 等保三级 Task 5：client fixture 的 lifespan 在 setenv 之前已启动，
    # 必须手动重新注入 jwt_auth.bootstrap_* 与预创建 admin 才能让
    # login-api 真实路径走通（避免默认 "" 与 None 凭据 fail-loud）。
    from app.shared.utils.auth.Safety import jwt_auth
    from app.shared.utils.auth.user_db import UserDB
    jwt_auth.bootstrap_username = "admin"
    jwt_auth.bootstrap_password = "P@ssword1!"
    if asyncio.run(UserDB.get_user_by_username("admin")) is None:
        asyncio.run(UserDB.create_user("admin", "P@ssword1!", role="admin"))

    payload = {
        "username": "admin",
        "password": "P@ssword1!",
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


def test_validate_response_includes_visible_menus_for_admin(client, admin_headers, monkeypatch):
    """admin validate 响应含 visible_menus（全量 enabled 项 id）。

    shared/test_auth_router.py 用的 client 是 test_auth_router.py 自己的 fixture
    （create_app() + include_router(auth_router)），不会自动注入 menu_permission_service。
    此处 monkeypatch 把真实 MenuPermissionService(db=None) 挂到 client.app.state，
    并 mock UserDB.get_user_by_username 让 username='admin' 返 role='admin'。
    """
    from app.core.menu_registry import get_enabled_items
    from app.shared.utils.auth.menu_permission_service import MenuPermissionService

    monkeypatch.setattr(
        client.app.state, "menu_permission_service",
        MenuPermissionService(db=None), raising=False,
    )

    async def fake_get_user(username):
        if username == "admin":
            return {"id": 1, "username": "admin", "role": "admin", "allowed_agents": []}
        return None
    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username",
        fake_get_user,
    )

    response = client.get("/api/auth/validate", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert "visible_menus" in data
    expected = sorted(
        [m.id for m in get_enabled_items()],
        key=lambda mid: next(m.sort_order for m in get_enabled_items() if m.id == mid),
    )
    assert data["visible_menus"] == expected


def test_validate_response_includes_visible_menus_for_normal_user(client, user_headers, monkeypatch):
    """普通用户 validate 响应含 visible_menus（service 过滤后；空 ACL 仅 ['profile']）。

    与上面同理 monkeypatch 注入 MenuPermissionService(db=None) 并 mock UserDB
    让 username='testuser' 返 role='user'，普通用户空 ACL 走 fail-secure 仅 ['profile']。
    """
    from app.shared.utils.auth.menu_permission_service import MenuPermissionService

    monkeypatch.setattr(
        client.app.state, "menu_permission_service",
        MenuPermissionService(db=None), raising=False,
    )

    async def fake_get_user(username):
        if username == "testuser":
            return {"id": 2, "username": "testuser", "role": "user", "allowed_agents": []}
        return None
    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username",
        fake_get_user,
    )

    response = client.get("/api/auth/validate", headers=user_headers)
    assert response.status_code == 200
    data = response.json()
    assert "visible_menus" in data
    assert data["visible_menus"] == ["profile"]


def test_login_response_includes_visible_menus(client, monkeypatch):
    """POST /api/auth/login-api 响应含 visible_menus（admin 登录后看到所有菜单）。"""
    from app.shared.utils.auth.menu_permission_service import MenuPermissionService

    monkeypatch.setenv("AUTH_DEFAULT_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("AUTH_DEFAULT_ADMIN_PASSWORD", "P@ssword1!")

    # 2026-08-11 等保三级 Task 5：lifespan 早于 setenv 触发，必须手动重注
    from app.shared.utils.auth.Safety import jwt_auth
    from app.shared.utils.auth.user_db import UserDB
    jwt_auth.bootstrap_username = "admin"
    jwt_auth.bootstrap_password = "P@ssword1!"
    if asyncio.run(UserDB.get_user_by_username("admin")) is None:
        asyncio.run(UserDB.create_user("admin", "P@ssword1!", role="admin"))

    monkeypatch.setattr(
        client.app.state, "menu_permission_service",
        MenuPermissionService(db=None), raising=False,
    )

    async def fake_get_user(username):
        if username == "admin":
            return {"id": 1, "username": "admin", "role": "admin", "allowed_agents": []}
        return None
    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username",
        fake_get_user,
    )

    response = client.post(
        "/api/auth/login-api",
        json={"username": "admin", "password": "P@ssword1!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "visible_menus" in data
    assert len(data["visible_menus"]) > 0
    assert "profile" in data["visible_menus"]
    # admin 应能看到权限管理
    assert "permission-management" in data["visible_menus"]


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


def test_login_api_sets_access_token_cookie(client, monkeypatch):
    """
    测试登录响应同时下发 access_token HttpOnly Cookie

    Args:
        client: FastAPI TestClient
        monkeypatch: pytest monkeypatch fixture

    Returns:
        None
    """
    monkeypatch.setenv("AUTH_DEFAULT_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("AUTH_DEFAULT_ADMIN_PASSWORD", "P@ssword1!")
    # 2026-08-11 Task 5：lifespan 早于 setenv 触发，必须手动重注
    from app.shared.utils.auth.Safety import jwt_auth
    from app.shared.utils.auth.user_db import UserDB
    jwt_auth.bootstrap_username = "admin"
    jwt_auth.bootstrap_password = "P@ssword1!"
    if asyncio.run(UserDB.get_user_by_username("admin")) is None:
        asyncio.run(UserDB.create_user("admin", "P@ssword1!", role="admin"))

    response = client.post(
        "/api/auth/login-api",
        json={"username": "admin", "password": "P@ssword1!"},
    )
    assert response.status_code == 200
    # JSON body 保留 access_token（程序化客户端兼容）
    assert "access_token" in response.json()
    cookies = response.headers.get_list("set-cookie")
    access = [c for c in cookies if c.startswith("access_token=")]
    assert len(access) == 1
    assert "HttpOnly" in access[0]
    assert "Path=/api" in access[0]
    assert "Max-Age=1800" in access[0]


def test_login_api_refresh_cookie_has_samesite_strict(client, monkeypatch):
    """
    测试 refresh_token Cookie 保持 HttpOnly + SameSite=Strict（回归）

    Args:
        client: FastAPI TestClient
        monkeypatch: pytest monkeypatch fixture

    Returns:
        None
    """
    monkeypatch.setenv("AUTH_DEFAULT_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("AUTH_DEFAULT_ADMIN_PASSWORD", "P@ssword1!")
    # 2026-08-11 Task 5：lifespan 早于 setenv 触发，必须手动重注
    from app.shared.utils.auth.Safety import jwt_auth
    from app.shared.utils.auth.user_db import UserDB
    jwt_auth.bootstrap_username = "admin"
    jwt_auth.bootstrap_password = "P@ssword1!"
    if asyncio.run(UserDB.get_user_by_username("admin")) is None:
        asyncio.run(UserDB.create_user("admin", "P@ssword1!", role="admin"))

    response = client.post(
        "/api/auth/login-api",
        json={"username": "admin", "password": "P@ssword1!"},
    )
    cookies = response.headers.get_list("set-cookie")
    refresh = [c for c in cookies if c.startswith("refresh_token=")]
    assert len(refresh) == 1
    assert "HttpOnly" in refresh[0]
    assert "SameSite=strict" in refresh[0].lower() or "samesite=strict" in refresh[0].lower()


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


def test_refresh_sets_new_access_token_cookie(client, monkeypatch):
    """
    测试刷新接口轮换 access_token Cookie

    覆盖属性：
    - Set-Cookie 中存在唯一一条 access_token=
    - Cookie 值与响应体 access_token 一致（轮换）
    - HttpOnly
    - Path=/api
    - Max-Age=1800

    Args:
        client: FastAPI TestClient
        monkeypatch: pytest monkeypatch fixture

    Returns:
        None
    """
    monkeypatch.setenv("AUTH_DEFAULT_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("AUTH_DEFAULT_ADMIN_PASSWORD", "P@ssword1!")
    # 2026-08-11 Task 5：lifespan 早于 setenv 触发，必须手动重注
    from app.shared.utils.auth.Safety import jwt_auth
    from app.shared.utils.auth.user_db import UserDB
    jwt_auth.bootstrap_username = "admin"
    jwt_auth.bootstrap_password = "P@ssword1!"
    if asyncio.run(UserDB.get_user_by_username("admin")) is None:
        asyncio.run(UserDB.create_user("admin", "P@ssword1!", role="admin"))

    login_resp = client.post(
        "/api/auth/login-api",
        json={"username": "admin", "password": "P@ssword1!"},
    )
    assert login_resp.status_code == 200
    resp = client.post("/api/auth/refresh")
    assert resp.status_code == 200
    body_token = resp.json()["access_token"]
    cookies = resp.headers.get_list("set-cookie")
    access = [c for c in cookies if c.startswith("access_token=")]
    assert len(access) == 1
    assert f"access_token={body_token}" in access[0]
    assert "HttpOnly" in access[0]
    assert "Path=/api" in access[0]
    assert "Max-Age=1800" in access[0]


def test_validate_accepts_cookie_auth(client, admin_headers):
    """
    测试 validate 接口支持 Cookie 携带 access_token（无 Authorization 头）

    Args:
        client: FastAPI TestClient
        admin_headers: admin 认证请求头（用于取有效 token 字符串）

    Returns:
        None
    """
    token = admin_headers["Authorization"].split(" ", 1)[1]
    client.cookies.set("access_token", token, path="/api")
    response = client.get("/api/auth/validate")
    assert response.status_code == 200
    assert response.json()["username"] == "admin"


def test_logout_deletes_access_token_cookie(client, admin_headers):
    """
    测试登出响应删除 access_token Cookie

    Args:
        client: FastAPI TestClient
        admin_headers: admin 认证请求头

    Returns:
        None
    """
    response = client.post("/api/auth/logout", headers=admin_headers)
    assert response.status_code == 200
    cookies = response.headers.get_list("set-cookie")
    deleted = [c for c in cookies if c.startswith("access_token=") and "Max-Age=0" in c]
    assert len(deleted) == 1


def test_logout_via_cookie_auth_with_csrf_header(client, admin_headers):
    """
    测试 Cookie 鉴权 + X-Requested-With 头的写请求放行

    Args:
        client: FastAPI TestClient
        admin_headers: admin 认证请求头（用于取有效 token 字符串）

    Returns:
        None
    """
    token = admin_headers["Authorization"].split(" ", 1)[1]
    client.cookies.set("access_token", token, path="/api")
    response = client.post(
        "/api/auth/logout",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert response.status_code == 200


def test_cookie_auth_write_request_without_csrf_header_rejected(client, admin_headers):
    """
    测试 Cookie 鉴权写请求缺 X-Requested-With 头返回 403（CSRF 防线）

    Args:
        client: FastAPI TestClient
        admin_headers: admin 认证请求头

    Returns:
        None
    """
    token = admin_headers["Authorization"].split(" ", 1)[1]
    client.cookies.set("access_token", token, path="/api")
    response = client.post("/api/auth/logout")
    assert response.status_code == 403


def test_bearer_auth_write_request_exempt_from_csrf(client, admin_headers):
    """
    测试 Bearer 鉴权写请求豁免 CSRF 头校验（既有行为回归）

    Args:
        client: FastAPI TestClient
        admin_headers: admin 认证请求头

    Returns:
        None
    """
    response = client.post("/api/auth/logout", headers=admin_headers)
    assert response.status_code == 200
