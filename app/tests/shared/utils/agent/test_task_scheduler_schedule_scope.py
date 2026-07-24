# -*- coding:utf-8 -*-
"""
TaskSchedulerService 按用户隔离（OwnershipScope）测试模块。

验证:
- list_schedules 按 scope 过滤;admin 见全部,普通用户仅见自己创建
- get_schedule / update_schedule / delete_schedule / set_schedule_enabled /
  trigger_schedule / list_runs 对缺失/越权统一抛 TaskScheduleNotFoundError(404)
- get_schedule_internal 不做归属校验(供 execute_schedule 等运行时使用)
- _assert_api_list_access 校验每个 api 节点归属;非 admin 引用他人节点被拒;
  admin 可跨用户引用;节点不存在/类型非 api 同样被拒
- create_schedule / update_schedule 集成(api_list 与 notify_policy_id 跨用户拒绝)
"""
import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.shared.utils.agent.task_scheduler_service import (
    TaskScheduleNotFoundError,
    TaskScheduleValidationError,
    TaskSchedulerService,
)
from app.shared.utils.auth.ownership_scope import OwnershipScope


# ==== FakeDb / FakeScheduler =================================================

class FakeDb:
    """最小化 asyncpg 替身:仅支持 agent_task_schedules / agent_task_runs CRUD。"""

    def __init__(self):
        self.schedules = {}
        self.runs = []
        self.next_schedule_id = 1
        self.next_run_id = 1

    async def fetch(self, query, *args):
        if "FROM agent_task_schedules" in query:
            rows = list(self.schedules.values())
            # service 拼接 WHERE created_by_user_id = $N (来自 scope.sql_filter);
            # 这里粗略解析: 若 query 含 WHERE created_by_user_id = $1 则按
            # args[0] 过滤。
            if "WHERE created_by_user_id" in query:
                owner_id = args[0] if args else None
                rows = [r for r in rows if r.get("created_by_user_id") == owner_id]
            return rows
        if "FROM agent_task_runs" in query:
            schedule_id = args[0]
            limit = args[1]
            rows = [r for r in self.runs if r["schedule_id"] == schedule_id]
            rows.sort(key=lambda r: r["id"], reverse=True)
            return rows[:limit]
        return []

    async def fetchrow(self, query, *args):
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
                "target_type": args[10],
                "script_name": args[11],
                "script_args": args[12],
                "notify_enabled": args[13],
                "notify_policy_id": args[14],
                "last_run_at": None,
                "next_run_at": None,
                "created_at": datetime(2026, 7, 24, 10, 0, 0),
                "updated_at": datetime(2026, 7, 24, 10, 0, 0),
            }
            self.schedules[row["id"]] = row
            self.next_schedule_id += 1
            return row
        if "UPDATE agent_task_schedules" in query:
            schedule_id = args[0]
            row = self.schedules.get(schedule_id)
            if row is None:
                return None
            # 全量 UPDATE 顺序:name, description, agent_name, prompt,
            # cron_expression, timezone, enabled, context_overrides,
            # max_concurrent_runs, target_type, script_name, script_args,
            # notify_enabled, notify_policy_id, next_run_at
            (
                row["name"], row["description"], row["agent_name"], row["prompt"],
                row["cron_expression"], row["timezone"], row["enabled"],
                row["context_overrides"], row["max_concurrent_runs"],
                row["target_type"], row["script_name"], row["script_args"],
                row["notify_enabled"], row["notify_policy_id"],
                row["next_run_at"],
            ) = args[1:]
            row["updated_at"] = datetime(2026, 7, 24, 11, 0, 0)
            return row
        if "SELECT * FROM agent_task_schedules" in query:
            schedule_id = args[0]
            return self.schedules.get(schedule_id)
        if "INSERT INTO agent_task_runs" in query:
            row = {
                "id": self.next_run_id,
                "schedule_id": args[0],
                "agent_name": args[1],
                "prompt_snapshot": args[2],
                "status": args[3],
                "trigger_type": args[4],
                "target_type": args[5],
                "script_name": args[6],
                "scheduled_at": args[7],
                "started_at": args[8],
                "finished_at": args[9],
                "duration_ms": args[10],
                "output_text": args[11],
                "error_message": args[12],
                "created_at": datetime(2026, 7, 24, 12, 0, 0),
            }
            self.runs.append(row)
            self.next_run_id += 1
            return row
        return None

    async def execute(self, query, *args):
        if "DELETE FROM agent_task_schedules" in query:
            schedule_id = args[0]
            if schedule_id in self.schedules:
                del self.schedules[schedule_id]
                return "DELETE 1"
            return "DELETE 0"
        if "UPDATE agent_task_schedules SET enabled" in query:
            schedule_id = args[0]
            row = self.schedules.get(schedule_id)
            if row is None:
                return "UPDATE 0"
            row["enabled"] = args[1]
            row["next_run_at"] = args[2]
            return "UPDATE 1"
        return "OK"


