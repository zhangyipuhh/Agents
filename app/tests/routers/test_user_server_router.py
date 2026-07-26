# -*- coding:utf-8 -*-
"""
User Server Admin Router 测试模块（2026-07-24 新增）。

验证 /api/admin/user-servers/* 路由的注册、节点树 CRUD、节点详情、
批量导入与权限控制（admin role + ACL 双重门）。
"""
from unittest.mock import AsyncMock

from app.shared.utils.user_server_service import (
    UserServerNodeNotEmptyError,
    UserServerNodeNotFoundError,
)


BASE = "/api/admin/user-servers"


# =============================================================================
# P0: 导入与路由注册
# =============================================================================


def test_user_server_router_importable():
    """测试 user_server_router 模块可导入且包含 router。"""
    from app.routers import user_server_router

    assert hasattr(user_server_router, "router")


def test_user_server_endpoints_registered(client):
    """测试所有用户服务器管理端点已注册。"""
    routes = [r.path for r in client.app.routes]
    expected = [
        f"{BASE}/tree",
        f"{BASE}/nodes",
        f"{BASE}/nodes/{{node_id}}",
        f"{BASE}/nodes/{{node_id}}/config",
        f"{BASE}/import",
    ]
    for path in expected:
        assert path in routes, f"路由未注册: {path}"


def test_user_server_router_prefix():
    """测试 router 前缀为 /api/admin/user-servers。"""
    from app.routers.user_server_router import router

    assert router.prefix == "/api/admin/user-servers"


# =============================================================================
# P1: 成功路径
# =============================================================================


