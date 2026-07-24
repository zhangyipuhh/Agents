# -*- coding:utf-8 -*-
"""
TaskSchedulerService 测试模块。

验证智能体定时任务服务的导入、调度同步、手动触发与执行状态写入。
"""
import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.shared.utils.auth.ownership_scope import OwnershipScope


class FakeScheduler:
    """测试用调度器，记录 add/remove/start/shutdown 调用。"""

    def __init__(self):
        self.jobs = {}
        self.started = False
        self.shutdown_called = False

    def add_job(self, func, trigger=None, id=None, args=None, replace_existing=False, **kwargs):
        self.jobs[id] = {
            "func": func,
            "trigger": trigger,
            "args": args or [],
            "replace_existing": replace_existing,
            "kwargs": kwargs,
        }
        return SimpleNamespace(id=id, next_run_time=datetime(2026, 7, 10, 9, 0, 0))

    def remove_job(self, job_id):
        self.jobs.pop(job_id, None)

    def get_job(self, job_id):
        return self.jobs.get(job_id)

    def start(self):
        self.started = True

    def shutdown(self, wait=False):
        self.shutdown_called = True


class FakeDb:
    """测试用异步 DB，按 SQL 关键字模拟 task_schedules/task_runs 行为。"""

    def __init__(self):
        self.schedules = {}
        self.runs = {}
        self.next_schedule_id = 1
        self.next_run_id = 1
        self.execute_calls = []

    async def fetch(self, query, *args):
        if "FROM agent_task_schedules" in query:
            return list(self.schedules.values())
        if "FROM agent_task_runs" in query:
            schedule_id = args[0]
            return [r for r in self.runs.values() if r["schedule_id"] == schedule_id]
        return []

    async def fetchrow(self, query, *args):
        if "UPDATE agent_task_schedules" in query and "RETURNING" in query:
            schedule_id = args[0]
            row = self.schedules.get(schedule_id)
            if not row:
                return None
            if "SET enabled" in query:
                row["enabled"] = args[1]
                row["next_run_at"] = args[2]
            else:
                # update_schedule 全量更新分支：16 个 args
                # args[0]=id, args[1]=name, ..., args[10]=target_type,
                # args[11]=script_name, args[12]=script_args,
                # args[13]=notify_enabled, args[14]=notify_policy_id, args[15]=next_run_at
                row.update({
                    "name": args[1],
                    "description": args[2],
                    "agent_name": args[3],
                    "prompt": args[4],
                    "cron_expression": args[5],
                    "timezone": args[6],
                    "enabled": args[7],
                    "context_overrides": args[8],
                    "max_concurrent_runs": args[9],
                    "target_type": args[10],
                    "script_name": args[11],
                    "script_args": args[12],
                    "notify_enabled": args[13],
                    "notify_policy_id": args[14],
                    "next_run_at": args[15],
                })
            return row
        if "FROM agent_task_schedules" in query and "WHERE id" in query:
            return self.schedules.get(args[0])
        if "status = 'running'" in query:
            schedule_id = args[0]
            return next((r for r in self.runs.values() if r["schedule_id"] == schedule_id and r["status"] == "running"), None)
        if "FROM users" in query:
            return {"id": args[0], "username": "admin"}
        if "INSERT INTO agent_task_schedules" in query:
            # create_schedule INSERT：15 个 args
            # args[0]=name, ..., args[10]=target_type, args[11]=script_name, args[12]=script_args,
            # args[13]=notify_enabled, args[14]=notify_policy_id
            row = {
                "id": self.next_schedule_id,
                "name": args[0],
                "description": args[1],
                "agent_name": args[2],
                "prompt": args[3],
                "cron_expression": args[4],
                "timezone": args[5],
                "enabled": args[6],
                "created_by_user_id": args[7],
                "context_overrides": args[8],
                "max_concurrent_runs": args[9],
                "target_type": args[10],
                "script_name": args[11],
                "script_args": args[12],
                "notify_enabled": args[13],
                "notify_policy_id": args[14],
                "last_run_at": None,
                "next_run_at": None,
                "created_at": datetime(2026, 7, 10, 8, 0, 0),
                "updated_at": datetime(2026, 7, 10, 8, 0, 0),
            }
            self.schedules[row["id"]] = row
            self.next_schedule_id += 1
            return row
        if "INSERT INTO agent_task_runs" in query:
            # _create_run INSERT：9 个 args
            # args[0]=schedule_id, ..., args[6]=scheduled_at,
            # args[7]=target_type, args[8]=script_name
            row = {
                "id": self.next_run_id,
                "schedule_id": args[0],
                "session_id": args[1],
                "agent_name": args[2],
                "prompt_snapshot": args[3],
                "status": args[4],
                "trigger_type": args[5],
                "scheduled_at": args[6],
                "target_type": args[7],
                "script_name": args[8],
                "started_at": None,
                "finished_at": None,
                "duration_ms": None,
                "output_text": None,
                "error_message": None,
                "created_at": datetime(2026, 7, 10, 8, 0, 0),
            }
            self.runs[row["id"]] = row
            self.next_run_id += 1
            return row
        if "FROM agent_task_schedules" in query and "WHERE id" in query:
            return self.schedules.get(args[0])
        if "FROM users" in query:
            return {"id": args[0], "username": "admin"}
        if "status = 'running'" in query:
            schedule_id = args[0]
            return next((r for r in self.runs.values() if r["schedule_id"] == schedule_id and r["status"] == "running"), None)
        return None

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))
        if "UPDATE agent_task_runs" in query and "status = $2" in query:
            run_id = args[0]
            run = self.runs[run_id]
            run["status"] = args[1]
            run["session_id"] = args[2] or run.get("session_id")
            run["started_at"] = args[3] or run.get("started_at")
            run["finished_at"] = args[4] or run.get("finished_at")
            run["duration_ms"] = args[5] or run.get("duration_ms")
            run["output_text"] = args[6] or run.get("output_text")
            run["error_message"] = args[7] or run.get("error_message")
            return "UPDATE 1"
        if "UPDATE agent_task_schedules" in query and "next_run_at" in query:
            schedule_id = args[0]
            if schedule_id in self.schedules:
                self.schedules[schedule_id]["next_run_at"] = args[1]
            return "UPDATE 1"
        return "UPDATE 1"


