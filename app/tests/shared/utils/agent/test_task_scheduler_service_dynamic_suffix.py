# -*- coding:utf-8 -*-
"""
TaskSchedulerService ``dynamic_context_suffix`` 注入 E2E 测试

覆盖场景: 2026-08-23 bug 修复 —— 定时任务的 agent 任务分支在执行时
``context_overrides`` 没有生成 ``<servers>`` XML 后缀, 导致 LLM 系统
提示词缺失 ``referenced_servers`` 触发器引用项。

测试策略:
    通过 ``monkeypatch`` 替换 ``execute_schedule`` 涉及的全部 DB / 锁 /
    Session / 日志副作用, 让代码能走到 agent 分支 (line 812 前后),
    仅验证 ``prepare_overrides_with_dynamic_suffix`` 被调用,
    ``build_agent_instance.context_overrides`` 同时含 ``referenced_servers``
    与 ``dynamic_context_suffix``。

Date: 2026-08-23
Author: AI Assistant
"""
import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _build_schedule():
    """构造含 referenced_servers 的 schedule 字典。"""
    return {
        "id": 1,
        "name": "test-sched",
        "agent_name": "map_agent",
        "prompt": "查询 prod 服务器的磁盘使用",
        "trigger_type": "manual",
        "target_type": "agent",
        "notify_enabled": False,
        "notify_policy_id": None,
        "script_name": None,
        "script_args": {},
        "created_by_user_id": 99,
        "enabled": True,
        "context_overrides": {
            "referenced_servers": [
                {"name": "prod-api", "server_type": "linux"},
                {"name": "win-db", "server_type": "windows"},
            ],
        },
    }


def _patch_service_for_execute(monkeypatch, overrides=None):
    """构造最小可执行 ``execute_schedule`` 的 mock 集合。

    返回:
        service: TaskSchedulerService 实例
        captured: dict, 收集 build_agent_instance 调用参数
    """
    captured = {"overrides": None, "agent_name": None, "session_id": None}

    async def fake_build_agent_instance(
        agent_name, session_id, message, context_overrides=None, **kwargs
    ):
        captured["agent_name"] = agent_name
        captured["session_id"] = session_id
        captured["overrides"] = context_overrides
        fake_agent = MagicMock()

        async def fake_invoke(*args, **kwargs):
            return {"output": "fake-output"}

        fake_agent.invoke = fake_invoke
        return fake_agent, MagicMock(), MagicMock()

    agent_config_service = MagicMock()
    agent_config_service.build_agent_instance = fake_build_agent_instance

    async def fake_prepare(ovrs, session_id):
        out = dict(ovrs or {})
        nodes = out.get("referenced_servers") or []
        server_lines = "\n".join(
            f'  <server name="{it["name"]}" server_type="{it["server_type"]}" />'
            for it in nodes
        )
        out["dynamic_context_suffix"] = (
            "<servers>\n" + server_lines + "\n</servers>"
        )
        return out

    agent_config_service.prepare_overrides_with_dynamic_suffix = fake_prepare
    agent_config_service.get_agent_config = AsyncMock(
        return_value=SimpleNamespace(display_name="地图智能体")
    )

    # 构造 service
    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value=None)
    db.execute = AsyncMock(return_value=None)
    service = TaskSchedulerService(
        db=db,
        scheduler=MagicMock(),
        agent_config_service=agent_config_service,
    )

    # 替换 execute_schedule 前置路径上的所有副作用
    schedule = overrides if overrides is not None else _build_schedule()
    monkeypatch.setattr(
        service, "get_schedule_internal", AsyncMock(return_value=schedule)
    )
    monkeypatch.setattr(
        service, "_get_running_run", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        service, "_create_run", AsyncMock(return_value={"id": 100})
    )
    monkeypatch.setattr(
        service, "_update_run", AsyncMock()
    )
    monkeypatch.setattr(
        service, "_install_run_logger", MagicMock(return_value=MagicMock())
    )
    monkeypatch.setattr(
        service, "_uninstall_run_logger", MagicMock()
    )
    monkeypatch.setattr(
        service, "_mark_schedule_run_completed", AsyncMock()
    )
    monkeypatch.setattr(
        service, "_extract_output_text", MagicMock(return_value="fake-output")
    )
    monkeypatch.setattr(
        service, "_duration_ms", MagicMock(return_value=10)
    )
    monkeypatch.setattr(
        service, "_get_created_by_user",
        AsyncMock(return_value={"id": 99, "username": "scheduler-user"}),
    )

    # stub SessionDB（避免真实 DB）
    monkeypatch.setattr(
        "app.shared.utils.agent.task_scheduler_service.SessionDB",
        MagicMock(add_session=AsyncMock(), update_session_agent=AsyncMock()),
    )

    return service, captured


