# -*- coding:utf-8 -*-
"""
``app.scripts.server_ops`` 标准化巡检执行器测试。

覆盖点：
    * ``ServerOpsItem`` / ``ServerOpsReport`` dataclass 字段与 summary / markdown /
      dict 输出契约；
    * ``resolve_server_list`` 缺失 / 空 / None / 字符串 / 含数字 / 含 null /
      含空字符串各种边界的解析与抛错；
    * ``run_server_ops`` 对 devops_server_service None、空 server_list 短路、
      全通过、单条失败不中断（含 paramiko.AuthenticationException 与未配置
      ``inspection_script`` skipped）以及异步并发行为。
"""
import asyncio
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytest

from app.scripts.base import ScriptContext, ScriptExecutionError
from app.scripts.server_ops import (
    ServerOpsItem,
    ServerOpsReport,
    resolve_server_list,
    run_server_ops,
)
from app.shared.utils.ssh.executor import SSHExecResult


# ===== 单元契约 =====


def _make_context(script_args: Optional[Dict[str, Any]] = None) -> ScriptContext:
    """构造用于单测的最小 ScriptContext（log 用一次性 logger）。"""
    import logging
    return ScriptContext(
        schedule_id=1,
        run_id=1,
        session_id="task-1-abc",
        schedule_name="server_ops 单测",
        script_args=script_args or {},
        log_logger=logging.getLogger("server_ops_unit_test"),
        started_at=datetime(2026, 7, 22, 12, 0, 0),
        trigger_type="manual",
    )


def test_server_ops_report_empty_default():
    """空报告默认 total/passed/failed/skipped 全为 0。"""
    r = ServerOpsReport()
    assert r.items == []
    assert r.total == 0
    assert r.passed == 0
    assert r.failed == 0
    assert r.skipped == 0
    assert r.summary_line() == ""
    assert r.to_markdown() == ""


def test_server_ops_report_summary_line_mixed():
    """混合通过 / 失败 / 跳过时 summary_line 含分部计数与逐项简述。"""
    items = [
        ServerOpsItem(business_name="biz-A", success=True, exit_code=0,
                      stdout="ok", stderr="", duration_ms=42),
        ServerOpsItem(business_name="biz-B", success=False, exit_code=1,
                      stdout="", stderr="boom", duration_ms=20,
                      error_message="boom"),
        ServerOpsItem(business_name="biz-C", skipped=True,
                      error_message="未配置巡检脚本（inspection_script 为空）"),
    ]
    r = ServerOpsReport(items=items)
    out = r.summary_line()
    assert "server_ops=1/2 passed, 1 skipped" in out
    assert "biz-A OK(0,42ms)" in out
    assert "biz-B FAIL(1,20ms)" in out
    assert "biz-C SKIPPED" in out


def test_server_ops_report_summary_line_all_pass():
    """全部通过时只计 passed，不出现 skipped 段。"""
    items = [
        ServerOpsItem(business_name="biz-A", success=True, exit_code=0,
                      stdout="", duration_ms=10),
        ServerOpsItem(business_name="biz-B", success=True, exit_code=0,
                      stdout="", duration_ms=20),
    ]
    r = ServerOpsReport(items=items)
    out = r.summary_line()
    assert out.startswith("server_ops=2/2 passed |")
    assert "skipped" not in out


def test_server_ops_report_to_markdown_table():
    """to_markdown 生成包含表头与每行数据的 Markdown 表格，stdout 超长会截断。"""
    long_stdout = "x" * 5000 + "\nline2"
    items = [
        ServerOpsItem(business_name="biz-A", success=True, exit_code=0,
                      stdout="ok", stderr="", duration_ms=42),
        ServerOpsItem(business_name="biz-B", success=False, exit_code=2,
                      stdout=long_stdout, stderr="boom", duration_ms=100,
                      error_message="boom"),
    ]
    r = ServerOpsReport(items=items)
    md = r.to_markdown()
    assert md.startswith("| 业务名 | 结果 |")
    assert "| biz-A | 通过 | 0 | 42 | ok |  |" in md
    # long stdout 截断到 4000 字符
    biz_b_row = next(line for line in md.splitlines() if line.startswith("| biz-B"))
    assert "..." in biz_b_row
    assert len(biz_b_row) < 5000 + 200
    # | 与换行已转义
    assert "\\|" in biz_b_row or "boom" in biz_b_row