class FakeScheduler:
    """最小化 APScheduler 替身。"""

    def __init__(self):
        self.jobs = {}

    def add_job(self, func, trigger, id, **kwargs):
        self.jobs[id] = {"func": func, "trigger": trigger, "kwargs": kwargs}

    def remove_job(self, job_id):
        self.jobs.pop(job_id, None)

    def start(self):
        pass


def _make_service(db=None):
    """构造 TaskSchedulerService 实例(注入必要 stub)。"""
    db = db if db is not None else FakeDb()
    scheduler = FakeScheduler()
    service = TaskSchedulerService(
        db=db, agent_config_service=MagicMock(), scheduler=scheduler,
    )
    return service, db, scheduler


def _make_payload(target_type="agent", **overrides):
    """构造合法 schedule payload。"""
    payload = {
        "name": "巡检任务",
        "description": "demo",
        "cron_expression": "0 * * * *",
        "timezone": "Asia/Shanghai",
        "enabled": True,
        "max_concurrent_runs": 1,
        "context_overrides": {},
        "target_type": target_type,
    }
    if target_type == "agent":
        payload.update({"agent_name": "demo_agent", "prompt": "hello"})
    else:
        payload.update({
            "script_name": "demo_script",
            "script_args": {},
            "notify_enabled": False,
        })
    payload.update(overrides)
    return payload


# ==== list_schedules =========================================================

def test_list_schedules_admin_sees_all():
    """admin list_schedules 返回所有 schedule。"""
    service, db, _ = _make_service()
    db.schedules[1] = {"id": 1, "name": "a", "created_by_user_id": 42,
                       "agent_name": "x", "prompt": "p",
                       "cron_expression": "0 * * * *", "timezone": "Asia/Shanghai",
                       "enabled": True, "target_type": "agent",
                       "script_name": None, "script_args": "{}",
                       "notify_enabled": False, "notify_policy_id": None,
                       "context_overrides": "{}", "max_concurrent_runs": 1,
                       "last_run_at": None, "next_run_at": None}
    db.schedules[2] = {"id": 2, "name": "b", "created_by_user_id": 99,
                       "agent_name": "x", "prompt": "p",
                       "cron_expression": "0 * * * *", "timezone": "Asia/Shanghai",
                       "enabled": True, "target_type": "agent",
                       "script_name": None, "script_args": "{}",
                       "notify_enabled": False, "notify_policy_id": None,
                       "context_overrides": "{}", "max_concurrent_runs": 1,
                       "last_run_at": None, "next_run_at": None}
    admin_scope = OwnershipScope.for_user(1, is_admin=True)

    result = asyncio.run(service.list_schedules(admin_scope))

    ids = {r["id"] for r in result}
    assert ids == {1, 2}


