# -*- coding:utf-8 -*-
"""
MCP Admin Router 测试模块

验证 /api/admin/mcp/* 路由的 CRUD 和 toggle 功能。
使用 client fixture（来自全局 conftest.py）。
"""
import pytest


class _FakeRegistryBase:
    """测试用 FakeRegistry 基类，提供 shutdown 方法供 lifespan 清理调用。

    生产对等初始化点：app/core/server.py lifespan 中
    `app.state.mcp_registry = registry`（真实 MCPToolsRegistry 有 shutdown 方法）。
    """

    async def shutdown(self):
        pass


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


# =============================================================================
# Registry 同步测试（2026-06-24 新增）
# 验证 4 个写路由在 DB 操作后调用了 mcp_registry 对应方法
# =============================================================================


def test_create_server_syncs_registry(client, admin_headers, monkeypatch):
    """测试 POST /servers 创建后同步调用 registry.add_server。"""
    async def fake_create(self, config):
        return {"name": config.name, "type": config.type, "enabled": True}

    monkeypatch.setattr(
        "app.shared.utils.agent.mcp_service.McpConfigService.create_server",
        fake_create,
    )

    # mock registry
    add_server_calls = []

    class FakeRegistry(_FakeRegistryBase):
        async def add_server(self, name, config):
            add_server_calls.append((name, config))

    client.app.state.mcp_registry = FakeRegistry()

    response = client.post(
        "/api/admin/mcp/servers",
        headers=admin_headers,
        json={"name": "amap", "type": "sse", "url": "http://x"},
    )
    assert response.status_code == 201
    assert len(add_server_calls) == 1
    assert add_server_calls[0][0] == "amap"
    assert add_server_calls[0][1]["name"] == "amap"


def test_update_server_syncs_registry(client, admin_headers, monkeypatch):
    """测试 PUT /servers/{name} 更新后同步调用 registry.update_server。"""
    async def fake_update(self, name, config):
        return {"name": name, "type": config.type, "enabled": True}

    monkeypatch.setattr(
        "app.shared.utils.agent.mcp_service.McpConfigService.update_server",
        fake_update,
    )

    update_server_calls = []

    class FakeRegistry(_FakeRegistryBase):
        async def update_server(self, name, config):
            update_server_calls.append((name, config))

    client.app.state.mcp_registry = FakeRegistry()

    response = client.put(
        "/api/admin/mcp/servers/amap",
        headers=admin_headers,
        json={"name": "amap", "type": "sse", "url": "http://y"},
    )
    assert response.status_code == 200
    assert len(update_server_calls) == 1
    assert update_server_calls[0][0] == "amap"


def test_delete_server_syncs_registry(client, admin_headers, monkeypatch):
    """测试 DELETE /servers/{name} 删除后同步调用 registry.remove_server。"""
    async def fake_delete(self, name):
        return None

    monkeypatch.setattr(
        "app.shared.utils.agent.mcp_service.McpConfigService.delete_server",
        fake_delete,
    )

    remove_server_calls = []

    class FakeRegistry(_FakeRegistryBase):
        async def remove_server(self, name):
            remove_server_calls.append(name)

    client.app.state.mcp_registry = FakeRegistry()

    response = client.delete(
        "/api/admin/mcp/servers/amap",
        headers=admin_headers,
    )
    assert response.status_code == 204
    assert len(remove_server_calls) == 1
    assert remove_server_calls[0] == "amap"


def test_toggle_server_syncs_registry(client, admin_headers, monkeypatch):
    """测试 POST /servers/{name}/toggle 后同步调用 registry.toggle_server。"""
    async def fake_toggle(self, name, enabled):
        return None

    monkeypatch.setattr(
        "app.shared.utils.agent.mcp_service.McpConfigService.toggle_server",
        fake_toggle,
    )

    toggle_server_calls = []

    class FakeRegistry(_FakeRegistryBase):
        async def toggle_server(self, name, enabled):
            toggle_server_calls.append((name, enabled))

    client.app.state.mcp_registry = FakeRegistry()

    response = client.post(
        "/api/admin/mcp/servers/amap/toggle",
        headers=admin_headers,
        params={"enabled": False},
    )
    assert response.status_code == 200
    assert len(toggle_server_calls) == 1
    assert toggle_server_calls[0] == ("amap", False)


def test_build_config_dict_contains_new_fields():
    """测试 _build_config_dict 包含 4 个新字段（args/env/headers/connect_timeout）。"""
    from app.routers.mcp_admin_router import _build_config_dict
    from app.shared.utils.agent.mcp_service import McpServerConfig

    config = McpServerConfig(
        name="amap",
        type="sse",
        url="http://x",
        args=["-y", "server"],
        env={"KEY": "VAL"},
        headers={"Authorization": "Bearer token"},
        connect_timeout=30,
    )
    result = _build_config_dict(config)
    assert result["args"] == ["-y", "server"]
    assert result["env"] == {"KEY": "VAL"}
    assert result["headers"] == {"Authorization": "Bearer token"}
    assert result["connect_timeout"] == 30