def make_payload(**overrides):
    """构造定时任务请求 payload。"""
    payload = {
        "name": "每日巡检",
        "description": "每天执行一次",
        "agent_name": "map_agent",
        "prompt": "检查今日任务",
        "cron_expression": "0 9 * * *",
        "timezone": "Asia/Shanghai",
        "enabled": True,
        "context_overrides": {},
        "max_concurrent_runs": 1,
    }
    payload.update(overrides)
    return payload


def test_task_scheduler_service_importable():
    """测试 task_scheduler_service 模块可导入。"""
    from app.shared.utils.agent import task_scheduler_service

    assert hasattr(task_scheduler_service, "TaskSchedulerService")


def test_create_schedule_adds_scheduler_job():
    """测试 create_schedule 写入 DB 后同步添加内存调度任务。"""
    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService

    db = FakeDb()
    scheduler = FakeScheduler()
    service = TaskSchedulerService(db=db, agent_config_service=MagicMock(), scheduler=scheduler)

    row = asyncio.run(service.create_schedule(make_payload(), created_by_user_id=1))

    assert row["id"] == 1
    assert "agent-task-schedule-1" in scheduler.jobs
    assert scheduler.jobs["agent-task-schedule-1"]["replace_existing"] is True


def test_set_schedule_disabled_removes_scheduler_job():
    """测试禁用任务时移除内存调度任务。"""
    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService

    db = FakeDb()
    scheduler = FakeScheduler()
    service = TaskSchedulerService(db=db, agent_config_service=MagicMock(), scheduler=scheduler)
    row = asyncio.run(service.create_schedule(make_payload(), created_by_user_id=1))

    updated = asyncio.run(
        service.set_schedule_enabled(
            row["id"], False, OwnershipScope.for_user(1, is_admin=True),
        )
    )

    assert updated["enabled"] is False
    assert "agent-task-schedule-1" not in scheduler.jobs


def test_trigger_schedule_returns_run_id_and_dispatches_background_task(monkeypatch):
    """测试手动触发任务返回 run_id 并调度后台执行。"""
    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService

    db = FakeDb()
    service = TaskSchedulerService(db=db, agent_config_service=MagicMock(), scheduler=FakeScheduler())
    row = asyncio.run(service.create_schedule(make_payload(), created_by_user_id=1))
    service.execute_schedule = AsyncMock()

    result = asyncio.run(
        service.trigger_schedule(row["id"], OwnershipScope.for_user(1, is_admin=True))
    )

    assert result["id"] == 1
    assert result["status"] == "pending"
    service.execute_schedule.assert_called_once()


def test_execute_schedule_success_writes_success_run(monkeypatch):
    """测试任务执行成功时复用 build_agent_instance 并写入 success 状态。"""
    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService

    class FakeAgent:
        async def invoke(self, input_state, context, config):
            return {"messages": [SimpleNamespace(content="执行完成")]} 

    fake_agent_config_service = MagicMock()
    fake_agent_config_service.get_agent_config = AsyncMock(return_value=SimpleNamespace(display_name="地图智能体"))
    fake_agent_config_service.build_agent_instance = AsyncMock(
        return_value=(FakeAgent(), SimpleNamespace(session_id="task-1"), {"messages": []})
    )
    db = FakeDb()
    service = TaskSchedulerService(db=db, agent_config_service=fake_agent_config_service, scheduler=FakeScheduler())
    row = asyncio.run(service.create_schedule(make_payload(), created_by_user_id=1))

    monkeypatch.setattr("app.shared.utils.auth.session_db.SessionDB.add_session", AsyncMock())
    monkeypatch.setattr("app.shared.utils.auth.session_db.SessionDB.update_session_agent", AsyncMock())

    asyncio.run(service.execute_schedule(row["id"], trigger_type="manual"))

    assert any(run["status"] == "success" for run in db.runs.values())
    fake_agent_config_service.build_agent_instance.assert_awaited_once()


def test_execute_schedule_failure_writes_failed_run(monkeypatch):
    """测试任务执行失败时写入 failed 状态和错误信息。"""
    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService

    fake_agent_config_service = MagicMock()
    fake_agent_config_service.get_agent_config = AsyncMock(return_value=SimpleNamespace(display_name="地图智能体"))
    fake_agent_config_service.build_agent_instance = AsyncMock(side_effect=RuntimeError("boom"))
    db = FakeDb()
    service = TaskSchedulerService(db=db, agent_config_service=fake_agent_config_service, scheduler=FakeScheduler())
    row = asyncio.run(service.create_schedule(make_payload(), created_by_user_id=1))

    monkeypatch.setattr("app.shared.utils.auth.session_db.SessionDB.add_session", AsyncMock())
    monkeypatch.setattr("app.shared.utils.auth.session_db.SessionDB.update_session_agent", AsyncMock())

    asyncio.run(service.execute_schedule(row["id"], trigger_type="manual"))

    failed_runs = [run for run in db.runs.values() if run["status"] == "failed"]
    assert failed_runs
    assert "boom" in failed_runs[0]["error_message"]


def test_execute_schedule_skips_when_previous_run_is_running():
    """测试同一任务已有 running 执行时，本次写入 skipped。"""
    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService

    db = FakeDb()
    service = TaskSchedulerService(db=db, agent_config_service=MagicMock(), scheduler=FakeScheduler())
    row = asyncio.run(service.create_schedule(make_payload(), created_by_user_id=1))
    db.runs[1] = {
        "id": 1,
        "schedule_id": row["id"],
        "status": "running",
        "error_message": None,
    }

    asyncio.run(service.execute_schedule(row["id"], trigger_type="scheduled"))

    skipped_runs = [run for run in db.runs.values() if run["status"] == "skipped"]
    assert skipped_runs
    assert "previous run still running" in skipped_runs[0]["error_message"]


