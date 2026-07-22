# -*- coding:utf-8 -*-
"""``app.scripts.ops.ops_report`` 单元测试。"""
from app.scripts.ops.ops_report import OpsSummary, OpsAlerts, OpsAlertItem, compute_ops_summary
from app.scripts.ops.ops_report import compute_ops_alerts
from app.scripts.ops.ops_report import resolve_server_ip_map
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