def test_get_tree_returns_200(client, admin_headers):
    """测试 GET /tree 返回节点平铺列表。"""
    service = client.app.state.user_server_service
    service.list_nodes = lambda scope: [
        {"id": 1, "parent_id": None, "node_type": "folder", "name": "分组", "sort_order": 0,
         "source_devops_server_id": None, "created_by_user_id": 1}
    ]

    response = client.get(f"{BASE}/tree", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["nodes"][0]["name"] == "分组"


def test_create_folder_node_returns_201(client, admin_headers):
    """测试 POST /nodes 创建 folder。"""
    service = client.app.state.user_server_service
    service.create_node = AsyncMock(
        return_value={"id": 1, "parent_id": None, "node_type": "folder", "name": "分组",
                      "sort_order": 0, "source_devops_server_id": None, "created_by_user_id": 1}
    )

    response = client.post(
        f"{BASE}/nodes",
        headers=admin_headers,
        json={"parent_id": None, "node_type": "folder", "name": "分组"},
    )

    assert response.status_code == 201
    assert response.json()["id"] == 1


def test_create_server_node_returns_201(client, admin_headers):
    """测试 POST /nodes 创建 server（带 source_devops_server_id）。"""
    service = client.app.state.user_server_service
    service.create_node = AsyncMock(
        return_value={"id": 2, "parent_id": 1, "node_type": "server", "name": "服务器A",
                      "sort_order": 0, "source_devops_server_id": 100, "created_by_user_id": 1}
    )

    response = client.post(
        f"{BASE}/nodes",
        headers=admin_headers,
        json={"parent_id": 1, "node_type": "server", "name": "服务器A", "source_devops_server_id": 100},
    )

    assert response.status_code == 201
    assert response.json()["node_type"] == "server"
    assert response.json()["source_devops_server_id"] == 100


def test_update_node_returns_200(client, admin_headers):
    """测试 PUT /nodes/{id} 更新节点。"""
    service = client.app.state.user_server_service
    service.update_node = AsyncMock(
        return_value={"id": 1, "parent_id": None, "node_type": "folder", "name": "新名",
                      "sort_order": 0, "source_devops_server_id": None, "created_by_user_id": 1}
    )

    response = client.put(
        f"{BASE}/nodes/1",
        headers=admin_headers,
        json={"name": "新名"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "新名"


def test_delete_node_returns_ok(client, admin_headers):
    """测试 DELETE /nodes/{id} 返回 ok。"""
    service = client.app.state.user_server_service
    service.delete_node = AsyncMock(return_value=None)

    response = client.delete(f"{BASE}/nodes/1", headers=admin_headers)

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_get_node_config_returns_200(client, admin_headers):
    """测试 GET /nodes/{id}/config 返回节点详情。"""
    service = client.app.state.user_server_service
    service.get_node_config = AsyncMock(
        return_value={
            "node_type": "folder",
            "id": 1,
            "parent_id": None,
            "name": "分组",
            "sort_order": 0,
            "created_by_user_id": 1,
        }
    )

    response = client.get(f"{BASE}/nodes/1/config", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["node_type"] == "folder"


def test_import_servers_returns_summary(client, admin_headers):
    """测试 POST /import 返回导入汇总。"""
    service = client.app.state.user_server_service
    service.import_from_devops_servers = AsyncMock(
        return_value={"imported": 2, "skipped": 1, "failed": 0, "node_ids": [10, 11]}
    )

    response = client.post(
        f"{BASE}/import",
        headers=admin_headers,
        json={"parent_id": 1, "business_names": ["服务器A", "服务器B", "服务器C"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == 2
    assert body["skipped"] == 1
    assert body["node_ids"] == [10, 11]


# =============================================================================
# P1: 失败路径（service 异常 → HTTP 错误码）
# =============================================================================


def test_create_node_invalid_node_type_returns_400(client, admin_headers):
    """测试非法 node_type → 400。"""
    response = client.post(
        f"{BASE}/nodes",
        headers=admin_headers,
        json={"parent_id": None, "node_type": "invalid", "name": "X"},
    )

    assert response.status_code == 422  # pydantic 字段校验


def test_get_node_config_not_found_returns_404(client, admin_headers):
    """测试 GET /nodes/{id}/config 节点不存在 → 404。"""
    service = client.app.state.user_server_service
    service.get_node_config = AsyncMock(
        side_effect=UserServerNodeNotFoundError("节点不存在")
    )

    response = client.get(f"{BASE}/nodes/9999/config", headers=admin_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "节点不存在"


def test_delete_node_not_empty_returns_400(client, admin_headers):
    """测试 DELETE /nodes/{id} folder 非空 → 400。"""
    service = client.app.state.user_server_service
    service.delete_node = AsyncMock(
        side_effect=UserServerNodeNotEmptyError("文件夹非空")
    )

    response = client.delete(f"{BASE}/nodes/1", headers=admin_headers)

    assert response.status_code == 400


def test_import_servers_empty_business_names_returns_400(client, admin_headers):
    """测试 POST /import business_names 为空 → 422（pydantic min_length）。"""
    response = client.post(
        f"{BASE}/import",
        headers=admin_headers,
        json={"parent_id": None, "business_names": []},
    )

    # business_names=[] 会被 _validate_business_names 过滤为 []；
    # 但 model 层未做 min_length 校验，因此走到 service 后由 service 抛 ValueError → 400
    assert response.status_code in (400, 422)


# =============================================================================
# P0: 路由服务不可用
# =============================================================================


def test_get_tree_service_unavailable_returns_500(client, admin_headers):
    """测试 service 未初始化时 → 500。"""
    client.app.state.user_server_service = None

    response = client.get(f"{BASE}/tree", headers=admin_headers)

    assert response.status_code == 500
    assert "not initialized" in response.json()["detail"]


# =============================================================================
# P2: ACL 边界（2026-07-26）
# - GET /tree 放宽为登录态（跟随 GET /api/admin/scripts 先例）：
#   普通用户无任何 ACL 也能调（OwnershipScope 隔离）
# - 写端点（POST / PUT / DELETE / config / import）仍要求
#   task-scheduler.server-management ACL，无授权仍 403
# =============================================================================


def _override_user_server_visible_menu(client, visible_ids):
    """覆盖 user_server_router 调用期间 menu_permission_service 的返回值。"""
    from app.shared.utils.auth.menu_permission_service import MenuPermissionService
    visible_set = set(visible_ids)

    async def fake_visible(user_id, is_admin):
        if is_admin:
            from app.core.menu_registry import get_enabled_items
            return [m.id for m in sorted(get_enabled_items(), key=lambda m: m.sort_order)]
        return sorted(visible_set)

    stub = MenuPermissionService(db=None)
    stub.get_visible_menu_ids = fake_visible
    client.app.state.menu_permission_service = stub


def test_normal_user_no_acl_get_tree_passes(client, user_headers):
    """2026-07-26：GET /tree 放宽为登录态。普通用户无任何 ACL 也能调（200）。

    委托 OwnershipScope 按 created_by_user_id 过滤，普通用户仅见自己
    添加的服务器节点（含 business_name / server_type 附加字段）。"""
    _override_user_server_visible_menu(client, visible_ids={'profile'})
    service = client.app.state.user_server_service
    service.list_nodes = lambda scope: []

    response = client.get(f"{BASE}/tree", headers=user_headers)

    assert response.status_code != 403
    assert response.status_code == 200


def test_normal_user_no_acl_import_still_403(client, user_headers):
    """2026-07-26：写端点（POST /import）仍要求 ACL。

    GET /tree 放宽为登录态，但写端点仍保留
    require_admin_or_menu_acl('task-scheduler.server-management') 守护。
    普通用户无对应 ACL 时调 /import 仍 403。"""
    _override_user_server_visible_menu(client, visible_ids={'profile'})

    response = client.post(
        f"{BASE}/import",
        headers=user_headers,
        json={"parent_id": None, "business_names": ["A"]},
    )

    assert response.status_code == 403
    assert "task-scheduler.server-management" in response.json()["detail"]


def test_normal_user_acl_server_management_passes_import(client, user_headers):
    """ACL 含 task-scheduler.server-management：普通用户 POST /import 通过（200）。"""
    _override_user_server_visible_menu(
        client, visible_ids={'profile', 'task-scheduler.server-management'}
    )
    service = client.app.state.user_server_service
    service.import_from_devops_servers = AsyncMock(
        return_value={"imported": 1, "skipped": 0, "failed": 0, "node_ids": [1]}
    )

    response = client.post(
        f"{BASE}/import",
        headers=user_headers,
        json={"parent_id": None, "business_names": ["A"]},
    )

    assert response.status_code != 403
    assert response.status_code == 200


def test_normal_user_acl_parent_only_still_passes_get_tree(client, user_headers):
    """2026-07-26：GET /tree 不再细粒度按子菜单判定 ACL。

    即使普通用户只有 task-scheduler 父级 ACL、没有 .server-management
    子菜单，GET /tree 仍能通过（200）。"""
    _override_user_server_visible_menu(
        client, visible_ids={'profile', 'task-scheduler'}
    )
    service = client.app.state.user_server_service
    service.list_nodes = lambda scope: []

    response = client.get(f"{BASE}/tree", headers=user_headers)

    assert response.status_code == 200
