# -*- coding:utf-8 -*-
"""
沈阳不动产运维巡检报告专用模块。

定义综述统计口径与告警条目数据类:
    * ``OpsSummary`` —— 综述段落统计口径(总项/成功/有问题/分项计数)
    * ``OpsAlerts`` / ``OpsAlertItem`` —— 关键告警条目集合

报告路径: ``<项目根>/data/attachments/Task/{slug}/{ts}_{run_id}.docx``
参见 :func:`app.core.config.paths.resolve_task_attachment_path`。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional


# 综述段落使用的状态中文映射(从 server_ops._INSPECTION_STATUS_ZH 同步;
# ops_inspection_sweep.py 也有同样的私有副本)。
_INSPECTION_STATUS_ZH = {
    "pass": "通过",
    "warn": "告警",
    "crit": "严重",
    "unassessed": "未评估",
    "skipped": "未执行",
}


@dataclass(frozen=True)
class OpsSummary:
    """综述统计口径。

    Attributes:
        total: 总检查项数(服务器 + 接口,不含网络)。
        passed: 成功项数。
        problem: 有问题项数。
        server_total/server_passed/server_problem: 服务器三项计数。
        server_failed_count: 执行失败或跳过的服务器数。
        server_warn_count: 巡检状态为 warn 的服务器数。
        server_crit_count: 巡检状态为 crit 的服务器数。
        api_total/api_passed/api_problem: 接口三项计数。
    """

    total: int = 0
    passed: int = 0
    problem: int = 0
    server_total: int = 0
    server_passed: int = 0
    server_problem: int = 0
    server_failed_count: int = 0
    server_warn_count: int = 0
    server_crit_count: int = 0
    api_total: int = 0
    api_passed: int = 0
    api_problem: int = 0


@dataclass(frozen=True)
class OpsAlertItem:
    """单条告警条目。

    Attributes:
        business: 业务名(服务器)或接口名。
        metric: 指标名(服务器)或 "HTTP 检查"(接口)。
        value: 当前值(已渲染为字符串)。
        threshold: 阈值文本(如 "warn=80, crit=90")。
        status: 状态(WARN / CRIT / FAIL)。
        detail: 说明文本。
    """

    business: str
    metric: str
    value: str
    threshold: str
    status: str
    detail: str = ""


@dataclass(frozen=True)
class OpsAlerts:
    """告警条目集合。

    Attributes:
        server_warn_crit: 服务器 warn/crit 字段条目。
        api_failed: 接口失败条目。
    """

    server_warn_crit: List[OpsAlertItem] = field(default_factory=list)
    api_failed: List[OpsAlertItem] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """返回:
            bool: 是否无任何告警。
        """
        return not self.server_warn_crit and not self.api_failed


def compute_ops_summary(server_report, api_report) -> OpsSummary:
    """计算综述统计口径。

    参数:
        server_report: :class:`ServerOpsReport`,服务器巡检结果聚合。
        api_report: :class:`ApiCheckReport`,接口检查结果聚合。

    返回:
        OpsSummary: 综述统计结果。
    """
    server_total = len(server_report.items)
    server_passed = sum(
        1 for it in server_report.items
        if it.success is True and it.inspection_status == "pass" and not it.skipped
    )
    server_failed_count = sum(
        1 for it in server_report.items if it.skipped or it.success is False
    )
    server_warn_count = sum(
        1 for it in server_report.items if it.inspection_status == "warn"
    )
    server_crit_count = sum(
        1 for it in server_report.items if it.inspection_status == "crit"
    )
    server_problem = server_total - server_passed

    api_total = len(api_report.items)
    api_passed = sum(1 for it in api_report.items if it.check_passed is True)
    api_problem = sum(
        1 for it in api_report.items
        if it.check_passed is False or it.check_passed is None
    )

    total = server_total + api_total
    passed = server_passed + api_passed
    problem = server_problem + api_problem

    return OpsSummary(
        total=total,
        passed=passed,
        problem=problem,
        server_total=server_total,
        server_passed=server_passed,
        server_problem=server_problem,
        server_failed_count=server_failed_count,
        server_warn_count=server_warn_count,
        server_crit_count=server_crit_count,
        api_total=api_total,
        api_passed=api_passed,
        api_problem=api_problem,
    )


def _format_field_value(field: Mapping[str, Any]) -> str:
    """把字段评估结果格式化为「值 + 单位」文本;None 渲染为「无值」。"""
    value = field.get("value")
    unit = field.get("unit") or ""
    if value is None:
        return "无值"
    return f"{value}{unit}" if unit else str(value)


def _format_field_threshold(field: Mapping[str, Any]) -> str:
    """把字段阈值格式化为「warn=X, crit=Y」文本;None 渲染为「-」。"""
    warn = field.get("warn")
    crit = field.get("crit")
    warn_text = "-" if warn is None else str(warn)
    crit_text = "-" if crit is None else str(crit)
    return f"warn={warn_text}, crit={crit_text}"


def compute_ops_alerts(server_report, api_report) -> OpsAlerts:
    """计算关键告警条目。

    服务器告警: 仅 ``field_results`` 中 ``status in {warn, crit}`` 的字段;
    接口告警: 仅 ``check_passed is False`` 的接口。
    执行失败/跳过的服务器与缺失接口不进入告警列表,仅在 Word 报告中展示。

    参数:
        server_report: :class:`ServerOpsReport`。
        api_report: :class:`ApiCheckReport`。

    返回:
        OpsAlerts: 关键告警集合。
    """
    server_items: List[OpsAlertItem] = []
    for srv in server_report.items:
        if srv.success is not True or srv.skipped:
            continue
        for field in srv.field_results or []:
            status = field.get("status")
            if status not in {"warn", "crit"}:
                continue
            name_zh = field.get("name_zh") or field.get("key") or ""
            message = field.get("message") or ""
            metric = f"{name_zh}（{message}）" if message else name_zh
            server_items.append(OpsAlertItem(
                business=srv.business_name,
                metric=metric,
                value=_format_field_value(field),
                threshold=_format_field_threshold(field),
                status="WARN" if status == "warn" else "CRIT",
                detail=message,
            ))

    api_items: List[OpsAlertItem] = []
    for it in api_report.items:
        if it.check_passed is not False:
            continue
        api_items.append(OpsAlertItem(
            business=it.name or f"接口 {it.node_id}",
            metric="HTTP 检查",
            value=f"HTTP {it.http_status}",
            threshold="-",
            status="FAIL",
            detail=(it.error_message or ""),
        ))

    return OpsAlerts(server_warn_crit=server_items, api_failed=api_items)
