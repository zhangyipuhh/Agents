# -*- coding:utf-8 -*-
"""
Task Scheduler Admin Router 脚本任务触发测试。

验证 POST /api/admin/task-schedules/{id}/trigger 在 target_type='script' 任务上
返回 202，且 _handle_service_error 对 asyncpg.PostgresError 输出 500 + 业务 detail。
"""
from unittest.mock import AsyncMock

import pytest
from asyncpg import NotNullViolationError


def test_trigger_script_schedule_returns_202(client, admin_headers):
    """脚本任务的 trigger 端点返回 202 与脚本类型 run 记录。

    参数:
        client: TestClient fixture。
        admin_headers: admin 身份头 fixture。

    返回值:
        None

    异常:
        AssertionError: 状态码非 202 或 body 不包含 script 任务标记
    """
    service = client.app.state.task_scheduler_service
    service.trigger_schedule = AsyncMock(
        return_value={
            "id": 9,
            "status": "pending",
            "target_type": "script",
            "script_name": "hello_script",
            "agent_name": "script:hello_script",
            "prompt_snapshot": "[script] hello_script",
        }
    )

    response = client.post(
        "/api/admin/task-schedules/2/trigger", headers=admin_headers
    )

    assert response.status_code == 202
    body = response.json()
    assert body["target_type"] == "script"
    assert body["script_name"] == "hello_script"
    assert body["agent_name"] == "script:hello_script"
    service.trigger_schedule.assert_awaited_once_with(2)


def test_trigger_handles_db_error_returns_500_with_detail(client, admin_headers):
    """service 抛 asyncpg.NotNullViolationError 时路由返回 500 + 业务 detail。

    参数:
        client: TestClient fixture。
        admin_headers: admin 身份头 fixture。

    返回值:
        None

    异常:
        AssertionError: 状态码非 500 或 detail 中未包含 'database error' 标记
    """
    service = client.app.state.task_scheduler_service
    real_exc = NotNullViolationError(
        'null value in column "agent_name" of relation "agent_task_runs" '
        "violates not-null constraint"
    )

    async def raise_db_error(_schedule_id):
        raise real_exc

    service.trigger_schedule = AsyncMock(side_effect=raise_db_error)

    response = client.post(
        "/api/admin/task-schedules/2/trigger", headers=admin_headers
    )

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "database error" in detail
    assert "NotNullViolationError" in detail


def test_handle_service_error_postgres_error_mapping():
    """_handle_service_error 直接对 asyncpg.PostgresError 抛出 HTTPException(500)。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 分支未生效或 detail 缺失关键字段
    """
    from fastapi import HTTPException

    from app.routers import task_scheduler_router as router_module

    exc = NotNullViolationError(
        'null value in column "agent_name" violates not-null constraint'
    )
    with pytest.raises(HTTPException) as ei:
        router_module._handle_service_error(exc)

    assert ei.value.status_code == 500
    assert "database error" in ei.value.detail
    assert "NotNullViolationError" in ei.value.detail