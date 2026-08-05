# -*- coding:utf-8 -*-
"""
inspection_script_admin_router 单元测试（2026-08-03 新增）

覆盖目标：
    - 路由注册（list / scan / detail）
    - GET 列表 200，返回白名单字段
    - POST scan 200，返回 4 个数字
    - GET 详情 200 / 404
    - ACL 矩阵：admin 直接通过；普通用户列表端点需
      ``task-scheduler.server-management`` ACL；扫描与详情仅 admin
    - 服务未初始化 → 500
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


INSPECTION_SCRIPT_LIBRARY_MENU_ID = "task-scheduler.inspection-script-library"


def _build_real_service():
    """构造真实的 ``InspectionScriptService`` 实例（db=stub MagicMock）。

    Returns:
        InspectionScriptService: 真实服务实例（db 桩为 ``MagicMock``，
            覆盖 ``fetch`` / ``fetchrow`` / ``execute`` 三个 async 方法）
    """
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = MagicMock(name="db_pool_stub")
    db.fetch = AsyncMock(return_value=[])
    db.fetchrow = AsyncMock(return_value=None)
    db.execute = AsyncMock(return_value=None)
    return InspectionScriptService(db=db, config_path="unused.yaml")


@pytest.fixture
def inspection_router_setup(app):
    """手动挂载 ``InspectionScriptService``（生产对等）。"""
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
    """测试 /api/admin/inspection-scripts* 端点已注册。"""
    routes = [r.path for r in client.app.routes]
    expected = [
        "/api/admin/inspection-scripts",
        "/api/admin/inspection-scripts/scan",
    ]
    for path in expected:
        assert path in routes, f"路由未注册: {path}"


def test_delete_endpoint_registered(client):
    """DELETE /api/admin/inspection-scripts/{script_id} 已注册（2026-08-04 新增）。

    用 ``client.app.router.routes`` 查全部路径，校验 DELETE 方法也挂上了。
    """
    delete_paths = {
        r.path
        for r in client.app.routes
        if getattr(r, "methods", None) and "DELETE" in r.methods
    }
    # FastAPI 把 path 与 full_path 一致挂在 route.path；按 pattern 精确匹配
    target = "/api/admin/inspection-scripts/{script_id}"
    assert target in delete_paths, (
        f"DELETE 路由未注册: {target}（已注册: {sorted(delete_paths)[:10]}）"
    )


# =============================================================================
# P1: 列表端点
# =============================================================================


def test_list_returns_whitelisted_fields(client, inspection_router_setup, admin_headers, monkeypatch):
    """GET 返回白名单字段（不含脚本原文）。"""
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
    # inspection_script / inspection_fields 不进入响应
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
# P2: 扫描端点
# =============================================================================


def test_scan_returns_four_numbers(client, inspection_router_setup, admin_headers, monkeypatch):
    """POST /scan 返回 5 个数字（2026-08-04 编辑优先新增 skipped）。"""

    async def fake_scan():
        return {"scanned": 2, "inserted": 1, "updated": 1, "failed": 0, "skipped": 0}

    monkeypatch.setattr(
        inspection_router_setup.state.inspection_script_service,
        "scan_and_upsert",
        fake_scan,
    )
    resp = client.post("/api/admin/inspection-scripts/scan", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"scanned", "inserted", "updated", "failed", "skipped"}
    assert body == {"scanned": 2, "inserted": 1, "updated": 1, "failed": 0, "skipped": 0}


# =============================================================================
# P3: 详情端点
# =============================================================================


def test_detail_returns_full_content(client, inspection_router_setup, admin_headers, monkeypatch):
    """GET /{id} 命中时返回完整字段（含脚本原文与字段规则）。"""
    detail = {
        "id": 1,
        "name": "linux-bash",
        "display_name": "Linux Bash",
        "platform": "linux",
        "version": "bash",
        "inspection_parser": "json",
        "inspection_script": "echo probe",
        "inspection_fields": [
            {"key": "disk_used_pct", "name_zh": "磁盘使用率", "unit": "%",
             "direction": "high", "warn": 80.0, "crit": 90.0}
        ],
        "created_at": None,
        "updated_at": "2026-08-03",
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
    assert "9999" not in resp.text


def test_detail_service_missing_returns_500(client, admin_headers):
    """服务未初始化 → 500。"""
    from app.main import app

    saved = getattr(app.state, "inspection_script_service", None)
    app.state.inspection_script_service = None
    try:
        resp = client.get("/api/admin/inspection-scripts/1", headers=admin_headers)
        assert resp.status_code == 500
    finally:
        app.state.inspection_script_service = saved


# =============================================================================
# P3.5: 更新端点（2026-08-04 新增）
# =============================================================================


def test_update_script_detail_returns_full_record(
    client, inspection_router_setup, admin_headers, monkeypatch
):
    """PUT /{id} 返回完整详情（_DETAIL_FIELDS）。"""
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
            "display_name": "Linux Bash",
            "platform": "linux",
            "version": "bash",
            "inspection_parser": "json",
            "inspection_script": "echo manual",
            "inspection_fields": [],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "linux-bash"
    assert body["inspection_script"] == "echo manual"


def test_update_script_detail_missing_returns_404(
    client, inspection_router_setup, admin_headers, monkeypatch
):
    """PUT /{id} 不存在 → 404，detail='脚本不存在'。"""
    async def fake_update(_id, _payload):
        return None
    monkeypatch.setattr(
        inspection_router_setup.state.inspection_script_service,
        "update_script_detail",
        AsyncMock(side_effect=fake_update),
    )
    resp = client.put(
        "/api/admin/inspection-scripts/9999",
        headers=admin_headers,
        json={
            "display_name": "X", "platform": "linux",
            "version": "", "inspection_parser": "json",
            "inspection_script": None, "inspection_fields": [],
        },
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "脚本不存在"


def test_update_script_detail_requires_admin(
    client, inspection_router_setup, user_headers
):
    """非 admin 调 PUT → 403。"""
    resp = client.put(
        "/api/admin/inspection-scripts/1",
        headers=user_headers,
        json={"display_name": "X"},
    )
    assert resp.status_code == 403


def test_update_script_detail_uses_real_async_path(
    client, inspection_router_setup, admin_headers, monkeypatch
):
    """回归测试：模拟真实 async service，确保 router 会 await(2026-08-05 新增)。

    旧实现漏 await 时，ResponseValidationError 会在序列化阶段触发 500。
    用 AsyncMock 替换并保持函数为 async，验证端到端 200。
    """
    detail = {
        "id": 1,
        "name": "linux-bash",
        "display_name": "Linux Bash",
        "platform": "linux",
        "version": "bash",
        "inspection_parser": "json",
        "inspection_script": "echo manual",
        "inspection_fields": [],
        "created_at": None,
        "updated_at": "2026-08-04",
    }

    async def fake_update(_id, _payload):
        return detail

    monkeypatch.setattr(
        inspection_router_setup.state.inspection_script_service,
        "update_script_detail",
        AsyncMock(side_effect=fake_update),
    )
    resp = client.put(
        "/api/admin/inspection-scripts/1",
        headers=admin_headers,
        json={
            "display_name": "Linux Bash",
            "platform": "linux",
            "version": "bash",
            "inspection_parser": "json",
            "inspection_script": "echo manual",
            "inspection_fields": [],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "linux-bash"


# =============================================================================
# P4: ACL 矩阵
# =============================================================================


def test_list_admin_passes_without_acl(client, inspection_router_setup, admin_headers, monkeypatch):
    """admin 直 bypass：列表端点不要求菜单 ACL。"""
    monkeypatch.setattr(
        inspection_router_setup.state.inspection_script_service,
        "list_scripts",
        lambda: [],
    )
    resp = client.get("/api/admin/inspection-scripts", headers=admin_headers)
    assert resp.status_code == 200


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


def test_scan_requires_admin(
    client, inspection_router_setup, user_headers, grant_server_management_acl, monkeypatch
):
    """POST /scan 仅 admin，普通用户即便有 ACL 仍 403。"""
    resp = client.post("/api/admin/inspection-scripts/scan", headers=user_headers)
    assert resp.status_code == 403


def test_detail_requires_admin(
    client, inspection_router_setup, user_headers, grant_server_management_acl, monkeypatch
):
    """GET /{id} 仅 admin，普通用户即便有 ACL 仍 403。"""
    monkeypatch.setattr(
        inspection_router_setup.state.inspection_script_service,
        "get_script_detail",
        lambda _id: None,
    )
    resp = client.get("/api/admin/inspection-scripts/1", headers=user_headers)
    assert resp.status_code == 403


# =============================================================================
# P4: DELETE 端点（2026-08-04 新增）
# =============================================================================


def test_delete_inspection_script_returns_204(
    client, inspection_router_setup, admin_headers, monkeypatch
):
    """DELETE /{id} 命中时返回 204（无响应体）。"""
    async def fake_delete(_id):
        return True

    monkeypatch.setattr(
        inspection_router_setup.state.inspection_script_service,
        "delete_script",
        fake_delete,
    )
    resp = client.delete(
        "/api/admin/inspection-scripts/11",
        headers=admin_headers,
    )
    assert resp.status_code == 204
    # 204 No Content：无响应体
    assert resp.content == b""


def test_delete_inspection_script_404_when_missing(
    client, inspection_router_setup, admin_headers, monkeypatch
):
    """DELETE /{id} 不存在 → 404 + 「脚本不存在」，不回显 script_id。"""
    async def fake_delete(_id):
        return False

    monkeypatch.setattr(
        inspection_router_setup.state.inspection_script_service,
        "delete_script",
        fake_delete,
    )
    resp = client.delete(
        "/api/admin/inspection-scripts/9999",
        headers=admin_headers,
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"] == "脚本不存在"
    # 不回显 script_id
    assert "9999" not in resp.text


def test_delete_inspection_script_500_when_service_missing(client, admin_headers):
    """DELETE /{id} 在 service 未初始化时 → 500。"""
    from app.main import app

    saved = getattr(app.state, "inspection_script_service", None)
    app.state.inspection_script_service = None
    try:
        resp = client.delete(
            "/api/admin/inspection-scripts/1",
            headers=admin_headers,
        )
        assert resp.status_code == 500
    finally:
        app.state.inspection_script_service = saved


def test_delete_inspection_script_requires_admin(
    client, inspection_router_setup, user_headers, grant_server_management_acl
):
    """DELETE /{id} 仅 admin，普通用户即便有 ACL 仍 403。"""
    resp = client.delete(
        "/api/admin/inspection-scripts/1",
        headers=user_headers,
    )
    assert resp.status_code == 403