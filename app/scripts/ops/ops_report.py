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
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional

from app.shared.utils.report.word.config import (
    CoverConfig, CoverElementConfig, ReportConfig, SectionConfig, TableSectionConfig,
    TocConfig, TocEntry,
)


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


def resolve_server_ip_map(
    devops_server_service,
    server_report,
) -> Dict[str, Optional[str]]:
    """从 :class:`DevOpsServerService` 反查每台服务器的 IP。

    反查失败的项(服务不可用 / KeyError / 异常)统一返回 ``None``,
    由调用方在报告中渲染为 ``-``,不中断整体流程。

    字段兼容性:真实 :class:`DevOpsServerService.get_connection_config` 返回的字典
    使用 ``ip`` 字段(参见 ``app/shared/utils/devops_server_service.py:357``),同时兼容
    ``host`` 别名(历史测试桩 / 旧版 dict 接口)。

    参数:
        devops_server_service: 调度器注入的 ``DevOpsServerService`` 实例;可能为 ``None``。
        server_report: :class:`ServerOpsReport`。

    返回:
        Dict[str, Optional[str]]: ``business_name -> ip`` 映射;IP 缺失为 ``None``。
    """
    result: Dict[str, Optional[str]] = {}
    if devops_server_service is None:
        for srv in server_report.items:
            result[srv.business_name] = None
        return result

    for srv in server_report.items:
        try:
            config = devops_server_service.get_connection_config(srv.business_name)
            # 兼容真实 DevOpsServerService 的 ip 字段与可能的 host 别名
            if isinstance(config, dict):
                host = config.get("ip") or config.get("host")
            elif config is not None:
                host = getattr(config, "ip", None) or getattr(config, "host", None)
            else:
                host = None
            result[srv.business_name] = host
        except Exception:
            result[srv.business_name] = None
    return result


# --------------------------------------------------------------------------
# Word 报告配置构造(用于 docx 渲染层)
# --------------------------------------------------------------------------

def _server_meta_rows(item, host: Optional[str]) -> List[List[str]]:
    """构造单个业务的服务器元信息表行(2 列: 项目/值)。"""
    return [
        ["业务名", item.business_name or "-"],
        ["服务器 IP", host or "-"],
        ["SSH 退出码", "-" if item.exit_code is None else str(item.exit_code)],
        ["耗时", "-" if item.duration_ms is None else f"{item.duration_ms} ms"],
        ["巡检状态", _INSPECTION_STATUS_ZH.get(item.inspection_status, item.inspection_status or "-")],
    ]


def _server_field_rows(item) -> List[List[str]]:
    """构造单个业务的字段明细表行(5 列)。"""
    rows: List[List[str]] = []
    for fr in item.field_results or []:
        name_zh = fr.get("name_zh") or fr.get("key") or ""
        message = fr.get("message") or ""
        metric = f"{name_zh}（{message}）" if message else name_zh
        rows.append([
            metric,
            _format_field_value(fr),
            _format_field_threshold(fr),
            _INSPECTION_STATUS_ZH.get(fr.get("status") or "unassessed", "未评估"),
            message or "-",
        ])
    return rows


def _api_meta_rows(item) -> List[List[str]]:
    """构造单个接口的元信息表行(2 列)。"""
    if item.check_passed is None:
        result_text = "节点缺失"
    elif item.check_passed is True:
        result_text = "通过"
    else:
        result_text = "失败"
    return [
        ["节点 ID", str(item.node_id)],
        ["名称", item.name or "-"],
        ["接口地址", item.path or "-"],
        ["HTTP 状态", "-" if item.http_status is None else str(item.http_status)],
        ["耗时", "-" if item.duration_ms is None else f"{item.duration_ms} ms"],
        ["检查结果", result_text],
    ]


def _api_assertion_rows(item) -> List[List[str]]:
    """构造单个接口的断言明细表行(5 列)。"""
    rows: List[List[str]] = []
    for assertion in item.assertion_results or []:
        rule = assertion.get("rule") or {}
        rows.append([
            str(rule.get("type") or assertion.get("type") or "-"),
            str(rule.get("value") if rule.get("value") is not None else assertion.get("expected") or "-"),
            str(assertion.get("actual") or "-"),
            "✓" if assertion.get("passed") is True else ("✗" if assertion.get("passed") is False else "-"),
            str(assertion.get("detail") or "-"),
        ])
    return rows


