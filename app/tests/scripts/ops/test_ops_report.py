# -*- coding:utf-8 -*-
"""``app.scripts.ops.ops_report`` 单元测试。"""
from datetime import datetime

from app.shared.utils.report.word.config import (
    ReportConfig, SectionConfig, TableSectionConfig,
)
from app.scripts.ops.ops_report import OpsSummary, OpsAlerts, OpsAlertItem, compute_ops_summary
from app.scripts.ops.ops_report import compute_ops_alerts
from app.scripts.ops.ops_report import resolve_server_ip_map
from app.scripts.ops.ops_report import build_ops_report_config
from app.scripts.api_check import ApiCheckItem, ApiCheckReport
from app.scripts.server_ops import ServerOpsItem, ServerOpsReport


def _server(biz, status="pass", success=True, skipped=False):
    return ServerOpsItem(
        business_name=biz, success=success, inspection_status=status, skipped=skipped,
    )


def _api(node_id, name, check_passed=True):
    return ApiCheckItem(node_id=node_id, name=name, path="/x", check_passed=check_passed)


def test_ops_summary_dataclass_basic():
    s = OpsSummary(
        total=5, passed=3, problem=2,
        server_total=3, server_passed=2, server_problem=1,
        server_failed_count=1, server_warn_count=1, server_crit_count=0,
        api_total=2, api_passed=1, api_problem=1,
    )
    assert s.total == 5
    assert s.passed == 3
    assert s.problem == 2


def test_ops_alerts_is_empty():
    assert OpsAlerts(server_warn_crit=[], api_failed=[]).is_empty is True
    a = OpsAlerts(
        server_warn_crit=[OpsAlertItem(business="x", metric="y", value="z",
                                       threshold="-", status="WARN", detail="")],
        api_failed=[],
    )
    assert a.is_empty is False


def test_compute_summary_all_passed():
    srv = ServerOpsReport(items=[_server("A"), _server("B")])
    api = ApiCheckReport(items=[_api("1", "X"), _api("2", "Y")])
    s = compute_ops_summary(srv, api)
    assert s.total == 4 and s.passed == 4 and s.problem == 0
    assert s.server_total == 2 and s.server_passed == 2 and s.server_problem == 0
    assert s.api_total == 2 and s.api_passed == 2 and s.api_problem == 0


def test_compute_summary_with_failures():
    srv = ServerOpsReport(items=[
        _server("A", "pass", True),
        _server("B", "crit", False),
        _server("C", "skipped", None, skipped=True),
    ])
    api = ApiCheckReport(items=[
        _api("1", "X", check_passed=True),
        _api("2", "Y", check_passed=False),
        _api("3", "Z", check_passed=None),
    ])
    s = compute_ops_summary(srv, api)
    assert s.total == 6
    assert s.server_passed == 1 and s.server_problem == 2
    assert s.server_failed_count == 2  # B(crit,fail) + C(skipped)
    assert s.server_crit_count == 1
    assert s.api_passed == 1 and s.api_problem == 2


def test_compute_summary_empty():
    s = compute_ops_summary(ServerOpsReport(), ApiCheckReport())
    assert s.total == 0 and s.passed == 0 and s.problem == 0


def test_compute_alerts_warn_crit_only():
    srv = ServerOpsReport(items=[
        ServerOpsItem(
            business_name="A", success=True, inspection_status="pass",
            field_results=[
                {"key": "cpu", "name_zh": "CPU 使用率", "unit": "%",
                 "value": 75.2, "warn": 80, "crit": 90,
                 "status": "warn", "message": ""},
                {"key": "disk", "name_zh": "磁盘使用率", "unit": "%",
                 "value": 92.0, "warn": 80, "crit": 90,
                 "status": "crit", "message": "磁盘 /data"},
            ],
        ),
        ServerOpsItem(
            business_name="B", success=True, inspection_status="pass",
            field_results=[
                {"key": "cpu", "name_zh": "CPU 使用率", "unit": "%",
                 "value": 30.0, "warn": 80, "crit": 90,
                 "status": "pass", "message": ""},
            ],
        ),
    ])
    api = ApiCheckReport(items=[
        ApiCheckItem(node_id="1", name="OK", path="/ok", check_passed=True),
        ApiCheckItem(node_id="2", name="FAIL", path="/x", check_passed=False,
                     http_status=500, duration_ms=30),
    ])
    alerts = compute_ops_alerts(srv, api)
    assert len(alerts.server_warn_crit) == 2
    assert alerts.server_warn_crit[0].business == "A"
    assert alerts.server_warn_crit[0].status == "WARN"
    assert alerts.server_warn_crit[1].status == "CRIT"
    assert len(alerts.api_failed) == 1
    assert alerts.api_failed[0].business == "FAIL"
    assert alerts.api_failed[0].status == "FAIL"
    assert alerts.is_empty is False


def test_compute_alerts_excludes_skipped_and_missing():
    srv = ServerOpsReport(items=[
        ServerOpsItem(business_name="A", success=False, skipped=True,
                      inspection_status="skipped"),
    ])
    api = ApiCheckReport(items=[
        ApiCheckItem(node_id="1", name="M", path="/x", check_passed=None),
    ])
    alerts = compute_ops_alerts(srv, api)
    assert alerts.server_warn_crit == []
    assert alerts.api_failed == []
    assert alerts.is_empty is True


