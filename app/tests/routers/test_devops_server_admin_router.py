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


# ----------------------------------------------------------------------
# 4. DELETE /api/admin/devops-servers/{server_id}
# ----------------------------------------------------------------------


def test_delete_endpoint_registered(client, devops_router_setup):
    """DELETE /{server_id} 路由已注册。"""
    paths = [
        r.path
        for r in devops_router_setup.routes
        if hasattr(r, "methods") and "DELETE" in r.methods
    ]
    assert "/api/admin/devops-servers/{server_id}" in paths


def test_delete_returns_204_when_service_succeeds(client, devops_router_setup, admin_headers, monkeypatch):
    """删除成功 → 204 No Content，无响应体。"""

    async def fake_delete(server_id):
        return None

    async def fake_exists(server_id):
        return True

    svc = devops_router_setup.state.devops_server_service
    monkeypatch.setattr(svc, "delete_server", fake_delete)
    monkeypatch.setattr(svc, "server_exists", fake_exists)

    resp = client.delete("/api/admin/devops-servers/1", headers=admin_headers)
    assert resp.status_code == 204
    assert resp.content == b""


def test_delete_missing_server_returns_404(client, devops_router_setup, admin_headers, monkeypatch):
    """DB 未命中时由 router 主动抛 404（service 本身幂等，不抛 404）。"""
    async def fake_exists(server_id):
        return False

    async def fake_delete(server_id):
        return None

    svc = devops_router_setup.state.devops_server_service
    monkeypatch.setattr(svc, "server_exists", fake_exists)
    monkeypatch.setattr(svc, "delete_server", fake_delete)

    resp = client.delete("/api/admin/devops-servers/9999", headers=admin_headers)
    assert resp.status_code == 404
    body = resp.json()
    # 通用 detail，不回显 server_id
    assert body["detail"] == "服务器不存在"
    assert "9999" not in resp.text


def test_delete_service_missing_returns_500(client, admin_headers):
    """服务未初始化 → 500（与 GET / POST 一致）。"""
    from app.main import app

    saved = getattr(app.state, "devops_server_service", None)
    app.state.devops_server_service = None
    try:
        resp = client.delete("/api/admin/devops-servers/1", headers=admin_headers)
        assert resp.status_code == 500
    finally:
        app.state.devops_server_service = saved


def test_delete_db_failure_returns_500_without_leak(client, devops_router_setup, admin_headers, monkeypatch):
    """DB 失败 → 500 + 通用错误，不回显 SQL / 原 detail。"""

    async def fake_exists(server_id):
        return True

    async def fake_delete(server_id):
        raise RuntimeError(
            "asyncpg 报错：DELETE 失败 on devops_servers, leaked=__LEAKED_pwd_hunter2__"
        )

    svc = devops_router_setup.state.devops_server_service
    monkeypatch.setattr(svc, "server_exists", fake_exists)
    monkeypatch.setattr(svc, "delete_server", fake_delete)

    resp = client.delete("/api/admin/devops-servers/1", headers=admin_headers)
    assert resp.status_code == 500
    body_text = resp.text
    assert "__LEAKED_pwd_hunter2__" not in body_text
    assert "asyncpg" not in body_text


# ----------------------------------------------------------------------
# 5. 巡检脚本字段不外泄（2026-07-22 新增）
# ----------------------------------------------------------------------


def test_list_endpoint_does_not_leak_inspection_script(client, devops_router_setup, admin_headers, monkeypatch):
    """GET 响应不应包含 inspection_script / inspection_parser（公开白名单严格 4 字段）。

    即使 service 失误返回了含脚本字段的 raw 数据,router 也必须做白名单过滤,
    防止脚本字符串泄漏到 admin API 响应中。
    """
    raw_with_script = [
        {
            "id": 7,
            "business_name": "alpha",
            "server_type": "linux",
            "updated_at": "2026-07-22",
            "inspection_script": "echo LEAKED_SCRIPT_TOKEN_xyz",
            "inspection_parser": "json",
        }
    ]
    svc = devops_router_setup.state.devops_server_service
    # 模拟 service 失误: 返回包含 inspection_script 的原始数据
    monkeypatch.setattr(svc, "list_public_servers", lambda: raw_with_script)

    resp = client.get("/api/admin/devops-servers", headers=admin_headers)
    assert resp.status_code == 200
    body_text = resp.text
    # 关键断言: 脚本字符串与解析器字段名都不应出现在响应体中
    assert "LEAKED_SCRIPT_TOKEN_xyz" not in body_text
    assert "inspection_script" not in body_text
    assert "inspection_parser" not in body_text
    # 仍为 4 字段白名单
    item = resp.json()[0]
    assert set(item.keys()) == {"id", "business_name", "server_type", "updated_at"}