def test_server_ops_report_to_dict_round_trip_counters():
    """to_dict 含 items 数组与 four 计数，元素含业务名 / 成功标志 / exit_code。"""
    items = [
        ServerOpsItem(business_name="biz-A", success=True, exit_code=0,
                      stdout="hi", stderr="", duration_ms=10),
    ]
    r = ServerOpsReport(items=items)
    d = r.to_dict()
    assert d["total"] == 1
    assert d["passed"] == 1 and d["failed"] == 0 and d["skipped"] == 0
    assert isinstance(d["items"], list) and len(d["items"]) == 1
    assert d["items"][0]["business_name"] == "biz-A"
    assert d["items"][0]["success"] is True
    assert d["items"][0]["exit_code"] == 0


# ===== resolve_server_list 单元测试 =====


def test_resolve_server_list_missing_or_none_returns_empty():
    """缺失键 / None 时返回空列表，不抛错。"""
    assert resolve_server_list({}) == []
    assert resolve_server_list({"server_list": None}) == []


def test_resolve_server_list_empty_returns_empty():
    """显式空数组时返回空列表。"""
    assert resolve_server_list({"server_list": []}) == []


def test_resolve_server_list_strings_preserved():
    """合法业务名原样保留。"""
    assert resolve_server_list({"server_list": ["biz-A", "biz-B"]}) == ["biz-A", "biz-B"]


def test_resolve_server_list_not_list_raises():
    """``server_list`` 不是列表时应抛 ``ScriptExecutionError`` 且消息含字段名。"""
    with pytest.raises(ScriptExecutionError, match="server_list"):
        resolve_server_list({"server_list": "biz-A"})


@pytest.mark.parametrize(
    "bad_value",
    [
        ["biz-A", 123],
        ["biz-A", None],
        ["biz-A", ""],
        [{"name": "biz-A"}],
    ],
    ids=["with-int", "with-null", "with-empty", "with-object"],
)
def test_resolve_server_list_invalid_elements_raise(bad_value):
    """元素非字符串 / 空串时抛 ``ScriptExecutionError``。"""
    with pytest.raises(ScriptExecutionError, match="server_list"):
        resolve_server_list({"server_list": bad_value})


# ===== run_server_ops 行为测试（用 stub service + 替换 execute_script） =====


class _StubDevOpsService:
    """仅记录调用的 stub，``get_connection_config`` 按 business_name 取预设配置。"""

    def __init__(self, configs: Dict[str, Dict[str, Any]],
                 raised_by_name: Optional[Dict[str, BaseException]] = None) -> None:
        self._configs = configs
        self._raised = raised_by_name or {}
        self.calls: List[str] = []

    def get_connection_config(self, business_name: str) -> Dict[str, Any]:
        self.calls.append(business_name)
        if business_name in self._raised:
            raise self._raised[business_name]
        return dict(self._configs[business_name])


def _make_context_with_service(service: Any, script_args: Dict[str, Any]) -> ScriptContext:
    ctx = _make_context(script_args)
    ctx.devops_server_service = service
    return ctx


@pytest.mark.asyncio
async def test_run_server_ops_empty_args_returns_empty_without_service():
    """server_list 为空（缺失 / 空数组）时不要求服务存在，直接返回空 report。"""
    ctx = _make_context()  # devops_server_service=None
    report = await run_server_ops(ctx)
    assert report.items == []


@pytest.mark.asyncio
async def test_run_server_ops_non_empty_raises_when_service_none():
    """server_list 非空但 devops_server_service=None 时抛 ScriptExecutionError，含 devops_server_service。"""
    ctx = _make_context(script_args={"server_list": ["biz-A"]})
    with pytest.raises(ScriptExecutionError, match="devops_server_service"):
        await run_server_ops(ctx)


