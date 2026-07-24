# -*- coding:utf-8 -*-
"""
TaskSchedulerService.notify_policy_id 归属校验测试。

验证：
- ``_assert_notify_policy_access`` 在 admin / 普通用户 / system 三种 scope 下判定正确
- 普通用户跨用户引用策略被拒（抛 ``TaskScheduleValidationError``）
- 普通用户引用自己的策略：通过
- 策略不存在：抛 ``TaskScheduleValidationError``
- email_config_service 未注入：跳过校验（不阻断）
"""
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.shared.utils.agent.task_scheduler_service import (
    TaskSchedulerService,
    TaskScheduleValidationError,
)


# =============================================================================
# P0: 导入与构造
# =============================================================================


def test_helper_importable():
    """TaskSchedulerService 可导入（含归属校验 helper）。"""
    from app.shared.utils.agent import task_scheduler_service

    assert hasattr(task_scheduler_service, "TaskSchedulerService")


def _make_service_with_email_mock(
    policy: Optional[Dict[str, Any]],
    email_service_injected: bool = True,
) -> TaskSchedulerService:
    """构造 TaskSchedulerService，注入 fake email_config_service。

    参数:
        policy: ``get_policy_internal`` 返回的策略；``None`` 模拟策略不存在。
        email_service_injected: False 时 _email_config_service 为 None
            （模拟 lifespan 未初始化或 Memory 模式）。

    返回:
        TaskSchedulerService: 实例。
    """
    service = TaskSchedulerService.__new__(TaskSchedulerService)
    service._db = MagicMock()
    if email_service_injected:
        email_service = MagicMock()
        email_service.get_policy_internal = AsyncMock(return_value=policy)
        service._email_config_service = email_service
    else:
        service._email_config_service = None
    return service


# =============================================================================
# P1: _assert_notify_policy_access 判定
# =============================================================================


@pytest.mark.asyncio
async def test_assert_notify_policy_access_none_skips():
    """notify_policy_id 为 None 时直接跳过校验（无需 DB 查询）。"""
    service = _make_service_with_email_mock(policy=None)
    # 不应抛异常
    await service._assert_notify_policy_access(
        notify_policy_id=None, schedule_owner_user_id=42, is_admin=False,
    )
    # email service 不应被调用
    service._email_config_service.get_policy_internal.assert_not_called()


@pytest.mark.asyncio
async def test_assert_notify_policy_access_owner_user_passes():
    """普通用户引用自己创建的策略：通过校验。"""
    policy = {"id": 7, "created_by_user_id": 42, "name": "我的策略"}
    service = _make_service_with_email_mock(policy=policy)
    await service._assert_notify_policy_access(
        notify_policy_id=7, schedule_owner_user_id=42, is_admin=False,
    )


@pytest.mark.asyncio
async def test_assert_notify_policy_access_other_user_rejected():
    """普通用户引用他人策略：抛 ``TaskScheduleValidationError``。

    校验语义：策略 owner（99）!= schedule 创建人（42），且非 admin，拒绝。
    """
    policy = {"id": 7, "created_by_user_id": 99, "name": "他人策略"}
    service = _make_service_with_email_mock(policy=policy)
    with pytest.raises(TaskScheduleValidationError) as exc_info:
        await service._assert_notify_policy_access(
            notify_policy_id=7, schedule_owner_user_id=42, is_admin=False,
        )
    assert "notify_policy_id" in str(exc_info.value)
    assert "7" in str(exc_info.value)


@pytest.mark.asyncio
async def test_assert_notify_policy_access_admin_passes_for_any_owner():
    """admin 角色可关联任何用户创建的策略。"""
    policy = {"id": 7, "created_by_user_id": 99, "name": "他人策略"}
    service = _make_service_with_email_mock(policy=policy)
    # is_admin=True → 通过校验（即便 owner != 99 与 admin_user_id 不一致）
    await service._assert_notify_policy_access(
        notify_policy_id=7, schedule_owner_user_id=1, is_admin=True,
    )


@pytest.mark.asyncio
async def test_assert_notify_policy_access_not_found_rejected():
    """notify_policy_id 在数据库不存在：抛 ``TaskScheduleValidationError``。"""
    service = _make_service_with_email_mock(policy=None)
    with pytest.raises(TaskScheduleValidationError) as exc_info:
        await service._assert_notify_policy_access(
            notify_policy_id=9999, schedule_owner_user_id=42, is_admin=False,
        )
    assert "不存在" in str(exc_info.value)


@pytest.mark.asyncio
async def test_assert_notify_policy_access_email_service_none_skips():
    """email_config_service 未注入（Memory 模式 / lifespan 未初始化）：跳过校验。

    行为契约：校验失败不阻断任务创建（运行时 ``_dispatch_script_email``
    也会跳过发邮件并打 warning 日志），保证 Memory 模式部署兼容。
    """
    service = _make_service_with_email_mock(
        policy=None, email_service_injected=False,
    )
    # 不抛异常
    await service._assert_notify_policy_access(
        notify_policy_id=7, schedule_owner_user_id=42, is_admin=False,
    )


@pytest.mark.asyncio
async def test_assert_notify_policy_access_owner_none_with_admin_passes():
    """策略 owner_id 为 None（数据库异常）但调用方为 admin：放过（admin 通透）。

    防御兜底：owner_id=None 时 ``can_access`` 对普通用户返回 False，但 admin
    不受影响。
    """
    policy = {"id": 7, "created_by_user_id": None, "name": "异常策略"}
    service = _make_service_with_email_mock(policy=policy)
    # admin 通过
    await service._assert_notify_policy_access(
        notify_policy_id=7, schedule_owner_user_id=1, is_admin=True,
    )


# =============================================================================
# P1: create_schedule / update_schedule 集成（轻量）
# =============================================================================


@pytest.mark.asyncio
async def test_create_schedule_cross_user_policy_rejected():
    """create_schedule 在 ``_assert_notify_policy_access`` 阶段被拒绝。

    通过真实 TaskSchedulerService + 注入 fake email_config_service 验证：
    调用 ``create_schedule`` 时若 notify_policy_id 属于他人，直接抛
    ``TaskScheduleValidationError``，不会进入 INSERT 流程。
    """
    service = TaskSchedulerService.__new__(TaskSchedulerService)
    service._db = MagicMock()
    # email service 返回他人策略
    email_service = MagicMock()
    email_service.get_policy_internal = AsyncMock(
        return_value={"id": 7, "created_by_user_id": 999, "name": "他人策略"}
    )
    service._email_config_service = email_service

    # 任何合法 payload 都因 notify_policy_id 越权被拒
    payload = {
        "name": "我的任务",
        "cron_expression": "0 * * * *",
        "target_type": "script",
        "script_name": "demo",
        "notify_enabled": True,
        "notify_policy_id": 7,
    }
    with pytest.raises(TaskScheduleValidationError):
        await service.create_schedule(
            payload=payload,
            created_by_user_id=42,
            is_admin=False,
        )
    # 不应进入 DB INSERT 流程
    service._db.fetchrow.assert_not_called()
    service._db.execute.assert_not_called()