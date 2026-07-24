# -*- coding:utf-8 -*-
"""
API Config Admin Router 按用户隔离（OwnershipScope）测试模块。

验证:
- 路由层把 OwnershipScope.from_request 构造的 scope 透传给 service 方法
- 非 admin（testuser）调用 GET /tree 收到仅自己节点的列表
- 跨用户访问节点时 route 把 ApiConfigNotFoundError 映射为 404
- admin 调用无隔离限制
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def _grant_testuser_api_acl(client):
    """覆盖 client 的 menu_permission_service:授予 testuser task-scheduler.api-config 权限。

    普通用户在 conftest 默认下仅可见 ``profile``,需要追加
    ``task-scheduler.api-config`` ACL 才能调 ``/api/admin/api-configs/*``。
    """
    from app.shared.utils.auth.menu_permission_service import MenuPermissionService

    visible_set = {"profile", "task-scheduler.api-config"}

    async def fake_visible(user_id, is_admin):
        if is_admin:
            from app.core.menu_registry import get_enabled_items
            return [m.id for m in sorted(get_enabled_items(), key=lambda m: m.sort_order)]
        return sorted(visible_set)

    stub = MenuPermissionService(db=None)
    stub.get_visible_menu_ids = fake_visible
    client.app.state.menu_permission_service = stub


@pytest.fixture(autouse=True)
def _grant_acl_for_user_headers(client):
    """autouse:所有 user_headers 用例自动授予 api-config ACL。"""
    _grant_testuser_api_acl(client)
    yield


# =============================================================================
# P0: 端点路由已注册
# =============================================================================


def test_endpoints_registered(client):
    """api-config 端点必须已注册。"""
    routes = [r.path for r in client.app.routes]
    assert "/api/admin/api-configs/tree" in routes
    assert "/api/admin/api-configs/nodes" in routes
    assert "/api/admin/api-configs/nodes/{node_id}" in routes
    assert "/api/admin/api-configs/nodes/{node_id}/config" in routes
    assert "/api/admin/api-configs/nodes/{node_id}/send" in routes
    assert "/api/admin/api-configs/nodes/{node_id}/runs" in routes


# =============================================================================
# P1: GET /tree 透传 scope
# =============================================================================


def test_get_tree_passes_admin_scope_to_service(client, admin_headers):
    """admin 调用 GET /tree:service.get_tree 收到 admin scope。"""
    service = client.app.state.api_config_service
    service.get_tree = AsyncMock(return_value={"nodes": []})

    response = client.get("/api/admin/api-configs/tree", headers=admin_headers)

    assert response.status_code == 200
    scope_arg = service.get_tree.await_args.args[0]
    assert scope_arg.is_admin is True
    assert scope_arg.user_id == 1  # admin 测试 fixture id


def test_get_tree_passes_user_scope_to_service(client, user_headers):
    """普通用户调用 GET /tree:scope.is_admin=False / user_id=2。"""
    service = client.app.state.api_config_service
    service.get_tree = AsyncMock(return_value={"nodes": []})

    response = client.get("/api/admin/api-configs/tree", headers=user_headers)

    assert response.status_code == 200
    scope_arg = service.get_tree.await_args.args[0]
    assert scope_arg.is_admin is False
    assert scope_arg.user_id == 2  # testuser id


def test_get_tree_filters_to_user_only(client, user_headers):
    """普通用户 GET /tree:返回的 nodes 仅为 service.get_tree(scope) 的结果。"""
    service = client.app.state.api_config_service
    scoped_nodes = [{"id": 4, "parent_id": None, "node_type": "api", "name": "我的接口", "created_by_user_id": 2}]
    service.get_tree = AsyncMock(return_value=scoped_nodes)

    response = client.get("/api/admin/api-configs/tree", headers=user_headers)

    assert response.status_code == 200
    assert response.json() == {"nodes": scoped_nodes}


# =============================================================================
# P1: create_node 透传 scope,created_by 写入由 service 完成
# =============================================================================


def test_create_node_passes_user_scope_to_service(client, user_headers):
    """普通用户 POST /nodes:scope.user_id == 2,is_admin == False。"""
    service = client.app.state.api_config_service
    service.create_node = AsyncMock(
        return_value={"id": 7, "parent_id": None, "node_type": "folder",
                      "name": "我的分组", "created_by_user_id": 2}
    )

    response = client.post(
        "/api/admin/api-configs/nodes",
        headers=user_headers,
        json={"parent_id": None, "node_type": "folder", "name": "我的分组"},
    )

    assert response.status_code == 201
    scope_arg = service.create_node.await_args.args[3]
    assert scope_arg.is_admin is False
    assert scope_arg.user_id == 2


# =============================================================================
# P1: 跨用户访问节点 → 404 契约
# =============================================================================


def test_get_config_cross_user_returns_404(client, user_headers):
    """普通用户 GET 他人节点 /config:service 抛 ApiConfigNotFoundError → 路由 404。"""
    from app.shared.utils.api_config_service import ApiConfigNotFoundError

    service = client.app.state.api_config_service
    service.get_config = AsyncMock(
        side_effect=ApiConfigNotFoundError("节点不存在")
    )

    response = client.get(
        "/api/admin/api-configs/nodes/999/config", headers=user_headers,
    )

    assert response.status_code == 404


def test_update_node_cross_user_returns_404(client, user_headers):
    """普通用户 PUT 他人节点:service 抛 ApiConfigNotFoundError → 404。"""
    from app.shared.utils.api_config_service import ApiConfigNotFoundError

    service = client.app.state.api_config_service
    service.update_node = AsyncMock(
        side_effect=ApiConfigNotFoundError("节点不存在")
    )

    response = client.put(
        "/api/admin/api-configs/nodes/999",
        headers=user_headers,
        json={"name": "x"},
    )

    assert response.status_code == 404


def test_delete_node_cross_user_returns_404(client, user_headers):
    """普通用户 DELETE 他人节点:service 抛 ApiConfigNotFoundError → 404。"""
    from app.shared.utils.api_config_service import ApiConfigNotFoundError

    service = client.app.state.api_config_service
    service.delete_node = AsyncMock(
        side_effect=ApiConfigNotFoundError("节点不存在")
    )

    response = client.delete(
        "/api/admin/api-configs/nodes/999", headers=user_headers,
    )

    assert response.status_code == 404


def test_send_request_cross_user_returns_404(client, user_headers):
    """普通用户 POST 他人节点 /send:service 抛 ApiConfigNotFoundError → 404。"""
    from app.shared.utils.api_config_service import ApiConfigNotFoundError

    service = client.app.state.api_config_service
    service.send_request = AsyncMock(
        side_effect=ApiConfigNotFoundError("节点不存在")
    )

    response = client.post(
        "/api/admin/api-configs/nodes/999/send", headers=user_headers,
    )

    assert response.status_code == 404


def test_list_runs_cross_user_returns_404(client, user_headers):
    """普通用户 GET 他人节点 /runs:service 抛 ApiConfigNotFoundError → 404。"""
    from app.shared.utils.api_config_service import ApiConfigNotFoundError

    service = client.app.state.api_config_service
    service.list_runs = AsyncMock(
        side_effect=ApiConfigNotFoundError("节点不存在")
    )

    response = client.get(
        "/api/admin/api-configs/nodes/999/runs", headers=user_headers,
    )

    assert response.status_code == 404


# =============================================================================
# P1: create_node 父节点不可见 → 400
# =============================================================================


def test_create_node_parent_cross_user_returns_400(client, user_headers):
    """普通用户在他人 folder 下创建节点:service 抛 ValueError → 路由 400。"""
    service = client.app.state.api_config_service
    service.create_node = AsyncMock(
        side_effect=ValueError("父节点不存在: 999")
    )

    response = client.post(
        "/api/admin/api-configs/nodes",
        headers=user_headers,
        json={"parent_id": 999, "node_type": "api", "name": "越权"},
    )

    assert response.status_code == 400
    assert "父节点不存在" in response.json()["detail"]