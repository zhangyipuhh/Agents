# -*- coding:utf-8 -*-
"""注册审批 + IP 白名单端到端集成测试(2026-08-30 新增)

端到端验证完整链路:
1. enabled=False 时,register 行为与现状一致(注册即 active,立即可登录)
2. enabled=True 时,register 创建 pending_approval 用户,login 返回 403,
   admin 走 /api/users/{id}/approve 审批通过后用户可登录
3. enabled=True + IP 不在白名单 -> /register 返 403 (中间件 fail-closed)

测试策略:
- 纯 memory 模式,无 PG 依赖
- ``_patch_registration_security`` 整体替换 ``settings.registration_security`` 实例
  (monkeypatch 自动还原),确保 register 函数内局部 import 的 settings 也看到新配置
- enabled=True 时 ``ip_whitelist`` 必须非空(middleware fail-closed 语义),
  register 请求需显式带 ``X-Real-IP: 127.0.0.1`` 命中白名单
- fresh_app 在 create_app 之前主动 populate admin 到 ``UserDB._memory_users``,
  绕开 lifespan 中 ensure_admin_exists 与业务测试的时序耦合
"""
import asyncio
import sys
from unittest.mock import MagicMock

# 环境可能未安装 asyncpg, 预先 mock 以避免 Safety -> database 导入链失败
if "asyncpg" not in sys.modules:
    sys.modules["asyncpg"] = MagicMock()

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="function")
def fresh_app(monkeypatch):
    """构造含 auth_router + user_router 的最小 app, memory 模式, 无外部依赖。

    主动 populate 一个占位 admin 到 ``UserDB._memory_users`` (password_hash=""),
    让 lifespan 中 ``ensure_admin_exists`` 走「admin 已存在 + 哈希非弱默认」分支
    静默返回,不抛出 fail-loud RuntimeError。
    """
    from app.shared.utils.auth.user_db import UserDB

    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0

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
        "allowed_agents": [],
        "status": "active",
        "status_reason": None,
        "register_ip": None,
        "approved_by_user_id": None,
        "approved_at": None,
        "created_at": None,
        "updated_at": None,
    }
    UserDB._memory_id_counter = 1

    from app.core.server import create_app
    from app.shared.routers.auth_router import router as auth_router_mod
    from app.shared.routers.user_router import router as user_router_mod

    _app = create_app()
    _app.include_router(auth_router_mod)
    _app.include_router(user_router_mod)
    return _app


@pytest.fixture(scope="function")
def client(fresh_app):
    """FastAPI TestClient。

    Args:
        fresh_app: 含 auth_router + user_router 的 FastAPI 应用。

    Yields:
        TestClient: HTTP 测试客户端。
    """
    with TestClient(fresh_app) as c:
        yield c


def _patch_registration_security(monkeypatch, *, enabled, ip_whitelist):
    """替换全局 ``settings.registration_security`` 实例 (monkeypatch 自动还原)。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        enabled: 总开关 (bool)。
        ip_whitelist: IP 白名单列表 (list[str]); 留空触发 fail-closed
            拒绝所有 register 请求。
    """
    from app.core.config.settings import RegistrationSecuritySettings, settings

    new_cfg = RegistrationSecuritySettings(
        enabled=enabled,
        ip_whitelist=list(ip_whitelist) if ip_whitelist else [],
    )
    monkeypatch.setattr(settings, "registration_security", new_cfg)


def _register_payload(username: str, phone: str, email: str, real_name: str) -> dict:
    """构造 /api/auth/register 的标准请求体。

    Args:
        username: 用户名 (>=3 char)
        phone: 中国大陆手机号
        email: 邮箱地址
        real_name: 真实姓名 (2-20 char)

    Returns:
        dict: 含强口令 + 验证码 mock 字段的请求体。
    """
    return {
        "username": username,
        "password": "Test@123",
        "confirm_password": "Test@123",
        "real_name": real_name,
        "phone": phone,
        "email": email,
        "department": "",
        "position": "",
        "captcha_key": "k",
        "captcha_code": "ABCD",
    }


def test_e2e_disabled_register_then_login_succeeds(monkeypatch, client):
    """enabled=False 端到端: 注册后立即可登录 (向后兼容路径)。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        client: FastAPI TestClient。

    Returns:
        None
    """
    _patch_registration_security(monkeypatch, enabled=False, ip_whitelist=[])
    monkeypatch.setattr(
        "app.shared.utils.auth.captcha.captcha_manager.verify",
        lambda key, code: True,
    )

    r = client.post("/api/auth/register", json=_register_payload(
        "e2e_disabled", "13800138000", "e2e_disabled@example.com", "E2E",
    ))
    assert r.status_code == 200, r.text
    assert r.json()["message"] == "注册成功"

    from app.shared.utils.auth.user_db import UserDB
    user = asyncio.run(UserDB.get_user_by_username("e2e_disabled"))
    assert user is not None
    assert user["status"] == "active"

    r_login = client.post(
        "/api/auth/login",
        json={
            "username": "e2e_disabled",
            "password": "Test@123",
            "captcha_key": "k",
            "captcha_code": "ABCD",
        },
    )
    assert r_login.status_code == 200, r_login.text


