# -*- coding:utf-8 -*-
"""
示例脚本：演示 ``@register_script`` 装饰器用法。

通过定时任务调度时：
    * ``context.script_args`` 由 ``agent_task_schedules.script_args`` JSON 注入
    * ``context.log_logger`` 写入 ``data/logs/Task/{slug}/{YYYYMMDD_HHMMSS}_{run_id}.log``
    * 返回字符串作为 ``output_text`` 写入 ``agent_task_runs``
"""
from app.scripts.base import ScriptContext
from app.scripts.registry import register_script


@register_script(
    name="hello_script",
    display_name="示例问候脚本",
    description="每分钟输出一条问候日志，用于验证脚本调度链路。",
    params_schema={
        "type": "object",
        "properties": {
            "greeting": {
                "type": "string",
                "default": "Hello",
                "description": "问候语前缀",
            },
        },
    },
)
async def run(context: ScriptContext) -> str:
    """执行示例脚本。

    参数:
        context: 脚本运行上下文，含 ``script_args`` / ``log_logger`` 等字段。

    返回:
        str: 拼接后的问候字符串，作为 ``output_text`` 写入执行历史。

    异常:
        无：本示例不会主动抛出异常。
    """
    greeting = context.script_args.get("greeting", "Hello")
    message = (
        f"{greeting} from schedule {context.schedule_name} "
        f"(run_id={context.run_id}, trigger={context.trigger_type})"
    )
    context.log_logger.info("hello_script executed: %s", message)
    return message
