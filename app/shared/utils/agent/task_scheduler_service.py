#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
智能体定时任务服务模块。

该模块负责管理智能体定时任务的数据库记录、应用内调度器注册、
手动触发和执行历史写入。定时任务执行时复用 AgentConfigService
统一构造入口，确保系统提示词、Skill 绑定和工具绑定与聊天路径一致。
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

from app.core.agent.AgentConfig import ExecuteConfig
from app.core.config.settings import settings
from app.shared.utils.auth.session_db import SessionDB


logger = logging.getLogger(__name__)


class TaskScheduleNotFoundError(Exception):
    """定时任务不存在时抛出。"""


class TaskScheduleValidationError(Exception):
    """定时任务参数校验失败时抛出。"""


class TaskSchedulerService:
    """智能体定时任务服务。

    参数:
        db: 数据库连接池，需支持 fetch / fetchrow / execute 异步方法。
        agent_config_service: AgentConfigService 实例，用于构造智能体。
        scheduler: 可选调度器实例，测试中可注入 FakeScheduler。
        max_concurrency: 全局最大并发执行数；未传入时读取配置。
    """

    def __init__(
        self,
        db: Any,
        agent_config_service: Any,
        scheduler: Optional[Any] = None,
        max_concurrency: Optional[int] = None,
    ) -> None:
        """初始化定时任务服务。

        参数:
            db: 数据库连接池，需支持 fetch / fetchrow / execute。
            agent_config_service: 智能体配置服务。
            scheduler: 应用内调度器，默认创建 AsyncIOScheduler。
            max_concurrency: 全局最大并发数。
        """
        self._db = db
        self._agent_config_service = agent_config_service
        self._scheduler = scheduler or AsyncIOScheduler(timezone=settings.task_scheduler_timezone)
        self._run_semaphore = asyncio.Semaphore(
            max_concurrency or settings.task_scheduler_max_concurrency
        )
        self._started = False

    @staticmethod
    def _job_id(schedule_id: int) -> str:
        """生成 APScheduler job id。

        参数:
            schedule_id: 定时任务 ID。

        返回:
            str: 调度器 job id。
        """
        return f"agent-task-schedule-{schedule_id}"

    @staticmethod
    def _decode_jsonb(value: Any, default: Any) -> Any:
        """防御性反序列化 JSONB 字段。

        参数:
            value: 数据库返回值，可能为 None / str / dict / list。
            default: 解析失败或为空时返回的默认值。

        返回:
            Any: 解析后的 Python 对象。
        """
        if value is None:
            return default
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                logger.warning("Failed to decode task scheduler JSONB value")
                return default
        return value

    @classmethod
    def _decode_schedule_row(cls, row: Any) -> Optional[Dict[str, Any]]:
        """将任务 DB row 转换为 dict。

        参数:
            row: asyncpg Record 或 dict。

        返回:
            Optional[Dict[str, Any]]: 任务字典，row 为空时返回 None。
        """
        if row is None:
            return None
        result = dict(row)
        result["context_overrides"] = cls._decode_jsonb(
            result.get("context_overrides"), {}
        )
        return result

    @staticmethod
    def _decode_run_row(row: Any) -> Optional[Dict[str, Any]]:
        """将执行历史 DB row 转换为 dict。

        参数:
            row: asyncpg Record 或 dict。

        返回:
            Optional[Dict[str, Any]]: 执行历史字典，row 为空时返回 None。
        """
        if row is None:
            return None
        return dict(row)

    @staticmethod
    def _build_trigger(cron_expression: str, timezone: str) -> CronTrigger:
        """构造 CronTrigger 并校验表达式。

        参数:
            cron_expression: 5 段 crontab 表达式。
            timezone: IANA 时区名称。

        返回:
            CronTrigger: APScheduler cron trigger。

        异常:
            TaskScheduleValidationError: cron 或 timezone 非法时抛出。
        """
        try:
            tz = ZoneInfo(timezone)
        except Exception as exc:
            raise TaskScheduleValidationError(f"Invalid timezone: {timezone}") from exc
        try:
            return CronTrigger.from_crontab(cron_expression, timezone=tz)
        except Exception as exc:
            raise TaskScheduleValidationError(f"Invalid cron_expression: {cron_expression}") from exc

    def _calculate_next_run_at(self, schedule: Dict[str, Any]) -> Optional[datetime]:
        """计算任务下一次运行时间。

        参数:
            schedule: 定时任务记录。

        返回:
            Optional[datetime]: 下一次运行时间；无法计算时返回 None。
        """
        trigger = self._build_trigger(schedule["cron_expression"], schedule["timezone"])
        now = datetime.now(ZoneInfo(schedule["timezone"]))
        next_run = trigger.get_next_fire_time(None, now)
        if next_run is None:
            return None
        return next_run.replace(tzinfo=None)

    async def start(self) -> None:
        """启动应用内调度器。

        返回:
            None。
        """
        if self._started:
            return
        if hasattr(self._scheduler, "start"):
            self._scheduler.start()
        self._started = True

    async def shutdown(self) -> None:
        """关闭应用内调度器。

        返回:
            None。
        """
        if hasattr(self._scheduler, "shutdown"):
            self._scheduler.shutdown(wait=False)
        self._started = False

    async def preload_all(self) -> None:
        """从数据库加载启用任务并注册到调度器。

        返回:
            None。
        """
        rows = await self._db.fetch(
            """
            SELECT * FROM agent_task_schedules
            WHERE enabled = TRUE
            ORDER BY id ASC
            """
        )
        for row in rows:
            schedule = self._decode_schedule_row(row)
            if schedule:
                await self._sync_scheduler_job(schedule)

    async def list_schedules(self) -> List[Dict[str, Any]]:
        """列出所有定时任务。

        返回:
            List[Dict[str, Any]]: 定时任务列表。
        """
        rows = await self._db.fetch(
            """
            SELECT * FROM agent_task_schedules
            ORDER BY created_at DESC, id DESC
            """
        )
        return [self._decode_schedule_row(row) for row in rows]

    async def get_schedule(self, schedule_id: int) -> Dict[str, Any]:
        """获取单个定时任务。

        参数:
            schedule_id: 定时任务 ID。

        返回:
            Dict[str, Any]: 定时任务记录。

        异常:
            TaskScheduleNotFoundError: 任务不存在时抛出。
        """
        row = await self._db.fetchrow(
            "SELECT * FROM agent_task_schedules WHERE id = $1",
            schedule_id,
        )
        schedule = self._decode_schedule_row(row)
        if schedule is None:
            raise TaskScheduleNotFoundError(f"Task schedule {schedule_id} not found")
        return schedule

    async def create_schedule(
        self,
        payload: Dict[str, Any],
        created_by_user_id: int,
    ) -> Dict[str, Any]:
        """创建定时任务并同步调度器。

        参数:
            payload: 定时任务字段。
            created_by_user_id: 创建人用户 ID。

        返回:
            Dict[str, Any]: 新建任务记录。

        异常:
            TaskScheduleValidationError: 参数非法时抛出。
        """
        self._validate_payload(payload, partial=False)
        row = await self._db.fetchrow(
            """
            INSERT INTO agent_task_schedules (
                name, description, agent_name, prompt, cron_expression,
                timezone, enabled, created_by_user_id, context_overrides,
                max_concurrent_runs
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10)
            RETURNING *
            """,
            payload["name"],
            payload.get("description"),
            payload["agent_name"],
            payload["prompt"],
            payload["cron_expression"],
            payload.get("timezone") or settings.task_scheduler_timezone,
            payload.get("enabled", True),
            created_by_user_id,
            json.dumps(payload.get("context_overrides") or {}, ensure_ascii=False),
            payload.get("max_concurrent_runs") or 1,
        )
        schedule = self._decode_schedule_row(row)
        next_run_at = self._calculate_next_run_at(schedule)
        schedule["next_run_at"] = next_run_at
        await self._db.execute(
            """
            UPDATE agent_task_schedules
            SET next_run_at = $2, updated_at = CURRENT_TIMESTAMP
            WHERE id = $1
            """,
            schedule["id"],
            next_run_at,
        )
        if schedule.get("enabled"):
            await self._sync_scheduler_job(schedule)
        return schedule

    async def update_schedule(
        self,
        schedule_id: int,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """更新定时任务并同步调度器。

        参数:
            schedule_id: 定时任务 ID。
            payload: 需要更新的字段。

        返回:
            Dict[str, Any]: 更新后的任务记录。

        异常:
            TaskScheduleNotFoundError: 任务不存在时抛出。
            TaskScheduleValidationError: 参数非法时抛出。
        """
        current = await self.get_schedule(schedule_id)
        merged = {**current, **{k: v for k, v in payload.items() if v is not None}}
        self._validate_payload(merged, partial=False)
        next_run_at = self._calculate_next_run_at(merged)
        row = await self._db.fetchrow(
            """
            UPDATE agent_task_schedules
            SET name = $2,
                description = $3,
                agent_name = $4,
                prompt = $5,
                cron_expression = $6,
                timezone = $7,
                enabled = $8,
                context_overrides = $9::jsonb,
                max_concurrent_runs = $10,
                next_run_at = $11,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $1
            RETURNING *
            """,
            schedule_id,
            merged["name"],
            merged.get("description"),
            merged["agent_name"],
            merged["prompt"],
            merged["cron_expression"],
            merged["timezone"],
            merged.get("enabled", True),
            json.dumps(merged.get("context_overrides") or {}, ensure_ascii=False),
            merged.get("max_concurrent_runs") or 1,
            next_run_at,
        )
        schedule = self._decode_schedule_row(row)
        if schedule.get("enabled"):
            await self._sync_scheduler_job(schedule)
        else:
            self._remove_scheduler_job(schedule_id)
        return schedule

    async def set_schedule_enabled(
        self,
        schedule_id: int,
        enabled: bool,
    ) -> Dict[str, Any]:
        """启用或禁用定时任务。

        参数:
            schedule_id: 定时任务 ID。
            enabled: True 启用，False 禁用。

        返回:
            Dict[str, Any]: 更新后的任务记录。

        异常:
            TaskScheduleNotFoundError: 任务不存在时抛出。
        """
        schedule = await self.get_schedule(schedule_id)
        schedule["enabled"] = enabled
        next_run_at = self._calculate_next_run_at(schedule) if enabled else None
        row = await self._db.fetchrow(
            """
            UPDATE agent_task_schedules
            SET enabled = $2, next_run_at = $3, updated_at = CURRENT_TIMESTAMP
            WHERE id = $1
            RETURNING *
            """,
            schedule_id,
            enabled,
            next_run_at,
        )
        updated = self._decode_schedule_row(row)
        if enabled:
            await self._sync_scheduler_job(updated)
        else:
            self._remove_scheduler_job(schedule_id)
        return updated

    async def delete_schedule(self, schedule_id: int) -> None:
        """删除定时任务并移除调度器 job。

        参数:
            schedule_id: 定时任务 ID。

        返回:
            None。

        异常:
            TaskScheduleNotFoundError: 任务不存在时抛出。
        """
        result = await self._db.execute(
            "DELETE FROM agent_task_schedules WHERE id = $1",
            schedule_id,
        )
        self._remove_scheduler_job(schedule_id)
        if isinstance(result, str) and result.endswith("0"):
            raise TaskScheduleNotFoundError(f"Task schedule {schedule_id} not found")

    async def list_runs(
        self,
        schedule_id: int,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """列出任务执行历史。

        参数:
            schedule_id: 定时任务 ID。
            limit: 最大返回条数。

        返回:
            List[Dict[str, Any]]: 执行历史列表。
        """
        rows = await self._db.fetch(
            """
            SELECT * FROM agent_task_runs
            WHERE schedule_id = $1
            ORDER BY created_at DESC, id DESC
            LIMIT $2
            """,
            schedule_id,
            limit,
        )
        return [self._decode_run_row(row) for row in rows]

    async def trigger_schedule(self, schedule_id: int) -> Dict[str, Any]:
        """手动触发定时任务。

        参数:
            schedule_id: 定时任务 ID。

        返回:
            Dict[str, Any]: pending 状态的执行记录。

        异常:
            TaskScheduleNotFoundError: 任务不存在时抛出。
        """
        schedule = await self.get_schedule(schedule_id)
        run = await self._create_run(schedule, "manual", None, status="pending")
        asyncio.create_task(
            self.execute_schedule(
                schedule_id,
                trigger_type="manual",
                scheduled_at=None,
                run_id=run["id"],
            )
        )
        return run

    async def execute_schedule(
        self,
        schedule_id: int,
        trigger_type: str,
        scheduled_at: Optional[datetime] = None,
        run_id: Optional[int] = None,
    ) -> None:
        """执行一次定时任务。

        参数:
            schedule_id: 定时任务 ID。
            trigger_type: 触发方式，manual 或 scheduled。
            scheduled_at: 计划触发时间。
            run_id: 已创建的执行记录 ID；为空时自动创建。

        返回:
            None。
        """
        async with self._run_semaphore:
            schedule = await self.get_schedule(schedule_id)
            if not schedule.get("enabled") and trigger_type == "scheduled":
                if run_id is None:
                    await self._create_run(schedule, trigger_type, scheduled_at, status="skipped")
                else:
                    await self._update_run(
                        run_id,
                        status="skipped",
                        error_message="schedule disabled",
                    )
                return

            running = await self._get_running_run(schedule_id)
            if running and running.get("id") != run_id:
                if run_id is None:
                    run = await self._create_run(schedule, trigger_type, scheduled_at, status="skipped")
                    run_id = run["id"]
                await self._update_run(
                    run_id,
                    status="skipped",
                    error_message="previous run still running",
                )
                return

            if run_id is None:
                run = await self._create_run(schedule, trigger_type, scheduled_at, status="pending")
                run_id = run["id"]

            session_id = f"task-{schedule_id}-{uuid.uuid4().hex}"
            started_at = datetime.now()
            await self._update_run(
                run_id,
                status="running",
                session_id=session_id,
                started_at=started_at,
            )

            try:
                user = await self._get_created_by_user(schedule["created_by_user_id"])
                agent_preview = await self._agent_config_service.get_agent_config(
                    schedule["agent_name"]
                )
                await SessionDB.add_session(session_id, user["id"], user["username"])
                await SessionDB.update_session_agent(
                    session_id,
                    schedule["agent_name"],
                    getattr(agent_preview, "display_name", schedule["agent_name"]),
                )
                agent, context_instance, input_state = await self._agent_config_service.build_agent_instance(
                    agent_name=schedule["agent_name"],
                    session_id=session_id,
                    message=schedule["prompt"],
                    context_overrides=schedule.get("context_overrides") or {},
                )
                result = await agent.invoke(
                    input_state=input_state,
                    context=context_instance,
                    config=ExecuteConfig(
                        configurable={"thread_id": session_id},
                        recursion_limit=100,
                    ),
                )
                output_text = self._extract_output_text(result)
                finished_at = datetime.now()
                await self._update_run(
                    run_id,
                    status="success",
                    session_id=session_id,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=self._duration_ms(started_at, finished_at),
                    output_text=output_text,
                )
                await self._mark_schedule_run_completed(schedule_id, finished_at)
            except Exception as exc:
                logger.exception("Task schedule %s execution failed", schedule_id)
                finished_at = datetime.now()
                await self._update_run(
                    run_id,
                    status="failed",
                    session_id=session_id,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=self._duration_ms(started_at, finished_at),
                    error_message=str(exc),
                )

    def _validate_payload(self, payload: Dict[str, Any], partial: bool) -> None:
        """校验任务 payload。

        参数:
            payload: 待校验字段。
            partial: 是否部分更新。

        返回:
            None。

        异常:
            TaskScheduleValidationError: 参数非法时抛出。
        """
        required = ("name", "agent_name", "prompt", "cron_expression")
        if not partial:
            for field in required:
                if not str(payload.get(field) or "").strip():
                    raise TaskScheduleValidationError(f"{field} is required")
        if payload.get("cron_expression") and payload.get("timezone"):
            self._build_trigger(payload["cron_expression"], payload["timezone"])
        if int(payload.get("max_concurrent_runs") or 1) < 1:
            raise TaskScheduleValidationError("max_concurrent_runs must be greater than 0")

    async def _sync_scheduler_job(self, schedule: Dict[str, Any]) -> None:
        """同步单条 enabled 任务到调度器。

        参数:
            schedule: 定时任务记录。

        返回:
            None。
        """
        trigger = self._build_trigger(schedule["cron_expression"], schedule["timezone"])
        self._scheduler.add_job(
            self.execute_schedule,
            trigger=trigger,
            id=self._job_id(schedule["id"]),
            args=[schedule["id"], "scheduled"],
            replace_existing=True,
            coalesce=True,
            misfire_grace_time=None,
            max_instances=1,
        )

    def _remove_scheduler_job(self, schedule_id: int) -> None:
        """从调度器移除任务。

        参数:
            schedule_id: 定时任务 ID。

        返回:
            None。
        """
        job_id = self._job_id(schedule_id)
        if hasattr(self._scheduler, "get_job") and self._scheduler.get_job(job_id) is None:
            return
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            logger.debug("Scheduler job %s already removed", job_id)

    async def _create_run(
        self,
        schedule: Dict[str, Any],
        trigger_type: str,
        scheduled_at: Optional[datetime],
        status: str,
    ) -> Dict[str, Any]:
        """创建执行记录。

        参数:
            schedule: 定时任务记录。
            trigger_type: 触发方式。
            scheduled_at: 计划触发时间。
            status: 初始状态。

        返回:
            Dict[str, Any]: 执行记录。
        """
        row = await self._db.fetchrow(
            """
            INSERT INTO agent_task_runs (
                schedule_id, session_id, agent_name, prompt_snapshot,
                status, trigger_type, scheduled_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            schedule["id"],
            None,
            schedule["agent_name"],
            schedule["prompt"],
            status,
            trigger_type,
            scheduled_at,
        )
        return self._decode_run_row(row)

    async def _update_run(
        self,
        run_id: int,
        status: str,
        session_id: Optional[str] = None,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
        duration_ms: Optional[int] = None,
        output_text: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """更新执行记录状态。

        参数:
            run_id: 执行记录 ID。
            status: 新状态。
            session_id: 本次执行创建的会话 ID。
            started_at: 开始时间。
            finished_at: 结束时间。
            duration_ms: 执行耗时毫秒。
            output_text: 执行输出文本。
            error_message: 错误信息。

        返回:
            None。
        """
        await self._db.execute(
            """
            UPDATE agent_task_runs
            SET status = $2,
                session_id = COALESCE($3, session_id),
                started_at = COALESCE($4, started_at),
                finished_at = COALESCE($5, finished_at),
                duration_ms = COALESCE($6, duration_ms),
                output_text = COALESCE($7, output_text),
                error_message = COALESCE($8, error_message)
            WHERE id = $1
            """,
            run_id,
            status,
            session_id,
            started_at,
            finished_at,
            duration_ms,
            output_text,
            error_message,
        )

    async def _get_running_run(self, schedule_id: int) -> Optional[Dict[str, Any]]:
        """查询同一任务是否已有 running 执行。

        参数:
            schedule_id: 定时任务 ID。

        返回:
            Optional[Dict[str, Any]]: 正在执行的记录；不存在时返回 None。
        """
        row = await self._db.fetchrow(
            """
            SELECT * FROM agent_task_runs
            WHERE schedule_id = $1 AND status = 'running'
            ORDER BY id DESC
            LIMIT 1
            """,
            schedule_id,
        )
        return self._decode_run_row(row)

    async def _get_created_by_user(self, user_id: int) -> Dict[str, Any]:
        """查询任务创建人用户信息。

        参数:
            user_id: 用户 ID。

        返回:
            Dict[str, Any]: 至少包含 id 与 username。
        """
        row = await self._db.fetchrow(
            "SELECT id, username FROM users WHERE id = $1",
            user_id,
        )
        if row:
            return dict(row)
        return {"id": user_id, "username": "system"}

    async def _mark_schedule_run_completed(
        self,
        schedule_id: int,
        finished_at: datetime,
    ) -> None:
        """更新任务最近运行时间和下一次运行时间。

        参数:
            schedule_id: 定时任务 ID。
            finished_at: 本次结束时间。

        返回:
            None。
        """
        schedule = await self.get_schedule(schedule_id)
        next_run_at = self._calculate_next_run_at(schedule)
        await self._db.execute(
            """
            UPDATE agent_task_schedules
            SET last_run_at = $2,
                next_run_at = $3,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $1
            """,
            schedule_id,
            finished_at,
            next_run_at,
        )

    @staticmethod
    def _extract_output_text(result: Any) -> str:
        """从 Agent 执行结果中提取最终文本。

        参数:
            result: Agent.invoke 返回值。

        返回:
            str: 最后一条消息文本。
        """
        if isinstance(result, dict):
            messages = result.get("messages") or []
            if messages:
                last_message = messages[-1]
                content = getattr(last_message, "content", None)
                if content is not None:
                    return str(content)
                return str(last_message)
        return str(result or "")

    @staticmethod
    def _duration_ms(started_at: datetime, finished_at: datetime) -> int:
        """计算执行耗时毫秒。

        参数:
            started_at: 开始时间。
            finished_at: 结束时间。

        返回:
            int: 毫秒耗时。
        """
        return int((finished_at - started_at).total_seconds() * 1000)