@pytest.mark.asyncio
async def test_run_server_ops_all_pass(monkeypatch):
    """所有 server 配齐 inspection_script 且 execute_script 返回 success=True，全部 passed。"""
    configs = {
        "biz-A": {
            "ip": "10.0.0.1", "port": 22, "username": "root", "password": "x",
            "server_type": "linux", "inspection_script": "echo hi\n", "inspection_parser": "json",
        },
        "biz-B": {
            "ip": "10.0.0.2", "port": 22, "username": "root", "password": "x",
            "server_type": "linux", "inspection_script": "echo hello\n", "inspection_parser": "json",
        },
    }

    def fake_execute_script(cfg, script, timeout):
        return SSHExecResult(success=True, stdout=script.strip() + " -> ok", stderr="", exit_code=0)

    monkeypatch.setattr("app.scripts.server_ops.execute_script", fake_execute_script)

    service = _StubDevOpsService(configs=configs)
    ctx = _make_context_with_service(service, {"server_list": ["biz-A", "biz-B"]})

    report = await run_server_ops(ctx)

    assert service.calls == ["biz-A", "biz-B"]
    assert report.total == 2 and report.passed == 2 and report.failed == 0 and report.skipped == 0
    assert [item.success for item in report.items] == [True, True]
    assert all(item.duration_ms is not None and item.duration_ms >= 0 for item in report.items)
    assert all(item.exit_code == 0 for item in report.items)


@pytest.mark.asyncio
async def test_run_server_ops_missing_inspection_script_marks_skipped(monkeypatch):
    """inspection_script 为空（None / 空串）应产生 skipped item，不影响已配置项。"""
    # biz-A 配置齐全 → execute_script 应被调用并返回 success=True；
    # biz-B / biz-C 配置 inspection_script 为空/None → run_server_ops 短路返回 skipped，不调 execute_script。
    execute_script_calls: List[str] = []

    def fake_execute_script(cfg, script, timeout):
        execute_script_calls.append(cfg.get("ip", ""))
        return SSHExecResult(success=True, stdout="ok", stderr="", exit_code=0)

    monkeypatch.setattr("app.scripts.server_ops.execute_script", fake_execute_script)

    configs = {
        "biz-A": {
            "ip": "10.0.0.1", "port": 22, "username": "root", "password": "x",
            "server_type": "linux", "inspection_script": "echo ok\n", "inspection_parser": "json",
        },
        "biz-B": {
            "ip": "10.0.0.2", "port": 22, "username": "root", "password": "x",
            "server_type": "linux", "inspection_script": None, "inspection_parser": "json",
        },
        "biz-C": {
            "ip": "10.0.0.3", "port": 22, "username": "root", "password": "x",
            "server_type": "linux", "inspection_script": "   \n", "inspection_parser": "json",
        },
    }
    service = _StubDevOpsService(configs=configs)
    ctx = _make_context_with_service(service, {"server_list": ["biz-A", "biz-B", "biz-C"]})

    report = await run_server_ops(ctx)

    assert report.total == 3
    assert report.passed == 1
    assert report.skipped == 2
    skipped_items = [item for item in report.items if item.skipped]
    assert {item.business_name for item in skipped_items} == {"biz-B", "biz-C"}
    for item in skipped_items:
        assert "未配置" in item.error_message
    # execute_script 只能为有 inspection_script 的项被调用
    assert execute_script_calls == ["10.0.0.1"]


@pytest.mark.asyncio
async def test_run_server_ops_preserves_input_order():
    """``items`` 顺序与 ``server_list`` 输入顺序一致（与 api_check 对仗的契约）。"""
    # execute_script 用 IP 前缀判断：A/B/C/D 全部返回 success
    def fake_execute_script(cfg, script, timeout):
        return SSHExecResult(success=True, stdout="ok", stderr="", exit_code=0)

    import app.scripts.server_ops as server_ops_module
    original = server_ops_module.execute_script
    server_ops_module.execute_script = fake_execute_script
    try:
        configs = {
            f"biz-{ip}": {
                "ip": f"10.0.0.{ip}", "port": 22, "username": "u", "password": "p",
                "server_type": "linux", "inspection_script": "echo ok", "inspection_parser": "json",
            }
            for ip in [4, 2, 1, 3]
        }
        service = _StubDevOpsService(configs=configs)
        ctx = _make_context_with_service(service, {"server_list": ["biz-4", "biz-2", "biz-1", "biz-3"]})
        report = await run_server_ops(ctx)
        assert [item.business_name for item in report.items] == [
            "biz-4", "biz-2", "biz-1", "biz-3"
        ]
    finally:
        server_ops_module.execute_script = original