def test_list_schedules_user_sees_only_own():
    """普通用户 list_schedules 仅返回自己创建的 schedule。"""
    service, db, _ = _make_service()
    db.schedules[1] = {"id": 1, "name": "a", "created_by_user_id": 42,
                       "agent_name": "x", "prompt": "p",
                       "cron_expression": "0 * * * *", "timezone": "Asia/Shanghai",
                       "enabled": True, "target_type": "agent",
                       "script_name": None, "script_args": "{}",
                       "notify_enabled": False, "notify_policy_id": None,
                       "context_overrides": "{}", "max_concurrent_runs": 1,
                       "last_run_at": None, "next_run_at": None}
    db.schedules[2] = {"id": 2, "name": "b", "created_by_user_id": 99,
                       "agent_name": "x", "prompt": "p",
                       "cron_expression": "0 * * * *", "timezone": "Asia/Shanghai",
                       "enabled": True, "target_type": "agent",
                       "script_name": None, "script_args": "{}",
                       "notify_enabled": False, "notify_policy_id": None,
                       "context_overrides": "{}", "max_concurrent_runs": 1,
                       "last_run_at": None, "next_run_at": None}
    user_scope = OwnershipScope.for_user(42, is_admin=False)

    result = asyncio.run(service.list_schedules(user_scope))

    ids = {r["id"] for r in result}
    assert ids == {1}


# ==== get_schedule / get_schedule_internal ===================================

def test_get_schedule_cross_user_raises_not_found():
    """普通用户访问他人 schedule 抛 TaskScheduleNotFoundError。"""
    service, db, _ = _make_service()
    row = asyncio.run(
        service.create_schedule(_make_payload(), created_by_user_id=99)
    )
    user_scope = OwnershipScope.for_user(42, is_admin=False)

    with pytest.raises(TaskScheduleNotFoundError):
        asyncio.run(service.get_schedule(row["id"], user_scope))


def test_get_schedule_admin_passes():
    """admin 访问他人 schedule 正常返回。"""
    service, db, _ = _make_service()
    row = asyncio.run(
        service.create_schedule(_make_payload(), created_by_user_id=99)
    )
    admin_scope = OwnershipScope.for_user(1, is_admin=True)

    fetched = asyncio.run(service.get_schedule(row["id"], admin_scope))

    assert fetched["id"] == row["id"]


def test_get_schedule_missing_raises_not_found():
    """get_schedule 缺失 schedule 抛 NotFound。"""
    service, _, _ = _make_service()
    admin_scope = OwnershipScope.for_user(1, is_admin=True)

    with pytest.raises(TaskScheduleNotFoundError):
        asyncio.run(service.get_schedule(9999, admin_scope))


def test_get_schedule_internal_skips_scope_check():
    """get_schedule_internal 不做归属校验,直接读取(供 execute_schedule 等运行时)。"""
    service, _, _ = _make_service()
    row = asyncio.run(
        service.create_schedule(_make_payload(), created_by_user_id=99)
    )

    # 即便 scope 不匹配也能读到
    fetched = asyncio.run(
        service.get_schedule_internal(row["id"])
    )

    assert fetched["id"] == row["id"]


# ==== update_schedule / delete_schedule / set_schedule_enabled ===============

def test_update_schedule_cross_user_raises_not_found():
    """普通用户更新他人 schedule 抛 NotFound,不进入 DB UPDATE。"""
    service, db, _ = _make_service()
    row = asyncio.run(
        service.create_schedule(_make_payload(), created_by_user_id=99)
    )
    user_scope = OwnershipScope.for_user(42, is_admin=False)

    with pytest.raises(TaskScheduleNotFoundError):
        asyncio.run(
            service.update_schedule(
                row["id"], {"description": "越权"}, user_scope,
            )
        )


def test_delete_schedule_cross_user_raises_not_found():
    """普通用户删除他人 schedule 抛 NotFound。"""
    service, db, _ = _make_service()
    row = asyncio.run(
        service.create_schedule(_make_payload(), created_by_user_id=99)
    )
    user_scope = OwnershipScope.for_user(42, is_admin=False)

    with pytest.raises(TaskScheduleNotFoundError):
        asyncio.run(service.delete_schedule(row["id"], user_scope))

    assert row["id"] in db.schedules  # 未被删


