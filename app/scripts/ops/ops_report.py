# -*- coding:utf-8 -*-
"""
沈阳不动产运维巡检报告专用模块。

包含:
    * ``OpsSummary`` —— 综述段落统计口径
    * ``OpsAlerts`` / ``OpsAlertItem`` —— 关键告警条目
    * ``compute_ops_summary`` / ``compute_ops_alerts`` —— 摘要/告警统计
    * ``build_ops_report_config`` —— 构建 :class:`ReportConfig`
    * ``build_ops_email_body`` —— 构建邮件正文文本

报告路径: ``<项目根>/data/attachments/Task/{slug}/{ts}_{run_id}.docx``
参见 :func:`app.core.config.paths.resolve_task_attachment_path`。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional


# 综述段落使用的状态中文映射(与 server_ops._INSPECTION_STATUS_ZH 对齐)。
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
