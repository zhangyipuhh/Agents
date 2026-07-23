# -*- coding:utf-8 -*-
"""
menu_permission_router 路由契约测试。

覆盖点：
- 3 个端点都受 require_admin 守护（普通用户返 403）
- admin 调用：GET menu-catalog 返全量；GET users/{id}/grants 返授权；
  PUT users/{id}/grants 全量覆盖
- PUT 失败抛 500
"""

from unittest.mock import AsyncMock


BASE = "/api/admin/permissions"


# =============================================================================
# P0: 导入与路由注册
# =============================================================================


def test_menu_permission_router_importable():
    """测试 menu_permission_router 模块可导入且包含 router。"""
    from app.routers import menu_permission_router

    assert hasattr(menu_permission_router, "router")


def test_menu_permission_endpoints_registered(client):
    """测试所有菜单权限端点已注册。"""
    routes = [r.path for r in client.app.routes]
    expected = [
        f"{BASE}/menu-catalog",
        f"{BASE}/users/{{user_id}}/grants",
    ]
    for path in expected:
        assert path in routes, f"路由未注册: {path}"


# =============================================================================
# P1: require_admin 守护
# =============================================================================


def test_menu_catalog_requires_admin(client, user_headers):
    """GET /menu-catalog 普通用户访问返回 403。"""
    response = client.get(f"{BASE}/menu-catalog", headers=user_headers)
    assert response.status_code == 403


def test_get_user_grants_requires_admin(client, user_headers):
    """GET /users/{id}/grants 普通用户访问返回 403。"""
    response = client.get(f"{BASE}/users/5/grants", headers=user_headers)
    assert response.status_code == 403


def test_put_user_grants_requires_admin(client, user_headers):
    """PUT /users/{id}/grants 普通用户访问返回 403。"""
    response = client.put(
        f"{BASE}/users/5/grants",
        headers=user_headers,
        json={"menu_ids": ["profile"]},
    )
    assert response.status_code == 403


# =============================================================================
# P1: admin 调用成功路径
# =============================================================================


def test_admin_can_get_menu_catalog(client, admin_headers):
    """admin GET /menu-catalog 返回全量注册表。"""
    response = client.get(f"{BASE}/menu-catalog", headers=admin_headers)

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) >= 10  # 至少一级 8 + 二级 8 - enabled=False 数


def test_admin_can_get_user_grants(client, admin_headers):
    """admin GET /users/{id}/grants 返回该用户的 menu_ids。"""
    service = client.app.state.menu_permission_service
    service.get_user_grants = AsyncMock(
        return_value={"profile", "user-management"}
    )

    response = client.get(f"{BASE}/users/5/grants", headers=admin_headers)

    assert response.status_code == 200
    assert set(response.json()["menu_ids"]) == {"profile", "user-management"}


def test_admin_can_get_user_grants_for_unknown_user(client, admin_headers):
    """admin GET 不存在用户的 grants 返回空集合（不报错）。"""
    service = client.app.state.menu_permission_service
    service.get_user_grants = AsyncMock(return_value=set())

    response = client.get(f"{BASE}/users/9999/grants", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["menu_ids"] == []


def test_admin_can_put_user_grants(client, admin_headers):
    """admin PUT /users/{id}/grants 全量覆盖。"""
    service = client.app.state.menu_permission_service
    service.replace = AsyncMock()
    service.get_user_grants = AsyncMock(
        return_value={"profile", "user-management", "user-management.users"}
    )

    response = client.put(
        f"{BASE}/users/5/grants",
        headers=admin_headers,
        json={
            "menu_ids": [
                "profile",
                "user-management",
                "user-management.users",
            ]
        },
    )

    assert response.status_code == 200
    # stub 应收到 replace 调用
    service.replace.assert_awaited_once()
    call_args = service.replace.await_args
    assert call_args.args[0] == 5
    assert call_args.args[1] == {
        "profile",
        "user-management",
        "user-management.users",
    }


def test_admin_put_empty_grants_clears_user(client, admin_headers):
    """admin PUT 空 menu_ids 清空该用户授权。"""
    service = client.app.state.menu_permission_service
    service.replace = AsyncMock()
    service.get_user_grants = AsyncMock(return_value=set())

    response = client.put(
        f"{BASE}/users/5/grants",
        headers=admin_headers,
        json={"menu_ids": []},
    )

    assert response.status_code == 200
    # replace 收到空 set
    call_args = service.replace.await_args
    assert call_args.args[1] == set()


def test_admin_put_db_error_returns_500(client, admin_headers):
    """admin PUT 触发 DB 错误时返 500。"""
    service = client.app.state.menu_permission_service
    service.replace = AsyncMock(side_effect=RuntimeError("DB error"))

    response = client.put(
        f"{BASE}/users/5/grants",
        headers=admin_headers,
        json={"menu_ids": ["profile"]},
    )

    assert response.status_code == 500
    assert "DB error" in response.json()["detail"]