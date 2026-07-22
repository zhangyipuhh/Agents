# -*- coding:utf-8 -*-
"""
服务器运维执行标准化模块。

``server_list`` 是脚本系统的**系统级标准参数**：凡在 ``params_schema`` 中声明
``server_list``（``x-control=server-multiselect`` / ``x-source=devops-servers`` /
``x-value-field=business_name``）的脚本，都可通过本模块获得**完全一致**的巡检
执行结果结构（业务名、成功/失败、退出码、stdout、stderr、耗时、错误），供生成
运行摘要、报告附件或邮件正文使用。命令来源是 **``devops_servers.inspection_script``
字段**（每台服务器预存的巡检脚本文本），不需要在脚本入参中重复指定。

契约要点：
    * ``script_args["server_list"]`` 元素为目标服务器的 ``business_name`` 字符串。
    * 执行复用 ``DevOpsServerService.get_connection_config``（已解密，含
      ``ip`` / ``port`` / ``username`` / ``password`` / ``server_type`` /
      ``inspection_script`` / ``inspection_parser``）以及
      ``app.shared.utils.ssh.executor.execute_script``（与 LangChain 解耦的
      阻塞 paramiko 执行器），本模块负责用 ``asyncio.to_thread`` 包装避免
      阻塞调度器事件循环。
    * 单台服务器失败（鉴权失败 / 连接超时 / ``inspection_script`` 未配置 /
      paramiko SSH 异常等）**不中断**整体巡检，失败原因记录到对应
      ``ServerOpsItem``。
    * ``server_list`` 为空时返回空 ``ServerOpsReport``，不要求服务可用。

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


# stdout 摘要最大长度（与 api_check_runs.response_body 的截断策略保持一致，
# 报告 markdown 表格不能塞下完整 JSON 输出）
_STDOUT_PREVIEW_MAX = 4000


@dataclass(frozen=True)
class ServerOpsItem:
    """单台服务器的巡检执行结果。

    Attributes:
        business_name: 服务器业务名（``devops_servers.business_name``）。
        success: 命令执行是否成功（退出码 0 且 stderr 为空）；未执行时为 None。
        exit_code: 远端进程退出码；未执行或被异常打断时为 None。
        stdout: 标准输出（已 strip）；未执行时为空字符串。
        stderr: 标准错误（已 strip）；成功执行时为空字符串。
        duration_ms: 执行耗时毫秒；未执行时为 None。
        error_message: 错误描述（鉴权失败 / 连接超时 / 未配置巡检脚本等）；
            成功执行时为空字符串。
        skipped: True 时表示本台服务器未执行（业务名无效、未配置
            ``inspection_script`` 等）；同时 ``success`` 为 None。
    """

    business_name: str
    success: Optional[bool] = None
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: Optional[int] = None
    error_message: str = ""
    skipped: bool = False


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
            int: 执行成功（``success is True``）的服务器数。
        """
        return sum(1 for item in self.items if item.success is True)

    @property
    def failed(self) -> int:
        """返回:
            int: 执行失败（``success is False``）的服务器数。
        """
        return sum(1 for item in self.items if item.success is False)

    @property
    def skipped(self) -> int:
        """返回:
            int: 未执行（``skipped is True``）的服务器数。
        """
        return sum(1 for item in self.items if item.skipped)

    def summary_line(self) -> str:
        """生成单行人类可读摘要，供 ``agent_task_runs.output_text`` 追加。

        格式示例::

            server_ops=2/3 passed, 1 skipped | biz-A OK(0,82ms); biz-B FAIL(1,45ms); biz-C SKIPPED

        返回:
            str: 摘要文本；``items`` 为空时返回空字符串。
        """
        if not self.items:
            return ""
        executed = self.total - self.skipped
        parts = [f"server_ops={self.passed}/{executed} passed"]
        if self.skipped:
            parts.append(f", {self.skipped} skipped")
        details = []
        for item in self.items:
            if item.skipped:
                details.append(f"{item.business_name} SKIPPED")
            elif item.success:
                ms = f"{item.duration_ms}ms" if item.duration_ms is not None else "-"
                details.append(f"{item.business_name} OK({item.exit_code},{ms})")
            else:
                ms = f"{item.duration_ms}ms" if item.duration_ms is not None else "-"
                details.append(f"{item.business_name} FAIL({item.exit_code},{ms})")
        return "".join(parts) + " | " + "; ".join(details)

    def to_markdown(self) -> str:
        """生成 Markdown 表格，供报告附件 / 邮件正文列举被检查服务器及状态。

        返回:
            str: Markdown 表格文本；``items`` 为空时返回空字符串。
        """
        if not self.items:
            return ""
        lines = [
            "| 业务名 | 结果 | 退出码 | 耗时(ms) | stdout 摘要 | 错误 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for item in self.items:
            if item.skipped:
                result_text = "未执行"
                exit_text = ""
                duration_text = ""
            elif item.success:
                result_text = "通过"
                exit_text = "" if item.exit_code is None else str(item.exit_code)
                duration_text = "" if item.duration_ms is None else str(item.duration_ms)
            else:
                result_text = "未通过"
                exit_text = "" if item.exit_code is None else str(item.exit_code)
                duration_text = "" if item.duration_ms is None else str(item.duration_ms)
            preview = item.stdout[:_STDOUT_PREVIEW_MAX]
            if len(item.stdout) > _STDOUT_PREVIEW_MAX:
                preview += "..."
            preview = preview.replace("\n", " ").replace("|", "\\|")
            error = (item.error_message or item.stderr or "").replace("\n", " ")
            error = error.replace("|", "\\|")
            lines.append(
                f"| {item.business_name} | {result_text} | {exit_text} | "
                f"{duration_text} | {preview} | {error} |"
            )
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为 JSON 可存储结构。

        返回:
            Dict[str, Any]: 含 ``items`` / ``total`` / ``passed`` / ``failed`` /
            ``skipped`` 的字典。
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
                }
                for item in self.items
            ],
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
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
    读取解密后的连接配置（含 ``inspection_script``），再用
    ``app.shared.utils.ssh.executor.execute_script`` 发起 SSH 执行（同步阻塞
    调用以 ``asyncio.to_thread`` 包装）。单台失败（鉴权失败 / 连接异常 /
    业务名未注册 / ``inspection_script`` 未配置等）**不中断**整体巡检。

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
        * ``KeyError`` (``get_connection_config`` 业务名未注册) → skipped；
        * 空 ``inspection_script``（None / 空串） → skipped；
        * SSH 鉴权 / 连接 / paramiko 异常 → failed，不中断调用方循环。
    """
    try:
        config = service.get_connection_config(business_name)
    except KeyError as exc:
        return ServerOpsItem(
            business_name=business_name,
            skipped=True,
            error_message=str(exc) or "业务名未注册",
        )
    except Exception as exc:  # noqa: BLE001 - 配置解析失败容错
        return ServerOpsItem(
            business_name=business_name,
            success=False,
            error_message=f"配置解析失败: {type(exc).__name__}: {exc}",
        )

    script_raw = config.get("inspection_script") if isinstance(config, dict) else None
    script = (script_raw or "").strip() if isinstance(script_raw, str) else ""
    if not script:
        return ServerOpsItem(
            business_name=business_name,
            skipped=True,
            error_message="未配置巡检脚本（inspection_script 为空）",
        )

    started = time.perf_counter()
    try:
        result: SSHExecResult = await asyncio.to_thread(
            execute_script, dict(config), script, ssh_timeout
        )
    except Exception as exc:  # noqa: BLE001 - 单台失败不中断整体
        duration_ms = int((time.perf_counter() - started) * 1000)
        return ServerOpsItem(
            business_name=business_name,
            success=False,
            duration_ms=duration_ms,
            error_message=f"{type(exc).__name__}: {exc}",
        )

    duration_ms = int((time.perf_counter() - started) * 1000)
    return ServerOpsItem(
        business_name=business_name,
        success=bool(result.success),
        exit_code=int(result.exit_code),
        stdout=result.stdout or "",
        stderr=result.stderr or "",
        duration_ms=duration_ms,
        error_message=result.stderr or "",
    )


logger = logging.getLogger(__name__)