# ===== 任务运行日志落盘测试（2026-07-15 新增） =====


def test_run_logger_name_format():
    """测试 _run_logger_name 返回形如 task.run.{id} 的稳定名称。"""
    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService

    assert TaskSchedulerService._run_logger_name(1) == "task.run.1"
    assert TaskSchedulerService._run_logger_name(42) == "task.run.42"


def test_resolve_task_log_path_uses_run_id_and_timestamp(monkeypatch, tmp_path):
    """测试 resolve_task_log_path 生成包含 run_id 与时间戳的路径。"""
    from datetime import datetime

    from app.core.config import paths as paths_module

    # 把 TASK_LOG_DIR 切到 tmp，避免污染真实 data/logs/Task
    monkeypatch.setattr(paths_module, "TASK_LOG_DIR", str(tmp_path))

    target = paths_module.resolve_task_log_path(
        "测试巡检",
        run_id=88,
        when=datetime(2026, 7, 15, 10, 30, 0),
    )
    assert target.parent.parent == tmp_path
    assert target.name == "20260715_103000_88.log"


def test_slugify_task_name_sanitizes_path_traversal():
    """测试 slugify_task_name 拒绝路径分隔符与控制字符。"""
    from app.core.config.paths import slugify_task_name

    assert "/" not in slugify_task_name("../../etc/passwd")
    assert "\\" not in slugify_task_name("..\\windows\\system32")
    assert slugify_task_name("") == "task"
    assert slugify_task_name("///") == "task"
    assert slugify_task_name("测试/巡检:A B") == "测试_巡检_A_B"


def test_install_and_uninstall_run_logger_creates_file(monkeypatch, tmp_path):
    """测试 _install_run_logger 创建 Markdown 文件，_uninstall_run_logger 清空 handlers。"""
    import logging

    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService

    from app.core.config import paths as paths_module

    monkeypatch.setattr(paths_module, "TASK_LOG_DIR", str(tmp_path))

    service = TaskSchedulerService(db=MagicMock(), agent_config_service=MagicMock(), scheduler=FakeScheduler())
    schedule = {
        "id": 1,
        "name": "测试巡检",
        "agent_name": "map_agent",
    }
    run_logger = service._install_run_logger(
        run_id=101,
        schedule=schedule,
        session_id="task-1-abc",
        started_at=datetime(2026, 7, 15, 11, 0, 0),
        trigger_type="manual",
    )

    assert run_logger.name == "task.run.101"
    assert run_logger.propagate is False
    assert run_logger.handlers, "FileHandler 应该已经被挂上"

    run_logger.info("业务日志样例")
    service._uninstall_run_logger(101, run_logger)

    assert run_logger.handlers == [], "uninstall 后必须清空所有 handler，防止泄漏"

    log_path = tmp_path / "测试巡检" / "20260715_110000_101.log"
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "# 定时任务运行记录" in content
    assert "schedule_id: 1" in content
    assert "run_id: 101" in content
    assert "trigger_type: manual" in content
    assert "业务日志样例" in content


def test_execute_schedule_writes_run_log_on_success(monkeypatch, tmp_path):
    """测试 execute_schedule 成功路径会写一份 run 级 Markdown 日志。"""
    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService

    from app.core.config import paths as paths_module

    monkeypatch.setattr(paths_module, "TASK_LOG_DIR", str(tmp_path))

    class FakeAgent:
        async def invoke(self, input_state, context, config):
            return {"messages": [SimpleNamespace(content="执行完成")]}

    fake_agent_config_service = MagicMock()
    fake_agent_config_service.get_agent_config = AsyncMock(return_value=SimpleNamespace(display_name="地图智能体"))
    fake_agent_config_service.build_agent_instance = AsyncMock(
        return_value=(FakeAgent(), SimpleNamespace(session_id="task-1"), {"messages": []})
    )

    db = FakeDb()
    service = TaskSchedulerService(db=db, agent_config_service=fake_agent_config_service, scheduler=FakeScheduler())
    row = asyncio.run(service.create_schedule(make_payload(name="测试巡检"), created_by_user_id=1))

    monkeypatch.setattr("app.shared.utils.auth.session_db.SessionDB.add_session", AsyncMock())
    monkeypatch.setattr("app.shared.utils.auth.session_db.SessionDB.update_session_agent", AsyncMock())

    asyncio.run(service.execute_schedule(row["id"], trigger_type="manual"))

    success_runs = [r for r in db.runs.values() if r["status"] == "success"]
    assert success_runs

    log_files = list((tmp_path / "测试巡检").glob("*.log"))
    assert len(log_files) == 1, f"应该恰好生成 1 个 log 文件，实际: {log_files}"
    content = log_files[0].read_text(encoding="utf-8")
    assert "任务执行成功" in content
    assert f"run_id: {success_runs[0]['id']}" in content


def test_execute_schedule_writes_run_log_on_failure(monkeypatch, tmp_path):
    """测试 execute_schedule 失败路径也会写一份 run 级日志（包含异常）。"""
    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService

    from app.core.config import paths as paths_module

    monkeypatch.setattr(paths_module, "TASK_LOG_DIR", str(tmp_path))

    fake_agent_config_service = MagicMock()
    fake_agent_config_service.get_agent_config = AsyncMock(return_value=SimpleNamespace(display_name="地图智能体"))
    fake_agent_config_service.build_agent_instance = AsyncMock(side_effect=RuntimeError("boom"))

    db = FakeDb()
    service = TaskSchedulerService(db=db, agent_config_service=fake_agent_config_service, scheduler=FakeScheduler())
    row = asyncio.run(service.create_schedule(make_payload(name="测试巡检"), created_by_user_id=1))

    monkeypatch.setattr("app.shared.utils.auth.session_db.SessionDB.add_session", AsyncMock())
    monkeypatch.setattr("app.shared.utils.auth.session_db.SessionDB.update_session_agent", AsyncMock())

    asyncio.run(service.execute_schedule(row["id"], trigger_type="manual"))

    failed_runs = [r for r in db.runs.values() if r["status"] == "failed"]
    assert failed_runs

    log_files = list((tmp_path / "测试巡检").glob("*.log"))
    assert len(log_files) == 1, f"失败时也应该写 1 个 log 文件，实际: {log_files}"
    content = log_files[0].read_text(encoding="utf-8")
    assert "任务执行失败" in content
    assert "boom" in content

    run_logger_name = f"task.run.{failed_runs[0]['id']}"
    import logging
    assert logging.getLogger(run_logger_name).handlers == []