def test_set_schedule_enabled_cross_user_raises_not_found():
    """普通用户启停他人 schedule 抛 NotFound。"""
    service, db, _ = _make_service()
    row = asyncio.run(
        service.create_schedule(_make_payload(), created_by_user_id=99)
    )
    user_scope = OwnershipScope.for_user(42, is_admin=False)

    with pytest.raises(TaskScheduleNotFoundError):
        asyncio.run(
            service.set_schedule_enabled(row["id"], False, user_scope)
        )

    assert db.schedules[row["id"]]["enabled"] is True


# ==== trigger_schedule / list_runs ==========================================

def test_trigger_schedule_cross_user_raises_not_found():
    """普通用户触发他人 schedule 抛 NotFound。"""
    service, db, _ = _make_service()
    row = asyncio.run(
        service.create_schedule(_make_payload(), created_by_user_id=99)
    )
    user_scope = OwnershipScope.for_user(42, is_admin=False)

    with pytest.raises(TaskScheduleNotFoundError):
        asyncio.run(service.trigger_schedule(row["id"], user_scope))


def test_list_runs_cross_user_raises_not_found():
    """普通用户查他人 schedule runs 抛 NotFound(由缺失→404 而非空列表)。"""
    service, db, _ = _make_service()
    row = asyncio.run(
        service.create_schedule(_make_payload(), created_by_user_id=99)
    )
    user_scope = OwnershipScope.for_user(42, is_admin=False)

    with pytest.raises(TaskScheduleNotFoundError):
        asyncio.run(service.list_runs(row["id"], user_scope))


# ==== _assert_api_list_access ===============================================

class _StubApiConfigService:
    """最小化 ApiConfigService 替身,仅支持 get_node_internal。"""

    def __init__(self, nodes_by_id):
        self._nodes = nodes_by_id

    def get_node_internal(self, node_id):
        return self._nodes.get(node_id)


def _build_service_with_api_stub(api_nodes):
    """构造带 ApiConfigService stub 的 TaskSchedulerService。"""
    service, _, _ = _make_service()
    service._api_config_service = _StubApiConfigService(api_nodes)
    return service


@pytest.mark.asyncio
async def test_assert_api_list_access_owner_passes():
    """自己的 api 节点:校验通过。"""
    api_nodes = {
        10: {"id": 10, "node_type": "api", "created_by_user_id": 42},
        11: {"id": 11, "node_type": "api", "created_by_user_id": 42},
    }
    service = _build_service_with_api_stub(api_nodes)

    await service._assert_api_list_access(
        {"api_list": ["10", "11"]}, 42, False,
    )


@pytest.mark.asyncio
async def test_assert_api_list_access_other_user_rejected():
    """非 admin 引用他人 api 节点抛 TaskScheduleValidationError。"""
    api_nodes = {
        10: {"id": 10, "node_type": "api", "created_by_user_id": 99},  # 他人
    }
    service = _build_service_with_api_stub(api_nodes)

    with pytest.raises(TaskScheduleValidationError, match="不属于当前用户"):
        await service._assert_api_list_access(
            {"api_list": ["10"]}, 42, False,
        )


@pytest.mark.asyncio
async def test_assert_api_list_access_admin_bypasses():
    """admin 可跨用户引用任意 api 节点。"""
    api_nodes = {
        10: {"id": 10, "node_type": "api", "created_by_user_id": 99},
    }
    service = _build_service_with_api_stub(api_nodes)

    await service._assert_api_list_access(
        {"api_list": ["10"]}, 1, True,
    )


