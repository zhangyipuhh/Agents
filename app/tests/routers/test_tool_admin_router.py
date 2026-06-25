# -*- coding:utf-8 -*-
"""
Tool Admin Router 测试模块

验证 /api/admin/tools/* 路由的 CRUD、启用/禁用、扫描功能及 admin 权限校验。
使用 client fixture（来自全局 conftest.py），service 实例由
routers/conftest.py::_init_tool_service autouse fixture 注入。

测试策略：
- 路由注册：验证 7 个端点路径已注册到 app.routes
- 成功路径：monkeypatch service 方法返回固定值，验证响应 200/201/204
- 失败路径：monkeypatch service 方法抛 ToolNotFoundError/ToolAlreadyExistsError，
  验证响应 404/409
- 权限校验：非 admin 用户访问返回 403
- service 未初始化：删除 app.state.tool_service，验证返回 500
"""
import pytest

from app.shared.utils.agent.tool_service import (
    ToolAlreadyExistsError,
    ToolNotFoundError,
)


# =============================================================================
# P0: 导入与路由注册
# =============================================================================

def test_tool_admin_router_importable():
    """测试 tool_admin_router 模块可导入且包含 router 对象。

    验证目标：
        - 模块 ``app.routers.tool_admin_router`` 可正常导入
        - 模块包含 ``router`` 属性（APIRouter 实例）

    返回:
        None
    """
    from app.routers import tool_admin_router
    assert hasattr(tool_admin_router, "router")


def test_list_tools_endpoint_registered(client):
    """测试 GET /api/admin/tools 路由已注册。

    参数:
        client: FastAPI TestClient fixture

    返回:
        None
    """
    routes = [r.path for r in client.app.routes]
    assert "/api/admin/tools" in routes


def test_list_unregistered_endpoint_registered(client):
    """测试 GET /api/admin/tools/unregistered 路由已注册。

    参数:
        client: FastAPI TestClient fixture

    返回:
        None
    """
    routes = [r.path for r in client.app.routes]
    assert "/api/admin/tools/unregistered" in routes


def test_create_tool_endpoint_registered(client):
    """测试 POST /api/admin/tools 路由已注册。

    参数:
        client: FastAPI TestClient fixture

    返回:
        None
    """
    routes = [r.path for r in client.app.routes]
    assert "/api/admin/tools" in routes


def test_update_tool_endpoint_registered(client):
    """测试 PUT /api/admin/tools/{name} 路由已注册。

    参数:
        client: FastAPI TestClient fixture

    返回:
        None
    """
    routes = [r.path for r in client.app.routes]
    assert "/api/admin/tools/{name}" in routes


def test_delete_tool_endpoint_registered(client):
    """测试 DELETE /api/admin/tools/{name} 路由已注册。

    参数:
        client: FastAPI TestClient fixture

    返回:
        None
    """
    routes = [r.path for r in client.app.routes]
    assert "/api/admin/tools/{name}" in routes


def test_set_enabled_endpoint_registered(client):
    """测试 PUT /api/admin/tools/{name}/enabled 路由已注册。

    参数:
        client: FastAPI TestClient fixture

    返回:
        None
    """
    routes = [r.path for r in client.app.routes]
    assert "/api/admin/tools/{name}/enabled" in routes


def test_scan_endpoint_registered(client):
    """测试 POST /api/admin/tools/scan 路由已注册。

    参数:
        client: FastAPI TestClient fixture

    返回:
        None
    """
    routes = [r.path for r in client.app.routes]
    assert "/api/admin/tools/scan" in routes


# =============================================================================
# P1: 成功路径
# =============================================================================

