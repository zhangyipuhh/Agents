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

脚本参数 ``server_list`` 为字符串数组，每个元素是目标服务器的 ``business_name``
业务名（前端通过 ``x-value-field=business_name`` 唯一约束选择）;脚本仅演示
对该参数的读取、类型校验与输出追加,不读取连接配置、不执行 SSH、不做去重,
具体运维动作由真实脚本按需实现。空数组与缺失键行为等价,均不修改既有
摘要文本。

脚本参数 ``api_list`` 为字符串数组，每个元素是「API接口配置」树的 api 节点
id 字符串形式（前端通过 ``x-value-field=id`` 选择）;脚本通过共享检查器
``app.scripts.api_check.run_api_checks`` 逐个执行接口健康检查（Mock 断言
由接口配置决定，每次检查自动落库 ``api_check_runs``），拿到统一的
``ApiCheckReport`` 结构后把 ``summary_line()`` 追加到摘要、``to_markdown()``
写入 ``multi`` 模式的 ``.md`` 附件。空数组与缺失键行为等价，均不执行检查。
"""
import asyncio
from pathlib import Path

from app.core.config.paths import TASK_ATTACHMENT_DIR, slugify_task_name
from app.scripts.api_check import run_api_checks
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
            "server_list": {
                "type": "array",
                "title": "服务器列表",
                "description": "选择本次运维任务需要处理的已入库服务器",
                "items": {"type": "string"},
                "uniqueItems": True,
                "default": [],
                "x-control": "server-multiselect",
                "x-source": "devops-servers",
                "x-value-field": "business_name",
            },
            "api_list": {
                "type": "array",
                "title": "接口列表",
                "description": "选择本次任务需要健康检查的已配置接口（Mock 断言由接口配置决定）",
                "items": {"type": "string"},
                "uniqueItems": True,
                "default": [],
                "x-control": "api-multiselect",
                "x-source": "api-configs",
                "x-value-field": "id",
            },
        },
    },
)
async def run(context: ScriptContext) -> str | tuple[str, list[str]]:
    """执行样板脚本，根据 ``mode`` 返回不同结果。

    ``server_list`` 元素为业务名 (``business_name``),脚本仅演示对其读取、类型
    校验与摘要追加,不会读取连接配置或执行 SSH；空数组或缺失键保持既有摘要。
    ``api_list`` 元素为 API 节点 id 字符串,脚本通过 ``run_api_checks`` 执行
    接口健康检查（Mock 断言）并把统一摘要追加到正文；空数组或缺失键不执行
    检查；``api_config_service`` 不可用且 ``api_list`` 非空时抛
    ``ScriptExecutionError``。

    参数:
        context: 脚本运行上下文,含 ``script_args`` / ``log_logger`` / ``started_at`` /
            ``run_id`` / ``schedule_name`` / ``trigger_type`` / ``api_config_service``
            等字段。

    返回:
        str | tuple[str, list[str]]:
            * ``text`` 模式下返回纯文本摘要；
            * ``single`` / ``multi`` 模式下返回 ``(正文, 附件绝对路径列表)``。
            ``server_list`` / ``api_list`` 非空时其结果会追加到正文摘要末尾；
            均为空数组或缺失时不修改摘要文本。

    异常:
        ScriptExecutionError:
            * ``server_list`` 不是列表、元素不是非空字符串时抛出,错误消息包含
              ``server_list`` 字段名,便于调度器日志定位；
            * ``api_list`` 不是列表、元素非法或 ``api_config_service`` 不可用时
              抛出,错误消息包含 ``api_list`` 字段名；
            * ``mode=error`` 或 ``mode`` 不合法时抛出,调度器会将其消息写入
              ``agent_task_runs.error_message`` 并将 run 标记为 ``failed``。
    """
    script_args = context.script_args or {}
    mode = script_args.get("mode", "text")
    content = script_args.get("content", "定时任务执行成功")
    server_list = _resolve_server_list(script_args)
    api_report = await run_api_checks(context)

    summary = (
        f"{content} | schedule={context.schedule_name} "
        f"(run_id={context.run_id}, trigger={context.trigger_type}, "
        f"started_at={context.started_at.strftime('%Y-%m-%d %H:%M:%S')})"
    )
    summary = _append_server_list_to_summary(summary, server_list, context.log_logger)
    summary = _append_api_check_to_summary(summary, api_report, context.log_logger)

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
        md_content = f"## 附件二\n\n{summary}"
        if api_report.items:
            md_content += f"\n\n## 接口健康检查\n\n{api_report.to_markdown()}"
        await _write_attachment(path_txt, f"附件一\n{summary}")
        await _write_attachment(path_md, md_content)
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


def _resolve_server_list(script_args: dict) -> list[str]:
    """读取并校验 ``server_list`` 脚本参数。

    缺失键时按空列表处理；非列表或元素不是非空字符串时抛
    ``ScriptExecutionError``。脚本不去重，前端已按 schema 的 ``uniqueItems``
    约束保证唯一性，此处只做类型边界校验。

    参数:
        script_args: 脚本运行参数字典。

    返回:
        list[str]: 通过校验的业务名列表（缺失或空数组时返回 ``[]``）。

    异常:
        ScriptExecutionError: ``server_list`` 类型不合法时抛出，错误消息包含
        字段名 ``server_list``。
    """
    raw_value = script_args.get("server_list", [])
    if raw_value is None:
        raw_value = []

    if not isinstance(raw_value, list):
        raise ScriptExecutionError(
            "server_list 必须为字符串数组（业务名列表），"
            f"实际收到类型: {type(raw_value).__name__}"
        )

    validated: list[str] = []
    for index, item in enumerate(raw_value):
        if not isinstance(item, str):
            raise ScriptExecutionError(
                f"server_list[{index}] 必须为非空字符串，业务名列表中包含"
                f"非字符串元素: {type(item).__name__}"
            )
        if not item:
            raise ScriptExecutionError(
                f"server_list[{index}] 不能为空字符串，业务名必须非空"
            )
        validated.append(item)

    return validated


def _append_server_list_to_summary(
    summary: str,
    server_list: list[str],
    log_logger,
) -> str:
    """将 ``server_list`` 业务名追加到既有摘要末尾。

    空数组时原样返回 ``summary``,不追加空文案,保持与旧实现完全一致；非空
    时同时通过 ``log_logger.info`` 记录业务名列表,便于运维回溯。

    参数:
        summary: 既有摘要文本。
        server_list: 已校验的业务名列表。
        log_logger: ``ScriptContext.log_logger`` 提供的日志记录器。

    返回:
        str: 追加 ``server_list`` 后的摘要文本；空数组时返回原 ``summary``。
    """
    if not server_list:
        return summary

    suffix = " | server_list=" + ",".join(server_list)
    log_logger.info("server_list=%s", ",".join(server_list))
    return summary + suffix


def _append_api_check_to_summary(summary: str, api_report, log_logger) -> str:
    """把 ``api_list`` 健康检查统一摘要追加到既有摘要末尾。

    ``api_report.items`` 为空（未声明 / 空数组）时原样返回 ``summary``；
    非空时追加 ``ApiCheckReport.summary_line()`` 并通过 ``log_logger.info``
    记录逐项结果，便于运维回溯。

    参数:
        summary: 既有摘要文本。
        api_report: ``app.scripts.api_check.ApiCheckReport`` 统一检查结果。
        log_logger: ``ScriptContext.log_logger`` 提供的日志记录器。

    返回:
        str: 追加 ``api_check`` 摘要后的文本；无检查项时返回原 ``summary``。
    """
    if not api_report.items:
        return summary

    line = api_report.summary_line()
    log_logger.info("%s", line)
    for item in api_report.items:
        log_logger.info(
            "api_check id=%s name=%s passed=%s http_status=%s duration_ms=%s error=%s",
            item.node_id,
            item.name,
            item.check_passed,
            item.http_status,
            item.duration_ms,
            item.error_message,
        )
    return summary + " | " + line


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