def test_execute_schedule_run_logger_isolated_between_runs(monkeypatch, tmp_path):
    """测试同一个 run_id 在两次 execute_schedule 调用间互不污染 handler。"""
    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService

    from app.core.config import paths as paths_module

    monkeypatch.setattr(paths_module, "TASK_LOG_DIR", str(tmp_path))

    class FakeAgent:
        async def invoke(self, input_state, context, config):
            return {"messages": [SimpleNamespace(content="完成")]}

    fake_agent_config_service = MagicMock()
    fake_agent_config_service.get_agent_config = AsyncMock(return_value=SimpleNamespace(display_name="地图智能体"))
    fake_agent_config_service.build_agent_instance = AsyncMock(
        return_value=(FakeAgent(), SimpleNamespace(session_id="task-1"), {"messages": []})
    )

    db = FakeDb()
    service = TaskSchedulerService(db=db, agent_config_service=fake_agent_config_service, scheduler=FakeScheduler())
    row = asyncio.run(service.create_schedule(make_payload(name="测试巡检"), created_by_user_id=1))

    monkeypatch.setattr("app.shared.utils.auth.session_db.SessionDB.add_session", AsyncMock())
    monkeypatch.setattr("app.shared.utils.auth.session_db.SessionDB.update_session_agent", AsyncMock())

    asyncio.run(service.execute_schedule(row["id"], trigger_type="manual"))
    import logging
    run_logger = logging.getLogger("task.run.1")
    assert run_logger.handlers == [], "第一次 run 后 handler 必须清空"

    asyncio.run(service.execute_schedule(row["id"], trigger_type="manual"))
    run_logger_2 = logging.getLogger("task.run.2")
    assert run_logger_2.handlers == [], "第二次 run 后 handler 必须清空"

    log_files = list((tmp_path / "测试巡检").glob("*.log"))
    assert len(log_files) == 2, f"两次 run 应该生成 2 个文件，实际: {log_files}"


# ===== 脚本任务（target_type='script'）测试 =====


def test_validate_payload_rejects_script_task_without_script_name():
    """测试 target_type='script' 但缺 script_name 时抛 TaskScheduleValidationError。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 未抛出 TaskScheduleValidationError 时失败
    """
    from app.shared.utils.agent.task_scheduler_service import (
        TaskScheduleValidationError,
        TaskSchedulerService,
    )

    service = TaskSchedulerService(
        db=MagicMock(), agent_config_service=MagicMock(), scheduler=FakeScheduler()
    )
    payload = {
        "name": "脚本任务",
        "target_type": "script",
        "cron_expression": "0 9 * * *",
        # 故意缺 script_name
    }
    with pytest.raises(TaskScheduleValidationError) as exc_info:
        service._validate_payload(payload, partial=False)
    assert "script_name is required" in str(exc_info.value)


def test_validate_payload_rejects_agent_task_without_agent_name():
    """测试 target_type='agent' 但缺 agent_name 时抛 TaskScheduleValidationError。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 未抛出 TaskScheduleValidationError 时失败
    """
    from app.shared.utils.agent.task_scheduler_service import (
        TaskScheduleValidationError,
        TaskSchedulerService,
    )

    service = TaskSchedulerService(
        db=MagicMock(), agent_config_service=MagicMock(), scheduler=FakeScheduler()
    )
    payload = {
        "name": "智能体任务",
        "target_type": "agent",
        "prompt": "检查",
        "cron_expression": "0 9 * * *",
        # 故意缺 agent_name
    }
    with pytest.raises(TaskScheduleValidationError) as exc_info:
        service._validate_payload(payload, partial=False)
    assert "agent_name is required" in str(exc_info.value)


def test_validate_payload_rejects_notify_enabled_without_policy_id():
    """notify_enabled=True 但缺 notify_policy_id 时抛 TaskScheduleValidationError。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 未抛出 TaskScheduleValidationError 时失败
    """
    from app.shared.utils.agent.task_scheduler_service import (
        TaskScheduleValidationError,
        TaskSchedulerService,
    )

    service = TaskSchedulerService(
        db=MagicMock(), agent_config_service=MagicMock(), scheduler=FakeScheduler()
    )
    payload = {
        "name": "脚本任务",
        "target_type": "script",
        "script_name": "hello_script",
        "cron_expression": "0 9 * * *",
        "notify_enabled": True,
        # 故意缺 notify_policy_id
    }
    with pytest.raises(TaskScheduleValidationError) as exc_info:
        service._validate_payload(payload, partial=False)
    assert "notify_policy_id is required" in str(exc_info.value)


def test_validate_payload_rejects_non_positive_notify_policy_id():
    """notify_policy_id 必须为正整数。"""
    from app.shared.utils.agent.task_scheduler_service import (
        TaskScheduleValidationError,
        TaskSchedulerService,
    )

    service = TaskSchedulerService(
        db=MagicMock(), agent_config_service=MagicMock(), scheduler=FakeScheduler()
    )
    payload = {
        "name": "脚本任务",
        "target_type": "script",
        "script_name": "hello_script",
        "cron_expression": "0 9 * * *",
        "notify_enabled": True,
        "notify_policy_id": 0,
    }
    with pytest.raises(TaskScheduleValidationError) as exc_info:
        service._validate_payload(payload, partial=False)
    assert "positive integer" in str(exc_info.value)


