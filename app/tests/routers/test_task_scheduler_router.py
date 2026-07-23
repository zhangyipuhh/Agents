# -*- coding:utf-8 -*-
"""
Task Scheduler Admin Router 测试模块。

验证 /api/admin/task-schedules/* 路由的注册、CRUD、启停、手动触发、执行历史与权限控制。
"""
from unittest.mock import AsyncMock


# =============================================================================
# P0: 导入与路由注册
# =============================================================================

def test_task_scheduler_router_importable():
    """测试 task_scheduler_router 模块可导入且包含 router。"""
    from app.routers import task_scheduler_router

    assert hasattr(task_scheduler_router, "router")


def test_task_scheduler_endpoints_registered(client):
    """测试所有定时任务管理端点已注册。"""
    routes = [r.path for r in client.app.routes]
    expected = [
        "/api/admin/task-schedules",
        "/api/admin/task-schedules/{schedule_id}",
        "/api/admin/task-schedules/{schedule_id}/enabled",
        "/api/admin/task-schedules/{schedule_id}/trigger",
        "/api/admin/task-schedules/{schedule_id}/runs",
    ]
    for path in expected:
        assert path in routes, f"路由未注册: {path}"


# =============================================================================
# P2: ACL 双重门（2026-07-23）
# - admin role bypass ACL 直通
# - 普通用户 ACL 授权（task-scheduler.scheduled）后能调
# - 普通用户未授权 → 403
# =============================================================================


def _override_task_scheduler_visible_menu(client, visible_ids):
    """覆盖 task-scheduler_router 调用期间 menu_permission_service 的返回值。"""
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


def _stub_list_schedules(client):
    """stub task_scheduler_service.list_schedules 避免 db.fetch。"""
    svc = getattr(client.app.state, "task_scheduler_service", None)
    if svc is None:
        from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService
        from app.shared.utils.agent.agent_config_service import AgentConfigService
        svc = TaskSchedulerService(
            db=None,
            agent_config_service=AgentConfigService(db=None),
            email_config_service=None,
        )
        client.app.state.task_scheduler_service = svc
    svc.list_schedules = AsyncMock(return_value=[])
    svc.get_schedule = AsyncMock(return_value=None)
    svc.get_schedule_runs = AsyncMock(return_value=[])


def test_normal_user_no_acl_list_task_schedules_403(client, user_headers):
    """ACL 空：普通用户 GET /task-schedules 返 403（守卫拦截）。"""
    _override_task_scheduler_visible_menu(client, visible_ids={'profile'})
    resp = client.get("/api/admin/task-schedules", headers=user_headers)
    assert resp.status_code == 403


def test_normal_user_acl_scheduled_passes_list(client, user_headers):
    """ACL 含 task-scheduler.scheduled：普通用户 GET /task-schedules 通过（200 / 业务异常 500 都算 ACL 通过）。"""
    _override_task_scheduler_visible_menu(
        client, visible_ids={'profile', 'task-scheduler.scheduled'}
    )
    _stub_list_schedules(client)
    resp = client.get("/api/admin/task-schedules", headers=user_headers)
    # 关键：不是 403（ACL 通过），可以是 200 或 500（业务异常）
    assert resp.status_code != 403
    assert resp.status_code in (200, 500)


def test_normal_user_acl_no_scheduled_still_blocked(client, user_headers):
    """普通用户 ACL 含 task-scheduler 父级但缺 .scheduled 子菜单 → 仍 403。"""
    _override_task_scheduler_visible_menu(
        client, visible_ids={'profile', 'task-scheduler'}  # 仅父级
    )
    resp = client.get("/api/admin/task-schedules", headers=user_headers)
    assert resp.status_code == 403


def test_admin_still_bypasses_acl_for_task_schedules(client, admin_headers):
    """admin 角色 bypass ACL：ACL 空也能调（守卫不查 ACL）。"""
    _override_task_scheduler_visible_menu(client, visible_ids={'profile'})
    _stub_list_schedules(client)
    resp = client.get("/api/admin/task-schedules", headers=admin_headers)
    # 关键：不是 403（ACL bypass）
    assert resp.status_code != 403
    assert resp.status_code in (200, 500)