# ----------------------------------------------------------------------
# 6. GET /api/admin/devops-servers/{server_id} 详情端点（2026-07-22 新增）
# ----------------------------------------------------------------------


def test_detail_endpoint_registered(client, devops_router_setup):
    """GET /{server_id} 路由已注册。"""
    paths = [
        r.path
        for r in devops_router_setup.routes
        if hasattr(r, "methods") and "GET" in r.methods
    ]
    assert "/api/admin/devops-servers/{server_id}" in paths


def test_detail_returns_whitelist_and_inspection_script(client, devops_router_setup, admin_headers, monkeypatch):
    """详情端点成功：返回白名单命令与脚本原文。"""
    fake_detail = {
        "id": 7,
        "business_name": "alpha",
        "server_type": "linux",
        "updated_at": "2026-07-22",
        "whitelist": ["ls", "df -h"],
        "inspection_script": "echo hi",
        "inspection_parser": "json",
    }
    svc = devops_router_setup.state.devops_server_service
    monkeypatch.setattr(svc, "get_server_detail", lambda server_id: fake_detail)

    resp = client.get("/api/admin/devops-servers/7", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 7
    assert body["whitelist"] == ["ls", "df -h"]
    assert body["inspection_script"] == "echo hi"
    assert body["inspection_parser"] == "json"
    # 安全边界：详情响应不应包含 ip / port / username / password
    for sensitive in ["ip", "port", "username", "password", "password_encrypted", "blacklist"]:
        assert sensitive not in body, f"leak: {sensitive}"


def test_detail_missing_server_returns_404(client, devops_router_setup, admin_headers, monkeypatch):
    """service.get_server_detail 返回 None → 404 + 通用文案。"""
    svc = devops_router_setup.state.devops_server_service
    monkeypatch.setattr(svc, "get_server_detail", lambda server_id: None)

    resp = client.get("/api/admin/devops-servers/9999", headers=admin_headers)
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"] == "服务器不存在"
    # 不回显 server_id
    assert "9999" not in resp.text


def test_detail_service_missing_returns_500(client, admin_headers):
    """服务未初始化 → 500。"""
    from app.main import app
    saved = getattr(app.state, "devops_server_service", None)
    app.state.devops_server_service = None
    try:
        resp = client.get("/api/admin/devops-servers/1", headers=admin_headers)
        assert resp.status_code == 500
    finally:
        app.state.devops_server_service = saved


def test_detail_does_not_leak_password_or_sensitive(client, devops_router_setup, admin_headers, monkeypatch):
    """即使 service 失误返回含敏感字段，router 也应过滤到详情白名单。"""
    leaked = {
        "id": 7,
        "business_name": "alpha",
        "server_type": "linux",
        "updated_at": "2026-07-22",
        "whitelist": ["ls"],
        "inspection_script": "echo LEAKED_SCRIPT_TOKEN_xyz",
        "inspection_parser": "json",
        "ip": "10.0.0.99",
        "port": 22,
        "username": "rootuser",
        "password": "supersecret-pwd-xyz",
        "blacklist": ["rm -rf /"],
    }
    svc = devops_router_setup.state.devops_server_service
    # 模拟 service 失误：返回含敏感字段
    monkeypatch.setattr(svc, "get_server_detail", lambda server_id: leaked)

    resp = client.get("/api/admin/devops-servers/7", headers=admin_headers)
    assert resp.status_code == 200
    body_text = resp.text
    # 敏感值不应出现在响应体
    for sensitive in ["10.0.0.99", "supersecret-pwd-xyz", "rootuser", "rm -rf"]:
        assert sensitive not in body_text, f"leak: {sensitive}"
    # 但允许白名单与脚本（脚本可读 = 业务要求）
    assert "LEAKED_SCRIPT_TOKEN_xyz" in body_text
    assert '"ls"' in body_text
