# -*- coding:utf-8 -*-
"""
API Config Admin Router 测试模块。

验证 /api/admin/api-configs/* 路由的注册、节点树 CRUD、配置 upsert、
请求发送、调用历史与权限控制。
"""
from unittest.mock import AsyncMock

from app.shared.utils.api_config_service import ApiConfigNotFoundError


BASE = "/api/admin/api-configs"


# =============================================================================
# P0: 导入与路由注册
# =============================================================================

def test_api_config_router_importable():
    """测试 api_config_router 模块可导入且包含 router。"""
    from app.routers import api_config_router

    assert hasattr(api_config_router, "router")


def test_api_config_endpoints_registered(client):
    """测试所有 API 接口配置管理端点已注册。"""
    routes = [r.path for r in client.app.routes]
    expected = [
        f"{BASE}/tree",
        f"{BASE}/nodes",
        f"{BASE}/nodes/{{node_id}}",
        f"{BASE}/nodes/{{node_id}}/config",
        f"{BASE}/nodes/{{node_id}}/send",
        f"{BASE}/nodes/{{node_id}}/runs",
    ]
    for path in expected:
        assert path in routes, f"路由未注册: {path}"


# =============================================================================
# P1: 成功路径
# =============================================================================

def test_get_tree_returns_200(client, admin_headers):
    """测试 GET /tree 返回节点平铺列表。"""
    service = client.app.state.api_config_service
    service.get_tree = AsyncMock(
        return_value=[{"id": 1, "parent_id": None, "node_type": "folder", "name": "分组"}]
    )

    response = client.get(f"{BASE}/tree", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["nodes"][0]["name"] == "分组"


def test_create_node_returns_201(client, admin_headers):
    """测试 POST /nodes 创建节点。"""
    service = client.app.state.api_config_service
    service.create_node = AsyncMock(
        return_value={"id": 1, "parent_id": None, "node_type": "folder", "name": "分组"}
    )

    response = client.post(
        f"{BASE}/nodes",
        headers=admin_headers,
        json={"parent_id": None, "node_type": "folder", "name": "分组"},
    )

    assert response.status_code == 201
    assert response.json()["id"] == 1


def test_update_node_returns_200(client, admin_headers):
    """测试 PUT /nodes/{id} 更新节点。"""
    service = client.app.state.api_config_service
    service.update_node = AsyncMock(
        return_value={"id": 1, "parent_id": None, "node_type": "folder", "name": "新名"}
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
    service = client.app.state.api_config_service
    service.delete_node = AsyncMock(return_value=None)

    response = client.delete(f"{BASE}/nodes/1", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_get_config_returns_200(client, admin_headers):
    """测试 GET /nodes/{id}/config 返回配置对象。"""
    service = client.app.state.api_config_service
    service.get_config = AsyncMock(
        return_value={"id": 1, "node_id": 2, "method": "POST", "url": "https://a.b/c"}
    )

    response = client.get(f"{BASE}/nodes/2/config", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["method"] == "POST"


def test_upsert_config_returns_200(client, admin_headers):
    """测试 PUT /nodes/{id}/config 全量 upsert 配置。"""
    service = client.app.state.api_config_service
    service.upsert_config = AsyncMock(
        return_value={"id": 1, "node_id": 2, "method": "PUT", "url": "https://a.b/c"}
    )

    response = client.put(
        f"{BASE}/nodes/2/config",
        headers=admin_headers,
        json={
            "method": "PUT",
            "url": "https://a.b/c",
            "params": [],
            "headers": [],
            "body_type": "none",
            "body_content": "",
            "form_fields": [],
            "expectations": [],
        },
    )

    assert response.status_code == 200
    assert response.json()["method"] == "PUT"


def test_send_request_returns_200(client, admin_headers):
    """测试 POST /nodes/{id}/send 返回调用结果。"""
    service = client.app.state.api_config_service
    service.send_request = AsyncMock(
        return_value={
            "run_id": 1,
            "http_status": 200,
            "duration_ms": 12,
            "response_body": "ok",
            "check_passed": True,
            "assertion_results": [],
            "error_message": "",
        }
    )

    response = client.post(f"{BASE}/nodes/2/send", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["check_passed"] is True


def test_list_runs_returns_200(client, admin_headers):
    """测试 GET /nodes/{id}/runs 返回调用历史。"""
    service = client.app.state.api_config_service
    service.list_runs = AsyncMock(return_value=[{"id": 1, "http_status": 200}])

    response = client.get(f"{BASE}/nodes/2/runs", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["runs"][0]["http_status"] == 200


# =============================================================================
# P1: 失败路径与权限
# =============================================================================

def test_create_node_invalid_parent_returns_400(client, admin_headers):
    """测试创建节点时父节点校验失败返回 400。"""
    service = client.app.state.api_config_service
    service.create_node = AsyncMock(side_effect=ValueError("父节点不存在: 999"))

    response = client.post(
        f"{BASE}/nodes",
        headers=admin_headers,
        json={"parent_id": 999, "node_type": "folder", "name": "孤儿"},
    )

    assert response.status_code == 400


def test_update_node_missing_returns_404(client, admin_headers):
    """测试更新不存在节点返回 404。"""
    service = client.app.state.api_config_service
    service.update_node = AsyncMock(side_effect=ApiConfigNotFoundError("节点不存在: 999"))

    response = client.put(
        f"{BASE}/nodes/999",
        headers=admin_headers,
        json={"name": "不存在"},
    )

    assert response.status_code == 404


def test_update_node_cycle_returns_400(client, admin_headers):
    """测试更新节点成环返回 400。"""
    service = client.app.state.api_config_service
    service.update_node = AsyncMock(side_effect=ValueError("拒绝成环"))

    response = client.put(
        f"{BASE}/nodes/1",
        headers=admin_headers,
        json={"parent_id": 3},
    )

    assert response.status_code == 400


def test_delete_non_empty_folder_returns_400(client, admin_headers):
    """测试删除非空文件夹返回 400。"""
    service = client.app.state.api_config_service
    service.delete_node = AsyncMock(side_effect=ValueError("文件夹非空，拒绝删除"))

    response = client.delete(f"{BASE}/nodes/1", headers=admin_headers)

    assert response.status_code == 400


def test_delete_missing_node_returns_404(client, admin_headers):
    """测试删除不存在节点返回 404。"""
    service = client.app.state.api_config_service
    service.delete_node = AsyncMock(side_effect=ApiConfigNotFoundError("节点不存在: 999"))

    response = client.delete(f"{BASE}/nodes/999", headers=admin_headers)

    assert response.status_code == 404


def test_get_config_on_folder_returns_400(client, admin_headers):
    """测试对 folder 节点获取配置返回 400。"""
    service = client.app.state.api_config_service
    service.get_config = AsyncMock(side_effect=ValueError("节点不是 api 类型: 1"))

    response = client.get(f"{BASE}/nodes/1/config", headers=admin_headers)

    assert response.status_code == 400


def test_upsert_config_invalid_enum_returns_400(client, admin_headers):
    """测试 upsert 配置枚举非法返回 400。"""
    service = client.app.state.api_config_service
    service.upsert_config = AsyncMock(side_effect=ValueError("method 必须是"))

    response = client.put(
        f"{BASE}/nodes/2/config",
        headers=admin_headers,
        json={
            "method": "POST",
            "url": "https://a.b/c",
            "params": [],
            "headers": [],
            "body_type": "none",
            "body_content": "",
            "form_fields": [],
            "expectations": [{"type": "regex"}],
        },
    )

    assert response.status_code == 400


def test_user_cannot_access_api_configs(client, user_headers):
    """测试普通用户访问 API 接口配置管理接口返回 403。"""
    response = client.get(f"{BASE}/tree", headers=user_headers)

    assert response.status_code == 403


def test_api_config_service_missing_returns_500(client, admin_headers):
    """测试 ApiConfigService 未初始化时返回 500。"""
    original = client.app.state.api_config_service
    delattr(client.app.state, "api_config_service")
    try:
        response = client.get(f"{BASE}/tree", headers=admin_headers)
    finally:
        client.app.state.api_config_service = original

    assert response.status_code == 500
    assert response.json()["detail"] == "ApiConfigService not initialized"