def test_validate_payload_accepts_notify_enabled_with_policy_id():
    """notify_enabled=True + notify_policy_id 时不应抛异常。"""
    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService

    service = TaskSchedulerService(
        db=MagicMock(), agent_config_service=MagicMock(), scheduler=FakeScheduler()
    )
    payload = {
        "name": "脚本任务",
        "target_type": "script",
        "script_name": "hello_script",
        "cron_expression": "0 9 * * *",
        "notify_enabled": True,
        "notify_policy_id": 7,
    }
    # 不应抛异常
    service._validate_payload(payload, partial=False)


def test_execute_schedule_script_branch_calls_func(monkeypatch, tmp_path):
    """测试 execute_schedule 在 target_type='script' 时调用 registered.func 并写 success run。

    验证：
    - script_discovery_service.get_script 被调用
    - registered.func 被调用一次，参数为 ScriptContext
    - run 状态为 success，output_text 来自 func 返回值
    - 日志文件包含 target_type: script 和 script_name

    参数:
        monkeypatch: pytest fixture，用于替换 TASK_LOG_DIR。
        tmp_path: pytest fixture，隔离日志目录。

    返回值:
        None

    异常:
        AssertionError: 任一断言不满足时失败
    """
    from app.core.config import paths as paths_module
    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService

    monkeypatch.setattr(paths_module, "TASK_LOG_DIR", str(tmp_path))

    # 构造 fake script_discovery_service，返回带 AsyncMock func 的 registered 对象
    fake_registered = SimpleNamespace(
        name="hello_script",
        display_name="示例脚本",
        description="",
        func=AsyncMock(return_value="脚本执行输出"),
        params_schema=None,
        module_path="app.scripts.examples.hello_script",
    )
    fake_script_service = MagicMock()
    fake_script_service.get_script = MagicMock(return_value=fake_registered)

    db = FakeDb()
    service = TaskSchedulerService(
        db=db,
        agent_config_service=MagicMock(),
        scheduler=FakeScheduler(),
        script_discovery_service=fake_script_service,
    )
    # 构造 script 类型 payload 并移除 agent_name/prompt
    payload = make_payload(
        target_type="script",
        script_name="hello_script",
        script_args={"greeting": "hi"},
    )
    payload.pop("agent_name", None)
    payload.pop("prompt", None)
    row = asyncio.run(service.create_schedule(payload, created_by_user_id=1))

    asyncio.run(service.execute_schedule(row["id"], trigger_type="manual"))

    # 验证 func 被调用一次，参数是 ScriptContext
    fake_registered.func.assert_awaited_once()
    context_arg = fake_registered.func.await_args.args[0]
    assert context_arg.script_args == {"greeting": "hi"}
    assert context_arg.schedule_name == "每日巡检"

    # 验证 run 状态为 success
    success_runs = [r for r in db.runs.values() if r["status"] == "success"]
    assert success_runs, "应该有 success 状态的 run"
    assert success_runs[0]["output_text"] == "脚本执行输出"
    assert success_runs[0]["target_type"] == "script"
    assert success_runs[0]["script_name"] == "hello_script"

    # 验证日志文件包含 target_type 和 script_name
    log_files = list((tmp_path / "每日巡检").glob("*.log"))
    assert log_files, "应该生成日志文件"
    content = log_files[0].read_text(encoding="utf-8")
    assert "target_type: script" in content
    assert "script_name: hello_script" in content


def test_execute_schedule_script_branch_injects_api_config_service(monkeypatch, tmp_path):
    """测试 execute_schedule 在 target_type='script' 时把构造函数传入的
    ``api_config_service`` 透传到 ``ScriptContext.api_config_service`` 字段，
    供脚本侧 ``app.scripts.api_check.run_api_checks`` 消费。

    验证：
        * 构造函数 ``api_config_service=stub`` 后，``ScriptContext.api_config_service`` 为同一实例；
        * 未注入时（默认 None），``ScriptContext.api_config_service`` 为 None。

    生产对等初始化点：
        * ``TaskSchedulerService.__init__`` 新增 ``api_config_service`` 入参；
        * ``TaskSchedulerService.execute_schedule`` 构造 ``ScriptContext`` 时透传。
    """
    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService

    monkeypatch.setattr(
        "app.core.config.paths.TASK_LOG_DIR", str(tmp_path), raising=False
    )

    fake_registered = SimpleNamespace(
        name="hello_script",
        display_name="示例脚本",
        description="",
        func=AsyncMock(return_value="ok"),
        params_schema=None,
        module_path="app.scripts.examples.hello_script",
    )
    fake_script_service = MagicMock()
    fake_script_service.get_script = MagicMock(return_value=fake_registered)

    # 场景 1：注入 api_config_service
    fake_api_config_service = MagicMock(name="api_config_service")
    db1 = FakeDb()
    service1 = TaskSchedulerService(
        db=db1,
        agent_config_service=MagicMock(),
        scheduler=FakeScheduler(),
        script_discovery_service=fake_script_service,
        api_config_service=fake_api_config_service,
    )
    payload = make_payload(target_type="script", script_name="hello_script", script_args={})
    payload.pop("agent_name", None)
    payload.pop("prompt", None)
    row = asyncio.run(service1.create_schedule(payload, created_by_user_id=1))
    asyncio.run(service1.execute_schedule(row["id"], trigger_type="manual"))

    ctx = fake_registered.func.await_args.args[0]
    assert ctx.api_config_service is fake_api_config_service

    # 场景 2：未注入时为 None（与 email_config_service 同模式回退）
    fake_registered.func.reset_mock()
    db2 = FakeDb()
    service2 = TaskSchedulerService(
        db=db2,
        agent_config_service=MagicMock(),
        scheduler=FakeScheduler(),
        script_discovery_service=fake_script_service,
    )
    row2 = asyncio.run(service2.create_schedule(payload, created_by_user_id=1))
    asyncio.run(service2.execute_schedule(row2["id"], trigger_type="manual"))
    ctx2 = fake_registered.func.await_args.args[0]
    assert ctx2.api_config_service is None


