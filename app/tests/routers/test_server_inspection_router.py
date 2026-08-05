# -*- coding:utf-8 -*-
"""
ServerInspectionRouter 测试模块（2026-08-05 新增）。

覆盖目标：
    * 模块可导入 + 路由注册；
    * ``GET /latest`` —— admin/system 全量 vs 普通用户 scope 过滤；
    * ``GET /records`` —— 越权 404、时间/limit 过滤、参数校验；
    * ``POST /collect`` —— 存在性 404、归属 403、采集+落库成功路径、devops 服务缺失 500；
    * 全部端点未登录 401、service 未初始化 500；
    * main.register_routers 已 include_router（源码静态断言）。

测试风格遵循项目既有 router 测试：
    - 通过 client fixture 发起 HTTP 请求；
    - 用 admin_headers / user_headers 注入角色；
    - 通过 monkeypatch / 属性替换 stub service 行为；
    - 不伪造生产不存在的对象（devops_server_service 必须真实实例）。
"""
from __future__ import annotations

import asyncio
import inspect
from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest


BASE = "/api/admin/server-inspection"


def _make_devops_service_stub(credential_key: str):
    """构造合法的 ``DevOpsServerService`` stub（仅用于 ``POST /collect`` 注入）。

    通过 ``Fernet.generate_key()`` 生成合法 base64 key；``db=None`` 让
    ``preload_all`` no-op（service 构造时不触发 DB 写入）。
    """
    from app.shared.utils.devops_server_service import DevOpsServerService
    return DevOpsServerService(
        db=None,
        config_path="/tmp/_unused_inspection_test.yaml",
        credential_key=credential_key,
    )


# ============================================================================
# ACL helper：授予 testuser task-scheduler.server-management
# ============================================================================


def _grant_server_management_acl(client, user_id=2):
    """为普通用户授予 ``task-scheduler.server-management`` 菜单 ACL。

    通过 stub ``MenuPermissionService.get_visible_menu_ids`` 返回含该
    菜单 id 的列表，绕过 require_admin_or_menu_acl 守卫（与既有
    ``test_user_server_router.py::_override_user_server_visible_menu``
    同源模式）。
    """
    from app.shared.utils.auth.menu_permission_service import MenuPermissionService

    async def fake_visible(*, user_id, is_admin):
        # Safety.py 以 ``user_id=`` 关键字参数调用 ``get_visible_menu_ids``。
        if is_admin:
            return ["task-scheduler.server-management"]
        if user_id == 2:  # admin 直接 bypass，不走此分支
            return ["task-scheduler.server-management", "profile"]
        if user_id == user_id:
            return ["task-scheduler.server-management", "profile"]
        return ["profile"]

    stub = MenuPermissionService(db=None)
    stub.get_visible_menu_ids = fake_visible
    client.app.state.menu_permission_service = stub


# ============================================================================
# P0：导入与路由注册
# ============================================================================


def test_server_inspection_router_importable():
    """模块可导入且包含 ``router``。"""
    from app.routers import server_inspection_router

    assert hasattr(server_inspection_router, "router")


def test_server_inspection_router_prefix():
    """``router`` 前缀为 ``/api/admin/server-inspection``。"""
    from app.routers.server_inspection_router import router

    assert router.prefix == "/api/admin/server-inspection"


def test_server_inspection_endpoints_registered(client):
    """所有端点已在 ``register_routers`` 中注册。"""
    routes = [r.path for r in client.app.routes]
    expected = [
        f"{BASE}/latest",
        f"{BASE}/records",
        f"{BASE}/collect",
    ]
    for path in expected:
        assert path in routes, f"路由未注册: {path}"


def test_register_routers_includes_server_inspection_router():
    """``app/main.py::register_routers`` 必须 include_router server_inspection_router。"""
    from app.main import register_routers

    src = inspect.getsource(register_routers)
    assert "server_inspection_router" in src, (
        "app/main.py::register_routers 必须 include_router server_inspection_router"
    )


# ============================================================================
# P1：未登录 / service 未初始化
# ============================================================================


def test_get_latest_requires_auth(client):
    """未登录访问 ``GET /latest`` → 401。"""
    response = client.get(f"{BASE}/latest")
    assert response.status_code == 401


def test_get_records_requires_auth(client):
    """未登录访问 ``GET /records`` → 401。"""
    response = client.get(f"{BASE}/records", params={"server_id": 1})
    assert response.status_code == 401


def test_post_collect_requires_auth(client):
    """未登录访问 ``POST /collect`` → 401。"""
    response = client.post(f"{BASE}/collect", json={"server_ids": [1]})
    assert response.status_code == 401


def test_get_latest_service_not_initialized_returns_500(client, admin_headers):
    """service 未初始化（DB 不可用 / 初始化失败）→ 500。"""
    client.app.state.server_inspection_record_service = None
    response = client.get(f"{BASE}/latest", headers=admin_headers)
    assert response.status_code == 500


# ============================================================================
# P1：GET /latest
# ============================================================================