def test_list_tools_returns_200(client, admin_headers, monkeypatch):
    """测试 GET /api/admin/tools 返回 200 及工具列表。

    参数:
        client: FastAPI TestClient fixture
        admin_headers: admin 认证请求头
        monkeypatch: pytest monkeypatch fixture

    返回:
        None
    """
    async def fake_list_tools(self):
        return [{"name": "search", "category": "filesystem", "enabled": True}]

    monkeypatch.setattr(
        "app.shared.utils.agent.tool_service.ToolRegistryService.list_tools",
        fake_list_tools,
    )

    response = client.get("/api/admin/tools", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["name"] == "search"


def test_list_unregistered_returns_200(client, admin_headers, monkeypatch):
    """测试 GET /api/admin/tools/unregistered 返回 200 及未注册工具列表。

    参数:
        client: FastAPI TestClient fixture
        admin_headers: admin 认证请求头
        monkeypatch: pytest monkeypatch fixture

    返回:
        None
    """
    async def fake_scan(self):
        return [{"name": "new_tool", "file_path": "app/core/tools/x.py"}]

    monkeypatch.setattr(
        "app.shared.utils.agent.tool_service.ToolRegistryService.scan_unregistered",
        fake_scan,
    )

    response = client.get("/api/admin/tools/unregistered", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["name"] == "new_tool"


def test_create_tool_returns_201(client, admin_headers, monkeypatch):
    """测试 POST /api/admin/tools 创建工具返回 201。

    参数:
        client: FastAPI TestClient fixture
        admin_headers: admin 认证请求头
        monkeypatch: pytest monkeypatch fixture

    返回:
        None
    """
    async def fake_create(self, config):
        return {
            "name": config["name"],
            "category": config["category"],
            "enabled": config.get("enabled", True),
        }

    monkeypatch.setattr(
        "app.shared.utils.agent.tool_service.ToolRegistryService.create_tool",
        fake_create,
    )

    response = client.post(
        "/api/admin/tools",
        headers=admin_headers,
        json={
            "name": "search",
            "category": "filesystem",
            "module_path": "app.core.tools.BaseTools",
            "file_path": "app/core/tools/BaseTools.py",
        },
    )
    assert response.status_code == 201
    assert response.json()["name"] == "search"


def test_update_tool_returns_200(client, admin_headers, monkeypatch):
    """测试 PUT /api/admin/tools/{name} 更新工具返回 200。

    参数:
        client: FastAPI TestClient fixture
        admin_headers: admin 认证请求头
        monkeypatch: pytest monkeypatch fixture

    返回:
        None
    """
    async def fake_update(self, name, config):
        return {"name": name, "category": config.get("category", "")}

    monkeypatch.setattr(
        "app.shared.utils.agent.tool_service.ToolRegistryService.update_tool",
        fake_update,
    )

    response = client.put(
        "/api/admin/tools/search",
        headers=admin_headers,
        json={"category": "sandbox", "enabled": False},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "search"
    assert response.json()["category"] == "sandbox"


def test_delete_tool_returns_204(client, admin_headers, monkeypatch):
    """测试 DELETE /api/admin/tools/{name} 删除工具返回 204。

    参数:
        client: FastAPI TestClient fixture
        admin_headers: admin 认证请求头
        monkeypatch: pytest monkeypatch fixture

    返回:
        None
    """
    async def fake_delete(self, name):
        return None

    monkeypatch.setattr(
        "app.shared.utils.agent.tool_service.ToolRegistryService.delete_tool",
        fake_delete,
    )

    response = client.delete(
        "/api/admin/tools/search", headers=admin_headers
    )
    assert response.status_code == 204


def test_set_tool_enabled_returns_200(client, admin_headers, monkeypatch):
    """测试 PUT /api/admin/tools/{name}/enabled 启用/禁用工具返回 200。

    参数:
        client: FastAPI TestClient fixture
        admin_headers: admin 认证请求头
        monkeypatch: pytest monkeypatch fixture

    返回:
        None
    """
    async def fake_set_enabled(self, name, enabled):
        return {"name": name, "enabled": enabled}

    monkeypatch.setattr(
        "app.shared.utils.agent.tool_service.ToolRegistryService.set_tool_enabled",
        fake_set_enabled,
    )

    response = client.put(
        "/api/admin/tools/search/enabled",
        headers=admin_headers,
        json={"enabled": False},
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is False


def test_scan_unregistered_returns_200(client, admin_headers, monkeypatch):
    """测试 POST /api/admin/tools/scan 扫描未注册工具返回 200。

    参数:
        client: FastAPI TestClient fixture
        admin_headers: admin 认证请求头
        monkeypatch: pytest monkeypatch fixture

    返回:
        None
    """
    async def fake_scan(self):
        return [{"name": "scanned_tool", "file_path": "app/core/tools/y.py"}]

    monkeypatch.setattr(
        "app.shared.utils.agent.tool_service.ToolRegistryService.scan_unregistered",
        fake_scan,
    )

    response = client.post("/api/admin/tools/scan", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["name"] == "scanned_tool"


# =============================================================================
# P1: 失败路径
# =============================================================================

def test_create_tool_conflict_returns_409(client, admin_headers, monkeypatch):
    """测试 POST /api/admin/tools 工具已存在返回 409。

    参数:
        client: FastAPI TestClient fixture
        admin_headers: admin 认证请求头
        monkeypatch: pytest monkeypatch fixture

    返回:
        None
    """
    async def fake_create(self, config):
        raise ToolAlreadyExistsError(f"Tool '{config['name']}' already exists")

    monkeypatch.setattr(
        "app.shared.utils.agent.tool_service.ToolRegistryService.create_tool",
        fake_create,
    )

    response = client.post(
        "/api/admin/tools",
        headers=admin_headers,
        json={
            "name": "search",
            "category": "filesystem",
            "module_path": "app.core.tools.BaseTools",
            "file_path": "app/core/tools/BaseTools.py",
        },
    )
    assert response.status_code == 409


def test_update_tool_not_found_returns_404(client, admin_headers, monkeypatch):
    """测试 PUT /api/admin/tools/{name} 工具不存在返回 404。

    参数:
        client: FastAPI TestClient fixture
        admin_headers: admin 认证请求头
        monkeypatch: pytest monkeypatch fixture

    返回:
        None
    """
    async def fake_update(self, name, config):
        raise ToolNotFoundError(f"Tool '{name}' not found")

    monkeypatch.setattr(
        "app.shared.utils.agent.tool_service.ToolRegistryService.update_tool",
        fake_update,
    )

    response = client.put(
        "/api/admin/tools/missing",
        headers=admin_headers,
        json={"category": "sandbox"},
    )
    assert response.status_code == 404


def test_delete_tool_not_found_returns_404(client, admin_headers, monkeypatch):
    """测试 DELETE /api/admin/tools/{name} 工具不存在返回 404。

    参数:
        client: FastAPI TestClient fixture
        admin_headers: admin 认证请求头
        monkeypatch: pytest monkeypatch fixture

    返回:
        None
    """
    async def fake_delete(self, name):
        raise ToolNotFoundError(f"Tool '{name}' not found")

    monkeypatch.setattr(
        "app.shared.utils.agent.tool_service.ToolRegistryService.delete_tool",
        fake_delete,
    )

    response = client.delete(
        "/api/admin/tools/missing", headers=admin_headers
    )
    assert response.status_code == 404


def test_set_tool_enabled_not_found_returns_404(client, admin_headers, monkeypatch):
    """测试 PUT /api/admin/tools/{name}/enabled 工具不存在返回 404。

    参数:
        client: FastAPI TestClient fixture
        admin_headers: admin 认证请求头
        monkeypatch: pytest monkeypatch fixture

    返回:
        None
    """
    async def fake_set_enabled(self, name, enabled):
        raise ToolNotFoundError(f"Tool '{name}' not found")

    monkeypatch.setattr(
        "app.shared.utils.agent.tool_service.ToolRegistryService.set_tool_enabled",
        fake_set_enabled,
    )

    response = client.put(
        "/api/admin/tools/missing/enabled",
        headers=admin_headers,
        json={"enabled": True},
    )
    assert response.status_code == 404


# =============================================================================
# P1: 权限校验
# =============================================================================

def test_list_tools_non_admin_returns_403(client, user_headers):
    """测试非 admin 用户访问 GET /api/admin/tools 返回 403。

    参数:
        client: FastAPI TestClient fixture
        user_headers: 普通用户认证请求头

    返回:
        None
    """
    response = client.get("/api/admin/tools", headers=user_headers)
    assert response.status_code == 403


def test_create_tool_non_admin_returns_403(client, user_headers):
    """测试非 admin 用户访问 POST /api/admin/tools 返回 403。

    参数:
        client: FastAPI TestClient fixture
        user_headers: 普通用户认证请求头

    返回:
        None
    """
    response = client.post(
        "/api/admin/tools",
        headers=user_headers,
        json={
            "name": "search",
            "category": "filesystem",
            "module_path": "app.core.tools.BaseTools",
            "file_path": "app/core/tools/BaseTools.py",
        },
    )
    assert response.status_code == 403


def test_delete_tool_non_admin_returns_403(client, user_headers):
    """测试非 admin 用户访问 DELETE /api/admin/tools/{name} 返回 403。

    参数:
        client: FastAPI TestClient fixture
        user_headers: 普通用户认证请求头

    返回:
        None
    """
    response = client.delete(
        "/api/admin/tools/search", headers=user_headers
    )
    assert response.status_code == 403


# =============================================================================
# P2: service 未初始化（边界条件）
# =============================================================================

def test_list_tools_service_not_initialized_returns_500(client, admin_headers):
    """测试 ToolRegistryService 未初始化时 GET /api/admin/tools 返回 500。

    生产场景：lifespan 中 ToolRegistryService 初始化失败（try/except 包裹），
    app.state.tool_service 不存在，路由应返回 500 而非 AttributeError。

    参数:
        client: FastAPI TestClient fixture
        admin_headers: admin 认证请求头

    返回:
        None
    """
    # 删除 fixture 注入的 service，模拟 lifespan 初始化失败
    if hasattr(client.app.state, "tool_service"):
        delattr(client.app.state, "tool_service")

    response = client.get("/api/admin/tools", headers=admin_headers)
    assert response.status_code == 500


def test_create_tool_service_not_initialized_returns_500(client, admin_headers):
    """测试 ToolRegistryService 未初始化时 POST /api/admin/tools 返回 500。

    参数:
        client: FastAPI TestClient fixture
        admin_headers: admin 认证请求头

    返回:
        None
    """
    if hasattr(client.app.state, "tool_service"):
        delattr(client.app.state, "tool_service")

    response = client.post(
        "/api/admin/tools",
        headers=admin_headers,
        json={
            "name": "search",
            "category": "filesystem",
            "module_path": "app.core.tools.BaseTools",
            "file_path": "app/core/tools/BaseTools.py",
        },
    )
    assert response.status_code == 500


# =============================================================================
# P1: 请求体校验
# =============================================================================

def test_create_tool_missing_required_field_returns_422(client, admin_headers):
    """测试 POST /api/admin/tools 缺少必填字段返回 422。

    缺少 category（必填），Pydantic 校验失败返回 422。

    参数:
        client: FastAPI TestClient fixture
        admin_headers: admin 认证请求头

    返回:
        None
    """
    response = client.post(
        "/api/admin/tools",
        headers=admin_headers,
        json={
            "name": "search",
            # 缺少 category
            "module_path": "app.core.tools.BaseTools",
            "file_path": "app/core/tools/BaseTools.py",
        },
    )
    assert response.status_code == 422