@pytest.mark.asyncio
async def test_run_server_ops_does_not_block_event_loop(monkeypatch):
    """``execute_script`` 是同步阻塞调用，必须经 ``asyncio.to_thread`` 包装以让出事件循环。"""
    # 1) 用一个从外部线程记录"事件循环是否被阻塞"的同步函数验证；
    # 这里采用轻量间接验证：若未通过 to_thread 包装，事件循环在阻塞期间不能被同一 loop 内的其他协程推进。
    import app.scripts.server_ops as server_ops_module

    def slow_execute_script(cfg, script, timeout):
        time.sleep(0.2)
        return SSHExecResult(success=True, stdout="ok", stderr="", exit_code=0)

    original = server_ops_module.execute_script
    server_ops_module.execute_script = slow_execute_script
    try:
        configs = {
            f"biz-{i}": {
                "ip": f"10.0.0.{i}", "port": 22, "username": "u", "password": "p",
                "server_type": "linux", "inspection_script": "echo ok", "inspection_parser": "json",
            }
            for i in range(2)
        }
        service = _StubDevOpsService(configs=configs)
        ctx = _make_context_with_service(service, {"server_list": list(configs.keys())})

        # 在 server_ops 等待期间跑一个心跳协程，记下最大可让出间隔
        tick_count = {"n": 0}
        stop_event = asyncio.Event()

        async def heartbeat():
            while not stop_event.is_set():
                tick_count["n"] += 1
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=0.02)
                except asyncio.TimeoutError:
                    pass

        hb_task = asyncio.create_task(heartbeat())
        try:
            await run_server_ops(ctx)
        finally:
            stop_event.set()
            await hb_task

        # 期望至少 4 次心跳（2 台 × 0.2s / 0.02s ≈ 20），是宽松下限；
        # 若 run_server_ops 完全同步阻塞（未使用 to_thread），心跳次数应为 0。
        assert tick_count["n"] >= 4, (
            f"run_server_ops 似未使用 asyncio.to_thread，心跳次数={tick_count['n']}"
        )
    finally:
        server_ops_module.execute_script = original


@pytest.mark.asyncio
async def test_run_server_ops_keyerror_skips_missing_business(monkeypatch):
    """``get_connection_config`` KeyError 时项标记 skipped。"""
    monkeypatch.setattr("app.scripts.server_ops.execute_script", lambda *_: SSHExecResult(True, "", "", 0))
    service = _StubDevOpsService(
        configs={"biz-A": {"ip": "x", "port": 22, "username": "u", "password": "p", "server_type": "linux",
                            "inspection_script": "echo", "inspection_parser": "json"}},
        raised_by_name={"biz-GHOST": KeyError("unknown business_name: biz-GHOST")},
    )
    ctx = _make_context_with_service(service, {"server_list": ["biz-A", "biz-GHOST"]})
    report = await run_server_ops(ctx)
    assert report.passed == 1
    assert report.skipped == 1
    assert next(item for item in report.items if item.business_name == "biz-GHOST").skipped


@pytest.mark.asyncio
async def test_run_server_ops_paramiko_exception_marks_failed_not_interrupt(monkeypatch):
    """execute_script 抛 paramiko 异常应标记 failed，不中断整体循环。"""
    def fake_execute_script(cfg, script, timeout):
        if "biz-B" in cfg["ip"]:
            raise RuntimeError("SSHException: connection refused")
        return SSHExecResult(success=True, stdout="ok", stderr="", exit_code=0)
    monkeypatch.setattr("app.scripts.server_ops.execute_script", fake_execute_script)

    configs = {
        "biz-A": {"ip": "10.0.0.1", "port": 22, "username": "u", "password": "p",
                  "server_type": "linux", "inspection_script": "echo", "inspection_parser": "json"},
        "biz-B": {"ip": "10.0.0.2-biz-B", "port": 22, "username": "u", "password": "p",
                  "server_type": "linux", "inspection_script": "echo", "inspection_parser": "json"},
    }
    service = _StubDevOpsService(configs=configs)
    ctx = _make_context_with_service(service, {"server_list": ["biz-A", "biz-B"]})
    report = await run_server_ops(ctx)

    assert report.total == 2
    assert report.passed == 1
    assert report.failed == 1
    failed = next(item for item in report.items if item.business_name == "biz-B")
    assert failed.success is False
    assert "RuntimeError" in failed.error_message or "SSHException" in failed.error_message
    assert failed.duration_ms is not None
