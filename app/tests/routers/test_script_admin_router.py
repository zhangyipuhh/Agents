# -*- coding:utf-8 -*-
"""
Script Admin Router 测试模块。

验证 /api/admin/scripts 下的脚本列表与扫描接口：
- 路由注册
- 白名单字段过滤
- 扫描接口返回 ScanSummary
- 服务未初始化时返回 500
- 普通用户访问返回 403

生产对等初始化点：app/core/server.py lifespan 中
``ScriptDiscoveryService(SCRIPTS_DIR)`` 创建并挂到
``app.state.script_discovery_service``，受 ``settings.script_scan_enabled`` 控制。
"""
from unittest.mock import AsyncMock, MagicMock

import pytest


# =============================================================================
# P0: 导入与路由注册
# =============================================================================

def test_script_admin_router_importable():
    """测试 script_admin_router 模块可导入且包含 router。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 模块不可导入或无 router 属性时失败
    """
    from app.routers import script_admin_router

    assert hasattr(script_admin_router, "router")


def test_script_admin_endpoints_registered(client):
    """测试 /api/admin/scripts 与 /api/admin/scripts/scan 端点已注册。

    参数:
        client: TestClient fixture。

    返回值:
        None

    异常:
        AssertionError: 路由未注册时失败
    """
    routes = [r.path for r in client.app.routes]
    expected = [
        "/api/admin/scripts",
        "/api/admin/scripts/scan",
    ]
    for path in expected:
        assert path in routes, f"路由未注册: {path}"


# =============================================================================
# P1: 成功路径
# =============================================================================

def test_list_scripts_returns_200(client, admin_headers):
    """测试 GET /api/admin/scripts 返回白名单字段列表。

    参数:
        client: TestClient fixture。
        admin_headers: admin 身份头 fixture。

    返回值:
        None

    异常:
        AssertionError: 状态码非 200 或返回字段不在白名单时失败
    """
    service = MagicMock()
    service.list_scripts = MagicMock(
        return_value=[
            {
                "name": "hello_script",
                "display_name": "示例脚本",
                "description": "演示",
                "params_schema": None,
                "module_path": "app.scripts.examples.hello_script",
            }
        ]
    )
    client.app.state.script_discovery_service = service

    response = client.get("/api/admin/scripts", headers=admin_headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "hello_script"
    assert data[0]["display_name"] == "示例脚本"
    # 白名单字段：不应包含 func 等内部字段
    assert "func" not in data[0]


def test_scan_scripts_returns_200(client, admin_headers):
    """测试 POST /api/admin/scripts/scan 返回 ScanSummary。

    参数:
        client: TestClient fixture。
        admin_headers: admin 身份头 fixture。

    返回值:
        None

    异常:
        AssertionError: 状态码非 200 或 summary 字段缺失时失败
    """
    service = MagicMock()
    service.scan = AsyncMock(
        return_value={"scanned": 3, "registered": 2, "failed": 1}
    )
    client.app.state.script_discovery_service = service

    response = client.post("/api/admin/scripts/scan", headers=admin_headers)

    assert response.status_code == 200
    summary = response.json()
    assert summary["scanned"] == 3
    assert summary["registered"] == 2
    assert summary["failed"] == 1
    service.scan.assert_awaited_once()


# =============================================================================
# P1: 失败路径与权限
# =============================================================================

def test_script_admin_service_missing_returns_500(client, admin_headers):
    """测试 script_discovery_service 未初始化时返回 500。

    参数:
        client: TestClient fixture。
        admin_headers: admin 身份头 fixture。

    返回值:
        None

    异常:
        AssertionError: 状态码非 500 或错误信息不匹配时失败
    """
    # 确保属性不存在
    if hasattr(client.app.state, "script_discovery_service"):
        delattr(client.app.state, "script_discovery_service")

    response = client.get("/api/admin/scripts", headers=admin_headers)

    assert response.status_code == 500
    assert response.json()["detail"] == "ScriptDiscoveryService not initialized"


def test_user_cannot_access_script_admin(client, user_headers):
    """测试普通用户访问脚本管理接口返回 403。

    参数:
        client: TestClient fixture。
        user_headers: 普通用户身份头 fixture。

    返回值:
        None

    异常:
        AssertionError: 状态码非 403 时失败
    """
    response = client.get("/api/admin/scripts", headers=user_headers)

    assert response.status_code == 403
