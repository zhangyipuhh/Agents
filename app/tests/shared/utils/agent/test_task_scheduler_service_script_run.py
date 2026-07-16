# -*- coding:utf-8 -*-
"""
TaskSchedulerService._create_run 占位写入逻辑测试。

验证 target_type='script' 任务的 _create_run 写入 agent_task_runs 时使用
占位字符串（避免 agent_name / prompt_snapshot NOT NULL 约束被违反）。
"""
import asyncio
from datetime import datetime
from unittest.mock import MagicMock

from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService


class FakeDbCapture:
    """捕获 _create_run 的 fetchrow 调用参数，便于断言占位写入。"""

    def __init__(self):
        self.calls = []

    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        return {
            "id": 1,
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
            "created_at": datetime(2026, 7, 16, 9, 0, 0),
        }


def _make_service(db):
    """构造一个 stub TaskSchedulerService（db 已注入）。"""
    return TaskSchedulerService(
        db=db,
        agent_config_service=MagicMock(),
    )


def test_create_run_script_schedule_writes_placeholder_agent_name():
    """脚本任务（含 script_name）写入占位 agent_name / prompt_snapshot。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 占位字符串或列值与预期不符
    """
    db = FakeDbCapture()
    service = _make_service(db)

    schedule = {
        "id": 2,
        "agent_name": None,
        "prompt": None,
        "target_type": "script",
        "script_name": "hello_script",
    }
    run = asyncio.run(
        service._create_run(schedule, "manual", None, status="pending")
    )

    # 返回的 run row 应包含占位字段
    assert run["agent_name"] == "script:hello_script"
    assert run["prompt_snapshot"] == "[script] hello_script"
    assert run["target_type"] == "script"
    assert run["script_name"] == "hello_script"

    # 写入 DB 时使用的 args 也应是占位值（避免 asyncpg.NotNullViolationError）
    _query, args = db.calls[0]
    assert args[2] == "script:hello_script"
    assert args[3] == "[script] hello_script"
    assert args[7] == "script"
    assert args[8] == "hello_script"


def test_create_run_script_schedule_missing_script_name_uses_unknown_placeholder():
    """脚本任务但 script_name 为 None 时回退到 'unknown' 占位。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 占位字符串不是 'unknown' 后缀
    """
    db = FakeDbCapture()
    service = _make_service(db)

    schedule = {
        "id": 2,
        "agent_name": None,
        "prompt": None,
        "target_type": "script",
        "script_name": None,
    }
    run = asyncio.run(
        service._create_run(schedule, "manual", None, status="pending")
    )

    assert run["agent_name"] == "script:unknown"
    assert run["prompt_snapshot"] == "[script] unknown"
    assert run["script_name"] is None

    _query, args = db.calls[0]
    assert args[2] == "script:unknown"
    assert args[3] == "[script] unknown"
    assert args[8] is None


def test_create_run_agent_schedule_passthrough():
    """agent 任务保持原行为（agent_name / prompt_snapshot 沿用 schedule）。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: agent 任务被错误地覆盖为占位字符串
    """
    db = FakeDbCapture()
    service = _make_service(db)

    schedule = {
        "id": 1,
        "agent_name": "map_agent",
        "prompt": "检查今日任务",
        "target_type": "agent",
        "script_name": None,
    }
    run = asyncio.run(
        service._create_run(schedule, "scheduled", None, status="pending")
    )

    assert run["agent_name"] == "map_agent"
    assert run["prompt_snapshot"] == "检查今日任务"
    assert run["target_type"] == "agent"
    assert run["script_name"] is None

    _query, args = db.calls[0]
    assert args[2] == "map_agent"
    assert args[3] == "检查今日任务"
    assert args[7] == "agent"
    assert args[8] is None


def test_create_run_agent_schedule_none_prompt_uses_empty_string():
    """agent 任务 prompt 为 None 时写入空串（保持历史行为，不引入 None）。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: prompt_snapshot 不是空串
    """
    db = FakeDbCapture()
    service = _make_service(db)

    schedule = {
        "id": 1,
        "agent_name": "map_agent",
        "prompt": None,
        "target_type": "agent",
        "script_name": None,
    }
    run = asyncio.run(
        service._create_run(schedule, "manual", None, status="pending")
    )

    assert run["prompt_snapshot"] == ""
    _query, args = db.calls[0]
    assert args[3] == ""