def build_ops_report_config(
    *,
    summary: OpsSummary,
    alerts: OpsAlerts,
    server_report,
    api_report,
    ip_map: Mapping[str, Optional[str]],
    schedule_name: str,
    started_at: datetime,
) -> ReportConfig:
    """构建运维巡检 Word 报告的 :class:`ReportConfig`。

    章节结构:
        0. 封面 (主标题「沈阳不动产运维报告」+ 时间 + 任务名)
        0. 目录 (5 条 TocEntry,实际为 4 个一级标题)
        1. 一、综述 (分段叙事段落)
        2. 二、网络检查 (固定段落)
        3. 三、服务器基本情况 (按业务循环)
        4. 四、接口健康检查 (按接口循环)

    参数:
        summary: :class:`OpsSummary`。
        alerts: :class:`OpsAlerts`。
        server_report: :class:`ServerOpsReport`。
        api_report: :class:`ApiCheckReport`。
        ip_map: 业务名到 IP 的映射,缺失为 ``None``。
        schedule_name: 任务名。
        started_at: 执行开始时间。

    返回:
        ReportConfig: 完整报告配置。
    """
    sections: List[SectionConfig] = []

    # 1. 综述
    sections.append(SectionConfig(section_type="heading", content="一、综述", level=1))
    sections.append(SectionConfig(
        section_type="paragraph",
        content=(
            f"本次运维巡检共检查 {summary.total} 大项，其中成功 {summary.passed} 项，"
            f"有问题 {summary.problem} 项。"
        ),
    ))
    sections.append(SectionConfig(
        section_type="paragraph",
        content=(
            f"网络检查：暂不检查（1 项，已排除）。"
        ),
    ))
    sections.append(SectionConfig(
        section_type="paragraph",
        content=(
            f"服务器：共 {summary.server_total} 项，成功 {summary.server_passed} 项，"
            f"有问题 {summary.server_problem} 项（其中执行失败/跳过 "
            f"{summary.server_failed_count} 项，阈值告警 {summary.server_warn_count} 项、"
            f"严重 {summary.server_crit_count} 项）。"
        ),
    ))
    sections.append(SectionConfig(
        section_type="paragraph",
        content=(
            f"接口：共 {summary.api_total} 项，成功 {summary.api_passed} 项，"
            f"有问题 {summary.api_problem} 项。"
        ),
    ))

    # 2. 网络
    sections.append(SectionConfig(section_type="heading", content="二、网络检查", level=1))
    sections.append(SectionConfig(
        section_type="paragraph", content="本报告暂不检查网络。",
    ))

    # 3. 服务器
    sections.append(SectionConfig(section_type="heading", content="三、服务器基本情况", level=1))
    for item in server_report.items:
        sections.append(SectionConfig(section_type="heading", content=item.business_name, level=2))
        # 元信息表
        sections.append(SectionConfig(
            section_type="table",
            table=TableSectionConfig(
                headers=["项目", "值"],
                rows=_server_meta_rows(item, ip_map.get(item.business_name)),
                column_widths=[3.0, 12.0],
            ),
        ))
        # SSH 失败/跳过: 不渲染字段明细表, 追加说明段
        if item.skipped or item.success is False:
            reason = item.error_message or item.inspection_error or "未执行"
            sections.append(SectionConfig(
                section_type="paragraph",
                content=f"该服务器本次巡检未执行（{reason}），按 1 项有问题计入。",
            ))
            continue
        # 字段明细表
        field_rows = _server_field_rows(item)
        sections.append(SectionConfig(
            section_type="table",
            table=TableSectionConfig(
                headers=["指标", "当前值", "阈值", "状态", "说明"],
                rows=field_rows,
                column_widths=[5.0, 3.0, 3.0, 2.0, 2.0],
                status_column=3,
            ),
        ))

    # 4. 接口
    sections.append(SectionConfig(section_type="heading", content="四、接口健康检查", level=1))
    for item in api_report.items:
        title = item.name or f"接口 {item.node_id}"
        sections.append(SectionConfig(section_type="heading", content=title, level=2))
        sections.append(SectionConfig(
            section_type="table",
            table=TableSectionConfig(
                headers=["项目", "值"],
                rows=_api_meta_rows(item),
                column_widths=[3.0, 12.0],
            ),
        ))
        if item.check_passed is None:
            sections.append(SectionConfig(
                section_type="paragraph",
                content="该接口节点缺失或已删除。",
            ))
            continue
        sections.append(SectionConfig(
            section_type="table",
            table=TableSectionConfig(
                headers=["类型", "期望", "实际", "通过", "说明"],
                rows=_api_assertion_rows(item),
                column_widths=[3.0, 2.5, 2.5, 2.0, 5.0],
            ),
        ))

    # 封面 / 目录
    cover = CoverConfig(
        title=CoverElementConfig(text="沈阳不动产运维报告"),
        date=CoverElementConfig(
            text=started_at.strftime("%Y年%m月%d日 %H:%M"),
        ),
        attachment=CoverElementConfig(text=f"任务：{schedule_name}", alignment="right"),
        footer_note=CoverElementConfig(
            text="本报告由系统自动生成",
            alignment="center",
        ),
    )
    toc = TocConfig(
        entries=[
            TocEntry(text="一、综述", level=0),
            TocEntry(text="二、网络检查", level=0),
            TocEntry(text="三、服务器基本情况", level=0),
            TocEntry(text="四、接口健康检查", level=0),
        ],
    )

    return ReportConfig(cover=cover, toc=toc, sections=sections)


