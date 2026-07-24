# -*- coding:utf-8 -*-
"""
agent_permission_router 路由契约测试。

覆盖点：
- 3 个端点都受 require_admin 守护（普通用户返 403）
- admin 调用：GET /catalog 返全量；GET /users/{id}/grants 返授权；
  PUT /users/{id}/grants 全量覆盖
- PUT 失败抛 500
- 端点路径已注册
"""

from unittest.mock import AsyncMock


BASE = "/api/admin/permissions/agents"


# =============================================================================
# P0: 导入与路由注册
# =============================================================================


def test_agent_permission_router_importable():
    """测试 agent_permission_router 模块可导入且包含 router。"""
    from app.routers import agent_permission_router

    assert hasattr(agent_permission_router, "router")


def test_agent_permission_endpoints_registered(client):
    """测试所有智能体权限端点已注册。"""
    routes = [r.path for r in client.app.routes]
    expected = [
        f"{BASE}/catalog",
        f"{BASE}/users/{{user_id}}/grants",
    ]
    for path in expected:
        assert path in routes, f"路由未注册: {path}"


# =============================================================================
# P1: require_admin 守护
# =============================================================================


def test_catalog_requires_admin(client, user_headers):
    """GET /catalog 普通用户访问返回 403。"""
    response = client.get(f"{BASE}/catalog", headers=user_headers)
    assert response.status_code == 403


def test_get_grants_requires_admin(client, user_headers):
    """GET /users/{id}/grants 普通用户访问返回 403。"""
    response = client.get(f"{BASE}/users/1/grants", headers=user_headers)
    assert response.status_code == 403


def test_put_grants_requires_admin(client, user_headers):
    """PUT /users/{id}/grants 普通用户访问返回 403。"""
    response = client.put(
        f"{BASE}/users/1/grants",
        headers=user_headers,
        json={"agent_names": ["map_agent"]},
    )
    assert response.status_code == 403


# =============================================================================
# P1: GET /catalog
# =============================================================================


def test_catalog_admin_returns_all_agents(client, admin_headers, monkeypatch):
    """GET /catalog admin 调用返回全量智能体。"""
    from app.routers import agent_permission_router

    async def fake_list_all_agents_admin(self):
        return [
            {"name": "map_agent", "display_name": "地图智能体"},
            {"name": "project", "display_name": "运维项目智能体"},
            {"name": "knowledge_ydt", "display_name": "一点通规则库"},
        ]

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.list_all_agents_admin",
        fake_list_all_agents_admin,
    )

    response = client.get(f"{BASE}/catalog", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    names = [it["name"] for it in body["items"]]
    assert names == ["map_agent", "project", "knowledge_ydt"]


# =============================================================================
# P1: GET /users/{id}/grants
# =============================================================================


def test_get_user_grants_returns_authorized_agents(client, admin_headers, monkeypatch):
    """GET /users/{id}/grants admin 调用返回该用户已授权 agent_name 列表。"""
    from app.shared.utils.auth.agent_permission_service import AgentPermissionService

    # 注入缓存数据
    service = getattr(client.app.state, "agent_permission_service", None)
    assert service is not None, "AgentPermissionService 未初始化"
    # db=None 模式下直接手工填充缓存
    service._cache[42] = {"map_agent", "project"}

    response = client.get(f"{BASE}/users/42/grants", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert sorted(body["agent_names"]) == ["map_agent", "project"]


def test_get_user_grants_empty_for_unknown_user(client, admin_headers):
    """GET /users/{id}/grants 未授权用户返空列表。"""
    response = client.get(f"{BASE}/users/9999/grants", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["agent_names"] == []


# =============================================================================
# P1: PUT /users/{id}/grants
# =============================================================================


def test_put_user_grants_replaces_all(client, admin_headers):
    """PUT /users/{id}/grants 全量覆盖已授权 agent_name。"""
    target_user_id = 42
    response = client.put(
        f"{BASE}/users/{target_user_id}/grants",
        headers=admin_headers,
        json={"agent_names": ["map_agent", "knowledge_ydt"]},
    )
    # db=None 时 service.replace 仅写内存缓存，不抛错
    assert response.status_code == 200
    body = response.json()
    assert sorted(body["agent_names"]) == ["knowledge_ydt", "map_agent"]


def test_put_user_grants_clears_existing(client, admin_headers):
    """PUT 空列表会清空该用户所有授权。"""
    target_user_id = 42
    # 先设置
    client.put(
        f"{BASE}/users/{target_user_id}/grants",
        headers=admin_headers,
        json={"agent_names": ["map_agent"]},
    )
    # 再清空
    response = client.put(
        f"{BASE}/users/{target_user_id}/grants",
        headers=admin_headers,
        json={"agent_names": []},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["agent_names"] == []


def test_put_user_grants_db_failure_returns_500(client, admin_headers, monkeypatch):
    """PUT DB 写入失败返 500。"""
    from app.shared.utils.auth.agent_permission_service import AgentPermissionService

    async def broken_replace(self, user_id, agent_names, operator_id=None):
        raise RuntimeError("DB write failed")

    monkeypatch.setattr(AgentPermissionService, "replace", broken_replace)

    response = client.put(
        f"{BASE}/users/1/grants",
        headers=admin_headers,
        json={"agent_names": ["map_agent"]},
    )
    assert response.status_code == 500
    assert "保存失败" in response.json().get("detail", "")
