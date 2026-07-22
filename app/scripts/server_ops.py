# -*- coding:utf-8 -*-
"""
服务器运维执行标准化模块。

``server_list`` 是脚本系统的**系统级标准参数**：凡在 ``params_schema`` 中声明
``server_list``（``x-control=server-multiselect`` / ``x-source=devops-servers`` /
``x-value-field=business_name``）的脚本，都可通过本模块获得**完全一致**的巡检
执行结果结构（业务名、成功/失败、退出码、stdout、stderr、耗时、错误、巡检状态、
字段判定结果），供生成运行摘要、报告附件或邮件正文使用。命令来源是
**``devops_servers.inspection_script`` 字段**（每台服务器预存的巡检脚本文本），
不需要在脚本入参中重复指定。

契约要点：
    * ``script_args["server_list"]`` 元素为目标服务器的 ``business_name`` 字符串。
    * 执行复用 ``DevOpsServerService.get_connection_config``（已解密，含
      ``ip`` / ``port`` / ``username`` / ``password`` / ``server_type`` /
      ``inspection_script`` / ``inspection_parser`` / ``inspection_fields``）
      以及 ``app.shared.utils.ssh.executor.execute_script``（与 LangChain 解耦的
      阻塞 paramiko 执行器），本模块负责用 ``asyncio.to_thread`` 包装避免
      阻塞调度器事件循环。
    * 单台服务器失败（鉴权失败 / 连接超时 / ``inspection_script`` 未配置 /
      paramiko SSH 异常等）**不中断**整体巡检，失败原因记录到对应
      ``ServerOpsItem``。
    * ``server_list`` 为空时返回空 ``ServerOpsReport``，不要求服务可用。

巡检状态分级（``inspection_status``）：
    * ``pass`` —— 巡检脚本执行成功，所有评估字段未越线。
    * ``warn`` —— 巡检脚本执行成功，至少一个评估字段命中 warn 阈值（且无 crit）。
    * ``crit`` —— SSH 失败 / 解析失败 / 评估失败 / 规则阈值严重命中 / 字段缺失 /
      非数值 / raw 解析器与结构化规则同时存在等。
    * ``unassessed`` —— 巡检脚本执行成功，但无任何可评估规则。
    * ``skipped`` —— 未执行（业务名未注册 / ``inspection_script`` 未配置）。

success 与 inspection_status 解耦：
    * ``success`` 反映「SSH 退出码 0 且 stderr 为空」的纯执行语义；
    * ``inspection_status`` 反映「脚本输出按规则评估」的语义学判定。
    * 当 SSH 成功但评估命中 crit 时，``success=True`` 但 ``inspection_status="crit"``；
      反之 SSH 失败时 ``success=False`` 且 ``inspection_status="crit"``，
      **不会** 再走 stdout 解析评估。

使用示例::

    from app.scripts.server_ops import run_server_ops

    report = await run_server_ops(context)
    if report.items:
        summary = summary + " | " + report.summary_line()
        markdown_table = report.to_markdown()
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.scripts.base import ScriptContext, ScriptExecutionError
from app.shared.utils.ssh.executor import SSHExecResult, execute_script
from app.shared.utils.inspection.parser import (
    evaluate_inspection_fields,
    parse_inspection_output,
)


# stdout 摘要最大长度（与 api_check_runs.response_body 的截断策略保持一致，
# 报告 markdown 表格不能塞下完整 JSON 输出）
_STDOUT_PREVIEW_MAX = 4000

# SSH 退出码非 0 或 stderr 非空时的固定错误说明（不携带异常原文，避免泄漏）。
_SSH_EXEC_FAILURE_DEFAULT_ERROR = "远端巡检脚本执行失败"

# 解析 / 评估阶段异常统一前缀。
_PARSE_EVAL_FAILURE_PREFIX = "巡检解析评估失败"

# 配置解析异常统一前缀（不含敏感字段）。
_CONFIG_RESOLVE_FAILURE_PREFIX = "配置解析失败"


# 巡检状态中文显示映射（summary_line / to_markdown 复用）。
_INSPECTION_STATUS_ZH = {
    "pass": "通过",
    "warn": "告警",
    "crit": "严重",
    "unassessed": "未评估",
    "skipped": "未执行",
}


def _escape_cell(value: Any) -> str:
    """把单个 markdown 表格字段值安全化：换行转空格、管道转义。

    Args:
        value: 任意原始值（非字符串会被 str()）。

    Returns:
        str: 可直接写入 markdown 单元格的安全文本（单行，无未转义 ``|``）。
    """
    text = "" if value is None else str(value)
    return text.replace("\r", " ").replace("\n", " ").replace("|", "\\|")


def _format_field_message(field_result: Dict[str, Any]) -> str:
    """把单个字段评估结果格式化为人类可读的「中文名 原值+单位 状态/消息 阈值」文本。

    Args:
        field_result: ``InspectionFieldResult.vars()`` 形式的 dict。

    Returns:
        str: 单行、已 ``|`` 转义的安全文本，markdown 单元格可直接使用。
    """
    name = field_result.get("name_zh") or field_result.get("key") or ""
    unit = field_result.get("unit") or ""
    value = field_result.get("value")
    status = field_result.get("status") or "unassessed"
    message = field_result.get("message") or ""
    warn = field_result.get("warn")
    crit = field_result.get("crit")

    parts: List[str] = [name]
    if value is None:
        parts.append("无值")
    else:
        if unit:
            parts.append(f"{value}{unit}")
        else:
            parts.append(f"{value}")
    parts.append(_INSPECTION_STATUS_ZH.get(status, status))
    if message:
        parts.append(message)
    if warn is not None or crit is not None:
        warn_text = "warn=" + (str(warn) if warn is not None else "-")
        crit_text = "crit=" + (str(crit) if crit is not None else "-")
        parts.append(f"{warn_text} {crit_text}")
    text = " ".join(str(p) for p in parts if p)
    return _escape_cell(text)


@dataclass(frozen=True)
class ServerOpsItem:
    """单台服务器的巡检执行结果。

    Attributes:
        business_name: 服务器业务名（``devops_servers.business_name``）。
        success: SSH 命令执行是否成功（退出码 0 且 stderr 为空）；未执行时为 None。
        exit_code: 远端进程退出码；未执行或被异常打断时为 None。
        stdout: 标准输出（已 strip）；未执行时为空字符串。
        stderr: 标准错误（已 strip）；成功执行时为空字符串。
        duration_ms: 执行耗时毫秒；未执行时为 None。
        error_message: 错误描述（鉴权失败 / 连接超时 / 未配置巡检脚本 /
            解析评估失败等）；成功执行时为空字符串。
        skipped: True 时表示本台服务器未执行（业务名无效、未配置
            ``inspection_script`` 等）；同时 ``success`` 为 None。
        inspection_parser: 实际生效的解析器（json / kv / csv / raw）；默认 ``json``。
        parsed_values: 解析得到的原始值字典或字符串（``raw`` 透传 stdout）；
            解析失败或未解析时为 None。
        field_results: 各字段评估结果列表，元素为 ``InspectionFieldResult.vars()``
            形式 dict；未评估时为空列表。
        inspection_status: 巡检总体状态，取值 ``pass`` / ``warn`` / ``crit`` /
            ``unassessed`` / ``skipped``。
        inspection_error: 巡检阶段的错误说明（解析异常 / raw 评估不支持 /
            SSH 执行失败原因等）；无错误时为空字符串。**不**写入整个
            ``config`` / ``ip`` / ``password`` 等敏感字段。
    """

    business_name: str
    success: Optional[bool] = None
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: Optional[int] = None
    error_message: str = ""
    skipped: bool = False
    inspection_parser: str = "json"
    parsed_values: Any = None
    field_results: List[Dict[str, Any]] = field(default_factory=list)
    inspection_status: str = "unassessed"
    inspection_error: str = ""


@dataclass
class ServerOpsReport:
    """``server_list`` 巡检执行的统一结果结构。

    Attributes:
        items: 每台服务器的巡检结果，顺序与 ``server_list`` 一致。
    """

    items: List[ServerOpsItem] = field(default_factory=list)

    @property
    def total(self) -> int:
        """返回:
            int: 巡检的服务器总数（含跳过项）。
        """
        return len(self.items)

    @property
    def passed(self) -> int:
        """返回:
            int: SSH 执行成功（``success is True``）的服务器数。
        """
        return sum(1 for item in self.items if item.success is True)

    @property
    def failed(self) -> int:
        """返回:
            int: SSH 执行失败（``success is False``）的服务器数。
        """
        return sum(1 for item in self.items if item.success is False)

    @property
    def skipped(self) -> int:
        """返回未执行服务器数（skipped=True）。"""
        return sum(1 for item in self.items if item.skipped)

    @property
    def inspection_passed(self) -> int:
        """返回巡检状态为通过的服务器数（``inspection_status="pass"``）。"""
        return sum(1 for item in self.items if item.inspection_status == "pass")

    @property
    def inspection_warned(self) -> int:
        """返回巡检状态为告警的服务器数（``inspection_status="warn"``）。"""
        return sum(1 for item in self.items if item.inspection_status == "warn")

    @property
    def inspection_critical(self) -> int:
        """返回巡检状态为严重的服务器数（``inspection_status="crit"``）。"""
        return sum(1 for item in self.items if item.inspection_status == "crit")

    @property
    def inspection_unassessed(self) -> int:
        """返回巡检状态为未评估的服务器数（``inspection_status="unassessed"``）。"""
        return sum(
            1 for item in self.items if item.inspection_status == "unassessed"
        )

    def summary_line(self) -> str:
        """生成单行人类可读摘要，供 ``agent_task_runs.output_text`` 追加。

        格式示例::

            server_ops=2/3 passed, 1 skipped | inspection=pass:1,warn:0,crit:1,unassessed:0 | biz-A OK(0,42ms)/PASS; biz-B FAIL(1,45ms)/CRIT; biz-C SKIPPED/SKIPPED

        说明：
            * ``server_ops=<P>/<N> passed`` —— 旧契约（P 成功数 / N=total-skipped）；
            * ``inspection=pass:N,warn:N,crit:N,unassessed:N`` —— 巡检 4 项计数，
              ``skipped`` 项**不**计入其中任何一项；
            * 每项详情依次追加 ``/PASS|WARN|CRIT|UNASSESSED|SKIPPED`` 后缀。

        返回:
            str: 摘要文本；``items`` 为空时返回空字符串。
        """
        if not self.items:
            return ""
        executed = self.total - self.skipped
        parts = [f"server_ops={self.passed}/{executed} passed"]
        if self.skipped:
            parts.append(f", {self.skipped} skipped")
        parts.append(
            f" | inspection="
            f"pass:{self.inspection_passed},"
            f"warn:{self.inspection_warned},"
            f"crit:{self.inspection_critical},"
            f"unassessed:{self.inspection_unassessed}"
        )
        details = []
        for item in self.items:
            status = (item.inspection_status or "unassessed").upper()
            if item.skipped:
                details.append(f"{item.business_name} SKIPPED/{status}")
            elif item.success:
                ms = f"{item.duration_ms}ms" if item.duration_ms is not None else "-"
                details.append(f"{item.business_name} OK({item.exit_code},{ms})/{status}")
            else:
                ms = f"{item.duration_ms}ms" if item.duration_ms is not None else "-"
                details.append(f"{item.business_name} FAIL({item.exit_code},{ms})/{status}")
        return "".join(parts) + " | " + "; ".join(details)

    def to_markdown(self) -> str:
        """生成 Markdown 表格，供报告附件 / 邮件正文列举被检查服务器及状态。

        表格列（原 6 列后追加 2 列，共 8 列）：
            1. 业务名
            2. 结果（通过 / 未通过 / 未执行）
            3. 退出码
            4. 耗时（ms）
            5. stdout 摘要（截断到 4000 字符 + ``...``）
            6. 错误（error_message 或 stderr）
            7. 巡检状态（通过 / 告警 / 严重 / 未评估 / 未执行）
            8. 指标判定（字段中文名 + 原值+单位 + 状态/消息 + warn/crit 阈值）

        所有动态字段（业务名 / stdout / 错误 / 字段 message 等）中的换行
        替换为空格，``|`` 替换为 ``\\|``，确保不被 markdown 误解析为表格列。

        返回:
            str: Markdown 表格文本；``items`` 为空时返回空字符串。
        """
        if not self.items:
            return ""
        lines = [
            "| 业务名 | 结果 | 退出码 | 耗时(ms) | stdout 摘要 | 错误 | 巡检状态 | 指标判定 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for item in self.items:
            inspection_status_zh = _INSPECTION_STATUS_ZH.get(
                item.inspection_status or "unassessed",
                item.inspection_status or "unassessed",
            )
            if item.skipped:
                result_text = "未执行"
                exit_text = ""
                duration_text = ""
                inspection_text = _escape_cell("未执行")
                fields_text = _escape_cell(
                    item.error_message or item.inspection_error or "未执行"
                )
            elif item.success:
                result_text = "通过"
                exit_text = "" if item.exit_code is None else str(item.exit_code)
                duration_text = "" if item.duration_ms is None else str(item.duration_ms)
                inspection_text = _escape_cell(inspection_status_zh)
                if item.field_results:
                    fields_text = "; ".join(
                        _format_field_message(f) for f in item.field_results
                    )
                else:
                    fields_text = ""
            else:
                result_text = "未通过"
                exit_text = "" if item.exit_code is None else str(item.exit_code)
                duration_text = "" if item.duration_ms is None else str(item.duration_ms)
                inspection_text = _escape_cell(inspection_status_zh)
                if item.field_results:
                    fields_text = "; ".join(
                        _format_field_message(f) for f in item.field_results
                    )
                elif item.inspection_error:
                    fields_text = _escape_cell(item.inspection_error)
                else:
                    fields_text = ""
            preview = item.stdout[:_STDOUT_PREVIEW_MAX]
            if len(item.stdout) > _STDOUT_PREVIEW_MAX:
                preview += "..."
            preview = _escape_cell(preview)
            error_text = _escape_cell(item.error_message or item.stderr or "")
            # fields_text 与 inspection_text 已由 _format_field_message / _INSPECTION_STATUS_ZH
            # 处理为安全文本；inspection_text 额外走一次 ``_escape_cell`` 保持管道转义一致。
            business = _escape_cell(item.business_name)
            lines.append(
                f"| {business} | {result_text} | {exit_text} | "
                f"{duration_text} | {preview} | {error_text} | "
                f"{inspection_text} | {fields_text} |"
            )
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为 JSON 可存储结构。

        顶层除老的 ``items`` / ``total`` / ``passed`` / ``failed`` / ``skipped``
        计数外，额外包含 4 项巡检计数：``inspection_passed`` /
        ``inspection_warned`` / ``inspection_critical`` /
        ``inspection_unassessed``。

        每个 item 额外包含 ``inspection_parser`` / ``parsed_values`` /
        ``field_results`` / ``inspection_status`` / ``inspection_error``。

        返回:
            Dict[str, Any]: 含上述字段的字典，可被 ``json.dumps`` 序列化。
        """
        return {
            "items": [
                {
                    "business_name": item.business_name,
                    "success": item.success,
                    "exit_code": item.exit_code,
                    "stdout": item.stdout,
                    "stderr": item.stderr,
                    "duration_ms": item.duration_ms,
                    "error_message": item.error_message,
                    "skipped": item.skipped,
                    "inspection_parser": item.inspection_parser,
                    "parsed_values": item.parsed_values,
                    "field_results": list(item.field_results),
                    "inspection_status": item.inspection_status,
                    "inspection_error": item.inspection_error,
                }
                for item in self.items
            ],
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "inspection_passed": self.inspection_passed,
            "inspection_warned": self.inspection_warned,
            "inspection_critical": self.inspection_critical,
            "inspection_unassessed": self.inspection_unassessed,
        }


