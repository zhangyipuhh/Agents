# -*- coding:utf-8 -*-
"""
inspection_script_admin_router 单元测试(2026-08-03 新增;2026-09-16 重构)

覆盖目标:
    - 路由注册(list / detail / update / delete / segments CRUD)
    - GET 列表 200,返回白名单字段
    - GET 详情 200 / 404(2026-09-16 含 segments 字段)
    - ACL 矩阵:admin 直接通过;普通用户列表端点需
      ``task-scheduler.server-management`` ACL;详情/更新/删除/分段仅 admin
    - 服务未初始化 → 500
    - 2026-09-16 新增:分段 CRUD端点(/segments GET/POST/PUT/DELETE)
    - 2026-09-16 移除:/scan 端点(已 404/405)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


INSPECTION_SCRIPT_LIBRARY_MENU_ID = "task-scheduler.inspection-script-library"


def _build_real_service():
    """构造真实的 ``InspectionScriptService`` 实例(db=stub MagicMock)。

    2026-09-16:InspectionScriptService.__init__ 不再接受 config_path。

    Returns:
        InspectionScriptService: 真实服务实例
    """
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = MagicMock(name="db_pool_stub")
    db.fetch = AsyncMock(return_value=[])
    db.fetchrow = AsyncMock(return_value=None)
    db.execute = AsyncMock(return_value=None)
    return InspectionScriptService(db=db)


@pytest.fixture
def inspection_router_setup(app):
    """手动挂载 ``InspectionScriptService``(生产对等)。"""
    from app.shared.utils.inspection_script_service import InspectionScriptService

    svc = _build_real_service()
    app.state.inspection_script_service = svc
    InspectionScriptService.set_instance(svc)
    yield app
    InspectionScriptService.reset()
    if hasattr(app.state, "inspection_script_service"):
        app.state.inspection_script_service = None


@pytest.fixture
def grant_server_management_acl(client, monkeypatch):
    """给 testuser 授权 ``task-scheduler.inspection-script-library`` 菜单 ACL。"""
    from app.shared.utils.auth.menu_permission_service import MenuPermissionService

    svc = client.app.state.menu_permission_service
    if not isinstance(svc, MenuPermissionService):
        svc = MenuPermissionService(db=None)
        client.app.state.menu_permission_service = svc

    async def fake_visible(user_id, is_admin):
        if is_admin:
            from app.core.menu_registry import get_enabled_items

            return [m.id for m in sorted(get_enabled_items(), key=lambda m: m.sort_order)]
        return sorted({"profile", INSPECTION_SCRIPT_LIBRARY_MENU_ID})

    monkeypatch.setattr(svc, "get_visible_menu_ids", fake_visible)
    yield


# =============================================================================
# P0: 路由注册
# =============================================================================


def test_inspection_script_admin_router_importable():
    """测试 inspection_script_admin_router 模块可导入且包含 router。"""
    from app.routers import inspection_script_admin_router

    assert hasattr(inspection_script_admin_router, "router")


def test_endpoints_registered(client):
    """测试 /api/admin/inspection-scripts* 端点已注册(2026-09-16:移除 /scan)。"""
    routes = [r.path for r in client.app.routes]
    expected = [
        "/api/admin/inspection-scripts",
        "/api/admin/inspection-scripts/{script_id}",
        "/api/admin/inspection-scripts/{script_id}/segments",
        "/api/admin/inspection-scripts/{script_id}/segments/{segment_id}",
    ]
    for path in expected:
        assert path in routes, f"路由未注册: {path}"


def test_scan_endpoint_removed(client):
    """POST /api/admin/inspection-scripts/scan 已移除(2026-09-16)。

    直接断言路由表中无该路径(优先于 HTTP 行为断言,避免与鉴权链耦合)。
    """
    routes = [r.path for r in client.app.routes]
    assert "/api/admin/inspection-scripts/scan" not in routes


def test_delete_endpoint_registered(client):
    """DELETE /api/admin/inspection-scripts/{script_id} 已注册。"""
    delete_paths = {
        r.path
        for r in client.app.routes
        if getattr(r, "methods", None) and "DELETE" in r.methods
    }
    target = "/api/admin/inspection-scripts/{script_id}"
    assert target in delete_paths


# =============================================================================
# P1: 列表端点
# =============================================================================


def test_list_returns_whitelisted_fields(client, inspection_router_setup, admin_headers, monkeypatch):
    """GET 返回白名单字段(不含脚本原文)。"""
    monkeypatch.setattr(
        inspection_router_setup.state.inspection_script_service,
        "list_scripts",
        lambda: [
            {
                "id": 1,
                "name": "linux-bash",
                "display_name": "Linux Bash",
                "platform": "linux",
                "version": "bash",
                "inspection_parser": "json",
                "updated_at": "2026-08-03",
            }
        ],
    )

    resp = client.get("/api/admin/inspection-scripts", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 1
    item = body[0]
    assert item["name"] == "linux-bash"
    assert "inspection_script" not in item
    assert "inspection_fields" not in item


def test_list_service_missing_returns_500(client, admin_headers):
    """服务未初始化 → 500。"""
    from app.main import app

    saved = getattr(app.state, "inspection_script_service", None)
    app.state.inspection_script_service = None
    try:
        resp = client.get("/api/admin/inspection-scripts", headers=admin_headers)
        assert resp.status_code == 500
    finally:
        app.state.inspection_script_service = saved


# =============================================================================
# P3: 详情端点
# =============================================================================


def test_detail_returns_full_content_with_segments(
    client, inspection_router_setup, admin_headers, monkeypatch
):
    """GET /{id} 命中时返回完整字段(含 inspection_script / inspection_fields / segments)。"""
    detail = {
        "id": 1, "name": "linux-bash", "display_name": "Linux Bash",
        "platform": "linux", "version": "bash", "inspection_parser": "json",
        "inspection_script": "echo probe",
        "inspection_fields": [
            {"key": "disk_used_pct", "name_zh": "磁盘使用率", "unit": "%",
             "direction": "high", "warn": 80.0, "crit": 90.0}
        ],
        "segments": [
            {"id": 11, "segment_key": "cpu", "display_name": "CPU",
             "sort_order": 40, "script": "echo cpu", "enabled": True},
        ],
        "created_at": None, "updated_at": "2026-08-03",
    }
    monkeypatch.setattr(
        inspection_router_setup.state.inspection_script_service,
        "get_script_detail",
        lambda _id: detail,
    )
    resp = client.get("/api/admin/inspection-scripts/1", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "linux-bash"
    assert body["inspection_script"] == "echo probe"
    assert "segments" in body
    assert body["segments"][0]["segment_key"] == "cpu"


def test_detail_missing_returns_404(client, inspection_router_setup, admin_headers, monkeypatch):
    """GET /{id} 未命中时返回 404。"""
    monkeypatch.setattr(
        inspection_router_setup.state.inspection_script_service,
        "get_script_detail",
        lambda _id: None,
    )
    resp = client.get("/api/admin/inspection-scripts/9999", headers=admin_headers)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "脚本不存在"


# =============================================================================
# P3.5: 更新端点
# =============================================================================


def test_update_script_detail_returns_full_record(
    client, inspection_router_setup, admin_headers, monkeypatch
):
    """PUT /{id} 返回完整详情。"""
    detail = {
        "id": 1, "name": "linux-bash", "display_name": "Linux Bash",
        "platform": "linux", "version": "bash", "inspection_parser": "json",
        "inspection_script": "echo manual", "inspection_fields": [],
        "created_at": None, "updated_at": "2026-08-04",
    }
    monkeypatch.setattr(
        inspection_router_setup.state.inspection_script_service,
        "update_script_detail",
        AsyncMock(side_effect=lambda _id, _payload: detail),
    )
    resp = client.put(
        "/api/admin/inspection-scripts/1",
        headers=admin_headers,
        json={
            "display_name": "Linux Bash", "platform": "linux",
            "version": "bash", "inspection_parser": "json",
            "inspection_script": "echo manual", "inspection_fields": [],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "linux-bash"


def test_update_script_detail_requires_admin(client, inspection_router_setup, user_headers):
    """非 admin 调 PUT → 403。"""
    resp = client.put("/api/admin/inspection-scripts/1", headers=user_headers, json={"display_name": "X"})
    assert resp.status_code == 403


# =============================================================================
# P4: ACL 矩阵
# =============================================================================


def test_list_user_with_acl_passes(
    client, inspection_router_setup, user_headers, grant_server_management_acl, monkeypatch
):
    """普通用户拥有 server-management ACL → 列表 200。"""
    monkeypatch.setattr(
        inspection_router_setup.state.inspection_script_service,
        "list_scripts",
        lambda: [],
    )
    resp = client.get("/api/admin/inspection-scripts", headers=user_headers)
    assert resp.status_code == 200


def test_list_user_without_acl_returns_403(
    client, inspection_router_setup, user_headers, monkeypatch
):
    """普通用户无 server-management ACL → 列表 403。"""
    monkeypatch.setattr(
        inspection_router_setup.state.inspection_script_service,
        "list_scripts",
        lambda: [],
    )
    resp = client.get("/api/admin/inspection-scripts", headers=user_headers)
    assert resp.status_code == 403


def test_detail_requires_admin(
    client, inspection_router_setup, user_headers, grant_server_management_acl, monkeypatch
):
    """GET /{id} 仅 admin。"""
    monkeypatch.setattr(
        inspection_router_setup.state.inspection_script_service,
        "get_script_detail",
        lambda _id: None,
    )
    resp = client.get("/api/admin/inspection-scripts/1", headers=user_headers)
    assert resp.status_code == 403


# =============================================================================
# P5: DELETE 端点
# =============================================================================


def test_delete_inspection_script_returns_204(
    client, inspection_router_setup, admin_headers, monkeypatch
):
    """DELETE /{id} 命中时返回 204。"""
    async def fake_delete(_id):
        return True

    monkeypatch.setattr(
        inspection_router_setup.state.inspection_script_service,
        "delete_script",
        fake_delete,
    )
    resp = client.delete("/api/admin/inspection-scripts/11", headers=admin_headers)
    assert resp.status_code == 204
    assert resp.content == b""


def test_delete_inspection_script_404_when_missing(
    client, inspection_router_setup, admin_headers, monkeypatch
):
    """DELETE /{id} 不存在 → 404。"""
    async def fake_delete(_id):
        return False

    monkeypatch.setattr(
        inspection_router_setup.state.inspection_script_service,
        "delete_script",
        fake_delete,
    )
    resp = client.delete("/api/admin/inspection-scripts/9999", headers=admin_headers)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "脚本不存在"


def test_delete_inspection_script_unbinds_servers_and_segments_in_transaction(
    client, inspection_router_setup, admin_headers
):
    """DELETE 路由端到端:单事务内同时解绑 servers + 清理 segments。"""
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock, MagicMock
    from app.shared.utils.inspection_script_service import (
        InspectionScriptService,
    )

    db = MagicMock(name="asyncpg_pool_stub")
    conn = MagicMock(name="asyncpg_connection_stub")
    conn.fetchrow = AsyncMock(side_effect=[{"name": "linux-bash"}])
    # 2026-09-16:事务内 3 次 execute(UPDATE servers / DELETE segments / DELETE scripts)
    conn.execute = AsyncMock(side_effect=["UPDATE 1", "DELETE 4", "DELETE 1"])

    @asynccontextmanager
    async def _tx():
        yield None

    conn.transaction = MagicMock(side_effect=lambda: _tx())

    class _CM:
        def __init__(self, value):
            self._value = value

        async def __aenter__(self):
            return self._value

        async def __aexit__(self, exc_type, exc, tb):
            return False

    db.acquire = MagicMock(side_effect=lambda: _CM(conn))

    svc = InspectionScriptService(db=db)
    svc._cache["linux-bash"] = {"id": 7, "name": "linux-bash"}
    svc._id_cache[7] = {"id": 7, "name": "linux-bash"}

    inspection_router_setup.state.inspection_script_service = svc
    InspectionScriptService.set_instance(svc)
    try:
        resp = client.delete("/api/admin/inspection-scripts/7", headers=admin_headers)
    finally:
        InspectionScriptService.reset()
        inspection_router_setup.state.inspection_script_service = None

    assert resp.status_code == 204
    assert db.acquire.call_count == 1
    assert conn.transaction.call_count == 1
    assert conn.execute.await_count == 3
    executed_sqls = [c.args[0] for c in conn.execute.await_args_list]
    assert any("UPDATE devops_servers" in sql for sql in executed_sqls)
    assert any("DELETE FROM inspection_script_segments" in sql for sql in executed_sqls)
    assert any("DELETE FROM inspection_scripts" in sql for sql in executed_sqls)


# =============================================================================
# P6: 分段 CRUD 端点(2026-09-16 新增)
# =============================================================================


def test_list_segments_404_when_group_missing(
    client, inspection_router_setup, admin_headers, monkeypatch
):
    """GET /segments 组不存在 → 404。"""
    monkeypatch.setattr(
        inspection_router_setup.state.inspection_script_service,
        "list_segments",
        lambda _id: None,
    )
    resp = client.get(
        "/api/admin/inspection-scripts/999/segments",
        headers=admin_headers,
    )
    assert resp.status_code == 404


def test_create_segment_success_and_audit(
    client, inspection_router_setup, admin_headers, monkeypatch
):
    """POST /segments 成功返回白名单 + 写审计。"""
    seg = {
        "id": 11, "script_id": 1, "segment_key": "cpu",
        "display_name": "CPU", "sort_order": 40, "script": "echo c",
        "enabled": True, "created_at": None, "updated_at": None,
    }
    monkeypatch.setattr(
        inspection_router_setup.state.inspection_script_service,
        "upsert_segment",
        AsyncMock(side_effect=lambda _sid, _p: seg),
    )
    captured = {}

    def fake_log_service():
        captured["events"] = []
        class _Svc:
            def emit(self, event):
                captured["events"].append(event)
        return _Svc()

    from app.routers import inspection_script_admin_router as router_mod
    monkeypatch.setattr(router_mod, "get_log_service", fake_log_service)

    resp = client.post(
        "/api/admin/inspection-scripts/1/segments",
        headers=admin_headers,
        json={
            "segment_key": "cpu", "display_name": "CPU",
            "sort_order": 40, "script": "echo c", "enabled": True,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["segment_key"] == "cpu"
    assert len(captured["events"]) == 1
    ev = captured["events"][0]
    assert ev.action == "inspection_segment_create"
    assert ev.target_name == "1/cpu"
    assert ev.target_type == "inspection_script_segment"


def test_create_segment_400_on_validation_error(
    client, inspection_router_setup, admin_headers, monkeypatch
):
    """POST /segments service 抛 ValueError → 400。"""
    async def fake_upsert(_sid, _p):
        raise ValueError("segment_key 非法(须匹配 ^[a-z0-9][a-z0-9_-]{0,63}$)")

    monkeypatch.setattr(
        inspection_router_setup.state.inspection_script_service,
        "upsert_segment",
        fake_upsert,
    )
    resp = client.post(
        "/api/admin/inspection-scripts/1/segments",
        headers=admin_headers,
        json={
            "segment_key": "Bad Key!", "display_name": "X",
            "sort_order": 0, "script": "echo x",
        },
    )
    assert resp.status_code == 400
    assert "segment_key" in resp.json()["detail"]


def test_create_segment_404_when_group_missing(
    client, inspection_router_setup, admin_headers, monkeypatch
):
    """POST /segments 组不存在 → 404。"""
    async def fake_upsert(_sid, _p):
        return None

    monkeypatch.setattr(
        inspection_router_setup.state.inspection_script_service,
        "upsert_segment",
        fake_upsert,
    )
    resp = client.post(
        "/api/admin/inspection-scripts/999/segments",
        headers=admin_headers,
        json={"segment_key": "cpu", "script": "echo c"},
    )
    assert resp.status_code == 404


def test_update_segment_404_when_segment_missing(
    client, inspection_router_setup, admin_headers, monkeypatch
):
    """PUT /segments/{id} 不存在 → 404。"""
    async def fake_upsert(_sid, _p, segment_id=None):
        return None

    monkeypatch.setattr(
        inspection_router_setup.state.inspection_script_service,
        "upsert_segment",
        fake_upsert,
    )
    resp = client.put(
        "/api/admin/inspection-scripts/1/segments/99",
        headers=admin_headers,
        json={"segment_key": "cpu", "script": "echo c"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "分段不存在"


def test_delete_segment_204_and_404(
    client, inspection_router_setup, admin_headers, monkeypatch
):
    """DELETE /segments/{id} 204 / 404 双分支。"""
    # 204 成功
    async def fake_delete(_sid, _seg_id):
        return True

    monkeypatch.setattr(
        inspection_router_setup.state.inspection_script_service,
        "delete_segment",
        fake_delete,
    )
    resp = client.delete(
        "/api/admin/inspection-scripts/1/segments/11",
        headers=admin_headers,
    )
    assert resp.status_code == 204
    assert resp.content == b""

    # 404 不存在
    async def fake_delete_missing(_sid, _seg_id):
        return False

    monkeypatch.setattr(
        inspection_router_setup.state.inspection_script_service,
        "delete_segment",
        fake_delete_missing,
    )
    resp = client.delete(
        "/api/admin/inspection-scripts/1/segments/999",
        headers=admin_headers,
    )
    assert resp.status_code == 404


def test_segments_require_admin(
    client, inspection_router_setup, user_headers, grant_server_management_acl
):
    """分段 CRUD 端点仅 admin。"""
    # GET
    resp = client.get(
        "/api/admin/inspection-scripts/1/segments",
        headers=user_headers,
    )
    assert resp.status_code == 403
    # POST
    resp = client.post(
        "/api/admin/inspection-scripts/1/segments",
        headers=user_headers,
        json={"segment_key": "cpu", "script": "echo c"},
    )
    assert resp.status_code == 403
    # DELETE
    resp = client.delete(
        "/api/admin/inspection-scripts/1/segments/1",
        headers=user_headers,
    )
    assert resp.status_code == 403
