# -*- coding:utf-8 -*-
"""``app.scripts.ops.ops_report`` 单元测试。"""
from app.scripts.ops.ops_report import OpsSummary, OpsAlerts, OpsAlertItem, compute_ops_summary
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