def test_execute_schedule_script_branch_injects_devops_server_service(monkeypatch, tmp_path):
    """测试 execute_schedule 在 target_type='script' 时把构造函数传入的
    ``devops_server_service`` 透传到 ``ScriptContext.devops_server_service`` 字段，
    供脚本侧 ``app.scripts.server_ops.run_server_ops`` 消费。

    验证：
        * 构造函数 ``devops_server_service=stub`` 后，``ScriptContext.devops_server_service`` 为同一实例；
        * 未注入时（默认 None），``ScriptContext.devops_server_service`` 为 None。

    生产对等初始化点：
        * ``TaskSchedulerService.__init__`` 新增 ``devops_server_service`` 入参；
        * ``TaskSchedulerService.execute_schedule`` 构造 ``ScriptContext`` 时透传。
    """
    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService

    monkeypatch.setattr(
        "app.core.config.paths.TASK_LOG_DIR", str(tmp_path), raising=False
    )

    fake_registered = SimpleNamespace(
        name="hello_script",
        display_name="示例脚本",
        description="",
        func=AsyncMock(return_value="ok"),
        params_schema=None,
        module_path="app.scripts.examples.hello_script",
    )
    fake_script_service = MagicMock()
    fake_script_service.get_script = MagicMock(return_value=fake_registered)

    # 场景 1：注入 devops_server_service
    fake_devops_server_service = MagicMock(name="devops_server_service")
    db1 = FakeDb()
    service1 = TaskSchedulerService(
        db=db1,
        agent_config_service=MagicMock(),
        scheduler=FakeScheduler(),
        script_discovery_service=fake_script_service,
        devops_server_service=fake_devops_server_service,
    )
    payload = make_payload(target_type="script", script_name="hello_script", script_args={})
    payload.pop("agent_name", None)
    payload.pop("prompt", None)
    row = asyncio.run(service1.create_schedule(payload, created_by_user_id=1))
    asyncio.run(service1.execute_schedule(row["id"], trigger_type="manual"))

    ctx = fake_registered.func.await_args.args[0]
    assert ctx.devops_server_service is fake_devops_server_service

    # 场景 2：未注入时为 None（与 api_config_service 同模式回退）
    fake_registered.func.reset_mock()
    db2 = FakeDb()
    service2 = TaskSchedulerService(
        db=db2,
        agent_config_service=MagicMock(),
        scheduler=FakeScheduler(),
        script_discovery_service=fake_script_service,
    )
    row2 = asyncio.run(service2.create_schedule(payload, created_by_user_id=1))
    asyncio.run(service2.execute_schedule(row2["id"], trigger_type="manual"))
    ctx2 = fake_registered.func.await_args.args[0]
    assert ctx2.devops_server_service is None


def test_execute_schedule_script_branch_handles_missing_script(monkeypatch, tmp_path):
    """测试 target_type='script' 但 script 未注册时写 failed run。

    验证：
    - run 状态为 failed
    - error_message 包含 'not registered'

    参数:
        monkeypatch: pytest fixture，用于替换 TASK_LOG_DIR。
        tmp_path: pytest fixture，隔离日志目录。

    返回值:
        None

    异常:
        AssertionError: 任一断言不满足时失败
    """
    from app.core.config import paths as paths_module
    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService

    monkeypatch.setattr(paths_module, "TASK_LOG_DIR", str(tmp_path))

    # script_discovery_service.get_script 返回 None（未注册）
    fake_script_service = MagicMock()
    fake_script_service.get_script = MagicMock(return_value=None)

    db = FakeDb()
    service = TaskSchedulerService(
        db=db,
        agent_config_service=MagicMock(),
        scheduler=FakeScheduler(),
        script_discovery_service=fake_script_service,
    )
    payload = make_payload(
        target_type="script",
        script_name="missing_script",
        script_args={},
    )
    payload.pop("agent_name", None)
    payload.pop("prompt", None)
    row = asyncio.run(service.create_schedule(payload, created_by_user_id=1))

    asyncio.run(service.execute_schedule(row["id"], trigger_type="manual"))

    failed_runs = [r for r in db.runs.values() if r["status"] == "failed"]
    assert failed_runs, "应该有 failed 状态的 run"
    assert "not registered" in failed_runs[0]["error_message"]


def test_install_run_logger_includes_target_type_and_script_name(monkeypatch, tmp_path):
    """测试 _install_run_logger 生成的 Markdown 日志包含 target_type 和 script_name 字段。

    参数:
        monkeypatch: pytest fixture，用于替换 TASK_LOG_DIR。
        tmp_path: pytest fixture，隔离日志目录。

    返回值:
        None

    异常:
        AssertionError: 日志内容缺失 target_type/script_name 时失败
    """
    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService

    from app.core.config import paths as paths_module

    monkeypatch.setattr(paths_module, "TASK_LOG_DIR", str(tmp_path))

    service = TaskSchedulerService(
        db=MagicMock(), agent_config_service=MagicMock(), scheduler=FakeScheduler()
    )
    schedule = {
        "id": 7,
        "name": "脚本巡检",
        "target_type": "script",
        "script_name": "hello_script",
        "agent_name": None,
    }
    run_logger = service._install_run_logger(
        run_id=77,
        schedule=schedule,
        session_id="task-7-abc",
        started_at=datetime(2026, 7, 16, 14, 0, 0),
        trigger_type="scheduled",
    )

    log_files = list((tmp_path / "脚本巡检").glob("*.log"))
    assert log_files, "应该生成日志文件"
    content = log_files[0].read_text(encoding="utf-8")
    assert "target_type: script" in content
    assert "script_name: hello_script" in content
    assert "schedule_id: 7" in content
    assert "run_id: 77" in content

    # 清理 handler，避免泄漏
    service._uninstall_run_logger(77, run_logger)
    assert run_logger.handlers == []