# =============================================================================
# P1: 成功路径
# =============================================================================

def test_list_task_schedules_returns_200(client, admin_headers):
    """测试 GET /api/admin/task-schedules 返回任务列表。"""
    service = client.app.state.task_scheduler_service
    service.list_schedules = AsyncMock(return_value=[{"id": 1, "name": "每日巡检"}])

    response = client.get("/api/admin/task-schedules", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()[0]["name"] == "每日巡检"


def test_create_task_schedule_returns_201(client, admin_headers):
    """测试 POST /api/admin/task-schedules 创建任务。"""
    service = client.app.state.task_scheduler_service
    service.create_schedule = AsyncMock(return_value={"id": 1, "name": "每日巡检"})

    response = client.post(
        "/api/admin/task-schedules",
        headers=admin_headers,
        json={
            "name": "每日巡检",
            "agent_name": "map_agent",
            "prompt": "检查今日任务",
            "cron_expression": "0 9 * * *",
            "timezone": "Asia/Shanghai",
            "enabled": True,
            "context_overrides": {},
        },
    )

    assert response.status_code == 201
    assert response.json()["id"] == 1


def test_invalid_cron_returns_400(client, admin_headers):
    """测试非法 cron 表达式返回 400。"""
    response = client.post(
        "/api/admin/task-schedules",
        headers=admin_headers,
        json={
            "name": "每日巡检",
            "agent_name": "map_agent",
            "prompt": "检查今日任务",
            "cron_expression": "invalid cron",
            "timezone": "Asia/Shanghai",
            "enabled": True,
            "context_overrides": {},
        },
    )

    assert response.status_code == 400


def test_update_task_schedule_returns_200(client, admin_headers):
    """测试 PUT /api/admin/task-schedules/{id} 更新任务。"""
    service = client.app.state.task_scheduler_service
    service.update_schedule = AsyncMock(return_value={"id": 1, "name": "更新巡检"})

    response = client.put(
        "/api/admin/task-schedules/1",
        headers=admin_headers,
        json={"name": "更新巡检", "cron_expression": "30 9 * * *"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "更新巡检"


def test_set_task_schedule_enabled_returns_200(client, admin_headers):
    """测试 PUT /enabled 启停任务。"""
    service = client.app.state.task_scheduler_service
    service.set_schedule_enabled = AsyncMock(return_value={"id": 1, "enabled": False})

    response = client.put(
        "/api/admin/task-schedules/1/enabled",
        headers=admin_headers,
        json={"enabled": False},
    )

    assert response.status_code == 200
    assert response.json()["enabled"] is False


def test_trigger_task_schedule_returns_run_id(client, admin_headers):
    """测试 POST /trigger 返回执行记录。"""
    service = client.app.state.task_scheduler_service
    service.trigger_schedule = AsyncMock(return_value={"id": 9, "status": "pending"})

    response = client.post("/api/admin/task-schedules/1/trigger", headers=admin_headers)

    assert response.status_code == 202
    assert response.json()["id"] == 9


def test_list_task_runs_returns_200(client, admin_headers):
    """测试 GET /runs 返回执行历史。"""
    service = client.app.state.task_scheduler_service
    service.list_runs = AsyncMock(return_value=[{"id": 1, "status": "success"}])

    response = client.get("/api/admin/task-schedules/1/runs", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()[0]["status"] == "success"


def test_delete_task_schedule_returns_204(client, admin_headers):
    """测试 DELETE /api/admin/task-schedules/{id} 删除任务。"""
    service = client.app.state.task_scheduler_service
    service.delete_schedule = AsyncMock(return_value=None)

    response = client.delete("/api/admin/task-schedules/1", headers=admin_headers)

    assert response.status_code == 204


# =============================================================================
# P1: 失败路径与权限
# =============================================================================

def test_user_cannot_access_task_schedules(client, user_headers):
    """测试普通用户访问定时任务管理接口返回 403。"""
    response = client.get("/api/admin/task-schedules", headers=user_headers)

    assert response.status_code == 403


def test_task_scheduler_service_missing_returns_500(client, admin_headers):
    """测试 TaskSchedulerService 未初始化时返回 500。"""
    original = client.app.state.task_scheduler_service
    delattr(client.app.state, "task_scheduler_service")
    try:
        response = client.get("/api/admin/task-schedules", headers=admin_headers)
    finally:
        client.app.state.task_scheduler_service = original

    assert response.status_code == 500
    assert response.json()["detail"] == "TaskSchedulerService not initialized"


# =============================================================================
# P1: 脚本任务（target_type='script'）路径
# =============================================================================

def test_create_script_task_schedule_returns_201(client, admin_headers):
    """测试 POST 创建 target_type='script' 的任务返回 201。

    参数:
        client: TestClient fixture。
        admin_headers: admin 身份头 fixture。

    返回值:
        None

    异常:
        AssertionError: 状态码非 201 或返回字段不匹配时失败
    """
    service = client.app.state.task_scheduler_service
    service.create_schedule = AsyncMock(
        return_value={
            "id": 2,
            "name": "脚本巡检",
            "target_type": "script",
            "script_name": "hello_script",
            "script_args": {"greeting": "hi"},
        }
    )

    response = client.post(
        "/api/admin/task-schedules",
        headers=admin_headers,
        json={
            "name": "脚本巡检",
            "target_type": "script",
            "script_name": "hello_script",
            "script_args": {"greeting": "hi"},
            "cron_expression": "0 9 * * *",
            "timezone": "Asia/Shanghai",
            "enabled": True,
            "context_overrides": {},
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 2
    assert body["target_type"] == "script"
    assert body["script_name"] == "hello_script"
    service.create_schedule.assert_awaited_once()


def test_create_script_task_without_script_name_returns_422(client, admin_headers):
    """测试 target_type='script' 但缺 script_name 时返回 422（Pydantic model_validator）。

    参数:
        client: TestClient fixture。
        admin_headers: admin 身份头 fixture。

    返回值:
        None

    异常:
        AssertionError: 状态码非 422 时失败
    """
    response = client.post(
        "/api/admin/task-schedules",
        headers=admin_headers,
        json={
            "name": "脚本巡检",
            "target_type": "script",
            # 故意缺 script_name
            "cron_expression": "0 9 * * *",
            "timezone": "Asia/Shanghai",
            "enabled": True,
            "context_overrides": {},
        },
    )

    assert response.status_code == 422


def test_create_agent_task_with_script_name_returns_422(client, admin_headers):
    """测试 target_type='agent' 但携带 script_name 时返回 422。

    参数:
        client: TestClient fixture。
        admin_headers: admin 身份头 fixture。

    返回值:
        None

    异常:
        AssertionError: 状态码非 422 时失败
    """
    response = client.post(
        "/api/admin/task-schedules",
        headers=admin_headers,
        json={
            "name": "智能体巡检",
            "target_type": "agent",
            "agent_name": "map_agent",
            "prompt": "检查",
            "script_name": "hello_script",  # agent 类型不应携带 script_name
            "cron_expression": "0 9 * * *",
            "timezone": "Asia/Shanghai",
            "enabled": True,
            "context_overrides": {},
        },
    )

    assert response.status_code == 422


def test_create_task_schedule_empty_name_returns_422(client, admin_headers):
    """测试 name 为空字符串时返回 422（Pydantic min_length=1 校验）。

    复现 2026-07-16 排查过程中前端表单忘记填任务名称直接提交的场景：
    后端 CreateTaskScheduleRequest.name 字段的 min_length=1 校验会拒绝空字符串，
    此时 detail 应为 [{type:"string_too_short", loc:["body","name"], msg:"..."}]。

    参数:
        client: TestClient fixture。
        admin_headers: admin 身份头 fixture。

    返回值:
        None

    异常:
        AssertionError: 状态码非 422 时失败
    """
    response = client.post(
        "/api/admin/task-schedules",
        headers=admin_headers,
        json={
            "name": "",  # 故意为空字符串，触发 Pydantic min_length=1
            "target_type": "script",
            "script_name": "hello_script",
            "cron_expression": "*/5 * * * *",
            "timezone": "Asia/Shanghai",
            "enabled": True,
            "context_overrides": {},
        },
    )

    assert response.status_code == 422
    detail = response.json().get("detail")
    assert isinstance(detail, list), "Pydantic 422 detail 应为列表"
    assert any(d.get("loc") == ["body", "name"] for d in detail), (
        "期望 detail 中包含 loc=['body','name'] 的字段错误"
    )


# =============================================================================
# P1: 邮件通知字段（script + notify_enabled + notify_policy_id）路径
# =============================================================================

def test_create_script_task_with_notify_enabled_passes_through(client, admin_headers):
    """脚本任务带 notify_enabled=True + notify_policy_id 时 payload 应透传。"""
    service = client.app.state.task_scheduler_service
    service.create_schedule = AsyncMock(
        return_value={
            "id": 3,
            "name": "脚本告警",
            "target_type": "script",
            "script_name": "hello_script",
            "notify_enabled": True,
            "notify_policy_id": 5,
        }
    )

    response = client.post(
        "/api/admin/task-schedules",
        headers=admin_headers,
        json={
            "name": "脚本告警",
            "target_type": "script",
            "script_name": "hello_script",
            "cron_expression": "0 9 * * *",
            "timezone": "Asia/Shanghai",
            "enabled": True,
            "context_overrides": {},
            "notify_enabled": True,
            "notify_policy_id": 5,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["notify_enabled"] is True
    assert body["notify_policy_id"] == 5
    # 透传给 service 的 payload 也应包含这两个字段
    call_args = service.create_schedule.await_args
    payload = call_args.args[0]
    assert payload["notify_enabled"] is True
    assert payload["notify_policy_id"] == 5


def test_update_script_task_can_change_notify_enabled(client, admin_headers):
    """PUT 更新可单独修改 notify_enabled 与 notify_policy_id。"""
    service = client.app.state.task_scheduler_service
    service.update_schedule = AsyncMock(
        return_value={
            "id": 3,
            "notify_enabled": True,
            "notify_policy_id": 7,
        }
    )

    response = client.put(
        "/api/admin/task-schedules/3",
        headers=admin_headers,
        json={"notify_enabled": True, "notify_policy_id": 7},
    )

    assert response.status_code == 200
    service.update_schedule.assert_awaited_once()


def test_create_script_task_notify_enabled_without_policy_id_returns_400(
    client, admin_headers
):
    """notify_enabled=True 但 notify_policy_id 缺失时 service 抛 TaskScheduleValidationError → 400。"""
    service = client.app.state.task_scheduler_service
    from app.shared.utils.agent.task_scheduler_service import (
        TaskScheduleValidationError,
    )

    async def raise_validation(payload, **_kwargs):
        raise TaskScheduleValidationError(
            "notify_policy_id is required when notify_enabled=True"
        )

    service.create_schedule = AsyncMock(side_effect=raise_validation)

    response = client.post(
        "/api/admin/task-schedules",
        headers=admin_headers,
        json={
            "name": "脚本告警",
            "target_type": "script",
            "script_name": "hello_script",
            "cron_expression": "0 9 * * *",
            "timezone": "Asia/Shanghai",
            "enabled": True,
            "context_overrides": {},
            "notify_enabled": True,
            # notify_policy_id 缺失
        },
    )

    assert response.status_code == 400
    assert "notify_policy_id" in response.json()["detail"]


def test_create_script_task_notify_policy_id_zero_returns_422(client, admin_headers):
    """notify_policy_id <= 0 时 Pydantic ge=1 校验拒绝，返回 422。"""
    response = client.post(
        "/api/admin/task-schedules",
        headers=admin_headers,
        json={
            "name": "脚本告警",
            "target_type": "script",
            "script_name": "hello_script",
            "cron_expression": "0 9 * * *",
            "timezone": "Asia/Shanghai",
            "enabled": True,
            "context_overrides": {},
            "notify_enabled": True,
            "notify_policy_id": 0,  # 非法：必须 >= 1
        },
    )

    assert response.status_code == 422