# --------------------------------------------------------------------------
# resolve_server_ip_map 反查 IP
# --------------------------------------------------------------------------

class _FakeService:
    """最小桩:模拟 DevOpsServerService.get_connection_config。"""

    def __init__(self, mapping):
        self._mapping = mapping

    def get_connection_config(self, biz):
        if biz in self._mapping:
            return {"host": self._mapping[biz]}
        raise KeyError(biz)


def test_resolve_ip_map_returns_hosts():
    srv = ServerOpsReport(items=[
        ServerOpsItem(business_name="A"),
        ServerOpsItem(business_name="B"),
    ])
    svc = _FakeService({"A": "10.0.0.1", "B": "10.0.0.2"})
    m = resolve_server_ip_map(svc, srv)
    assert m == {"A": "10.0.0.1", "B": "10.0.0.2"}


def test_resolve_ip_map_handles_missing_service():
    srv = ServerOpsReport(items=[ServerOpsItem(business_name="A")])
    m = resolve_server_ip_map(None, srv)
    assert m == {"A": None}


def test_resolve_ip_map_handles_key_error():
    srv = ServerOpsReport(items=[ServerOpsItem(business_name="X")])
    svc = _FakeService({})
    m = resolve_server_ip_map(svc, srv)
    assert m == {"X": None}


def test_resolve_ip_map_handles_exception():
    class _Boom:
        def get_connection_config(self, biz):
            raise RuntimeError("boom")
    srv = ServerOpsReport(items=[ServerOpsItem(business_name="X")])
    m = resolve_server_ip_map(_Boom(), srv)
    assert m == {"X": None}


def test_resolve_ip_map_reads_ip_field():
    """真实 DevOpsServerService 返回 ip 字段,非 host。

    参见 ``app/shared/utils/devops_server_service.py:357``:`get_connection_config`
    返回的 dict 包含 ``ip`` 键,旧版代码只读 ``host`` 会导致所有 IP 都为 None。
    """
    class _RealLikeService:
        def get_connection_config(self, biz):
            return {"ip": "10.0.0.5", "port": 22, "username": "u"}

    srv = ServerOpsReport(items=[ServerOpsItem(business_name="A")])
    m = resolve_server_ip_map(_RealLikeService(), srv)
    assert m == {"A": "10.0.0.5"}


def test_resolve_ip_map_prefers_ip_over_host_alias():
    """``ip`` 字段优先于 ``host`` 别名,避免被历史别名字段误导。"""
    class _MixedService:
        def get_connection_config(self, biz):
            return {"ip": "10.0.0.7", "host": "192.168.0.1", "port": 22}

    srv = ServerOpsReport(items=[ServerOpsItem(business_name="A")])
    m = resolve_server_ip_map(_MixedService(), srv)
    assert m == {"A": "10.0.0.7"}


# --------------------------------------------------------------------------
# build_ops_report_config 报告配置构造
# --------------------------------------------------------------------------

def _build_summary():
    return compute_ops_summary(ServerOpsReport(items=[
        ServerOpsItem(business_name="A", success=True, inspection_status="pass"),
    ]), ApiCheckReport())


def test_build_report_config_structure():
    summary = _build_summary()
    alerts = compute_ops_alerts(ServerOpsReport(), ApiCheckReport())
    cfg = build_ops_report_config(
        summary=summary,
        alerts=alerts,
        server_report=ServerOpsReport(items=[
            ServerOpsItem(business_name="A", success=True, inspection_status="pass"),
        ]),
        api_report=ApiCheckReport(),
        ip_map={"A": "10.0.0.1"},
        schedule_name="运维巡检",
        started_at=datetime(2026, 7, 22, 15, 0, 0),
    )
    assert isinstance(cfg, ReportConfig)
    titles = [s.content for s in cfg.sections if s.section_type == "heading"]
    assert "一、综述" in titles
    assert "二、网络检查" in titles
    assert "三、服务器基本情况" in titles
    assert "四、接口健康检查" in titles
    # 业务名作为二级标题
    assert "A" in titles
    # 表格 SectionConfig
    tables = [s for s in cfg.sections if s.section_type == "table"]
    assert len(tables) >= 1
    # 封面标题
    assert cfg.cover is not None
    assert cfg.cover.title.text == "沈阳不动产运维报告"


def test_build_report_config_table_section_headers():
    summary = _build_summary()
    alerts = compute_ops_alerts(ServerOpsReport(), ApiCheckReport())
    cfg = build_ops_report_config(
        summary=summary, alerts=alerts,
        server_report=ServerOpsReport(items=[
            ServerOpsItem(business_name="A", success=True, inspection_status="pass"),
        ]),
        api_report=ApiCheckReport(),
        ip_map={"A": "10.0.0.1"},
        schedule_name="x", started_at=datetime(2026, 7, 22),
    )
    tables = [s for s in cfg.sections if s.section_type == "table"]
    # 元信息表 + 字段明细表 = 至少 1 个
    headers_combined = []
    for t in tables:
        headers_combined.append(t.table.headers[0])
    # 字段表首列应为「指标」或「项目」之一
    assert any(h in ["指标", "项目"] for h in headers_combined)
