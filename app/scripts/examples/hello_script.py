# -*- coding:utf-8 -*-
"""
定时任务脚本开发样板。

本脚本作为 ``app/scripts/`` 下脚本开发的标准样板，演示 ``@register_script``
装饰器的完整能力边界，可直接复制到新文件并修改业务逻辑。

通过定时任务调度时:
    * ``context.script_args`` 由 ``agent_task_schedules.script_args`` JSON 注入。
    * ``context.log_logger`` 写入 ``data/logs/Task/{slug}/{YYYYMMDD_HHMMSS}_{run_id}.log``。
    * 返回 ``str`` 时作为纯文本写入 ``agent_task_runs.output_text``（无附件）。
    * 返回 ``(body, attachments)`` 时,``body`` 写入 ``agent_task_runs.output_text``,
      ``attachments``（``str`` / ``list[str]`` / ``None``）作为通知邮件附件路径
      （须配置 ``notify_enabled=True`` + ``notify_policy_id`` 才会被消费）。
    * 附件建议落地路径: ``TASK_ATTACHMENT_DIR/{slug}/{YYYYMMDD_HHMMSS}_{run_id}.{ext}``。

脚本参数 ``mode`` 控制本次运行行为:
    * ``text``: 仅返回纯文本摘要。
    * ``single``: 生成一个 ``.txt`` 附件并返回 ``(body, [path])``。
    * ``multi``: 生成 ``.txt`` 与 ``.md`` 两个附件并返回 ``(body, [path1, path2])``。
    * ``error``: 抛出 ``ScriptExecutionError``,由调度器将本次 run 标记为 ``failed``。
"""
import asyncio
from pathlib import Path

from app.core.config.paths import TASK_ATTACHMENT_DIR, slugify_task_name
from app.scripts.base import ScriptContext, ScriptExecutionError
from app.scripts.registry import register_script


@register_script(
    name="hello_script",
    display_name="脚本开发样板",
    description="定时任务脚本开发的标准样板，展示参数读取、纯文本/单附件/多附件返回、异常处理与日志记录。",
    params_schema={
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["text", "single", "multi", "error"],
                "default": "text",
                "description": "运行模式：text 纯文本、single 单附件、multi 多附件、error 抛异常",
            },
            "content": {
                "type": "string",
                "default": "定时任务执行成功",
                "description": "输出正文内容",
            },
        },
    },
)
async def run(context: ScriptContext) -> str | tuple[str, list[str]]:
    """执行样板脚本，根据 ``mode`` 返回不同结果。

    参数:
        context: 脚本运行上下文，含 ``script_args`` / ``log_logger`` / ``started_at`` /
            ``run_id`` / ``schedule_name`` / ``trigger_type`` 等字段。

    返回:
        str | tuple[str, list[str]]:
            * ``text`` 模式下返回纯文本摘要；
            * ``single`` / ``multi`` 模式下返回 ``(正文, 附件绝对路径列表)``。

    异常:
        ScriptExecutionError: ``mode=error`` 或 ``mode`` 不合法时抛出，调度器会将其
        消息写入 ``agent_task_runs.error_message`` 并将 run 标记为 ``failed``。
    """
    script_args = context.script_args or {}
    mode = script_args.get("mode", "text")
    content = script_args.get("content", "定时任务执行成功")

    summary = (
        f"{content} | schedule={context.schedule_name} "
        f"(run_id={context.run_id}, trigger={context.trigger_type}, "
        f"started_at={context.started_at.strftime('%Y-%m-%d %H:%M:%S')})"
    )

    context.log_logger.info("hello_script 开始执行，mode=%s", mode)

    if mode == "text":
        context.log_logger.info("返回纯文本结果")
        return summary

    if mode == "single":
        attachment_path = _make_attachment_path(context, "txt")
        await _write_attachment(attachment_path, summary)
        context.log_logger.info("返回单附件: %s", attachment_path)
        return summary, [str(attachment_path.resolve())]

    if mode == "multi":
        path_txt = _make_attachment_path(context, "txt")
        path_md = _make_attachment_path(context, "md")
        await _write_attachment(path_txt, f"附件一\n{summary}")
        await _write_attachment(path_md, f"## 附件二\n\n{summary}")
        context.log_logger.info("返回多附件: %s, %s", path_txt, path_md)
        return summary, [
            str(path_txt.resolve()),
            str(path_md.resolve()),
        ]

    if mode == "error":
        raise ScriptExecutionError(
            "mode=error 被显式请求，用于演示异常向上透出"
        )

    raise ScriptExecutionError(f"不支持的 mode: {mode}")


def _make_attachment_path(context: ScriptContext, ext: str) -> Path:
    """生成附件存储路径。

    路径规则: ``TASK_ATTACHMENT_DIR/{slug}/{YYYYMMDD_HHMMSS}_{run_id}.{ext}``。
    父目录不存在时自动创建。

    参数:
        context: 脚本运行上下文，用于提取任务名、执行记录 ID 与开始时间。
        ext: 附件扩展名（不含点）。

    返回:
        Path: 附件绝对路径（父目录已创建）。
    """
    started_at = context.started_at
    timestamp = started_at.strftime("%Y%m%d_%H%M%S")
    slug = slugify_task_name(context.schedule_name)

    output_dir = Path(TASK_ATTACHMENT_DIR) / slug
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{timestamp}_{context.run_id}.{ext}"


async def _write_attachment(path: Path, content: str) -> None:
    """异步写入附件内容。

    参数:
        path: 附件目标路径。
        content: 写入内容。

    返回:
        None。

    异常:
        写入过程中的 IO 异常向上透出。
    """
    await asyncio.to_thread(path.write_text, content, encoding="utf-8")