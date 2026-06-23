# -*- coding:utf-8 -*-
"""
MCP Admin Router 测试模块

验证 /api/admin/mcp/* 路由的 CRUD 和 toggle 功能。
使用 client fixture（来自全局 conftest.py）。
"""
import pytest


def test_mcp_admin_router_importable():
    """测试 mcp_admin_router 模块可导入。"""
    from app.routers import mcp_admin_router
    assert hasattr(mcp_admin_router, "router")


def test_list_servers_endpoint_registered(client):
    """测试 GET /api/admin/mcp/servers 路由已注册。"""
    routes = [r.path for r in client.app.routes]
    assert "/api/admin/mcp/servers" in routes


def test_create_server_endpoint_registered(client):
    """测试 POST /api/admin/mcp/servers 路由已注册。"""
    routes = [r.path for r in client.app.routes]
    assert "/api/admin/mcp/servers" in routes


def test_toggle_server_endpoint_registered(client):
    """测试 POST /api/admin/mcp/servers/{name}/toggle 路由已注册。"""
    routes = [r.path for r in client.app.routes]
    assert "/api/admin/mcp/servers/{name}/toggle" in routes


def test_list_methods_endpoint_registered(client):
    """测试 GET /api/admin/mcp/servers/{name}/methods 路由已注册。"""
    routes = [r.path for r in client.app.routes]
    assert "/api/admin/mcp/servers/{name}/methods" in routes


def test_refresh_methods_endpoint_registered(client):
    """测试 POST /api/admin/mcp/servers/{name}/refresh-methods 路由已注册。"""
    routes = [r.path for r in client.app.routes]
    assert "/api/admin/mcp/servers/{name}/refresh-methods" in routes


def test_toggle_method_endpoint_registered(client):
    """测试 POST /api/admin/mcp/servers/{name}/methods/{method}/toggle 路由已注册。"""
    routes = [r.path for r in client.app.routes]
    assert "/api/admin/mcp/servers/{name}/methods/{method}/toggle" in routes


def test_list_servers_returns_200(client, admin_headers, monkeypatch):
    """测试 GET /api/admin/mcp/servers 返回 200。"""
    async def fake_list(self):
        return [{"name": "amap", "enabled": True}]

    monkeypatch.setattr(
        "app.shared.utils.agent.mcp_service.McpConfigService.list_servers",
        fake_list,
    )

    response = client.get("/api/admin/mcp/servers", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["name"] == "amap"


def test_create_server_returns_201(client, admin_headers, monkeypatch):
    """测试 POST /api/admin/mcp/servers 创建 server 返回 201。"""
    async def fake_create(self, config):
        return {"name": config.name, "type": config.type, "enabled": True}

    monkeypatch.setattr(
        "app.shared.utils.agent.mcp_service.McpConfigService.create_server",
        fake_create,
    )

    response = client.post(
        "/api/admin/mcp/servers",
        headers=admin_headers,
        json={"name": "amap", "type": "sse", "url": "http://x"},
    )
    assert response.status_code == 201
    assert response.json()["name"] == "amap"


def test_delete_server_returns_204(client, admin_headers, monkeypatch):
    """测试 DELETE /api/admin/mcp/servers/{name} 返回 204。"""
    async def fake_delete(self, name):
        return None

    monkeypatch.setattr(
        "app.shared.utils.agent.mcp_service.McpConfigService.delete_server",
        fake_delete,
    )

    response = client.delete("/api/admin/mcp/servers/amap", headers=admin_headers)
    assert response.status_code == 204


def test_toggle_server_returns_200(client, admin_headers, monkeypatch):
    """测试 POST /api/admin/mcp/servers/{name}/toggle 返回 200。"""
    async def fake_toggle(self, name, enabled):
        return None

    monkeypatch.setattr(
        "app.shared.utils.agent.mcp_service.McpConfigService.toggle_server",
        fake_toggle,
    )

    response = client.post(
        "/api/admin/mcp/servers/amap/toggle",
        headers=admin_headers,
        params={"enabled": False},
    )
    assert response.status_code == 200