# --------------------------------------------------------------------------
# 邮件正文构造(纯文本)
# --------------------------------------------------------------------------

def _fmt_dt(dt: datetime) -> str:
    """把 datetime 格式化为中文邮件时间戳;空值为 ``-``。"""
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else "-"


def build_ops_email_body(
    *,
    summary: OpsSummary,
    alerts: OpsAlerts,
    schedule_name: str,
    schedule_id: int,
    run_id: int,
    trigger_type: str,
    started_at: datetime,
    finished_at: Optional[datetime],
    report_file_name: Optional[str],
) -> str:
    """构造邮件正文文本(纯文本,不含 HTML)。

    段落结构:
        * 头部: 任务元数据
        * 综述
        * 关键告警(告警为空时省略整段)
        * 附件(无附件时省略整段)

    参数:
        summary: :class:`OpsSummary`。
        alerts: :class:`OpsAlerts`。
        schedule_name/schedule_id/run_id/trigger_type: 任务元数据。
        started_at/finished_at: 执行时间。
        report_file_name: Word 报告文件名;``None`` 时省略附件段落。

    返回:
        str: 邮件正文。
    """
    lines: List[str] = []
    lines.append(f"[{schedule_name}] 运维巡检报告")
    lines.append(f"任务 ID：{schedule_id}")
    lines.append(f"运行 ID：{run_id}")
    lines.append(f"触发方式：{trigger_type}")
    lines.append(f"开始时间：{_fmt_dt(started_at)}")
    lines.append(f"结束时间：{_fmt_dt(finished_at)}")
    lines.append("")
    lines.append("—— 综述 ——")
    lines.append(
        f"本次运维巡检共检查 {summary.total} 大项，其中成功 {summary.passed} 项，"
        f"有问题 {summary.problem} 项。"
    )
    lines.append("网络检查：暂不检查（1 项，已排除）。")
    lines.append(
        f"服务器：共 {summary.server_total} 项，成功 {summary.server_passed} 项，"
        f"有问题 {summary.server_problem} 项（其中执行失败/跳过 "
        f"{summary.server_failed_count} 项，阈值告警 {summary.server_warn_count} 项、"
        f"严重 {summary.server_crit_count} 项）。"
    )
    lines.append(
        f"接口：共 {summary.api_total} 项，成功 {summary.api_passed} 项，"
        f"有问题 {summary.api_problem} 项。"
    )

    if not alerts.is_empty:
        lines.append("")
        lines.append("—— 关键告警 ——")
        if alerts.server_warn_crit:
            lines.append("【服务器 · 阈值告警】")
            for item in alerts.server_warn_crit:
                lines.append(
                    f"- {item.business} · {item.metric} · {item.value} "
                    f"({item.threshold}) → {item.status}"
                )
        if alerts.api_failed:
            lines.append("【接口 · 检查失败】")
            for item in alerts.api_failed:
                lines.append(
                    f"- {item.business} · {item.metric} · {item.value} → {item.status}"
                )

    if report_file_name:
        lines.append("")
        lines.append("—— 附件 ——")
        lines.append(f"完整内容请参见附件 Word 报告：{report_file_name}")

    return "\n".join(lines)
