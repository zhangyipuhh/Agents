# -*- coding:utf-8 -*-
"""
脚本调度系统基础契约。

定义 ``ScriptContext``、``RegisteredScript``、``ScriptExecutionError`` 与
``ScriptResult`` 类型，为 ``@register_script`` 装饰器与 ``TaskSchedulerService``
脚本执行分支提供统一契约。

契约要点：
    * 脚本入口签名：``async def run(context: ScriptContext) -> ScriptResult``
    * 返回 ``str`` 时，作为 ``output_text`` 写入 ``agent_task_runs``（无附件）。
    * 返回 ``(body, attachments)`` 元组时，``body`` 作为 ``output_text``，
      ``attachments``（``str`` / ``list[str]`` / ``None``）作为邮件附件路径。
    * ``context.log_logger`` 是 ``TaskSchedulerService._install_run_logger`` 注入的
      run 级专用 logger，写入 ``data/logs/Task/{slug}/{YYYYMMDD_HHMMSS}_{run_id}.log``
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Union

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


# 脚本返回值类型：str（向后兼容）或 (body, attachments) 元组。
# attachments 支持 str（单条绝对路径）/ list[str]（多条）/ None（无附件）。
ScriptResult = Union[str, Tuple[str, Optional[Union[str, List[str]]]]]


def normalize_script_result(result: Any) -> Tuple[str, Optional[List[str]]]:
    """把脚本返回值归一化为 ``(body, attachments_list)``。

    契约：
        * ``str`` → ``(str, None)``：旧契约，输出文本无附件。
        * ``(body, None)`` / ``(body, [])`` → ``(body, None)``：新契约无附件。
        * ``(body, str)`` → ``(body, [str])``：单条附件。
        * ``(body, list[str])`` → ``(body, list[str])``：多条附件。

    参数:
        result: 脚本函数返回值。

    返回:
        Tuple[str, Optional[List[str]]]: ``(邮件正文, 附件绝对路径列表或 None)``。

    异常:
        ScriptExecutionError: 返回值既不是 ``str`` 也不是长度为 2 且首项为 ``str``
            的元组时抛出。
    """
    if isinstance(result, str):
        return result, None
    if isinstance(result, tuple) and len(result) == 2:
        body, attachments = result
        if not isinstance(body, str):
            raise ScriptExecutionError(
                f"ScriptResult tuple[0] must be str, got {type(body).__name__}"
            )
        if attachments is None:
            return body, None
        if isinstance(attachments, str):
            return body, [attachments]
        if isinstance(attachments, list):
            for item in attachments:
                if not isinstance(item, str):
                    raise ScriptExecutionError(
                        "ScriptResult tuple[1] must be str or list[str], "
                        f"got list element {type(item).__name__}"
                    )
            # 空列表归一化为 None（与「无附件」语义一致）
            return body, (attachments if attachments else None)
        raise ScriptExecutionError(
            "ScriptResult tuple[1] must be str or list[str], "
            f"got {type(attachments).__name__}"
        )
    raise ScriptExecutionError(
        f"ScriptResult must be str or (str, attachments) tuple, "
        f"got {type(result).__name__}"
    )


@dataclass
class RegisteredScript:
    """已注册脚本的元数据与函数引用。

    由 ``@register_script`` 装饰器构造，存入 ``app.scripts.registry`` 全局注册表。

    Attributes:
        name: 脚本唯一标识，用于 ``agent_task_schedules.script_name`` 引用。
        display_name: 前端展示名称。
        description: 脚本描述（前端表格展示）。
        func: 异步函数引用，签名为
            ``async def run(context: ScriptContext) -> ScriptResult``。
        params_schema: ``script_args`` 的 JSON schema，用于前端表单生成与校验。
        module_path: 脚本所在模块路径（如 ``app.scripts.examples.hello_script``），
            仅用于展示，不参与反射加载。
    """

    name: str
    display_name: str
    description: str
    func: Callable[[ScriptContext], Awaitable[ScriptResult]] = field(repr=False)
    params_schema: Dict[str, Any] = field(default_factory=dict)
    module_path: str = ""
