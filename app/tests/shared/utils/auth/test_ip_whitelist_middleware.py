# -*- coding:utf-8 -*-
"""IP 白名单中间件测试(注册审批 + IP 白名单,2026-08-30 新增)"""
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.shared.utils.auth.ip_whitelist_middleware import ip_whitelist_middleware
from app.core.config.settings import RegistrationSecuritySettings


@pytest.fixture
def app_with_route():
    app = FastAPI()
    router = APIRouter()

    @router.post("/api/auth/register")
    async def register():
        return {"ok": True}

    @router.post("/api/auth/login")
    async def login():
        return {"ok": True}

    @router.get("/api/users")
    async def list_users():
        return {"ok": True}

    app.include_router(router)
    app.middleware("http")(ip_whitelist_middleware)
    return app


@pytest.fixture
def client(app_with_route):
    with TestClient(app_with_route) as c:
        yield c


def test_disabled_passes_through(client, monkeypatch):
    """enabled=False 时所有路径直通,不查 X-Real-IP。"""
    monkeypatch.setattr(
        "app.shared.utils.auth.ip_whitelist_middleware.settings.registration_security",
        RegistrationSecuritySettings(enabled=False),
    )
    resp = client.post("/api/auth/register")
    assert resp.status_code == 200


def test_non_register_path_passes_through(client, monkeypatch):
    """enabled=True 时,/api/auth/login 等非注册路径不查 IP。"""
    monkeypatch.setattr(
        "app.shared.utils.auth.ip_whitelist_middleware.settings.registration_security",
        RegistrationSecuritySettings(enabled=True, ip_whitelist=["10.0.0.0/8"]),
    )
    resp = client.post("/api/auth/login")
    assert resp.status_code == 200


def test_missing_x_real_ip_blocked(client, monkeypatch):
    """enabled=True + 注册路径 + 缺失 X-Real-IP → 403。"""
    monkeypatch.setattr(
        "app.shared.utils.auth.ip_whitelist_middleware.settings.registration_security",
        RegistrationSecuritySettings(enabled=True, ip_whitelist=["10.0.0.0/8"]),
    )
    resp = client.post("/api/auth/register")
    assert resp.status_code == 403
    assert "无法识别" in resp.json()["detail"]


def test_invalid_ip_format_blocked(client, monkeypatch):
    """X-Real-IP 不是合法 IP 字符串 → 403。"""
    monkeypatch.setattr(
        "app.shared.utils.auth.ip_whitelist_middleware.settings.registration_security",
        RegistrationSecuritySettings(enabled=True, ip_whitelist=["10.0.0.0/8"]),
    )
    resp = client.post(
        "/api/auth/register", headers={"X-Real-IP": "not-an-ip"}
    )
    assert resp.status_code == 403
    assert "格式非法" in resp.json()["detail"]


def test_ip_not_in_whitelist_blocked(client, monkeypatch):
    """X-Real-IP 不在白名单 → 403。"""
    monkeypatch.setattr(
        "app.shared.utils.auth.ip_whitelist_middleware.settings.registration_security",
        RegistrationSecuritySettings(enabled=True, ip_whitelist=["10.0.0.0/8"]),
    )
    resp = client.post(
        "/api/auth/register", headers={"X-Real-IP": "8.8.8.8"}
    )
    assert resp.status_code == 403
    assert "不允许" in resp.json()["detail"]


def test_ip_in_whitelist_allowed(client, monkeypatch):
    """X-Real-IP 在白名单 CIDR 内 → 200。"""
    monkeypatch.setattr(
        "app.shared.utils.auth.ip_whitelist_middleware.settings.registration_security",
        RegistrationSecuritySettings(enabled=True, ip_whitelist=["10.0.0.0/8", "192.168.1.0/24"]),
    )
    resp = client.post(
        "/api/auth/register", headers={"X-Real-IP": "10.5.3.100"}
    )
    assert resp.status_code == 200


def test_empty_whitelist_blocks_all(client, monkeypatch):
    """白名单为空 → 拒绝所有(fail-closed)。"""
    monkeypatch.setattr(
        "app.shared.utils.auth.ip_whitelist_middleware.settings.registration_security",
        RegistrationSecuritySettings(enabled=True, ip_whitelist=[]),
    )
    resp = client.post(
        "/api/auth/register", headers={"X-Real-IP": "127.0.0.1"}
    )
    assert resp.status_code == 403


def test_cidr_boundary_matching(client, monkeypatch):
    """CIDR 边界匹配:192.168.1.100 应匹配 192.168.1.0/24。"""
    monkeypatch.setattr(
        "app.shared.utils.auth.ip_whitelist_middleware.settings.registration_security",
        RegistrationSecuritySettings(enabled=True, ip_whitelist=["192.168.1.0/24"]),
    )
    resp = client.post(
        "/api/auth/register", headers={"X-Real-IP": "192.168.1.100"}
    )
    assert resp.status_code == 200
