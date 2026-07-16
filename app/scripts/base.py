# -*- coding:utf-8 -*-
"""
脚本调度系统基础契约。

定义 ``ScriptContext``、``RegisteredScript`` 与 ``ScriptExecutionError``，
为 ``@register_script`` 装饰器与 ``TaskSchedulerService`` 脚本执行分支提供统一契约。

契约要点：
    * 脚本入口签名：``async def run(context: ScriptContext) -> str``
    * 返回字符串作为 ``output_text`` 写入 ``agent_task_runs``
    * ``context.log_logger`` 是 ``TaskSchedulerService._install_run_logger`` 注入的
      run 级专用 logger，写入 ``data/logs/Task/{slug}/{YYYYMMDD_HHMMSS}_{run_id}.log``
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict

from pydantic import BaseModel, ConfigDict, Field


class ScriptExecutionError(Exception):
    """脚本执行过程中抛出的业务异常。

    ``TaskSchedulerService.execute_schedule`` 捕获后会把 ``str(exc)`` 写入
    ``agent_task_runs.error_message``。
    """


class ScriptContext(BaseModel):
    """脚本运行时上下文。

    由 ``TaskSchedulerService.execute_schedule`` 在脚本分支中构造并注入到
    ``RegisteredScript.func`` 调用。

    Attributes:
        schedule_id: 定时任务 ID（``agent_task_schedules.id``）。
        run_id: 执行记录 ID（``agent_task_runs.id``）。
        session_id: 调度器生成的关联会话 ID，形如 ``task-{schedule_id}-{uuid}``。
            注意：脚本任务不创建 SessionDB 记录，此 ID 仅用于日志关联与排查。
        schedule_name: 任务名称，用于日志展示与日志文件路径生成。
        script_args: 用户配置的脚本参数（来自 ``agent_task_schedules.script_args``）。
        log_logger: run 级专用 logger，写入 ``data/logs/Task/{slug}/`` 下的 Markdown
            日志文件。脚本可通过 ``context.log_logger.info(...)`` 追加执行日志。
        started_at: 本次执行开始时间。
        trigger_type: 触发方式，``scheduled`` 或 ``manual``。
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    schedule_id: int = Field(..., description="定时任务 ID")
    run_id: int = Field(..., description="执行记录 ID")
    session_id: str = Field(..., description="调度器生成的关联会话 ID")
    schedule_name: str = Field(..., description="任务名称")
    script_args: Dict[str, Any] = Field(
        default_factory=dict, description="用户配置的脚本参数"
    )
    log_logger: logging.Logger = Field(
        ..., description="run 级专用 logger"
    )
    started_at: datetime = Field(..., description="本次执行开始时间")
    trigger_type: str = Field(..., description="触发方式：scheduled / manual")


@dataclass
class RegisteredScript:
    """已注册脚本的元数据与函数引用。

    由 ``@register_script`` 装饰器构造，存入 ``app.scripts.registry`` 全局注册表。

    Attributes:
        name: 脚本唯一标识，用于 ``agent_task_schedules.script_name`` 引用。
        display_name: 前端展示名称。
        description: 脚本描述（前端表格展示）。
        func: 异步函数引用，签名为 ``async def run(context: ScriptContext) -> str``。
        params_schema: ``script_args`` 的 JSON schema，用于前端表单生成与校验。
        module_path: 脚本所在模块路径（如 ``app.scripts.examples.hello_script``），
            仅用于展示，不参与反射加载。
    """

    name: str
    display_name: str
    description: str
    func: Callable[[ScriptContext], Awaitable[str]] = field(repr=False)
    params_schema: Dict[str, Any] = field(default_factory=dict)
    module_path: str = ""