def test_e2e_enabled_register_creates_pending_blocks_login(monkeypatch, client):
    """enabled=True 端到端: register 创建 pending_approval 用户, login 返 403。

    middleware 有 fail-closed 语义, ip_whitelist 必须非空, register 请求需
    带 ``X-Real-IP`` 头命中白名单。
    """
    _patch_registration_security(
        monkeypatch, enabled=True, ip_whitelist=["127.0.0.1"],
    )
    monkeypatch.setattr(
        "app.shared.utils.auth.captcha.captcha_manager.verify",
        lambda key, code: True,
    )

    r = client.post(
        "/api/auth/register",
        json=_register_payload(
            "e2e_pending", "13800138001", "e2e_pending@example.com", "E2E Pending",
        ),
        headers={"X-Real-IP": "127.0.0.1"},
    )
    assert r.status_code == 200, r.text
    assert "审批" in r.json()["message"]

    from app.shared.utils.auth.user_db import UserDB
    user = asyncio.run(UserDB.get_user_by_username("e2e_pending"))
    assert user is not None
    assert user["status"] == "pending_approval"
    assert user["register_ip"] == "127.0.0.1"
    assert user["approved_by_user_id"] is None
    assert user["approved_at"] is None

    r_login = client.post(
        "/api/auth/login",
        json={
            "username": "e2e_pending",
            "password": "Test@123",
            "captcha_key": "k",
            "captcha_code": "ABCD",
        },
    )
    assert r_login.status_code == 403, r_login.text
    assert "待管理员审批" in r_login.json()["detail"]


def test_e2e_enabled_approve_then_status_active(monkeypatch, client):
    """enabled=True 端到端: admin 审批通过后 user.status='active' 与审计字段写入。

    端到端真实路径: register (pending) -> admin token -> /api/users/{id}/approve
    -> RegistrationApprovalService.approve_user -> UserDB.update_user_status
    """
    _patch_registration_security(
        monkeypatch, enabled=True, ip_whitelist=["127.0.0.1"],
    )
    monkeypatch.setattr(
        "app.shared.utils.auth.captcha.captcha_manager.verify",
        lambda key, code: True,
    )

    r = client.post(
        "/api/auth/register",
        json=_register_payload(
            "e2e_approve", "13800138002", "e2e_approve@example.com", "E2E Approve",
        ),
        headers={"X-Real-IP": "127.0.0.1"},
    )
    assert r.status_code == 200, r.text

    from app.shared.utils.auth.user_db import UserDB
    user = asyncio.run(UserDB.get_user_by_username("e2e_approve"))
    assert user is not None
    pending_id = user["id"]
    assert user["status"] == "pending_approval"

    import jwt
    from datetime import datetime as _dt, timedelta as _td
    from app.shared.utils.auth.Safety import JWTAuth

    admin_payload = {
        "username": "admin",
        "type": "access",
        "exp": _dt.utcnow() + _td(minutes=30),
        "iat": _dt.utcnow(),
    }
    admin_token = jwt.encode(
        admin_payload, JWTAuth().secret_key, algorithm="HS256",
    )
    headers = {"Authorization": f"Bearer {admin_token}"}

    r_approve = client.post(
        f"/api/users/{pending_id}/approve",
        json={},
        headers=headers,
    )
    assert r_approve.status_code == 200, r_approve.text

    user_after = asyncio.run(UserDB.get_user_by_username("e2e_approve"))
    assert user_after["status"] == "active"
    assert user_after["approved_by_user_id"] is not None
    assert user_after["approved_at"] is not None


def test_e2e_enabled_ip_not_whitelisted_blocked(monkeypatch, client):
    """enabled=True + IP 不在白名单 -> register 返 403 (中间件 fail-closed 路径)。

    验证 ``ip_whitelist_middleware`` 在真实 enabled=True 配置下拦截非白名单 IP。
    """
    _patch_registration_security(
        monkeypatch, enabled=True, ip_whitelist=["10.0.0.1"],
    )
    monkeypatch.setattr(
        "app.shared.utils.auth.captcha.captcha_manager.verify",
        lambda key, code: True,
    )

    r = client.post(
        "/api/auth/register",
        json=_register_payload(
            "e2e_blocked", "13800138003", "e2e_blocked@example.com", "E2E Blocked",
        ),
        headers={"X-Real-IP": "127.0.0.1"},
    )
    assert r.status_code == 403, r.text
    assert "当前网络不允许注册" in r.json()["detail"]

    from app.shared.utils.auth.user_db import UserDB
    user = asyncio.run(UserDB.get_user_by_username("e2e_blocked"))
    assert user is None
