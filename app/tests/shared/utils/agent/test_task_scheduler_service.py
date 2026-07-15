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
                    "next_run_at": args[10],
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
                "last_run_at": None,
                "next_run_at": None,
                "created_at": datetime(2026, 7, 10, 8, 0, 0),
                "updated_at": datetime(2026, 7, 10, 8, 0, 0),
            }
            self.schedules[row["id"]] = row
            self.next_schedule_id += 1
            return row
        if "INSERT INTO agent_task_runs" in query:
            row = {
                "id": self.next_run_id,
                "schedule_id": args[0],
                "session_id": args[1],
                "agent_name": args[2],
                "prompt_snapshot": args[3],
                "status": args[4],
                "trigger_type": args[5],
                "scheduled_at": args[6],
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

    updated = asyncio.run(service.set_schedule_enabled(row["id"], False))

    assert updated["enabled"] is False
    assert "agent-task-schedule-1" not in scheduler.jobs


def test_trigger_schedule_returns_run_id_and_dispatches_background_task(monkeypatch):
    """测试手动触发任务返回 run_id 并调度后台执行。"""
    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService

    db = FakeDb()
    service = TaskSchedulerService(db=db, agent_config_service=MagicMock(), scheduler=FakeScheduler())
    row = asyncio.run(service.create_schedule(make_payload(), created_by_user_id=1))
    service.execute_schedule = AsyncMock()

    result = asyncio.run(service.trigger_schedule(row["id"]))

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