@pytest.mark.asyncio
async def test_execute_schedule_agent_branch_injects_dynamic_context_suffix(monkeypatch):
    """E2E: 定时任务 agent 分支注入 <servers> XML 后缀。

    验证: 给定 schedule.context_overrides.referenced_servers 含两台服务器,
    execute_schedule 的 agent 分支会调 prepare_overrides_with_dynamic_suffix,
    build_agent_instance 收到的 context_overrides 同时含
    ``referenced_servers`` 与 ``dynamic_context_suffix``。
    """
    service, captured = _patch_service_for_execute(monkeypatch)

    await service.execute_schedule(
        schedule_id=1,
        trigger_type="manual",
        scheduled_at=datetime.now(),
        run_id=100,
    )

    assert captured["overrides"] is not None
    overrides = captured["overrides"]
    assert "dynamic_context_suffix" in overrides
    assert (
        '<server name="prod-api" server_type="linux" />'
        in overrides["dynamic_context_suffix"]
    )
    assert (
        '<server name="win-db" server_type="windows" />'
        in overrides["dynamic_context_suffix"]
    )
    assert "referenced_servers" in overrides
    assert len(overrides["referenced_servers"]) == 2
    assert overrides["log_user_id"] == 99
    assert overrides["log_username"] == "scheduler-user"


@pytest.mark.asyncio
async def test_execute_schedule_agent_branch_regression_without_prepare(monkeypatch):
    """反向测试: 不调 prepare 时, dynamic_context_suffix 缺失（bug 复现）。

    验证: 若 ``prepare_overrides_with_dynamic_suffix`` 未被调用,
    ``build_agent_instance.context_overrides`` 中不会含
    ``dynamic_context_suffix``, 但 ``referenced_servers`` 一等 context
    字段仍会传入 —— 这正是 2026-08-23 修复前的 bug 现象。
    """
    service, captured = _patch_service_for_execute(monkeypatch)

    # 关键: 把 prepare 方法换成 passthrough, 模拟修复前
    async def passthrough(ovrs, session_id):
        return ovrs
    service._agent_config_service.prepare_overrides_with_dynamic_suffix = passthrough

    await service.execute_schedule(
        schedule_id=1,
        trigger_type="manual",
        scheduled_at=datetime.now(),
        run_id=100,
    )

    overrides = captured["overrides"]
    assert "dynamic_context_suffix" not in overrides
    assert "referenced_servers" in overrides


@pytest.mark.asyncio
async def test_execute_schedule_agent_branch_preserves_log_user_identity(monkeypatch):
    """审计身份字段(log_user_id / log_username)在动态后缀注入后保留。"""
    service, captured = _patch_service_for_execute(monkeypatch)

    await service.execute_schedule(
        schedule_id=1,
        trigger_type="manual",
        scheduled_at=datetime.now(),
        run_id=100,
    )

    overrides = captured["overrides"]
    assert overrides["log_user_id"] == 99
    assert overrides["log_username"] == "scheduler-user"


@pytest.mark.asyncio
async def test_execute_schedule_agent_branch_handles_empty_context_overrides(monkeypatch):
    """空 context_overrides 仍生成显式空 <servers></servers>。"""
    schedule = _build_schedule()
    schedule["context_overrides"] = {}
    service, captured = _patch_service_for_execute(monkeypatch, overrides=schedule)

    await service.execute_schedule(
        schedule_id=1,
        trigger_type="manual",
        scheduled_at=datetime.now(),
        run_id=100,
    )

    overrides = captured["overrides"]
    assert "dynamic_context_suffix" in overrides
    assert "<servers>" in overrides["dynamic_context_suffix"]
    assert "</servers>" in overrides["dynamic_context_suffix"]
    assert overrides["log_user_id"] == 99