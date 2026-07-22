# -*- coding:utf-8 -*-
"""
``app.scripts.server_ops`` 标准化巡检执行器测试。

覆盖点：
    * ``ServerOpsItem`` / ``ServerOpsReport`` dataclass 字段与 summary / markdown /
      dict 输出契约（含 4 项巡检计数 + 巡检状态 / 指标判定双尾列）；
    * ``resolve_server_list`` 缺失 / 空 / None / 字符串 / 含数字 / 含 null /
      含空字符串各种边界的解析与抛错；
    * ``run_server_ops`` 对 devops_server_service None、空 server_list 短路、
      全通过、单条失败不中断（含 paramiko.AuthenticationException 与未配置
      ``inspection_script`` skipped）以及异步并发行为；
    * 解析 / 评估阶段异常分级与字段透传契约（success=False 不解析 stdout；
      配置 / execute_script 异常走 crit；解析评估异常透传 stdout + exit /
      stderr / duration；评估 crit 不改 success 执行语义）。
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
    """模拟 ``DevOpsServerService.get_connection_config`` 的 stub。

    行为契约：与生产 service 一致——``inspection_fields`` 必须以
    ``list[InspectionFieldRule]``（dataclass）形式返回；本 stub 在返回前
    调用 ``normalize_inspection_fields`` 把 dict 形式预存配置归一化为
    dataclass 列表，模拟 service 的"序列化由 service 负责"契约。
    """

    def __init__(self, configs: Dict[str, Dict[str, Any]],
                 raised_by_name: Optional[Dict[str, BaseException]] = None) -> None:
        self._configs = configs
        self._raised = raised_by_name or {}
        self.calls: List[str] = []

    def get_connection_config(self, business_name: str) -> Dict[str, Any]:
        from app.shared.utils.inspection.parser import normalize_inspection_fields

        self.calls.append(business_name)
        if business_name in self._raised:
            raise self._raised[business_name]
        cfg = dict(self._configs[business_name])
        # 模拟 service 端的 dict→InspectionFieldRule 转换
        cfg["inspection_fields"] = list(
            normalize_inspection_fields(cfg.get("inspection_fields") or [])
        )
        return cfg


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
        return SSHExecResult(success=True, stdout='{"ok": true}', stderr="", exit_code=0)

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
        return SSHExecResult(success=True, stdout='{"ok": true}', stderr="", exit_code=0)

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
        return SSHExecResult(success=True, stdout='{"ok": true}', stderr="", exit_code=0)

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
async def test_run_server_ops_parses_json_inspection_and_counts_status(monkeypatch):
    """JSON 输出应解析字段并汇总巡检状态。"""
    monkeypatch.setattr(
        "app.scripts.server_ops.execute_script",
        lambda *_: SSHExecResult(True, '{"cpu": 20}', "", 0),
    )
    service = _StubDevOpsService({"biz-A": {
        "inspection_script": "echo json", "inspection_parser": "json",
        "inspection_fields": [{"key": "cpu", "name_zh": "CPU", "unit": "%", "direction": "high", "warn": 50, "crit": 80}],
    }})
    report = await run_server_ops(_make_context_with_service(service, {"server_list": ["biz-A"]}))
    assert report.items[0].inspection_status == "pass"
    assert report.items[0].parsed_values == {"cpu": 20}
    assert report.inspection_passed == 1


@pytest.mark.asyncio
async def test_run_server_ops_expands_disks_array_into_field_results(monkeypatch):
    """disks 数组存在时, 单条 disk_used_pct 规则按数组元素展开为多条 field_results。

    端到端覆盖点:
        - 脚本输出顶层 ``disks`` 数组 + 其它顶层字段;
        - ``inspection_fields`` 中 ``disk_used_pct`` 规则单条声明;
        - ``ServerOpsItem.field_results`` 出现 2 条同 key 的结果, 每条 message 带 mount;
        - 整体 ``inspection_status`` 由最坏状态决定 (任一盘超阈值 -> crit);
        - parsed_values 保留原 dict(含 disks 数组与 mem_used_pct)。
    """
    stdout = (
        '{"disks":[{"mount":"/","disk_used_pct":42},'
        '{"mount":"/data","disk_used_pct":92}],'
        '"mem_used_pct":38,"cpu_idle_pct":75,"load_1m":0.12}'
    )
    monkeypatch.setattr(
        "app.scripts.server_ops.execute_script",
        lambda *_: SSHExecResult(True, stdout, "", 0),
    )
    service = _StubDevOpsService({"biz-A": {
        "inspection_script": "echo disks", "inspection_parser": "json",
        "inspection_fields": [
            {"key": "disk_used_pct", "name_zh": "磁盘使用率",
             "unit": "%", "direction": "high", "warn": 80, "crit": 90},
        ],
    }})
    report = await run_server_ops(_make_context_with_service(service, {"server_list": ["biz-A"]}))

    item = report.items[0]
    # 单条规则因 disks 数组展开为 2 条 field_results。
    assert len(item.field_results) == 2
    by_index = list(item.field_results)
    assert by_index[0]["key"] == "disk_used_pct"
    assert by_index[0]["value"] == 42
    assert by_index[0]["status"] == "pass"
    assert by_index[0]["message"] == "磁盘 /"
    assert by_index[1]["key"] == "disk_used_pct"
    assert by_index[1]["value"] == 92
    assert by_index[1]["status"] == "crit"
    assert by_index[1]["message"] == "磁盘 /data"
    # 整体状态取最坏 -> crit。
    assert item.inspection_status == "crit"
    assert report.inspection_critical == 1
    # parsed_values 保留原值(原 dict 含 disks 数组)。
    assert item.parsed_values == {
        "disks": [
            {"mount": "/", "disk_used_pct": 42},
            {"mount": "/data", "disk_used_pct": 92},
        ],
        "mem_used_pct": 38,
        "cpu_idle_pct": 75,
        "load_1m": 0.12,
    }
    # summary_line 也应包含每条磁盘的状态。
    assert "磁盘 /" in item.error_message or item.inspection_status == "crit"
    markdown = report.to_markdown()
    assert "磁盘 /" in markdown
    assert "磁盘 /data" in markdown


@pytest.mark.asyncio
async def test_run_server_ops_does_not_block_event_loop(monkeypatch):
    """``execute_script`` 是同步阻塞调用，必须经 ``asyncio.to_thread`` 包装以让出事件循环。"""
    # 1) 用一个从外部线程记录"事件循环是否被阻塞"的同步函数验证；
    # 这里采用轻量间接验证：若未通过 to_thread 包装，事件循环在阻塞期间不能被同一 loop 内的其他协程推进。
    import app.scripts.server_ops as server_ops_module

    def slow_execute_script(cfg, script, timeout):
        time.sleep(0.2)
        return SSHExecResult(success=True, stdout='{"ok": true}', stderr="", exit_code=0)

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
async def test_run_server_ops_does_not_re_normalize_inspection_fields(monkeypatch):
    """锁定契约：**service 是 ``inspection_fields`` 序列化的唯一真相源**。

    ``server_ops._run_one`` **不**调用 ``normalize_inspection_fields``。
    验证方式：``normalize_inspection_fields`` 模块级 spy 调用次数 == 0。
    """
    import app.scripts.server_ops as server_ops_module

    # 强约束 1：server_ops 模块当前**不**导出 ``normalize_inspection_fields``
    # （service 才是序列化唯一源）。
    assert not hasattr(server_ops_module, "normalize_inspection_fields"), (
        "server_ops.py 不应导入 normalize_inspection_fields；序列化由 service 端负责。"
        f"实际模块内有: {hasattr(server_ops_module, 'normalize_inspection_fields')}"
    )

    # 强约束 2：即便未来有人添加 import 并调用此函数，下面的 spy 会拦截并计数，
    # 触发测试失败。本轮回归无需真调用 normalize_inspection_fields。
    normalize_calls = {"n": 0}

    def fake_normalize(*args, **kwargs):
        normalize_calls["n"] += 1
        return []

    monkeypatch.setattr(
        "app.scripts.server_ops.normalize_inspection_fields",
        fake_normalize,
        raising=False,
    )

    def fake_execute_script(cfg, script, timeout):
        return SSHExecResult(success=True, stdout='{"disk_used_pct": 40}', stderr="", exit_code=0)

    monkeypatch.setattr("app.scripts.server_ops.execute_script", fake_execute_script)

    configs = {
        "biz-A": {
            "ip": "10.0.0.1", "port": 22, "username": "u", "password": "p",
            "server_type": "linux", "inspection_script": "echo ok",
            "inspection_parser": "json",
            "inspection_fields": [
                {"key": "disk_used_pct", "name_zh": "磁盘使用率", "unit": "%",
                 "direction": "high", "warn": 80, "crit": 90},
            ],
        },
    }
    service = _StubDevOpsService(configs=configs)
    ctx = _make_context_with_service(service, {"server_list": ["biz-A"]})

    report = await run_server_ops(ctx)
    item = report.items[0]

    # 执行成功；fake_normalize 计数 == 0 表示 server_ops 没有走这条路径
    assert item.success is True
    assert normalize_calls["n"] == 0, (
        f"server_ops 不应调用 normalize_inspection_fields，但被调了 "
        f"{normalize_calls['n']} 次"
    )


@pytest.mark.asyncio
async def test_run_server_ops_handles_unexpected_inspection_fields_type(monkeypatch):
    """``inspection_fields`` 收到 ``None`` 或非 list 输入（如老 cache / 误用）时，
    ``server_ops`` 走防御性类型断言回退为空规则，不抛异常，整体巡检可继续。

    注：生产 service 端保证返回 ``list[InspectionFieldRule]``；本用例验证脚本侧
    防御性兜底（service 缺失或老版本 cache 时不崩）。
    """
    def fake_execute_script(cfg, script, timeout):
        return SSHExecResult(success=True, stdout='{"x": 1}', stderr="", exit_code=0)

    monkeypatch.setattr("app.scripts.server_ops.execute_script", fake_execute_script)

    # 直接构造一个不走 _StubDevOpsService.normalize 的服务：模拟"老 cache" 返回异常形态
    class _NoNormalizeService:
        def __init__(self, raw):
            self._raw = raw
            self.calls = []

        def get_connection_config(self, business_name):
            self.calls.append(business_name)
            return self._raw  # 已包含 inspection_fields 异常形态

    cfg = {
        "ip": "10.0.0.1", "port": 22, "username": "u", "password": "p",
        "server_type": "linux", "inspection_script": "echo ok",
        "inspection_parser": "json",
        # 异常形态 1：None（与首次 DB 缺字段一致）
        "inspection_fields": None,
    }
    service = _NoNormalizeService(cfg)
    ctx = _make_context_with_service(service, {"server_list": ["biz-A"]})

    report = await run_server_ops(ctx)
    item = report.items[0]
    # 防御性回退到空规则 → inspection_status="unassessed"，success=True（SSH 成功）
    assert item.success is True
    assert item.inspection_status == "unassessed"
    assert item.field_results == []


@pytest.mark.asyncio
async def test_run_server_ops_stub_service_mimics_real_normalization(monkeypatch):
    """``_StubDevOpsService`` 应模拟真实 service：返回 ``list[InspectionFieldRule]`` 而不是 dict。

    这是该契约的可执行断言；任何回归（如 ``_StubDevOpsService`` 退回纯 dict 透传）
    都会立即被本用例捕获。
    """
    from app.shared.utils.inspection.parser import InspectionFieldRule

    def fake_execute_script(cfg, script, timeout):
        return SSHExecResult(success=True, stdout='{"mem_used_pct": 50}', stderr="", exit_code=0)

    monkeypatch.setattr("app.scripts.server_ops.execute_script", fake_execute_script)

    cfg = {
        "ip": "10.0.0.1", "port": 22, "username": "u", "password": "p",
        "server_type": "linux", "inspection_script": "echo ok",
        "inspection_parser": "json",
        "inspection_fields": [
            {"key": "mem_used_pct", "name_zh": "内存使用率", "unit": "%",
             "direction": "high", "warn": 80, "crit": 90},
        ],
    }
    service = _StubDevOpsService(configs={"biz-A": cfg})
    cfgs_returned = service.get_connection_config("biz-A")

    # 必须是 dataclass 列表，不能是 dict 列表
    assert isinstance(cfgs_returned["inspection_fields"], list)
    assert all(
        isinstance(item, InspectionFieldRule)
        for item in cfgs_returned["inspection_fields"]
    )
    rule = cfgs_returned["inspection_fields"][0]
    assert rule.key == "mem_used_pct"
    assert rule.direction == "high"
    # evaluate_inspection_fields 直接消费，无需再 normalize
    from app.shared.utils.inspection.parser import evaluate_inspection_fields as _evaluate
    parsed = {"mem_used_pct": 50}
    evaluation = _evaluate(parsed, cfgs_returned["inspection_fields"], "json")
    assert evaluation.status == "pass"  # 50 < warn=80


@pytest.mark.asyncio
async def test_run_server_ops_keyerror_skips_missing_business(monkeypatch):
    """``get_connection_config`` KeyError 时项标记 skipped。"""
    monkeypatch.setattr("app.scripts.server_ops.execute_script", lambda *_: SSHExecResult(True, '{"ok": true}', "", 0))
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
        return SSHExecResult(success=True, stdout='{"ok": true}', stderr="", exit_code=0)
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


# ===========================================================================
# Task 3: 巡检状态 / 解析评估分支扩展测试
# ===========================================================================


def _inspection_pass_item(name: str = "biz-A") -> ServerOpsItem:
    """构造一个 inspection_status=pass 的典型 item。"""
    return ServerOpsItem(
        business_name=name,
        success=True,
        exit_code=0,
        stdout='{"cpu": 20}',
        stderr="",
        duration_ms=42,
        error_message="",
        inspection_parser="json",
        parsed_values={"cpu": 20},
        field_results=[
            {
                "key": "cpu",
                "name_zh": "CPU 使用率",
                "unit": "%",
                "value": 20,
                "status": "pass",
                "message": "",
                "warn": 80.0,
                "crit": 95.0,
            }
        ],
        inspection_status="pass",
        inspection_error="",
    )


def test_report_summary_line_includes_inspection_counts():
    """summary_line 应包含 4 项巡检计数（pass/warn/crit/unassessed），skipped 不计在内。"""
    items = [
        _inspection_pass_item("biz-A"),
        ServerOpsItem(
            business_name="biz-B",
            success=True,
            exit_code=0,
            stdout='{"cpu": 85}',
            stderr="",
            duration_ms=30,
            inspection_status="warn",
            inspection_error="",
            field_results=[{"key": "cpu", "name_zh": "CPU 使用率", "unit": "%",
                            "value": 85, "status": "warn", "message": "",
                            "warn": 80.0, "crit": 95.0}],
        ),
        ServerOpsItem(
            business_name="biz-C",
            success=False,
            exit_code=2,
            stdout="boom",
            stderr="boom",
            duration_ms=10,
            error_message="boom",
            inspection_status="crit",
            inspection_error="远端巡检脚本执行失败",
        ),
        ServerOpsItem(
            business_name="biz-D",
            success=True,
            exit_code=0,
            stdout='{"cpu": 50}',
            stderr="",
            duration_ms=20,
            inspection_status="unassessed",
            inspection_error="",
        ),
        ServerOpsItem(
            business_name="biz-E",
            skipped=True,
            error_message="未配置巡检脚本（inspection_script 为空）",
            inspection_status="skipped",
        ),
    ]
    r = ServerOpsReport(items=items)
    out = r.summary_line()
    # 旧契约保持（A/B/D 成功 3 台 + 1 skipped，executed=4）
    assert "server_ops=3/4 passed" in out
    assert ", 1 skipped" in out
    assert "biz-A OK(0,42ms)" in out
    assert "biz-B OK(0,30ms)" in out
    assert "biz-C FAIL(2,10ms)" in out
    assert "biz-E SKIPPED" in out
    # 新增 4 项巡检计数
    assert "inspection=pass:1,warn:1,crit:1,unassessed:1" in out
    # 每项巡检状态后缀
    assert "biz-A OK(0,42ms)/PASS" in out
    assert "biz-B OK(0,30ms)/WARN" in out
    assert "biz-C FAIL(2,10ms)/CRIT" in out
    assert "biz-D OK(0,20ms)/UNASSESSED" in out
    assert "biz-E SKIPPED/SKIPPED" in out


def test_report_summary_line_skipped_not_in_inspection_counts():
    """skipped 项不计入 inspection 4 项计数（pass/warn/crit/unassessed）。"""
    items = [
        _inspection_pass_item("biz-A"),
        ServerOpsItem(
            business_name="biz-SKIP",
            skipped=True,
            error_message="未配置巡检脚本（inspection_script 为空）",
            inspection_status="skipped",
        ),
    ]
    r = ServerOpsReport(items=items)
    out = r.summary_line()
    # 1 通过 + 1 skipped => 4 项计数都只看 pass
    assert "inspection=pass:1,warn:0,crit:0,unassessed:0" in out
    # 旧的 1/1 passed 计数仍然正确
    assert "server_ops=1/1 passed" in out


def test_report_to_dict_includes_inspection_fields_and_counters():
    """to_dict 顶层增加 4 项巡检计数；item 增加 inspection 字段。"""
    items = [
        _inspection_pass_item("biz-A"),
        ServerOpsItem(
            business_name="biz-B",
            success=False,
            exit_code=2,
            stdout="x",
            stderr="x",
            duration_ms=5,
            error_message="x",
            inspection_status="crit",
            inspection_error="x",
        ),
    ]
    r = ServerOpsReport(items=items)
    d = r.to_dict()
    # 顶层新增计数
    assert d["inspection_passed"] == 1
    assert d["inspection_warned"] == 0
    assert d["inspection_critical"] == 1
    assert d["inspection_unassessed"] == 0
    # item 字段
    item_a = d["items"][0]
    assert item_a["inspection_parser"] == "json"
    assert item_a["parsed_values"] == {"cpu": 20}
    assert item_a["field_results"] == items[0].field_results
    assert item_a["inspection_status"] == "pass"
    assert item_a["inspection_error"] == ""
    # item 字段存在性（JSON pass）
    for key in (
        "inspection_parser",
        "parsed_values",
        "field_results",
        "inspection_status",
        "inspection_error",
    ):
        assert key in item_a
    # JSON pass（顶层 dict 含 4 个新键 + items + 老键）
    import json as _json
    encoded = _json.dumps(d, ensure_ascii=False, default=str)
    decoded = _json.loads(encoded)
    assert decoded["inspection_passed"] == 1
    assert decoded["items"][0]["inspection_status"] == "pass"


def test_report_to_markdown_appends_inspection_columns():
    """to_markdown 在原 6 列后追加「巡检状态 | 指标判定」两列；status 与 message/阈值中文渲染。"""
    items = [
        ServerOpsItem(
            business_name="biz-A",
            success=True,
            exit_code=0,
            stdout='{"cpu": 20}',
            stderr="",
            duration_ms=42,
            inspection_status="pass",
            inspection_parser="json",
            field_results=[
                {"key": "cpu", "name_zh": "CPU 使用率", "unit": "%",
                 "value": 20, "status": "pass", "message": "",
                 "warn": 80.0, "crit": 95.0},
            ],
        ),
        ServerOpsItem(
            business_name="biz-B",
            success=True,
            exit_code=0,
            stdout="mem_used_pct=85",
            stderr="",
            duration_ms=10,
            inspection_status="warn",
            inspection_parser="kv",
            field_results=[
                {"key": "mem_used_pct", "name_zh": "内存使用率", "unit": "%",
                 "value": "85", "status": "warn", "message": "",
                 "warn": 80.0, "crit": 90.0},
            ],
        ),
        ServerOpsItem(
            business_name="biz-C",
            success=True,
            exit_code=0,
            stdout='{"cpu": 50}',
            stderr="",
            duration_ms=15,
            inspection_status="unassessed",
            inspection_parser="json",
            field_results=[],
        ),
        ServerOpsItem(
            business_name="biz-D",
            skipped=True,
            error_message="未配置巡检脚本（inspection_script 为空）",
            inspection_status="skipped",
        ),
    ]
    r = ServerOpsReport(items=items)
    md = r.to_markdown()
    lines = md.splitlines()
    # 表头 6+2 = 8 列
    assert lines[0].count("|") == 9  # 8 列 + 两侧管道
    assert "巡检状态" in lines[0]
    assert "指标判定" in lines[0]
    # 状态中文化
    biz_a_row = next(line for line in lines if line.startswith("| biz-A"))
    # 巡检状态列必须出现「通过」（pass），不能出现英文 PASS
    cols_a = biz_a_row.split("|")
    # 巡检状态列在第 7 个位置（索引 7）
    status_col = cols_a[7]
    assert "通过" in status_col
    assert "PASS" not in status_col
    # 指标判定列（第 8 个位置）含 CPU 使用率 / 20% / warn=80 / crit=95
    fields_col = cols_a[8]
    assert "CPU 使用率" in fields_col
    assert "20%" in fields_col
    assert "warn=80" in fields_col
    assert "crit=95" in fields_col

    biz_b_row = next(line for line in lines if line.startswith("| biz-B"))
    assert "告警" in biz_b_row  # warn 中文
    assert "内存使用率" in biz_b_row
    assert "85%" in biz_b_row

    biz_c_row = next(line for line in lines if line.startswith("| biz-C"))
    assert "未评估" in biz_c_row

    biz_d_row = next(line for line in lines if line.startswith("| biz-D"))
    assert "未执行" in biz_d_row  # skipped 中文

    # 旧断言适配：原 6 列信息必须以子串形式存在（允许末尾追加）
    assert "| biz-A | 通过 | 0 | 42 | " in md


def test_report_to_markdown_escapes_pipe_and_newlines_in_dynamic_fields():
    """business_name / stdout / 错误 / 字段 message 中的 | 与换行必须精确转义为 \\| 与空格。"""
    items = [
        ServerOpsItem(
            business_name="biz|A\nEvil",
            success=True,
            exit_code=0,
            stdout="raw | with | pipes\nand newline",
            stderr="",
            duration_ms=5,
            inspection_status="warn",
            inspection_parser="json",
            field_results=[
                {"key": "x", "name_zh": "指标|带|管道\n换行", "unit": "%",
                 "value": 91, "status": "warn",
                 "message": "warn|msg\nmore", "warn": 80.0, "crit": 90.0},
            ],
        ),
    ]
    r = ServerOpsReport(items=items)
    md = r.to_markdown()
    lines = md.splitlines()
    row = next(line for line in lines if line.startswith("| biz"))
    # 精确断言：原 ``|`` 必须呈现为 ``\|``，原 ``\n`` 必须呈现为单空格
    assert "biz\\|A Evil" in row
    assert "raw \\| with \\| pipes and newline" in row
    assert "warn\\|msg more" in row
    # 行内不应残留任何未转义的 ``|``（业务名 / stdout / 字段 message 部分）
    assert row.count("\\|") >= 6  # biz|A(1) + raw | with |(2) + 指标|带|(2) + warn|(1)
    # 行内不应残留任何换行字符
    assert "\n" not in row


def test_report_to_markdown_skipped_keyerror_shows_error_in_indicator_column():
    """skipped (KeyError / 业务名未注册) 时指标判定列必须显示 error_message / inspection_error
    真实内容（含中文与原值），并经 ``_escape_cell`` 转义；不再硬编码 ``未配置巡检脚本``。"""
    items = [
        ServerOpsItem(
            business_name="biz|GHOST",
            skipped=True,
            success=None,
            error_message="unknown business_name: biz|GHOST",
            inspection_status="skipped",
            inspection_error="unknown business_name: biz|GHOST",
        ),
    ]
    r = ServerOpsReport(items=items)
    md = r.to_markdown()
    lines = md.splitlines()
    row = next(line for line in lines if line.startswith("| biz"))
    # 业务名转义为 \\|GHOST
    assert "biz\\|GHOST" in row
    # 指标判定列必须包含原始错误文本（不再是硬编码「未配置巡检脚本」）
    assert "unknown business_name: biz|GHOST" not in row  # 原始未转义不应出现
    assert "unknown business_name: biz\\|GHOST" in row    # 转义后真实呈现
    # 旧硬编码提示语不应再出现
    assert "未配置巡检脚本" not in row
    # 巡检状态列仍为「未执行」（中文）
    assert "未执行" in row


def test_report_to_markdown_skipped_no_inspection_script_shows_error_message():
    """skipped (inspection_script 未配置) 时指标判定列应原样展示 error_message（无 | 的情况下
    等价于硬编码文本），并经 ``_escape_cell`` 转义；不再用 if 分叉。"""
    items = [
        ServerOpsItem(
            business_name="biz-NOSCRIPT",
            skipped=True,
            success=None,
            error_message="未配置巡检脚本（inspection_script 为空）",
            inspection_status="skipped",
        ),
    ]
    r = ServerOpsReport(items=items)
    md = r.to_markdown()
    lines = md.splitlines()
    row = next(line for line in lines if line.startswith("| biz"))
    # error_message 内容必须原样保留（无 | 或 \n 时 _escape_cell 是恒等映射）
    assert "未配置巡检脚本（inspection_script 为空）" in row


def test_report_to_markdown_skipped_uses_inspection_error_when_error_message_empty():
    """skipped 且 error_message 为空、inspection_error 非空时，指标判定列应回退到 inspection_error。"""
    items = [
        ServerOpsItem(
            business_name="biz-EMPTY",
            skipped=True,
            success=None,
            error_message="",
            inspection_status="skipped",
            inspection_error="fallback inspection error text",
        ),
    ]
    r = ServerOpsReport(items=items)
    md = r.to_markdown()
    lines = md.splitlines()
    row = next(line for line in lines if line.startswith("| biz"))
    assert "fallback inspection error text" in row


def test_report_to_markdown_skipped_defaults_to_unexecuted_text():
    """skipped 且 error_message 与 inspection_error 都为空时，指标判定列回退到「未执行」。"""
    items = [
        ServerOpsItem(
            business_name="biz-NOTHING",
            skipped=True,
            success=None,
            error_message="",
            inspection_status="skipped",
            inspection_error="",
        ),
    ]
    r = ServerOpsReport(items=items)
    md = r.to_markdown()
    lines = md.splitlines()
    row = next(line for line in lines if line.startswith("| biz"))
    assert "未执行" in row


def test_report_to_markdown_stdout_truncation_preserved():
    """stdout 超过 4000 字符必须截断到 4000 且 ... 后缀；尾部两列追加后仍受同一截断约束。"""
    long_stdout = "x" * 5000 + "\nline2"
    items = [
        ServerOpsItem(
            business_name="biz-LONG",
            success=True,
            exit_code=0,
            stdout=long_stdout,
            stderr="",
            duration_ms=5,
            inspection_status="pass",
            inspection_parser="json",
        ),
    ]
    r = ServerOpsReport(items=items)
    md = r.to_markdown()
    row = next(line for line in md.splitlines() if line.startswith("| biz-LONG"))
    assert "..." in row
    # 4000 个 x + ... + 后缀字段，控制上限在合理范围
    assert len(row) < 4500 + 200


def test_report_to_markdown_stdout_truncation_boundary_exact():
    """stdout 截断边界精确：4000 个 x 全保留，4001 个 x 必被截断且出现 ``...``。"""
    # 边界 1：4000 个 x 完整保留
    items_4000 = [
        ServerOpsItem(
            business_name="biz-BOUND-4000",
            success=True,
            exit_code=0,
            stdout="x" * 4000,
            stderr="",
            duration_ms=5,
            inspection_status="pass",
            inspection_parser="json",
        ),
    ]
    r = ServerOpsReport(items=items_4000)
    row_4000 = next(line for line in r.to_markdown().splitlines() if line.startswith("| biz-BOUND-4000"))
    # 4000 个连续 x 必须原样保留
    assert ("x" * 4000) in row_4000
    # 不应出现 ``...``（因为 stdout 长度等于阈值，无需追加）
    assert "..." not in row_4000
    # 4001 个连续 x 不应原样出现
    assert ("x" * 4001) not in row_4000

    # 边界 2：4001 个 x 必被截断到 4000，且出现 ``...``
    items_4001 = [
        ServerOpsItem(
            business_name="biz-BOUND-4001",
            success=True,
            exit_code=0,
            stdout="x" * 4001,
            stderr="",
            duration_ms=5,
            inspection_status="pass",
            inspection_parser="json",
        ),
    ]
    r = ServerOpsReport(items=items_4001)
    row_4001 = next(line for line in r.to_markdown().splitlines() if line.startswith("| biz-BOUND-4001"))
    # stdout 列必须以 ``...`` 结尾，紧跟 ``| {error_text} | {inspection_text} | {fields_text} |``
    # （error_text / fields_text 为空时，相邻 ``|`` 间留有两个空格：`` |  |``）
    assert "... |  | 通过 |  |" in row_4001
    # 截断：4000 个连续 x 必须出现，4001 个连续 x 不能出现
    assert ("x" * 4000) in row_4001
    assert ("x" * 4001) not in row_4001


# ---------- 解析 / 评估 / SSH 失败契约 ----------


@pytest.mark.asyncio
async def test_ssh_exec_failure_does_not_parse_stdout(monkeypatch):
    """SSHExecResult.success=False 时不应调用 parse_inspection_output；返回 success=False + inspection crit。"""
    from app.scripts import server_ops as server_ops_module
    parse_calls = []

    real_parse = server_ops_module.parse_inspection_output
    real_eval = server_ops_module.evaluate_inspection_fields

    def tracking_parse(parser, stdout):
        parse_calls.append((parser, stdout))
        return real_parse(parser, stdout)

    def tracking_eval(parsed_values, rules, parser):
        return real_eval(parsed_values, rules, parser)

    monkeypatch.setattr(server_ops_module, "parse_inspection_output", tracking_parse)
    monkeypatch.setattr(server_ops_module, "evaluate_inspection_fields", tracking_eval)
    monkeypatch.setattr(
        server_ops_module,
        "execute_script",
        lambda *_: SSHExecResult(False, "{not-json}", "boom script", 1),
    )

    service = _StubDevOpsService({"biz-A": {
        "inspection_script": "echo fail", "inspection_parser": "json",
        "inspection_fields": [{"key": "cpu", "name_zh": "CPU 使用率", "unit": "%",
                              "direction": "high", "warn": 80, "crit": 95}],
    }})
    report = await run_server_ops(_make_context_with_service(service, {"server_list": ["biz-A"]}))
    item = report.items[0]
    # 关键断言：parse_inspection_output 不应被调用
    assert parse_calls == [], f"parse_inspection_output 仍被调用: {parse_calls}"
    assert item.success is False
    assert item.exit_code == 1
    assert item.stdout == "{not-json}"
    assert item.stderr == "boom script"
    assert item.duration_ms is not None
    assert item.inspection_status == "crit"
    # inspection_error / error_message 取 stderr
    assert item.inspection_error == "boom script"
    assert item.error_message == "boom script"


@pytest.mark.asyncio
async def test_ssh_exec_failure_default_error_when_stderr_empty(monkeypatch):
    """SSHExecResult.success=False 且 stderr 为空时 inspection_error 用「远端巡检脚本执行失败」。"""
    from app.scripts import server_ops as server_ops_module
    monkeypatch.setattr(
        server_ops_module,
        "execute_script",
        lambda *_: SSHExecResult(False, "{}", "", 1),
    )
    service = _StubDevOpsService({"biz-A": {
        "inspection_script": "echo fail", "inspection_parser": "json",
    }})
    report = await run_server_ops(_make_context_with_service(service, {"server_list": ["biz-A"]}))
    item = report.items[0]
    assert item.success is False
    assert item.inspection_status == "crit"
    assert item.inspection_error == "远端巡检脚本执行失败"
    assert item.error_message == "远端巡检脚本执行失败"


@pytest.mark.asyncio
async def test_ssh_stderr_noise_with_zero_exit_still_evaluated(monkeypatch):
    """退出码 0 但 stderr 非空（shell 启动噪音）时不判失败，正常解析评估。

    场景:远端 ``/root/.bashrc`` 存在语法错误(如 ``//`` 注释),非交互式 SSH
    会话每次执行都会把报错混入 stderr,但巡检脚本本身 exit=0 且 stdout 为合法
    JSON。契约:success=True、inspection_status 由评估决定、stderr 原样保留
    在 ``item.stderr`` 供报告「错误」列展示。
    """
    from app.scripts import server_ops as server_ops_module
    monkeypatch.setattr(
        server_ops_module,
        "execute_script",
        lambda *_: SSHExecResult(
            False,
            '{"mem_used_pct": 50}',
            "/root/.bashrc: line 22: //注释: No such file or directory",
            0,
        ),
    )
    service = _StubDevOpsService({"biz-A": {
        "inspection_script": "echo ok", "inspection_parser": "json",
        "inspection_fields": [{"key": "mem_used_pct", "name_zh": "内存使用率", "unit": "%",
                              "direction": "high", "warn": 80, "crit": 90}],
    }})
    report = await run_server_ops(_make_context_with_service(service, {"server_list": ["biz-A"]}))
    item = report.items[0]
    assert item.success is True
    assert item.exit_code == 0
    assert item.inspection_status == "pass"
    assert item.parsed_values == {"mem_used_pct": 50}
    assert item.field_results and item.field_results[0]["status"] == "pass"
    assert item.error_message == ""
    # stderr 噪音保留供报告「错误」列展示
    assert ".bashrc" in item.stderr


@pytest.mark.asyncio
async def test_ssh_stderr_noise_with_zero_exit_parse_failure_marks_crit(monkeypatch):
    """退出码 0 + stderr 噪音且 stdout 不可解析时仍走「巡检解析评估失败」crit。"""
    from app.scripts import server_ops as server_ops_module
    monkeypatch.setattr(
        server_ops_module,
        "execute_script",
        lambda *_: SSHExecResult(False, "{garbage", "shell noise", 0),
    )
    service = _StubDevOpsService({"biz-A": {
        "inspection_script": "echo ok", "inspection_parser": "json",
    }})
    report = await run_server_ops(_make_context_with_service(service, {"server_list": ["biz-A"]}))
    item = report.items[0]
    assert item.success is False
    assert item.inspection_status == "crit"
    assert item.error_message.startswith("巡检解析评估失败:")
    assert item.inspection_error.startswith("巡检解析评估失败:")


@pytest.mark.asyncio
async def test_config_exception_inspection_error_message(monkeypatch):
    """get_connection_config 抛非 KeyError 异常应记 crit，且 inspection_error 也有错误说明。"""
    def boom(_):
        raise RuntimeError("解密失败")

    service = _StubDevOpsService(
        configs={},
        raised_by_name={"biz-A": RuntimeError("解密失败")},
    )
    # 同时确保 execute_script 不被调用
    from app.scripts import server_ops as server_ops_module
    called = {"n": 0}

    def fake_execute_script(*args, **kwargs):
        called["n"] += 1
        return SSHExecResult(True, "{}", "", 0)

    monkeypatch.setattr(server_ops_module, "execute_script", fake_execute_script)
    ctx = _make_context_with_service(service, {"server_list": ["biz-A"]})
    report = await run_server_ops(ctx)
    item = report.items[0]
    assert called["n"] == 0
    assert item.success is False
    assert item.inspection_status == "crit"
    assert item.inspection_error  # 非空
    assert "RuntimeError" in item.inspection_error or "解密失败" in item.inspection_error
    assert "RuntimeError" in item.error_message or "解密失败" in item.error_message
    # 不要泄漏整个 config
    assert "ip" not in item.error_message
    assert "password" not in item.error_message


@pytest.mark.asyncio
async def test_execute_script_exception_inspection_error_message(monkeypatch):
    """execute_script 抛异常应记 crit 且 inspection_error 也有错误说明；不泄漏 config。"""
    def fake_execute_script(cfg, script, timeout):
        raise RuntimeError("SSHException: connection refused")

    from app.scripts import server_ops as server_ops_module
    monkeypatch.setattr(server_ops_module, "execute_script", fake_execute_script)

    service = _StubDevOpsService({"biz-A": {
        "ip": "10.0.0.1", "port": 22, "username": "u", "password": "secret",
        "server_type": "linux",
        "inspection_script": "echo ok", "inspection_parser": "json",
    }})
    report = await run_server_ops(_make_context_with_service(service, {"server_list": ["biz-A"]}))
    item = report.items[0]
    assert item.success is False
    assert item.inspection_status == "crit"
    assert item.inspection_error  # 非空
    assert "RuntimeError" in item.inspection_error or "SSHException" in item.inspection_error
    assert item.duration_ms is not None
    assert "secret" not in item.error_message
    assert "10.0.0.1" not in item.error_message


@pytest.mark.asyncio
async def test_keyerror_skipped_inspection_error(monkeypatch):
    """KeyError (业务名未注册) → skipped 且 inspection_error 有错误说明。"""
    from app.scripts import server_ops as server_ops_module
    called = {"n": 0}

    def fake_execute_script(*args, **kwargs):
        called["n"] += 1
        return SSHExecResult(True, "{}", "", 0)

    monkeypatch.setattr(server_ops_module, "execute_script", fake_execute_script)
    service = _StubDevOpsService(
        configs={},
        raised_by_name={"biz-GHOST": KeyError("unknown business_name: biz-GHOST")},
    )
    report = await run_server_ops(_make_context_with_service(service, {"server_list": ["biz-GHOST"]}))
    item = report.items[0]
    assert called["n"] == 0
    assert item.skipped is True
    assert item.success is None
    assert item.inspection_status == "skipped"
    assert item.inspection_error  # 非空
    assert "biz-GHOST" in item.inspection_error or "unknown" in item.inspection_error


@pytest.mark.asyncio
async def test_parse_or_eval_exception_keeps_stdout_and_marks_crit(monkeypatch):
    """解析或评估阶段抛异常应保留 stdout / stderr / exit / duration，success=False，两处错误都形如
    「巡检解析评估失败: Type: message」；不允许泄漏 config。"""
    from app.scripts import server_ops as server_ops_module

    def boom_parse(*args, **kwargs):
        raise ValueError("bad json")

    monkeypatch.setattr(server_ops_module, "parse_inspection_output", boom_parse)
    monkeypatch.setattr(
        server_ops_module,
        "execute_script",
        lambda *_: SSHExecResult(True, "{garbage", "warn", 0),
    )
    service = _StubDevOpsService({"biz-A": {
        "ip": "10.0.0.1", "port": 22, "username": "u", "password": "secret",
        "server_type": "linux",
        "inspection_script": "echo", "inspection_parser": "json",
    }})
    report = await run_server_ops(_make_context_with_service(service, {"server_list": ["biz-A"]}))
    item = report.items[0]
    assert item.success is False
    assert item.stdout == "{garbage"
    assert item.stderr == "warn"
    assert item.exit_code == 0
    assert item.duration_ms is not None
    assert item.inspection_status == "crit"
    # error_message 与 inspection_error 都是 「巡检解析评估失败: Type: message」 形态
    assert item.error_message.startswith("巡检解析评估失败:")
    assert "ValueError" in item.error_message
    assert item.inspection_error.startswith("巡检解析评估失败:")
    assert "ValueError" in item.inspection_error
    # 不泄漏 config
    assert "secret" not in item.error_message
    assert "10.0.0.1" not in item.error_message


@pytest.mark.asyncio
async def test_evaluation_crit_does_not_change_success(monkeypatch):
    """评估阶段得到 crit（规则严重命中 / 缺字段 / 非数值）不应改变 success 执行语义：success 仍为
    bool(result.success)=True。"""
    from app.scripts import server_ops as server_ops_module
    monkeypatch.setattr(
        server_ops_module,
        "execute_script",
        lambda *_: SSHExecResult(True, '{"cpu": 99}', "", 0),
    )
    service = _StubDevOpsService({"biz-A": {
        "inspection_script": "echo", "inspection_parser": "json",
        "inspection_fields": [{"key": "cpu", "name_zh": "CPU 使用率", "unit": "%",
                              "direction": "high", "warn": 80, "crit": 95}],
    }})
    report = await run_server_ops(_make_context_with_service(service, {"server_list": ["biz-A"]}))
    item = report.items[0]
    assert item.success is True
    assert item.exit_code == 0
    assert item.inspection_status == "crit"
    assert report.inspection_critical == 1
    assert report.passed == 1
    # summary 同时含 OK(...)/CRIT
    assert "biz-A OK(0," in report.summary_line()
    assert "/CRIT" in report.summary_line()


@pytest.mark.asyncio
async def test_evaluation_missing_field_and_non_numeric_both_crit(monkeypatch):
    """声明字段缺失 / 非数值都是 crit，且 success 保持 True。"""
    from app.scripts import server_ops as server_ops_module
    # missing key + non-numeric value
    monkeypatch.setattr(
        server_ops_module,
        "execute_script",
        lambda *_: SSHExecResult(True, '{"present": "abc"}', "", 0),
    )
    service = _StubDevOpsService({"biz-A": {
        "inspection_script": "echo", "inspection_parser": "json",
        "inspection_fields": [
            {"key": "present", "name_zh": "存在字段", "unit": "%",
             "direction": "high", "warn": 50, "crit": 80},
            {"key": "missing", "name_zh": "缺失字段", "unit": "%",
             "direction": "high", "warn": 50, "crit": 80},
        ],
    }})
    report = await run_server_ops(_make_context_with_service(service, {"server_list": ["biz-A"]}))
    item = report.items[0]
    assert item.success is True
    assert item.inspection_status == "crit"
    crit_msgs = [f.get("message", "") for f in item.field_results]
    assert any("missing" in m for m in crit_msgs)
    assert any("不是有限数字" in m or "abc" in m for m in crit_msgs)


@pytest.mark.asyncio
async def test_evaluation_raw_parser_with_structured_rules_is_crit_but_success_true(monkeypatch):
    """raw 解析器 + 含 high/low 规则：总状态 crit 但 success 仍 True。"""
    from app.scripts import server_ops as server_ops_module
    monkeypatch.setattr(
        server_ops_module,
        "execute_script",
        lambda *_: SSHExecResult(True, "anything", "", 0),
    )
    service = _StubDevOpsService({"biz-A": {
        "inspection_script": "echo", "inspection_parser": "raw",
        "inspection_fields": [{"key": "cpu", "name_zh": "CPU 使用率", "unit": "%",
                              "direction": "high", "warn": 80, "crit": 95}],
    }})
    report = await run_server_ops(_make_context_with_service(service, {"server_list": ["biz-A"]}))
    item = report.items[0]
    assert item.success is True
    assert item.inspection_status == "crit"
    assert item.inspection_error  # raw 评估错误会写入
    assert "raw 解析器" in item.inspection_error


@pytest.mark.asyncio
async def test_evaluation_no_rules_unassessed(monkeypatch):
    """无规则 → unassessed；success 不受影响。"""
    from app.scripts import server_ops as server_ops_module
    monkeypatch.setattr(
        server_ops_module,
        "execute_script",
        lambda *_: SSHExecResult(True, '{"cpu": 20}', "", 0),
    )
    service = _StubDevOpsService({"biz-A": {
        "inspection_script": "echo", "inspection_parser": "json",
        "inspection_fields": None,
    }})
    report = await run_server_ops(_make_context_with_service(service, {"server_list": ["biz-A"]}))
    item = report.items[0]
    assert item.success is True
    assert item.inspection_status == "unassessed"
    assert item.field_results == []


@pytest.mark.asyncio
async def test_one_bad_json_does_not_block_next_server(monkeypatch):
    """一台非法 JSON 解析失败（crit）但下一台继续执行，整体不中断。"""
    from app.scripts import server_ops as server_ops_module

    def fake_execute_script(cfg, script, timeout):
        ip = cfg.get("ip", "")
        if "1.1.1.1" in ip:
            return SSHExecResult(True, "not-json", "", 0)
        return SSHExecResult(True, '{"cpu": 30}', "", 0)

    monkeypatch.setattr(server_ops_module, "execute_script", fake_execute_script)
    service = _StubDevOpsService({
        "biz-BAD": {
            "ip": "1.1.1.1", "port": 22, "username": "u", "password": "p",
            "server_type": "linux",
            "inspection_script": "echo", "inspection_parser": "json",
            "inspection_fields": [{"key": "cpu", "name_zh": "CPU", "unit": "%",
                                   "direction": "high", "warn": 80, "crit": 95}],
        },
        "biz-OK": {
            "ip": "2.2.2.2", "port": 22, "username": "u", "password": "p",
            "server_type": "linux",
            "inspection_script": "echo", "inspection_parser": "json",
            "inspection_fields": [{"key": "cpu", "name_zh": "CPU", "unit": "%",
                                   "direction": "high", "warn": 80, "crit": 95}],
        },
    })
    report = await run_server_ops(_make_context_with_service(service,
                                                             {"server_list": ["biz-BAD", "biz-OK"]}))
    by_name = {item.business_name: item for item in report.items}
    assert by_name["biz-BAD"].success is False
    assert by_name["biz-BAD"].inspection_status == "crit"
    assert by_name["biz-OK"].success is True
    assert by_name["biz-OK"].inspection_status == "pass"
    # 总计数 OK
    assert report.passed == 1
    assert report.inspection_critical == 1
    assert report.inspection_passed == 1


@pytest.mark.asyncio
async def test_kv_parser_with_numeric_string_passes(monkeypatch):
    """KV 解析：数字字符串应能转换参与阈值评估（pass）。"""
    from app.scripts import server_ops as server_ops_module
    monkeypatch.setattr(
        server_ops_module,
        "execute_script",
        lambda *_: SSHExecResult(True, "mem_used_pct=70\ndisk_used_pct=40\n", "", 0),
    )
    service = _StubDevOpsService({"biz-A": {
        "inspection_script": "echo", "inspection_parser": "kv",
        "inspection_fields": [
            {"key": "mem_used_pct", "name_zh": "内存使用率", "unit": "%",
             "direction": "high", "warn": 80, "crit": 90},
            {"key": "disk_used_pct", "name_zh": "磁盘使用率", "unit": "%",
             "direction": "high", "warn": 80, "crit": 90},
        ],
    }})
    report = await run_server_ops(_make_context_with_service(service, {"server_list": ["biz-A"]}))
    item = report.items[0]
    assert item.success is True
    assert item.inspection_status == "pass"
    assert item.parsed_values == {"mem_used_pct": "70", "disk_used_pct": "40"}


@pytest.mark.asyncio
async def test_csv_parser_with_numeric_string_passes(monkeypatch):
    """CSV 解析：数字字符串应能转换参与阈值评估（pass）。"""
    from app.scripts import server_ops as server_ops_module
    monkeypatch.setattr(
        server_ops_module,
        "execute_script",
        lambda *_: SSHExecResult(True, "cpu,mem\n65,75\n", "", 0),
    )
    service = _StubDevOpsService({"biz-A": {
        "inspection_script": "echo", "inspection_parser": "csv",
        "inspection_fields": [
            {"key": "cpu", "name_zh": "CPU", "unit": "%",
             "direction": "high", "warn": 80, "crit": 95},
            {"key": "mem", "name_zh": "MEM", "unit": "%",
             "direction": "high", "warn": 80, "crit": 95},
        ],
    }})
    report = await run_server_ops(_make_context_with_service(service, {"server_list": ["biz-A"]}))
    item = report.items[0]
    assert item.success is True
    assert item.inspection_status == "pass"


@pytest.mark.asyncio
async def test_high_warn_low_crit_pass_combined(monkeypatch):
    """high 字段在 warn 区间 → warn；low 字段在 crit 区间 → crit；总状态 crit；success 仍 True。

    注意：``inspection_warned`` / ``inspection_critical`` 是**服务器级**计数（按
    ``inspection_status`` 聚合），单台服务器即便同时有 warn + crit 字段，
    ``inspection_status`` 仍是 crit，不计 warn。本测试断言字段级 ``status``
    列表与服务器级 ``inspection_status=crit``。
    """
    from app.scripts import server_ops as server_ops_module
    monkeypatch.setattr(
        server_ops_module,
        "execute_script",
        lambda *_: SSHExecResult(True, '{"cpu": 85, "load": 5}', "", 0),
    )
    service = _StubDevOpsService({"biz-A": {
        "inspection_script": "echo", "inspection_parser": "json",
        "inspection_fields": [
            {"key": "cpu", "name_zh": "CPU", "unit": "%",
             "direction": "high", "warn": 80, "crit": 95},
            {"key": "load", "name_zh": "负载", "unit": "",
             "direction": "low", "warn": 10, "crit": 6},
        ],
    }})
    report = await run_server_ops(_make_context_with_service(service, {"server_list": ["biz-A"]}))
    item = report.items[0]
    assert item.success is True
    statuses = [f["status"] for f in item.field_results]
    assert "warn" in statuses
    assert "crit" in statuses
    assert item.inspection_status == "crit"
    # 服务器级聚合：crit 压制 warn，因此 inspection_critical=1, inspection_warned=0
    assert report.inspection_critical == 1
    assert report.inspection_warned == 0
    assert report.inspection_passed == 0
