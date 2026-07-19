# -*- coding:utf-8 -*-
"""
示例脚本:演示 ``@register_script`` 装饰器用法,并通过 ``WordReportGenerator``
生成 Word 报告作为邮件附件。

通过定时任务调度时:
    * ``context.script_args`` 由 ``agent_task_schedules.script_args`` JSON 注入
    * ``context.log_logger`` 写入 ``data/logs/Task/{slug}/{YYYYMMDD_HHMMSS}_{run_id}.log``
    * 返回 ``(body, attachment_path)`` 元组,``body`` 写入 ``agent_task_runs.output_text``,
      ``attachment_path`` 作为邮件附件绝对路径(须配置 ``notify_enabled=True``
      + ``notify_policy_id`` 才会被消费)。
    * 附件落地路径: ``TASK_ATTACHMENT_DIR/{slug}/{YYYYMMDD_HHMMSS}_{run_id}.docx``
"""
import asyncio
from pathlib import Path

from app.core.config.paths import TASK_ATTACHMENT_DIR, slugify_task_name
from app.scripts.base import ScriptContext
from app.scripts.registry import register_script
from app.shared.utils.report.word import (
    CoverConfig,
    FooterConfig,
    ReportConfig,
    SectionConfig,
    WordReportGenerator,
)


@register_script(
    name="hello_script",
    display_name="示例 Word 附件脚本",
    description="使用通用报告生成器创建 Word 执行报告,并作为通知邮件附件发送。",
    params_schema={
        "type": "object",
        "properties": {
            "greeting": {
                "type": "string",
                "default": "Hello",
                "description": "报告执行结果中的问候语前缀",
            },
        },
    },
)
async def run(context: ScriptContext) -> tuple[str, str]:
    """执行示例脚本,生成 Word 报告并返回 ``(body, attachment_path)``。

    参数:
        context: 脚本运行上下文,含 ``script_args`` / ``log_logger`` / ``started_at`` /
            ``run_id`` / ``schedule_name`` / ``trigger_type`` 等字段。

    返回:
        tuple[str, str]: ``(邮件正文, Word 附件绝对路径)`` 元组。``body`` 写入
        ``agent_task_runs.output_text``,``attachment_path`` 由调度器归一化后作为
        通知邮件的附件。

    异常:
        报告生成或保存过程中产生的异常向上透出,由 ``TaskSchedulerService.execute_schedule``
        将本次执行标记为 ``failed``。
    """
    greeting = context.script_args.get("greeting", "Hello")
    started_at = context.started_at
    timestamp = started_at.strftime("%Y%m%d_%H%M%S")
    slug = slugify_task_name(context.schedule_name)

    message = (
        f"{greeting} from schedule {context.schedule_name} "
        f"(run_id={context.run_id}, trigger={context.trigger_type})"
    )
    started_at_text = started_at.strftime("%Y-%m-%d %H:%M:%S")

    report_data = {
        "任务名称": context.schedule_name,
        "执行记录": str(context.run_id),
        "触发方式": context.trigger_type,
        "开始时间": started_at_text,
        "问候内容": message,
    }

    cover = CoverConfig.from_legacy(
        title="{{任务名称}}定时任务执行报告",
        date_text="生成日期：{{开始时间}}",
        blank_lines_before_title=3,
        blank_lines_after_title=1,
        blank_lines_before_date=2,
    )

    config = ReportConfig(
        cover=cover,
        toc=None,
        sections=[
            SectionConfig(
                section_type="heading",
                content="一、执行结果",
                level=1,
                in_toc=False,
            ),
            SectionConfig(section_type="paragraph", content="{{问候内容}}"),
            SectionConfig(
                section_type="heading",
                content="二、任务信息",
                level=1,
                in_toc=False,
            ),
            SectionConfig(section_type="paragraph", content="任务名称：{{任务名称}}"),
            SectionConfig(section_type="paragraph", content="执行记录：{{执行记录}}"),
            SectionConfig(section_type="paragraph", content="触发方式：{{触发方式}}"),
            SectionConfig(section_type="paragraph", content="开始时间：{{开始时间}}"),
        ],
        data=report_data,
        footer=FooterConfig(format="第{page}页", start_from="content"),
    )

    output_dir = Path(TASK_ATTACHMENT_DIR) / slug
    output_dir.mkdir(parents=True, exist_ok=True)
    attachment_path = output_dir / f"{timestamp}_{context.run_id}.docx"

    generator = WordReportGenerator(config)
    await asyncio.to_thread(generator.generate)
    await asyncio.to_thread(generator.save, str(attachment_path))

    context.log_logger.info(
        "hello_script generated Word attachment: %s", attachment_path
    )

    return message, str(attachment_path.resolve())