# =============================================================================
# _dispatch_script_email 邮件派发测试
# =============================================================================

def _make_email_service_stub(
    *,
    config=None,
    send_email=None,
    get_policy=None,
    get_active_server_config=None,
):
    """构造 EmailConfigService stub。"""
    svc = MagicMock()
    if config is not None:
        # 0 = no config；非 0 = 有配置（用任意 fake EmailServerConfig）
        svc.get_active_server_config = AsyncMock(
            return_value=config if config is not False else None
        )
    else:
        svc.get_active_server_config = AsyncMock(return_value=None)
    svc.get_policy = AsyncMock(return_value=get_policy or {"recipients": []})
    return svc


def test_dispatch_script_email_renders_template_and_sends():
    """脚本任务完成后应按策略模板渲染并调用 EmailService.send_email。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 渲染或发送流程异常时失败
    """
    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService

    fake_config = MagicMock()
    fake_config.host = "smtp.qq.com"
    fake_config.port = 465
    fake_config.use_ssl = True
    fake_config.username = "u@qq.com"
    fake_config.password = "auth"
    fake_config.sender_name = "ops"

    fake_email_service_instance = MagicMock()
    fake_email_service_instance.send_email = AsyncMock(
        return_value={"success": True, "message_id": "m1"}
    )

    fake_email_config_service = MagicMock()
    fake_email_config_service.get_policy_internal = AsyncMock(
        return_value={
            "id": 7,
            "name": "运维告警",
            "subject_template": "[{{schedule_name}}#{{run_id}}]",
            "body_template": "正文：{{script_output}}",
            "recipients": [
                {"user_id": 1, "email": "u1@example.com"},
                {"user_id": 2, "email": "u2@example.com"},
            ],
        }
    )
    fake_email_config_service.get_active_server_config = AsyncMock(
        return_value=fake_config
    )

    service = TaskSchedulerService(
        db=MagicMock(),
        agent_config_service=MagicMock(),
        scheduler=FakeScheduler(),
        email_config_service=fake_email_config_service,
    )

    # 通过 monkey-patch 让 EmailService(...) 返回我们的 stub
    import app.shared.utils.email.email_service as email_service_module

    original_email_service = email_service_module.EmailService
    email_service_module.EmailService = lambda cfg: fake_email_service_instance
    try:
        started_at = datetime(2026, 7, 17, 9, 0, 0)
        finished_at = datetime(2026, 7, 17, 9, 1, 0)
        run_logger = MagicMock()
        attachments = [r"E:\laboratory\AI\Agents\feature-agent-core-ref\data\attachments\Task\脚本巡检\report.docx"]

        asyncio.run(
            service._dispatch_script_email(
                schedule={"id": 5, "name": "脚本巡检", "notify_policy_id": 7},
                run_id=99,
                script_name="hello_script",
                script_output="巡检通过",
                attachments=attachments,
                started_at=started_at,
                finished_at=finished_at,
                trigger_type="scheduled",
                run_logger=run_logger,
            )
        )
    finally:
        email_service_module.EmailService = original_email_service

    fake_email_service_instance.send_email.assert_awaited_once()
    call_kwargs = fake_email_service_instance.send_email.await_args.kwargs
    assert call_kwargs["to"] == ["u1@example.com", "u2@example.com"]
    assert call_kwargs["subject"] == "[脚本巡检#99]"
    assert call_kwargs["body"] == "正文：巡检通过"
    assert call_kwargs["attachment_paths"] == attachments
    run_logger.info.assert_any_call(
        "脚本任务通知邮件已发送：policy_id=%s recipients=%d attachments=%d",
        7, 2, 1,
    )


def test_dispatch_script_email_uses_policy_name_when_no_subject_template():
    """未配置 subject_template 时使用策略名作为主题。"""
    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService

    fake_config = MagicMock()
    fake_config.host = "smtp.qq.com"
    fake_config.port = 465
    fake_config.use_ssl = True
    fake_config.username = "u@qq.com"
    fake_config.password = "auth"
    fake_config.sender_name = "ops"

    fake_email_service_instance = MagicMock()
    fake_email_service_instance.send_email = AsyncMock(
        return_value={"success": True, "message_id": "m1"}
    )

    fake_email_config_service = MagicMock()
    fake_email_config_service.get_policy_internal = AsyncMock(
        return_value={
            "id": 7,
            "name": "默认主题策略",
            "subject_template": "",
            "body_template": "",
            "recipients": [{"user_id": 1, "email": "u1@example.com"}],
        }
    )
    fake_email_config_service.get_active_server_config = AsyncMock(
        return_value=fake_config
    )

    service = TaskSchedulerService(
        db=MagicMock(),
        agent_config_service=MagicMock(),
        scheduler=FakeScheduler(),
        email_config_service=fake_email_config_service,
    )

    import app.shared.utils.email.email_service as email_service_module

    original = email_service_module.EmailService
    email_service_module.EmailService = lambda cfg: fake_email_service_instance
    try:
        started_at = datetime(2026, 7, 17, 9, 0, 0)
        finished_at = datetime(2026, 7, 17, 9, 1, 0)
        run_logger = MagicMock()

        asyncio.run(
            service._dispatch_script_email(
                schedule={"id": 5, "name": "cron", "notify_policy_id": 7},
                run_id=99,
                script_name="hello_script",
                script_output="脚本返回 body",
                attachments=None,
                started_at=started_at,
                finished_at=finished_at,
                trigger_type="manual",
                run_logger=run_logger,
            )
        )
    finally:
        email_service_module.EmailService = original

    # 验证 send_email 被调用（不应被 fail-soft 静默吞掉）
    assert fake_email_service_instance.send_email.await_count >= 1, (
        f"send_email 应被调用但未调用。warning: "
        f"{[c for c in run_logger.warning.call_args_list]}"
    )
    call_kwargs = fake_email_service_instance.send_email.await_args.kwargs
    assert call_kwargs["subject"] == "默认主题策略"
    # body_template 为空时，body 直接使用 script_output
    assert call_kwargs["body"] == "脚本返回 body"


