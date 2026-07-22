# -*- coding:utf-8 -*-
"""
``app.scripts.api_check`` 标准化检查器测试。

覆盖点：
    * ``ApiCheckItem`` / ``ApiCheckReport`` dataclass 字段与 summary/to_markdown/
      to_dict 输出契约；
    * ``resolve_api_list`` 缺失 / 空 / None / 字符串 / 含数字 / 含空串 / 含非整数串
      各种边界的解析与抛错；
    * ``run_api_checks`` 对 api_config_service None、空 api_list 全通过、部分失败、
      节点缺失不中断整体的行为契约。
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytest

from app.scripts.api_check import (
    ApiCheckItem,
    ApiCheckReport,
    resolve_api_list,
    run_api_checks,
)
from app.scripts.base import ScriptContext, ScriptExecutionError


# ===== 单元契约 =====


def _make_context(script_args: Optional[Dict[str, Any]] = None) -> ScriptContext:
    """构造用于单测的最小 ScriptContext（log 用一次性 logger）。"""
    import logging
    return ScriptContext(
        schedule_id=1,
        run_id=1,
        session_id="task-1-abc",
        schedule_name="api_check 单测",
        script_args=script_args or {},
        log_logger=logging.getLogger("api_check_unit_test"),
        started_at=datetime(2026, 7, 22, 10, 0, 0),
        trigger_type="manual",
    )


def test_api_check_report_empty_default():
    """空报告默认 total/passed/failed/skipped 全为 0。"""
    r = ApiCheckReport()
    assert r.items == []
    assert r.total == 0
    assert r.passed == 0
    assert r.failed == 0
    assert r.skipped == 0
    assert r.summary_line() == ""
    assert r.to_markdown() == ""


def test_api_check_report_summary_line_mixed():
    """混合通过/未通过/缺失时 summary_line 包含分部计数与逐项简述。"""
    items = [
        ApiCheckItem(node_id=10, name="查询接口", path="业务系统", check_passed=True,
                     http_status=200, duration_ms=45, error_message=""),
        ApiCheckItem(node_id=11, name="上报接口", path="", check_passed=False,
                     http_status=404, duration_ms=30, error_message="期望200实际404"),
        ApiCheckItem(node_id=99, name="", path="", check_passed=None,
                     error_message="接口节点不存在或已被删除"),
    ]
    r = ApiCheckReport(items=items)
    out = r.summary_line()
    assert "api_check=1/2 passed, 1 skipped" in out
    assert "id=10 OK 200/45ms" in out
    assert "id=11 FAIL 404/30ms" in out
    assert "id=99 MISSING" in out


def test_api_check_report_summary_line_no_passing():
    """全部未通过（含网络异常）时不存在 through 计入。"""
    items = [
        ApiCheckItem(node_id=11, name="上报接口", path="", check_passed=False,
                     http_status=None, duration_ms=None,
                     error_message="ConnectError: timeout"),
    ]
    r = ApiCheckReport(items=items)
    out = r.summary_line()
    assert "api_check=0/1 passed" in out
    assert "ERR/-" in out


def test_api_check_report_to_markdown_table():
    """to_markdown 生成包含表头与每行数据的 Markdown 表格。"""
    items = [
        ApiCheckItem(node_id=10, name="查询接口", path="业务系统", check_passed=True,
                     http_status=200, duration_ms=45, error_message=""),
        ApiCheckItem(node_id=11, name="上报接口", path="", check_passed=False,
                     http_status=404, duration_ms=30, error_message="期望200实际404"),
        ApiCheckItem(node_id=99, name="", path="", check_passed=None,
                     error_message="接口节点不存在或已被删除"),
    ]
    r = ApiCheckReport(items=items)
    md = r.to_markdown()
    assert md.startswith("| 接口 | 路径 |")
    assert "| 查询接口 | 业务系统 | 200 | 45 | 通过 |" in md
    assert "| 上报接口 |  | 404 | 30 | 未通过 | 期望200实际404 |" in md
    assert "| id=99 |  |  |  | 未执行 | 接口节点不存在或已被删除 |" in md


def test_api_check_report_to_dict_round_trip_counters():
    """to_dict 含 items 数组与 four 计数，items 元素可 JSON 序列化。"""
    items = [
        ApiCheckItem(node_id=10, name="查询", path="a", check_passed=True,
                     http_status=200, duration_ms=10, assertion_results=[{"type": "status_code", "passed": True}]),
    ]
    r = ApiCheckReport(items=items)
    d = r.to_dict()
    assert d["total"] == 1 and d["passed"] == 1 and d["failed"] == 0 and d["skipped"] == 0
    assert isinstance(d["items"], list) and len(d["items"]) == 1
    assert d["items"][0]["node_id"] == 10
    assert d["items"][0]["assertion_results"] == [{"type": "status_code", "passed": True}]


# ===== resolve_api_list 单元测试 =====


def test_resolve_api_list_missing_or_none_returns_empty():
    """缺失键 / None 时返回空列表，不抛错。"""
    assert resolve_api_list({}) == []
    assert resolve_api_list({"api_list": None}) == []


def test_resolve_api_list_empty_returns_empty():
    """显式空数组时返回空列表。"""
    assert resolve_api_list({"api_list": []}) == []


def test_resolve_api_list_strings_to_ints():
    """合法字符串 id 应转换为 int。"""
    assert resolve_api_list({"api_list": ["10", "11"]}) == [10, 11]


def test_resolve_api_list_not_list_raises():
    """``api_list`` 不是列表时应抛 ``ScriptExecutionError`` 且消息含字段名。"""
    with pytest.raises(ScriptExecutionError, match="api_list"):
        resolve_api_list({"api_list": "10"})


@pytest.mark.parametrize(
    "bad_value",
    [
        ["10", 123],
        ["10", None],
        ["10", ""],
        ["10", {"id": 11}],
        ["abc"],
    ],
    ids=["with-int", "with-null", "with-empty", "with-object", "non-integer-string"],
)
def test_resolve_api_list_invalid_elements_raise(bad_value):
    """元素非字符串 / 空串 / 非整数串时应抛 ``ScriptExecutionError``。"""
    with pytest.raises(ScriptExecutionError, match="api_list"):
        resolve_api_list({"api_list": bad_value})


# ===== run_api_checks 行为测试（用 stub service） =====


class _StubApiConfigService:
    """仅记录调用并按预设返回 send_request 假数据的 stub。"""

    def __init__(self, nodes: List[Dict[str, Any]], results_by_id: Dict[int, Dict[str, Any]],
                 raised_by_id: Optional[Dict[int, BaseException]] = None) -> None:
        self._nodes = nodes
        self._results = results_by_id
        self._raised = raised_by_id or {}
        self.get_tree_calls = 0
        self.send_request_calls: List[int] = []

    async def get_tree(self) -> List[Dict[str, Any]]:
        self.get_tree_calls += 1
        return self._nodes

    async def send_request(self, node_id: int) -> Dict[str, Any]:
        self.send_request_calls.append(node_id)
        if node_id in self._raised:
            raise self._raised[node_id]
        return self._results[node_id]


def _make_context_with_service(service: Any, script_args: Dict[str, Any]) -> ScriptContext:
    ctx = _make_context(script_args)
    ctx.api_config_service = service
    return ctx


@pytest.mark.asyncio
async def test_run_api_checks_empty_args_returns_empty_without_service_call():
    """api_list 为空（缺失 / 空数组）时即便 service 不存在也不抛错，不调用 get_tree。"""
    ctx = _make_context()  # api_config_service=None
    report = await run_api_checks(ctx)
    assert report.items == []


@pytest.mark.asyncio
async def test_run_api_checks_non_empty_raises_when_service_none():
    """api_list 非空但 api_config_service=None 时抛 ScriptExecutionError，含 api_list。"""
    from app.shared.utils.api_config_service import ApiConfigNotFoundError

    ctx = _make_context(script_args={"api_list": ["10"]})  # api_config_service=None
    with pytest.raises(ScriptExecutionError, match="api_config_service"):
        await run_api_checks(ctx)


@pytest.mark.asyncio
async def test_run_api_checks_all_pass():
    """api_list 中所有接口通过时报告含逐项 passed=True。"""
    nodes = [
        {"id": 10, "parent_id": None, "node_type": "api", "name": "查询接口", "sort_order": 0},
        {"id": 11, "parent_id": None, "node_type": "api", "name": "上报接口", "sort_order": 1},
    ]
    results = {
        10: {"run_id": 1, "http_status": 200, "duration_ms": 12,
             "response_body": "{}", "check_passed": True,
             "assertion_results": [{"type": "status_code", "passed": True}], "error_message": ""},
        11: {"run_id": 2, "http_status": 200, "duration_ms": 15,
             "response_body": "{}", "check_passed": True,
             "assertion_results": [{"type": "status_code", "passed": True}], "error_message": ""},
    }
    service = _StubApiConfigService(nodes=nodes, results_by_id=results)
    ctx = _make_context_with_service(service, {"api_list": ["10", "11"]})

    report = await run_api_checks(ctx)

    assert service.get_tree_calls == 1
    assert service.send_request_calls == [10, 11]
    assert report.total == 2 and report.passed == 2 and report.failed == 0 and report.skipped == 0
    assert all(item.check_passed is True for item in report.items)
    # path 为根节点下应为空字符串
    assert report.items[0].path == "" and report.items[0].name == "查询接口"


@pytest.mark.asyncio
async def test_run_api_checks_path_walks_parents():
    """parent 链应正确拼出父路径。"""
    nodes = [
        {"id": 1, "parent_id": None, "node_type": "folder", "name": "业务系统", "sort_order": 0},
        {"id": 2, "parent_id": 1, "node_type": "folder", "name": "子系统", "sort_order": 0},
        {"id": 10, "parent_id": 2, "node_type": "api", "name": "查询接口", "sort_order": 0},
    ]
    results = {
        10: {"run_id": 1, "http_status": 200, "duration_ms": 5,
             "check_passed": True, "assertion_results": [], "error_message": ""},
    }
    service = _StubApiConfigService(nodes=nodes, results_by_id=results)
    ctx = _make_context_with_service(service, {"api_list": ["10"]})

    report = await run_api_checks(ctx)
    assert report.items[0].path == "业务系统/子系统"
    assert report.items[0].name == "查询接口"


@pytest.mark.asyncio
async def test_run_api_checks_missing_node_does_not_interrupt():
    """节点缺失应得到 skipped 项（check_passed=None），不影响其它项。"""
    from app.shared.utils.api_config_service import ApiConfigNotFoundError

    nodes = [
        {"id": 10, "parent_id": None, "node_type": "api", "name": "查询接口", "sort_order": 0},
    ]
    results = {
        10: {"run_id": 1, "http_status": 200, "duration_ms": 5,
             "check_passed": True, "assertion_results": [], "error_message": ""},
    }
    service = _StubApiConfigService(nodes=nodes, results_by_id=results)
    ctx = _make_context_with_service(service, {"api_list": ["10", "99"]})

    report = await run_api_checks(ctx)

    assert report.total == 2
    assert report.passed == 1
    assert report.skipped == 1
    # 缺失项的 check_passed 应为 None 且 error_message 含提示
    missing = next(item for item in report.items if item.node_id == 99)
    assert missing.check_passed is None
    assert "不存在" in missing.error_message or "删除" in missing.error_message


@pytest.mark.asyncio
async def test_run_api_checks_send_request_exception_marks_failed():
    """send_request 抛 ApiConfigNotFoundError → skipped；其它异常 → failed。"""
    nodes = [
        {"id": 10, "parent_id": None, "node_type": "api", "name": "查询接口", "sort_order": 0},
        {"id": 11, "parent_id": None, "node_type": "api", "name": "上报接口", "sort_order": 1},
    ]
    results = {
        10: {"run_id": 1, "http_status": 200, "duration_ms": 5,
             "check_passed": True, "assertion_results": [], "error_message": ""},
    }
    from app.shared.utils.api_config_service import ApiConfigNotFoundError
    raised = {11: ApiConfigNotFoundError("api config 11 not found")}
    service = _StubApiConfigService(nodes=nodes, results_by_id=results, raised_by_id=raised)
    ctx = _make_context_with_service(service, {"api_list": ["10", "11"]})

    report = await run_api_checks(ctx)

    assert report.total == 2
    assert report.passed == 1
    assert report.skipped == 1
    # 11 号被 ApiConfigNotFoundError 标记为 skipped
    item11 = next(item for item in report.items if item.node_id == 11)
    assert item11.check_passed is None
    assert "not found" in item11.error_message


@pytest.mark.asyncio
async def test_run_api_checks_other_exception_marks_failed():
    """send_request 抛网络/超时等非预期异常应标记 failed，不中断整体循环。"""
    nodes = [
        {"id": 10, "parent_id": None, "node_type": "api", "name": "查询", "sort_order": 0},
        {"id": 11, "parent_id": None, "node_type": "api", "name": "上报", "sort_order": 1},
    ]
    results = {
        10: {"run_id": 1, "http_status": 200, "duration_ms": 5,
             "check_passed": True, "assertion_results": [], "error_message": ""},
    }
    raised = {11: RuntimeError("ConnectError: timeout")}
    service = _StubApiConfigService(nodes=nodes, results_by_id=results, raised_by_id=raised)
    ctx = _make_context_with_service(service, {"api_list": ["10", "11"]})

    report = await run_api_checks(ctx)

    assert report.total == 2
    assert report.passed == 1
    assert report.failed == 1
    failed_item = next(item for item in report.items if item.node_id == 11)
    assert failed_item.check_passed is False
    assert "ConnectError" in failed_item.error_message or "RuntimeError" in failed_item.error_message