def resolve_server_list(script_args: Dict[str, Any]) -> List[str]:
    """解析并校验 ``server_list`` 脚本参数，所有脚本共用的统一入口。

    缺失键或值为 ``None`` 时按空列表处理；元素为服务器业务名字符串。脚本侧
    不去重，前端已按 schema 的 ``uniqueItems`` 约束保证唯一性。

    参数:
        script_args: 脚本运行参数字典（``context.script_args``）。

    返回:
        List[str]: 通过校验的业务名列表（缺失或空数组时返回 ``[]``）。

    异常:
        ScriptExecutionError: ``server_list`` 不是列表、元素不是非空字符串时抛出，
        错误消息包含字段名 ``server_list``。
    """
    raw_value = (script_args or {}).get("server_list", [])
    if raw_value is None:
        raw_value = []

    if not isinstance(raw_value, list):
        raise ScriptExecutionError(
            "server_list 必须为字符串数组（业务名列表），"
            f"实际收到类型: {type(raw_value).__name__}"
        )

    validated: List[str] = []
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


async def run_server_ops(
    context: ScriptContext,
    server_list: Optional[List[str]] = None,
    *,
    ssh_timeout: int = 30,
) -> ServerOpsReport:
    """对 ``server_list`` 中的服务器逐个执行预存的 ``inspection_script`` 巡检脚本。

    每个接口通过 ``context.devops_server_service.get_connection_config(business_name)``
    读取解密后的连接配置（含 ``inspection_script`` / ``inspection_parser`` /
    ``inspection_fields``），再用
    ``app.shared.utils.ssh.executor.execute_script`` 发起 SSH 执行（同步阻塞
    调用以 ``asyncio.to_thread`` 包装）。单台失败（鉴权失败 / 连接异常 /
    业务名未注册 / ``inspection_script`` 未配置 / 解析评估失败等）
    **不中断**整体巡检。

    参数:
        context: 脚本运行上下文，需携带 ``devops_server_service`` 与 ``script_args``。
        server_list: 可选的服务器业务名列表；为 ``None`` 时通过
            ``resolve_server_list(context.script_args)`` 统一解析。
        ssh_timeout: 单台 SSH 执行超时（秒），限制在 ``ssh.executor`` 的 1-120 范围内。

    返回:
        ServerOpsReport: 统一巡检结果；``server_list`` 为空时 ``items`` 为空列表。

    异常:
        ScriptExecutionError: ``server_list`` 非空但 ``context.devops_server_service``
        为 ``None``（DB 未就绪或服务未注入）时抛出；``server_list`` 参数非法时
        由 ``resolve_server_list`` 抛出。
    """
    names = server_list if server_list is not None else resolve_server_list(context.script_args)
    if not names:
        return ServerOpsReport(items=[])

    service = getattr(context, "devops_server_service", None)
    if service is None:
        raise ScriptExecutionError(
            "devops_server_service 不可用，无法执行 server_list 巡检"
            "（数据库未就绪或调度器未注入该服务）"
        )

    items: List[ServerOpsItem] = []
    for business_name in names:
        item = await _run_one(business_name, service, ssh_timeout=ssh_timeout)
        items.append(item)

    return ServerOpsReport(items=items)