def test_dispatch_script_email_skips_when_email_service_not_configured():
    """email_config_service 未注入时跳过发邮件（不抛异常）。"""
    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService

    service = TaskSchedulerService(
        db=MagicMock(),
        agent_config_service=MagicMock(),
        scheduler=FakeScheduler(),
        email_config_service=None,
    )

    started_at = datetime(2026, 7, 17, 9, 0, 0)
    finished_at = datetime(2026, 7, 17, 9, 1, 0)
    run_logger = MagicMock()

    # 不抛异常
    asyncio.run(
        service._dispatch_script_email(
            schedule={"id": 5, "name": "x", "notify_policy_id": 1},
            run_id=99,
            script_name="hello_script",
            script_output="body",
            attachments=None,
            started_at=started_at,
            finished_at=finished_at,
            trigger_type="scheduled",
            run_logger=run_logger,
        )
    )

    # 应有 warning 记录未注入
    warning_calls = [
        c for c in run_logger.warning.call_args_list
        if "email_config_service 未注入" in str(c)
    ]
    assert warning_calls, "应记录 email_config_service 未注入的 warning"


def test_dispatch_script_email_skips_when_no_recipients():
    """策略无有效收件人时跳过发邮件。"""
    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService

    fake_email_config_service = MagicMock()
    fake_email_config_service.get_policy_internal = AsyncMock(
        return_value={
            "id": 7,
            "name": "空策略",
            "subject_template": "",
            "body_template": "",
            "recipients": [],
        }
    )

    service = TaskSchedulerService(
        db=MagicMock(),
        agent_config_service=MagicMock(),
        scheduler=FakeScheduler(),
        email_config_service=fake_email_config_service,
    )

    started_at = datetime(2026, 7, 17, 9, 0, 0)
    finished_at = datetime(2026, 7, 17, 9, 1, 0)
    run_logger = MagicMock()

    asyncio.run(
        service._dispatch_script_email(
            schedule={"id": 5, "name": "x", "notify_policy_id": 7},
            run_id=99,
            script_name="hello_script",
            script_output="body",
            attachments=None,
            started_at=started_at,
            finished_at=finished_at,
            trigger_type="scheduled",
            run_logger=run_logger,
        )
    )

    warning_calls = [
        c for c in run_logger.warning.call_args_list
        if "没有有效收件人" in str(c)
    ]
    assert warning_calls


def test_dispatch_script_email_skips_when_smtp_not_configured():
    """未配置启用 SMTP 时跳过发邮件。"""
    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService

    fake_email_config_service = MagicMock()
    fake_email_config_service.get_policy_internal = AsyncMock(
        return_value={
            "id": 7,
            "name": "策略",
            "subject_template": "",
            "body_template": "",
            "recipients": [{"user_id": 1, "email": "u@e.com"}],
        }
    )
    fake_email_config_service.get_active_server_config = AsyncMock(return_value=None)

    service = TaskSchedulerService(
        db=MagicMock(),
        agent_config_service=MagicMock(),
        scheduler=FakeScheduler(),
        email_config_service=fake_email_config_service,
    )

    started_at = datetime(2026, 7, 17, 9, 0, 0)
    finished_at = datetime(2026, 7, 17, 9, 1, 0)
    run_logger = MagicMock()

    asyncio.run(
        service._dispatch_script_email(
            schedule={"id": 5, "name": "x", "notify_policy_id": 7},
            run_id=99,
            script_name="hello_script",
            script_output="body",
            attachments=None,
            started_at=started_at,
            finished_at=finished_at,
            trigger_type="scheduled",
            run_logger=run_logger,
        )
    )

    warning_calls = [
        c for c in run_logger.warning.call_args_list
        if "SMTP" in str(c)
    ]
    assert warning_calls


def test_dispatch_script_email_send_failure_does_not_raise():
    """邮件发送失败不应抛异常（fail-soft）。"""
    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService

    fake_config = MagicMock()
    fake_config.host = "smtp.qq.com"
    fake_config.port = 465
    fake_config.use_ssl = True
    fake_config.username = "u@qq.com"
    fake_config.password = "auth"
    fake_config.sender_name = "ops"

    fake_email_service_instance = MagicMock()
    fake_email_service_instance.send_email = AsyncMock(
        side_effect=Exception("smtp connection refused")
    )

    fake_email_config_service = MagicMock()
    fake_email_config_service.get_policy_internal = AsyncMock(
        return_value={
            "id": 7,
            "name": "策略",
            "subject_template": "",
            "body_template": "",
            "recipients": [{"user_id": 1, "email": "u@e.com"}],
        }
    )
    fake_email_config_service.get_active_server_config = AsyncMock(
        return_value=fake_config
    )

    service = TaskSchedulerService(
        db=MagicMock(),
        agent_config_service=MagicMock(),
        scheduler=FakeScheduler(),
        email_config_service=fake_email_config_service,
    )

    import app.shared.utils.email.email_service as email_service_module

    original = email_service_module.EmailService
    email_service_module.EmailService = lambda cfg: fake_email_service_instance
    try:
        started_at = datetime(2026, 7, 17, 9, 0, 0)
        finished_at = datetime(2026, 7, 17, 9, 1, 0)
        run_logger = MagicMock()

        # 不抛异常
        asyncio.run(
            service._dispatch_script_email(
                schedule={"id": 5, "name": "x", "notify_policy_id": 7},
                run_id=99,
                script_name="hello_script",
                script_output="body",
                attachments=None,
                started_at=started_at,
                finished_at=finished_at,
                trigger_type="scheduled",
                run_logger=run_logger,
            )
        )
    finally:
        email_service_module.EmailService = original

    warning_calls = [
        c for c in run_logger.warning.call_args_list
        if "邮件发送失败" in str(c)
    ]
    assert warning_calls
