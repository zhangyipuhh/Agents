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
