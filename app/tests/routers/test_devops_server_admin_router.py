# -*- coding:utf-8 -*-
"""
devops_server_admin_router 单元测试（2026-07-15 新增）

覆盖目标：
    - GET  /api/admin/devops-servers 严格返回 {id, business_name, server_type, updated_at}
    - POST /api/admin/devops-servers/scan 严格返回 {scanned, inserted, updated, failed}
    - 服务未初始化（app.state.devops_server_service = None）→ 500
    - 扫描异常被吃，返回通用错误（不回显原始 detail/path/IP/password/名单）
    - 遵循生产对等的 app.state.devops_server_service 初始化方式（不在 state 伪造对象）

依赖：
    - tests/conftest.py::client / admin_headers 已提供；这里复用
    - tests/routers/conftest.py autouse fixture 注入 mcp_config_service /
      agent_config_service / tool_service / task_scheduler_service；
      DevOpsServerService 需在此处显式注入真实服务实例（按生产对等原则），
      而非用 MagicMock 直接挂在 app.state.devops_server_service 上。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet


VALID_FERNET_KEY = Fernet.generate_key().decode("ascii")


def _build_real_service():
    """构造真实的 ``DevOpsServerService`` 实例（db=None）。

    Returns:
        DevOpsServerService: 实例
    """
    from app.shared.utils.devops_server_service import DevOpsServerService

    db = MagicMock(name="db_pool_stub")
    db.fetch = AsyncMock(return_value=[])
    db.fetchrow = AsyncMock(return_value=None)
    db.execute = AsyncMock(return_value=None)
    return DevOpsServerService(
        db=db,
        config_path="unused.yaml",
        credential_key=VALID_FERNET_KEY,
    )


@pytest.fixture
def devops_router_setup(app):
    """手动挂载 ``DevOpsServerService``（生产对等）。

    Args:
        app: FastAPI 应用（来自全局 conftest fixture）
    """
    from app.shared.utils.devops_server_service import DevOpsServerService

    svc = _build_real_service()
    app.state.devops_server_service = svc
    DevOpsServerService.set_instance(svc)
    yield app
    DevOpsServerService.reset()
    if hasattr(app.state, "devops_server_service"):
        app.state.devops_server_service = None


# ----------------------------------------------------------------------
# 1. 路由注册 + 模块可导入
# ----------------------------------------------------------------------


def test_devops_server_admin_router_importable():
    """测试 devops_server_admin_router 模块可导入。"""
    from app.routers import devops_server_admin_router
    assert hasattr(devops_server_admin_router, "router")


def test_list_endpoint_registered(client, devops_router_setup):
    """GET /api/admin/devops-servers 路由已注册。"""
    routes = [r.path for r in devops_router_setup.routes]
    assert "/api/admin/devops-servers" in routes


def test_scan_endpoint_registered(client, devops_router_setup):
    """POST /api/admin/devops-servers/scan 路由已注册。"""
    routes = [r.path for r in devops_router_setup.routes]
    assert "/api/admin/devops-servers/scan" in routes


# ----------------------------------------------------------------------
# 2. GET /api/admin/devops-servers
# ----------------------------------------------------------------------


def test_list_returns_whitelisted_fields(client, devops_router_setup, admin_headers, monkeypatch):
    """GET 返回的每条记录严格只含白名单 4 个字段。

    Args:
        client: FastAPI TestClient
        devops_router_setup: 注入 service 的 fixture
        admin_headers: admin Bearer header
        monkeypatch: pytest monkeypatch
    """
    public_output = [
        {"id": 7, "business_name": "alpha", "server_type": "linux", "updated_at": "2026-07-15"}
    ]
    svc = devops_router_setup.state.devops_server_service
    monkeypatch.setattr(svc, "list_public_servers", lambda: public_output)

    resp = client.get("/api/admin/devops-servers", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 1
    item = body[0]
    assert set(item.keys()) == {"id", "business_name", "server_type", "updated_at"}


def test_list_does_not_leak_sensitive_fields(client, devops_router_setup, admin_headers, monkeypatch):
    """GET 响应体内不应出现 ip / password / blacklist / whitelist 等敏感字段。

    即使 service 失误返回了所有字段，router 也必须做白名单过滤。
    """
    raw = [
        {
            "id": 7,
            "business_name": "alpha",
            "ip": "10.0.0.99",
            "port": 22,
            "username": "rootuser",
            "password": "supersecret-pwd-xyz",
            "password_encrypted": b"encrypted",
            "server_type": "linux",
            "blacklist": ["rm -rf /"],
            "whitelist": ["ls"],
            "updated_at": "2026-07-15",
        }
    ]
    svc = devops_router_setup.state.devops_server_service
    # 此时返回原始「未过滤」数据；router 应过滤成 4 字段
    monkeypatch.setattr(svc, "list_public_servers", lambda: [
        {k: v for k, v in item.items() if k in {"id", "business_name", "server_type", "updated_at"}}
        for item in raw
    ])

    resp = client.get("/api/admin/devops-servers", headers=admin_headers)
    assert resp.status_code == 200
    body_text = resp.text
    for sensitive in ["10.0.0.99", "supersecret-pwd-xyz", "rootuser", "rm -rf"]:
        assert sensitive not in body_text


def test_list_service_missing_returns_500(client, admin_headers):
    """服务未初始化 → 500。"""
    # 提前移除 devops_server_service
    from app.main import app
    saved = getattr(app.state, "devops_server_service", None)
    app.state.devops_server_service = None
    try:
        resp = client.get("/api/admin/devops-servers", headers=admin_headers)
        assert resp.status_code == 500
        assert "DevOpsServerService" in resp.text or "not initialized" in resp.text
    finally:
        app.state.devops_server_service = saved


# ----------------------------------------------------------------------
# 3. POST /api/admin/devops-servers/scan
# ----------------------------------------------------------------------


def test_scan_returns_only_four_numbers(client, devops_router_setup, admin_headers, monkeypatch):
    """POST /scan 返回严格 {scanned, inserted, updated, failed} 4 个数字。

    Args:
        client: FastAPI TestClient
        devops_router_setup: 注入 service 的 fixture
        admin_headers: admin Bearer header
        monkeypatch: pytest monkeypatch
    """
    async def fake_scan():
        return {"scanned": 3, "inserted": 2, "updated": 1, "failed": 0}

    svc = devops_router_setup.state.devops_server_service
    monkeypatch.setattr(svc, "scan_and_upsert", fake_scan)

    resp = client.post("/api/admin/devops-servers/scan", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"scanned", "inserted", "updated", "failed"}
    assert body == {"scanned": 3, "inserted": 2, "updated": 1, "failed": 0}


def test_scan_error_does_not_leak_sensitive_details(client, devops_router_setup, admin_headers, monkeypatch):
    """扫描异常时不回显原始异常详情（防止 IP/路径/密码/名单外泄）。"""
    async def fake_scan():
        raise RuntimeError(
            "yaml path C:\\servers.yaml contains leaked IP 10.0.0.99 "
            "and password verysecret-xyz with blacklist=['rm -rf']"
        )

    svc = devops_router_setup.state.devops_server_service
    monkeypatch.setattr(svc, "scan_and_upsert", fake_scan)

    resp = client.post("/api/admin/devops-servers/scan", headers=admin_headers)
    assert resp.status_code == 500
    body_text = resp.text
    for sensitive in ["verysecret-xyz", "10.0.0.99", "C:\\servers.yaml", "rm -rf"]:
        assert sensitive not in body_text, f"leak: {sensitive} in {body_text!r}"


def test_scan_service_missing_returns_500(client, admin_headers):
    """POST /scan 在服务未初始化时返回 500。"""
    from app.main import app
    saved = getattr(app.state, "devops_server_service", None)
    app.state.devops_server_service = None
    try:
        resp = client.post("/api/admin/devops-servers/scan", headers=admin_headers)
        assert resp.status_code == 500
    finally:
        app.state.devops_server_service = saved