async def _run_one(
    business_name: str,
    service: Any,
    *,
    ssh_timeout: int,
) -> ServerOpsItem:
    """对单台服务器执行巡检并产出 ``ServerOpsItem``。

    异常分级：
        * ``KeyError`` (``get_connection_config`` 业务名未注册) → skipped，
          ``inspection_error`` 含原 KeyError 信息；
        * 空 ``inspection_script``（None / 空串） → skipped；
        * ``get_connection_config`` 抛其他异常（解密失败 / Fernet 错配等）
          → crit，``error_message`` / ``inspection_error`` 含「Type: message」
          但**不**泄漏整个 config（无 ip / password）；
        * SSH 鉴权 / 连接 / paramiko 异常 → crit，``inspection_error`` /
          ``error_message`` 含「Type: message」，**不**泄漏 config；
        * ``SSHExecResult.success=False`` → crit，**不**调用
          ``parse_inspection_output`` / ``evaluate_inspection_fields``；
          ``inspection_error`` / ``error_message`` 取 stderr 或「远端巡检脚本执行失败」；
        * 解析 / 评估阶段异常 → crit，保留 stdout / stderr / exit_code /
          duration；``error_message`` / ``inspection_error`` 统一为
          「巡检解析评估失败: Type: message」；**不**泄漏 config；
        * 评估本身得到 crit（raw+规则 / 缺字段 / 非数值 / 阈值严重命中）
          **不改变** SSH 执行语义，``success`` 仍为 ``bool(result.success)``。
    """
    # 1) 取连接配置
    try:
        config = service.get_connection_config(business_name)
    except KeyError as exc:
        return ServerOpsItem(
            business_name=business_name,
            skipped=True,
            error_message=str(exc) or "业务名未注册",
            inspection_status="skipped",
            inspection_error=str(exc) or "业务名未注册",
        )
    except Exception as exc:  # noqa: BLE001 - 配置解析失败容错
        msg = f"{type(exc).__name__}: {exc}"
        return ServerOpsItem(
            business_name=business_name,
            success=False,
            error_message=f"{_CONFIG_RESOLVE_FAILURE_PREFIX}: {msg}",
            inspection_status="crit",
            inspection_error=f"{_CONFIG_RESOLVE_FAILURE_PREFIX}: {msg}",
        )

    # 2) 校验 inspection_script 非空
    script_raw = config.get("inspection_script") if isinstance(config, dict) else None
    script = (script_raw or "").strip() if isinstance(script_raw, str) else ""
    if not script:
        msg = "未配置巡检脚本（inspection_script 为空）"
        return ServerOpsItem(
            business_name=business_name,
            skipped=True,
            error_message=msg,
            inspection_status="skipped",
            inspection_error=msg,
        )

    # 3) 执行 SSH（同步阻塞通过 to_thread 包装）
    started = time.perf_counter()
    try:
        result: SSHExecResult = await asyncio.to_thread(
            execute_script, dict(config), script, ssh_timeout
        )
    except Exception as exc:  # noqa: BLE001 - 单台失败不中断整体
        duration_ms = int((time.perf_counter() - started) * 1000)
        msg = f"{type(exc).__name__}: {exc}"
        return ServerOpsItem(
            business_name=business_name,
            success=False,
            duration_ms=duration_ms,
            error_message=msg,
            inspection_status="crit",
            inspection_error=msg,
        )

    duration_ms = int((time.perf_counter() - started) * 1000)
    parser = str(config.get("inspection_parser") or "json")

    # 4) SSH 失败：不解析 stdout，直接 crit
    if not result.success:
        stderr_text = (result.stderr or "").strip()
        err = stderr_text or _SSH_EXEC_FAILURE_DEFAULT_ERROR
        return ServerOpsItem(
            business_name=business_name,
            success=False,
            exit_code=int(result.exit_code),
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            duration_ms=duration_ms,
            error_message=err,
            inspection_parser=parser,
            inspection_status="crit",
            inspection_error=err,
        )

    # 5) 解析 + 评估阶段：成功执行才进入
    try:
        parsed_values = parse_inspection_output(parser, result.stdout or "")
        # ``inspection_fields`` 由 ``DevOpsServerService.get_connection_config``
        # 负责归一化为 ``list[InspectionFieldRule]``（含 ``key`` / ``name_zh`` /
        # ``unit`` / ``direction`` / ``warn`` / ``crit`` 属性）；本模块**不**
        # 调用 ``normalize_inspection_fields``，service 是序列化/结构化的唯一
        # 真相源。下方仅做防御性类型断言应对老 cache / 测试 stub 输入。
        raw_rules = config.get("inspection_fields")
        rules = raw_rules if isinstance(raw_rules, list) else []
        evaluation = evaluate_inspection_fields(parsed_values, rules, parser)
    except Exception as exc:  # noqa: BLE001 - 解析评估失败保留 stdout / stderr / exit
        msg = f"{type(exc).__name__}: {exc}"
        full_err = f"{_PARSE_EVAL_FAILURE_PREFIX}: {msg}"
        return ServerOpsItem(
            business_name=business_name,
            success=False,
            exit_code=int(result.exit_code),
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            duration_ms=duration_ms,
            error_message=full_err,
            inspection_parser=parser,
            parsed_values=None,
            field_results=[],
            inspection_status="crit",
            inspection_error=full_err,
        )

    # 6) 评估成功：success 仍为 SSH 执行语义，inspection_status 取 evaluation.status
    eval_error = evaluation.error_message or ""
    return ServerOpsItem(
        business_name=business_name,
        success=bool(result.success),
        exit_code=int(result.exit_code),
        stdout=result.stdout or "",
        stderr=result.stderr or "",
        duration_ms=duration_ms,
        error_message="",
        inspection_parser=parser,
        parsed_values=evaluation.parsed_values,
        field_results=[vars(field_result) for field_result in evaluation.fields],
        inspection_status=evaluation.status,
        inspection_error=eval_error,
    )


logger = logging.getLogger(__name__)