@pytest.mark.asyncio
async def test_assert_api_list_access_missing_node_rejected():
    """不存在的 api 节点 id 抛 TaskScheduleValidationError。"""
    api_nodes = {}  # 空
    service = _build_service_with_api_stub(api_nodes)

    with pytest.raises(TaskScheduleValidationError, match="不存在的接口节点"):
        await service._assert_api_list_access(
            {"api_list": ["999"]}, 42, False,
        )


@pytest.mark.asyncio
async def test_assert_api_list_access_folder_node_rejected():
    """node_type != api 视为不存在的接口节点。"""
    api_nodes = {
        10: {"id": 10, "node_type": "folder", "created_by_user_id": 42},
    }
    service = _build_service_with_api_stub(api_nodes)

    with pytest.raises(TaskScheduleValidationError, match="不存在的接口节点"):
        await service._assert_api_list_access(
            {"api_list": ["10"]}, 42, False,
        )


@pytest.mark.asyncio
async def test_assert_api_list_access_invalid_type_rejected():
    """api_list 元素非字符串抛 TaskScheduleValidationError。"""
    service = _build_service_with_api_stub({})

    with pytest.raises(TaskScheduleValidationError):
        await service._assert_api_list_access(
            {"api_list": [10, "11"]}, 42, False,
        )


@pytest.mark.asyncio
async def test_assert_api_list_access_non_integer_string_rejected():
    """api_list 元素非整数字符串抛 TaskScheduleValidationError。"""
    service = _build_service_with_api_stub({})

    with pytest.raises(TaskScheduleValidationError):
        await service._assert_api_list_access(
            {"api_list": ["abc"]}, 42, False,
        )


@pytest.mark.asyncio
async def test_assert_api_list_access_empty_list_passes():
    """api_list 为空列表视为不指定,校验通过。"""
    service = _build_service_with_api_stub({})

    await service._assert_api_list_access(
        {"api_list": []}, 42, False,
    )


@pytest.mark.asyncio
async def test_assert_api_list_access_no_api_list_key_passes():
    """script_args 不含 api_list key 视为不指定,校验通过。"""
    service = _build_service_with_api_stub({})

    await service._assert_api_list_access(
        {"mode": "text"}, 42, False,
    )


@pytest.mark.asyncio
async def test_assert_api_list_access_api_service_none_skips():
    """api_config_service 未注入时跳过校验并 warning(与 notify_policy 模式一致)。"""
    service, _, _ = _make_service()
    # 默认 _api_config_service 是 MagicMock,改为 None
    service._api_config_service = None

    await service._assert_api_list_access(
        {"api_list": ["10"]}, 42, False,
    )  # 不抛错


# ==== create_schedule / update_schedule api_list 集成 =======================

@pytest.mark.asyncio
async def test_create_schedule_api_list_cross_user_rejected():
    """create_schedule 在 _assert_api_list_access 阶段拒绝跨用户引用。"""
    service = _build_service_with_api_stub({
        10: {"id": 10, "node_type": "api", "created_by_user_id": 999},  # 他人
    })
    payload = _make_payload(
        target_type="script",
        script_args={"api_list": ["10"]},
    )

    with pytest.raises(TaskScheduleValidationError, match="不属于当前用户"):
        await service.create_schedule(
            payload=payload,
            created_by_user_id=42,
            is_admin=False,
        )


@pytest.mark.asyncio
async def test_update_schedule_api_list_cross_user_rejected():
    """update_schedule 在 _assert_api_list_access 阶段拒绝跨用户引用。"""
    service = _build_service_with_api_stub({
        10: {"id": 10, "node_type": "api", "created_by_user_id": 999},  # 他人
    })
    row = await service.create_schedule(
        payload=_make_payload(target_type="script"),
        created_by_user_id=42,
        is_admin=False,
    )

    with pytest.raises(TaskScheduleValidationError, match="不属于当前用户"):
        await service.update_schedule(
            schedule_id=row["id"],
            payload={"script_args": {"api_list": ["10"]}},
            scope=OwnershipScope.for_user(42, is_admin=False),
        )