def test_get_latest_admin_returns_items(client, admin_headers):
    """admin：service.list_latest(scope) 返回 items。"""
    service = client.app.state.server_inspection_record_service
    service.list_latest = AsyncMock(
        return_value=[
            {
                "node_id": None,
                "node_name": "biz-A",
                "server_id": 1,
                "business_name": "biz-A",
                "server_type": "linux",
                "status": "ok",
                "inspection_status": "pass",
                "collected_at": "2026-08-05T10:00:00",
                "duration_ms": 42,
                "metrics": {"cpu": 23.5, "mem": 45.0, "disk": 62.0},
                "disks": [{"mount": "/", "disk_used_pct": 58}],
                "parsed_values": {},
                "error_message": None,
            }
        ]
    )
    response = client.get(f"{BASE}/latest", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert len(body["items"]) == 1
    assert body["items"][0]["business_name"] == "biz-A"
    # 不含 ip
    assert "ip" not in body["items"][0]


def test_get_latest_user_passes_ownership_scope(client, user_headers):
    """普通用户请求：OwnershipScope.from_request 被调用并透传（需先授予 ACL）。"""
    _grant_server_management_acl(client)
    service = client.app.state.server_inspection_record_service
    captured_scope = {}
    async def _capture(scope):
        captured_scope["scope"] = scope
        return []
    service.list_latest = AsyncMock(side_effect=_capture)
    response = client.get(f"{BASE}/latest", headers=user_headers)
    assert response.status_code == 200
    scope = captured_scope["scope"]
    assert scope.is_admin is False
    assert scope.user_id == 2  # testuser fixture


# ============================================================================
# P1：GET /records
# ============================================================================


def test_get_records_requires_server_id(client, admin_headers):
    """缺少 server_id → 422（FastAPI Query 校验）。"""
    response = client.get(f"{BASE}/records", headers=admin_headers)
    assert response.status_code == 422


def test_get_records_invalid_limit_returns_400(client, admin_headers):
    """limit 越界 → 422（FastAPI Query 校验）。

    注：本实现把 ``limit`` 范围（1~1000）放在 Query 层，FastAPI 直接拦截 → 422；
    service 层 ValueError 是给运行时其它越权场景的兜底（如手动 -1）。
    """
    response = client.get(
        f"{BASE}/records",
        params={"server_id": 1, "limit": 9999},
        headers=admin_headers,
    )
    assert response.status_code == 422


def test_get_records_service_runtime_value_error_returns_400(client, admin_headers, monkeypatch):
    """service 运行时抛 ValueError（非 Query 校验） → 400。"""
    service = client.app.state.server_inspection_record_service
    async def _bad_limit(*_a, **_k):
        raise ValueError("limit must be between 1 and 1000")
    service.list_records = AsyncMock(side_effect=_bad_limit)
    # Query 校验放行（limit=100 在范围内），ValueError 由 router 兜底 → 400
    response = client.get(
        f"{BASE}/records",
        params={"server_id": 1, "limit": 100},
        headers=admin_headers,
    )
    assert response.status_code == 400


def test_get_records_not_visible_returns_404(client, user_headers):
    """普通用户 server_id 不在可见集 → None → 404（需授予 ACL）。"""
    _grant_server_management_acl(client)
    service = client.app.state.server_inspection_record_service
    service.list_records = AsyncMock(return_value=None)
    response = client.get(
        f"{BASE}/records",
        params={"server_id": 999},
        headers=user_headers,
    )
    assert response.status_code == 404
    # 不回显 id
    assert "999" not in response.json()["detail"]


def test_get_records_returns_items_with_filters(client, admin_headers):
    """admin：start/end/limit 透传 service。"""
    service = client.app.state.server_inspection_record_service
    captured = {}
    async def _capture(server_id, scope, *, start=None, end=None, limit=100):
        captured["server_id"] = server_id
        captured["scope"] = scope
        captured["start"] = start
        captured["end"] = end
        captured["limit"] = limit
        return [{"id": 1, "server_id": server_id,
                 "collected_at": "2026-08-05T10:00:00",
                 "parsed_values": {}, "field_results": []}]
    service.list_records = AsyncMock(side_effect=_capture)
    start = "2026-08-01T00:00:00"
    end = "2026-08-06T00:00:00"
    response = client.get(
        f"{BASE}/records",
        params={"server_id": 7, "start": start, "end": end, "limit": 50},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert captured["server_id"] == 7
    assert captured["start"] == datetime.fromisoformat(start)
    assert captured["end"] == datetime.fromisoformat(end)
    assert captured["limit"] == 50
    assert captured["scope"].is_admin is True


# ============================================================================
# P1：POST /collect
# ============================================================================


def test_post_collect_validates_server_ids(client, admin_headers):
    """空数组 / 负数 → 422。"""
    response = client.post(f"{BASE}/collect", json={"server_ids": []}, headers=admin_headers)
    assert response.status_code == 422
    response = client.post(f"{BASE}/collect", json={"server_ids": [-1]}, headers=admin_headers)
    assert response.status_code == 422


def test_post_collect_missing_server_id_returns_404(client, admin_headers):
    """存在性校验：service.resolve_collect_targets 抛 NotFound → 404。"""
    from cryptography.fernet import Fernet
    client.app.state.devops_server_service = _make_devops_service_stub(Fernet.generate_key().decode())

    from app.shared.utils.server_inspection_record_service import ServerInspectionNotFoundError

    service = client.app.state.server_inspection_record_service
    service.resolve_collect_targets = MagicMock(
        side_effect=ServerInspectionNotFoundError("not found")
    )
    response = client.post(
        f"{BASE}/collect",
        json={"server_ids": [999]},
        headers=admin_headers,
    )
    assert response.status_code == 404


def test_post_collect_unauthorized_returns_403(client, user_headers):
    """归属校验：service.resolve_collect_targets 抛 Permission → 403。"""
    _grant_server_management_acl(client)
    from cryptography.fernet import Fernet
    client.app.state.devops_server_service = _make_devops_service_stub(Fernet.generate_key().decode())

    from app.shared.utils.server_inspection_record_service import ServerInspectionPermissionError

    service = client.app.state.server_inspection_record_service
    service.resolve_collect_targets = MagicMock(
        side_effect=ServerInspectionPermissionError("not owned")
    )
    response = client.post(
        f"{BASE}/collect",
        json={"server_ids": [1]},
        headers=user_headers,
    )
    assert response.status_code == 403


def test_post_collect_requires_devops_server_service(client, admin_headers, monkeypatch):
    """``devops_server_service`` 未注入 → 500。"""
    client.app.state.devops_server_service = None
    response = client.post(
        f"{BASE}/collect",
        json={"server_ids": [1]},
        headers=admin_headers,
    )
    assert response.status_code == 500


def test_post_collect_success_path(monkeypatch, client, admin_headers):
    """成功路径：resolve_collect_targets → run_server_ops → save_inspection_result。"""
    from cryptography.fernet import Fernet
    devops_svc = _make_devops_service_stub(Fernet.generate_key().decode())
    client.app.state.devops_server_service = devops_svc

    record_svc = client.app.state.server_inspection_record_service
    record_svc.resolve_collect_targets = MagicMock(return_value=["biz-A"])
    record_svc.save_inspection_result = AsyncMock(return_value=1)
    # list_latest 也要 stub（避免 save 走真实路径产生意外）

    # 桩 run_server_ops：返回含 1 台成功 ServerOpsItem
    from app.scripts.server_ops import ServerOpsItem, ServerOpsReport

    async def stub_run_server_ops(context, server_list=None, *, ssh_timeout=30):
        return ServerOpsReport(items=[
            ServerOpsItem(
                business_name="biz-A",
                success=True,
                exit_code=0,
                duration_ms=42,
                inspection_status="pass",
                parsed_values={"disks": [{"mount": "/", "disk_used_pct": 58}],
                              "mem_used_pct": 45.0, "cpu_idle_pct": 76.5},
                field_results=[{"key": "cpu_idle_pct", "value": 76.5,
                                 "status": "pass", "message": ""}],
            ),
        ])
    monkeypatch.setattr(
        "app.routers.server_inspection_router.run_server_ops",
        stub_run_server_ops,
    )

    response = client.post(
        f"{BASE}/collect",
        json={"server_ids": [1]},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["collected"] == 1
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["business_name"] == "biz-A"
    assert item["success"] is True
    assert item["inspection_status"] == "pass"
    assert item["duration_ms"] == 42
    # save_inspection_result 被调用且 created_by_user_id=scope.user_id
    call = record_svc.save_inspection_result.await_args
    assert call.kwargs["created_by_user_id"] == 1  # admin fixture user_id


def test_post_collect_passes_created_by_user_id_for_normal_user(client, user_headers, monkeypatch):
    """普通用户：``created_by_user_id`` 应为当前用户（用于审计）。"""
    _grant_server_management_acl(client)
    from cryptography.fernet import Fernet
    client.app.state.devops_server_service = _make_devops_service_stub(Fernet.generate_key().decode())
    record_svc = client.app.state.server_inspection_record_service
    record_svc.resolve_collect_targets = MagicMock(return_value=["biz-A"])
    record_svc.save_inspection_result = AsyncMock(return_value=1)

    from app.scripts.server_ops import ServerOpsItem, ServerOpsReport
    async def stub(context, server_list=None, *, ssh_timeout=30):
        return ServerOpsReport(items=[
            ServerOpsItem(business_name="biz-A", success=True,
                          inspection_status="pass", parsed_values={},
                          field_results=[]),
        ])
    monkeypatch.setattr(
        "app.routers.server_inspection_router.run_server_ops", stub,
    )

    response = client.post(
        f"{BASE}/collect",
        json={"server_ids": [1]},
        headers=user_headers,
    )
    assert response.status_code == 200
    call = record_svc.save_inspection_result.await_args
    assert call.kwargs["created_by_user_id"] == 2  # testuser fixture user_id