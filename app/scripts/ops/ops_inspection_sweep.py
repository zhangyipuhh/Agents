# -*- coding:utf-8 -*-
"""
运维巡检扫描脚本（生产运维正式脚本）。

与 ``app.scripts.examples.hello_script``（脚本开发样板,演示 4 种 mode 与附件生成）
的区别:
    * 面向运维日常巡检,无 ``mode`` 切换,固定返回纯文本摘要;
    * 复用 ``app.scripts.server_ops.run_server_ops`` 与
      ``app.scripts.api_check.run_api_checks`` 的全量报告结构,确保 SSH 失败 /
      解析失败 / 评估失败等异常分级与全项目保持一致;
    * 对每台服务器按 ``inspection_fields`` 规则逐字段打印「解析值 + 阈值 + 状态」
      比对明细,便于事后审计追溯;
    * 对每个 API 接口打印断言明细,便于排查断言失败原因;
    * 所有日志统一通过 ``context.log_logger.info(...)`` 写入 ``data/logs/Task/{slug}/``。

脚本参数契约:
    * ``server_list``: 字符串数组,元素为 ``devops_servers.business_name``,
      由前端 ``x-control=server-multiselect`` / ``x-source=devops-servers`` /
      ``x-value-field=business_name`` 唯一约束选择。
    * ``api_list``: 字符串数组,元素为 ``api_config_nodes.id`` 字符串形式,
      由前端 ``x-control=api-multiselect`` / ``x-source=api-configs`` /
      ``x-value-field=id`` 唯一约束选择。

契约边界:
    * 命令来源是 ``devops_servers.inspection_script`` 字段,不在脚本入参中重复指定;
    * ``server_list`` / ``api_list`` 空数组或缺失键时,对应模块不执行,日志仅输出
      已有摘要,行为与 ``hello_script`` 对齐;
    * ``server_list`` 非空但 ``devops_server_service`` 不可用时,或 ``api_list``
      非空但 ``api_config_service`` 不可用时,由 ``run_server_ops`` /
      ``run_api_checks`` 抛 ``ScriptExecutionError`` 向上透出。

使用示例::

    # 1) 巡检 2 台服务器 + 1 个接口
    @register_script(name="ops_inspection_sweep", ...)
    async def run(context):
        # server_list=["业务A-生产", "业务B-生产"], api_list=["12"]
        ...

    # 2) 仅巡检服务器,不检查接口(api_list 缺失 = [])
    # 3) 仅检查接口,不巡检服务器(server_list 缺失 = [])
    # 4) 仅打印「无操作」摘要(server_list 与 api_list 均缺失)
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from app.core.config.paths import resolve_task_attachment_path
from app.scripts.api_check import run_api_checks
from app.scripts.base import ScriptContext, ScriptExecutionError, ScriptResult
from app.scripts.ops.ops_report import (
    build_ops_email_body,
    build_ops_report_config,
    compute_ops_alerts,
    compute_ops_summary,
    resolve_server_ip_map,
)
from app.scripts.registry import register_script
from app.scripts.server_ops import run_server_ops
from app.shared.utils.report.word.generator import WordReportGenerator


# 服务器级巡检状态中文映射(与 server_ops._INSPECTION_STATUS_ZH 对齐)。
_INSPECTION_STATUS_ZH = {
    "pass": "通过",
    "warn": "告警",
    "crit": "严重",
    "unassessed": "未评估",
    "skipped": "未执行",
}


# 单字段状态中文映射(与 server_ops._INSPECTION_STATUS_ZH 对齐)。
_FIELD_STATUS_ZH = {
    "pass": "PASS",
    "warn": "WARN",
    "crit": "CRIT",
    "unassessed": "未评估",
}


@register_script(
    name="ops_inspection_sweep",
    display_name="运维巡检扫描",
    description=(
        "对 server_list 中每台服务器执行预存的 inspection_script, 按 inspection_fields "
        "逐字段打印解析值与阈值比对明细; 对 api_list 中每个接口执行健康检查并打印 "
        "断言明细; 全量结果落到日志, 返回纯文本摘要。"
    ),
    params_schema={
        "type": "object",
        "properties": {
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
                "description": "选择本次任务需要健康检查的已配置接口(Mock 断言由接口配置决定)",
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
async def run(context: ScriptContext) -> "ScriptResult":
    """执行运维巡检扫描,生成 docx 报告并返回 ``(邮件正文, [附件路径])``。

    流程:
        1. 调用 ``run_server_ops(context)`` 与 ``run_api_checks(context)``;
        2. 计算综述统计与关键告警;
        3. 反查每台服务器 IP;
        4. 构建 :class:`ReportConfig` 并异步生成 docx;
        5. 构造邮件正文;
        6. 返回 ``(body, [docx_path])``;docx 生成失败时退化为 ``body``。

    参数:
        context: 脚本运行上下文,需携带 ``devops_server_service`` /
            ``api_config_service`` / ``script_args`` / ``log_logger`` / ``schedule_name``
            等字段。

    返回:
        ScriptResult: ``(body, [docx_path])`` 元组,docx 文件实际落盘;
            docx 生成失败时退化为 ``body`` 字符串(无附件)。

    异常:
        ScriptExecutionError: ``server_list`` 非空但 ``devops_server_service`` 不可用,
        或 ``api_list`` 非空但 ``api_config_service`` 不可用时,由 ``run_server_ops`` /
        ``run_api_checks`` 向上抛出; ``server_list`` / ``api_list`` 类型不合法由
        ``resolve_server_list`` / ``resolve_api_list`` 抛出。
    """
    script_args = context.script_args or {}
    started_str = context.started_at.strftime("%Y-%m-%d %H:%M:%S")

    base_summary = (
        f"ops_inspection_sweep | schedule={context.schedule_name} "
        f"(run_id={context.run_id}, trigger={context.trigger_type}, "
        f"started_at={started_str})"
    )

    context.log_logger.info(
        "ops_inspection_sweep 开始执行，server_list=%s, api_list=%s",
        script_args.get("server_list", []),
        script_args.get("api_list", []),
    )
    server_ops_report = await run_server_ops(context)
    _log_server_ops_detail(server_ops_report, context.log_logger)

    api_report = await run_api_checks(context)
    _log_api_check_detail(api_report, context.log_logger)

    # 综述 / 告警 / IP
    summary = compute_ops_summary(server_ops_report, api_report)
    alerts = compute_ops_alerts(server_ops_report, api_report)
    ip_map = resolve_server_ip_map(
        getattr(context, "devops_server_service", None),
        server_ops_report,
    )

    # docx
    docx_path = _resolve_attachment_path(
        context.schedule_name, context.run_id, context.started_at,
    )
    try:
        report_config = build_ops_report_config(
            summary=summary,
            alerts=alerts,
            server_report=server_ops_report,
            api_report=api_report,
            ip_map=ip_map,
            schedule_name=context.schedule_name,
            started_at=context.started_at,
        )
        await asyncio.to_thread(_generate_docx_report, report_config, docx_path)
        context.log_logger.info(
            "ops_inspection_sweep docx 生成成功 path=%s size=%d",
            docx_path, docx_path.stat().st_size,
        )
    except Exception as exc:
        context.log_logger.exception("ops_inspection_sweep docx 生成失败: %s", exc)
        docx_path = None

    # 邮件正文
    finished_at = datetime.now()
    body = build_ops_email_body(
        summary=summary,
        alerts=alerts,
        schedule_name=context.schedule_name,
        schedule_id=context.schedule_id,
        run_id=context.run_id,
        trigger_type=context.trigger_type,
        started_at=context.started_at,
        finished_at=finished_at,
        report_file_name=docx_path.name if docx_path else None,
    )

    # 兼容旧契约:body 末尾追加旧摘要便于数据库 output_text 可读
    summary_text = _append_server_ops_to_summary(base_summary, server_ops_report)
    summary_text = _append_api_check_to_summary(summary_text, api_report)
    body = body + "\n" + summary_text

    context.log_logger.info("ops_inspection_sweep 执行完成")
    if docx_path:
        return (body, [str(docx_path)])
    return body


def _append_server_ops_to_summary(summary: str, report) -> str:
    """把 ``ServerOpsReport`` 摘要追加到既有摘要末尾。

    ``report.items`` 为空(未声明 / 空数组 / 全部 skipped 等)时原样返回 ``summary``;
    非空时追加 ``summary_line()``。

    参数:
        summary: 既有摘要文本。
        report: ``app.scripts.server_ops.ServerOpsReport`` 统一巡检结果。

    返回:
        str: 追加 ``server_ops`` 摘要后的文本;无巡检项时返回原 ``summary``。
    """
    if not report.items:
        return summary
    return summary + " | " + report.summary_line()


def _append_api_check_to_summary(summary: str, report) -> str:
    """把 ``ApiCheckReport`` 摘要追加到既有摘要末尾。

    ``report.items`` 为空(未声明 / 空数组)时原样返回 ``summary``;
    非空时追加 ``summary_line()``。

    参数:
        summary: 既有摘要文本。
        report: ``app.scripts.api_check.ApiCheckReport`` 统一检查结果。

    返回:
        str: 追加 ``api_check`` 摘要后的文本;无检查项时返回原 ``summary``。
    """
    if not report.items:
        return summary
    return summary + " | " + report.summary_line()


def _log_server_ops_detail(report, log_logger) -> None:
    """逐服务器打印 ``inspection_fields`` 逐字段比对明细。

    对 ``report.items`` 中的每台服务器,依次记录:
        * 业务名 + IP/parser + inspection_fields 数量;
        * 解析后的 ``parsed_values``(JSON 字符串);
        * 每条字段的 ``(key / name_zh / unit / value / direction / warn / crit /
          status / message)`` 比对结果(含 ``disks`` 数组展开后的逐条 ``mount``
          上下文);
        * 整台服务器的 ``inspection_status`` + SSH 执行 ``success/exit_code/duration_ms``。

    skipped 项仅打印「业务名 + 跳过原因」,不打印字段明细。

    参数:
        report: ``ServerOpsReport``。
        log_logger: ``ScriptContext.log_logger`` 注入的 run 级 logger。

    返回:
        None。
    """
    if not report.items:
        log_logger.info("server_ops: 无巡检项(server_list 为空 / 缺失)")
        return

    log_logger.info("server_ops: 共 %d 台", report.total)

    for item in report.items:
        if item.skipped:
            log_logger.info(
                "server biz=%s SKIPPED reason=%s",
                item.business_name,
                item.error_message or item.inspection_error or "未配置巡检脚本",
            )
            continue

        # SSH 失败:打印错误摘要(不打印 parsed_values / field_results)
        if not item.success:
            log_logger.info(
                "server biz=%s FAIL exit=%s duration=%sms parser=%s error=%s inspection=%s",
                item.business_name,
                item.exit_code,
                item.duration_ms,
                item.inspection_parser,
                item.error_message or item.stderr or "远端执行失败",
                _INSPECTION_STATUS_ZH.get(item.inspection_status, item.inspection_status),
            )
            if item.inspection_error:
                log_logger.info(
                    "server biz=%s inspection_error=%s",
                    item.business_name,
                    item.inspection_error,
                )
            continue

        # SSH 成功 + 有/无字段规则:打印 parsed_values + 逐字段比对
        log_logger.info(
            "server biz=%s OK exit=%s duration=%sms parser=%s inspection=%s fields=%d",
            item.business_name,
            item.exit_code,
            item.duration_ms,
            item.inspection_parser,
            _INSPECTION_STATUS_ZH.get(item.inspection_status, item.inspection_status),
            len(item.field_results),
        )
        log_logger.info(
            "server biz=%s parsed_values=%s",
            item.business_name,
            _safe_json_dumps(item.parsed_values),
        )

        if not item.field_results:
            log_logger.info(
                "server biz=%s 无可评估字段(unassessed)",
                item.business_name,
            )
            continue

        for index, field_result in enumerate(item.field_results):
            log_logger.info(
                "server biz=%s field[%d] %s",
                item.business_name,
                index,
                _format_field_log(field_result),
            )


def _log_api_check_detail(report, log_logger) -> None:
    """逐接口打印断言明细。

    对 ``report.items`` 中的每个接口,依次记录:
        * 节点 id + 名称 + 路径;
        * ``http_status`` + ``duration_ms`` + ``check_passed``;
        * 每条断言的 ``(type / passed / detail)``。

    节点缺失(``check_passed=None``)或执行异常时仅打印错误摘要。

    参数:
        report: ``ApiCheckReport``。
        log_logger: ``ScriptContext.log_logger`` 注入的 run 级 logger。

    返回:
        None。
    """
    if not report.items:
        log_logger.info("api_check: 无检查项(api_list 为空 / 缺失)")
        return

    log_logger.info("api_check: 共 %d 个", report.total)

    for item in report.items:
        if item.check_passed is None:
            log_logger.info(
                "api id=%s name=%s MISSING reason=%s",
                item.node_id,
                item.name or f"id={item.node_id}",
                item.error_message or "接口节点不存在或已被删除",
            )
            continue

        log_logger.info(
            "api id=%s name=%s path=%s http=%s duration=%sms passed=%s",
            item.node_id,
            item.name or f"id={item.node_id}",
            item.path,
            item.http_status,
            item.duration_ms,
            item.check_passed,
        )
        if item.error_message:
            log_logger.info(
                "api id=%s error=%s",
                item.node_id,
                item.error_message,
            )

        for index, assertion in enumerate(item.assertion_results or []):
            log_logger.info(
                "api id=%s assertion[%d] %s",
                item.node_id,
                index,
                _format_assertion_log(assertion),
            )


def _format_field_log(field_result: Dict[str, Any]) -> str:
    """把单个字段评估结果格式化为单行可读文本(供 log_logger 一行输出)。

    输出形如::

        key=cpu_used_pct name=CPU使用率 unit=% value=75.2 direction=high warn=80 crit=90 -> WARN

    缺失值时显示 ``无值``;非数值字段保留原值;含 ``message`` 时附加 ``msg=...``。

    参数:
        field_result: ``InspectionFieldResult.vars()`` 形式的 dict。

    返回:
        str: 单行、便于日志搜索的安全文本。
    """
    key = field_result.get("key") or ""
    name_zh = field_result.get("name_zh") or ""
    unit = field_result.get("unit") or ""
    value = field_result.get("value")
    direction = field_result.get("direction") or ""
    warn = field_result.get("warn")
    crit = field_result.get("crit")
    status = field_result.get("status") or "unassessed"
    message = field_result.get("message") or ""

    value_text = "无值" if value is None else str(value)
    warn_text = "-" if warn is None else str(warn)
    crit_text = "-" if crit is None else str(crit)
    status_text = _FIELD_STATUS_ZH.get(status, status)

    parts = [
        f"key={key}",
        f"name={name_zh}",
        f"unit={unit}",
        f"value={value_text}",
        f"direction={direction or '-'}",
        f"warn={warn_text}",
        f"crit={crit_text}",
        f"-> {status_text}",
    ]
    if message:
        parts.append(f"msg={message}")
    return " ".join(parts)


def _format_assertion_log(assertion: Dict[str, Any]) -> str:
    """把单条断言结果格式化为单行可读文本(供 log_logger 一行输出)。

    输出形如::

        type=status_code passed=True detail=期望=200, 实际=200

    参数:
        assertion: ``ApiConfigService.send_request`` 返回的
            ``assertion_results`` 单条 dict,可能含 ``type`` / ``passed`` /
            ``detail`` / ``expected`` / ``actual`` 等字段。

    返回:
        str: 单行、便于日志搜索的安全文本。
    """
    parts = [
        f"type={assertion.get('type', '-')}",
        f"passed={assertion.get('passed', '-')}",
    ]
    detail = assertion.get("detail")
    if detail:
        parts.append(f"detail={detail}")
    return " ".join(parts)


def _safe_json_dumps(value: Any) -> str:
    """把任意 Python 对象安全序列化为 JSON 字符串(供日志输出)。

    与 ``json.dumps`` 的区别:
        * 默认 ``ensure_ascii=False``,保留中文 / unicode;
        * 失败时降级为 ``repr(value)``,不抛异常(便于日志容错)。

    参数:
        value: 任意 Python 对象(``None`` / ``dict`` / ``list`` / ``str`` 等)。

    返回:
        str: JSON 字符串;失败时返回 ``repr(value)``。
    """
    if value is None:
        return "null"
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return repr(value)


# --------------------------------------------------------------------------
# Phase D docx 报告 helper(Task D1 新增;D2 在 run() 中串联)
# --------------------------------------------------------------------------


def _resolve_attachment_path(schedule_name: str, run_id: int, started_at: datetime) -> Path:
    """解析运维报告 docx 附件路径。

    参数:
        schedule_name: 任务名,会经过 :func:`slugify_task_name` 安全化。
        run_id: 执行记录 ID。
        started_at: 执行开始时间。

    返回:
        Path: docx 绝对路径(父目录尚未创建)。
    """
    return resolve_task_attachment_path(schedule_name, run_id, started_at)


def _generate_docx_report(report_config, output_path: Path) -> None:
    """同步生成 docx 文件(阻塞调用,需在线程中执行)。

    参数:
        report_config: ``ReportConfig`` 实例。
        output_path: 输出 docx 绝对路径。

    返回:
        None。

    异常:
        OSError: 父目录创建失败或文件写入失败时由 ``python-docx`` 抛出。
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    generator = WordReportGenerator(report_config)
    generator.generate()
    generator.save(str(output_path))