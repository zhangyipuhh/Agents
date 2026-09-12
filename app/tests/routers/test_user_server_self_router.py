# -*- coding:utf-8 -*-
"""user_server_self_router 测试：GET /api/user-servers/tree 自助读端点。

2026-09-12 渗透整改新增：# 触发器数据源迁出 /api/admin/ 命名空间,
登录态 + OwnershipScope 隔离（admin 全量 / 普通用户仅自有）。
"""
from unittest.mock import MagicMock


def test_user_server_self_router_importable():
    """模块可导入且包含 router。"""
    from app.routers import user_server_self_router
    assert hasattr(user_server_self_router, "router")


def test_self_tree_endpoint_registered(client):
    """GET /api/user-servers/tree 已注册。"""
    routes = [r.path for r in client.app.routes]
    assert "/api/user-servers/tree" in routes


def test_self_tree_passes_scope_and_returns_nodes(client, user_headers):
    """普通用户调自助 tree：OwnershipScope.is_admin=False 透传 service。"""
    captured = {}

    service = client.app.state.user_server_service
    original = service.list_nodes

    def spy_list_nodes(scope):
        captured["is_admin"] = scope.is_admin
        captured["user_id"] = scope.user_id
        return [{"id": 1, "node_type": "server", "name": "s1"}]

    service.list_nodes = spy_list_nodes
    try:
        response = client.get("/api/user-servers/tree", headers=user_headers)
    finally:
        service.list_nodes = original

    assert response.status_code == 200
    assert response.json()["nodes"][0]["name"] == "s1"
    assert captured["is_admin"] is False
    assert captured["user_id"] == 2


def test_self_tree_admin_sees_all(client, admin_headers):
    """admin 调自助 tree：OwnershipScope.is_admin=True（与旧 admin tree 同语义）。"""
    captured = {}

    service = client.app.state.user_server_service
    original = service.list_nodes

    def spy_list_nodes(scope):
        captured["is_admin"] = scope.is_admin
        return []

    service.list_nodes = spy_list_nodes
    try:
        response = client.get("/api/user-servers/tree", headers=admin_headers)
    finally:
        service.list_nodes = original

    assert response.status_code == 200
    assert captured["is_admin"] is True


def test_self_tree_service_missing_returns_500(client, user_headers):
    """user_server_service 未初始化时返回 500。"""
    original = client.app.state.user_server_service
    delattr(client.app.state, "user_server_service")
    try:
        response = client.get("/api/user-servers/tree", headers=user_headers)
    finally:
        client.app.state.user_server_service = original

    assert response.status_code == 500
