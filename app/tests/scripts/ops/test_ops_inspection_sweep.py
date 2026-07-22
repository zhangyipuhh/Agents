# -*- coding:utf-8 -*-
"""
``app.scripts.ops.ops_inspection_sweep`` 运维巡检扫描脚本测试。

覆盖点:
    * 模块可正常导入,``@register_script`` 自动注册到全局 registry;
    * ``run`` 签名与 ``params_schema`` 契约(``server_list`` + ``api_list``);
    * 空入参:``server_list`` 与 ``api_list`` 均缺失/空数组时,正文仅含任务元数据,
      日志仅输出「无巡检项」+「无检查项」+ 收尾完成行;
    * ``server_list`` 路径:逐字段打印 ``parsed_values`` + 每条 ``inspection_fields``
      规则的 ``(key / name_zh / value / warn / crit / status)`` 比对明细,
      skipped 项不打印字段明细;
    * ``api_list`` 路径:逐接口打印 ``http_status / duration_ms / check_passed`` +
      每条断言的 ``(type / passed / detail)``;
    * SSH 失败 / 解析失败 / 评估失败仍输出日志,但不抛异常中断整体;
    * summary 返回值在 server/api 非空时分别追加 ``server_ops=...`` 与
      ``api_check=...`` 行。

测试隔离:autouse fixture 在每个用例前后清空 ``_SCRIPT_REGISTRY``,
避免与 ``hello_script`` / 其他脚本测试相互污染。
"""
from __future__ import annotations

import importlib
import inspect
import logging
import typing
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from app.scripts.api_check import ApiCheckItem, ApiCheckReport
from app.scripts.base import ScriptContext, ScriptExecutionError
from app.scripts.registry import clear_registry, get_registered_script
from app.scripts.server_ops import ServerOpsItem, ServerOpsReport


# ===== 公共 fixture =====


@pytest.fixture(autouse=True)
def _isolate_script_registry():
    """隔离全局脚本注册表,避免测试间相互污染。

    导入 ``app.scripts.ops.ops_inspection_sweep`` 会触发 ``@register_script``
    装饰器把 ``ops_inspection_sweep`` 写入全局 ``_SCRIPT_REGISTRY``。本 fixture
    在每个用例前后清空注册表,确保互不干扰。

    返回: 无。
    异常: 无。
    """
    clear_registry()
    yield
    clear_registry()


def _make_context(
    *,
    script_args: Optional[Dict[str, Any]] = None,
    schedule_name: str = "运维巡检任务",
    run_id: int = 200,
) -> ScriptContext:
    """构造一个隔离的 ``ScriptContext`` 测试对象。

    参数:
        script_args: 脚本参数字典。
        schedule_name: 任务名称。
        run_id: 执行记录 ID。
        started_at / trigger_type 固定,便于日志断言。

    返回:
        ScriptContext: 用于测试的上下文对象。
    """
    return ScriptContext(
        schedule_id=1,
        run_id=run_id,
        session_id=f"task-{run_id}-abc",
        schedule_name=schedule_name,
        script_args=script_args or {},
        log_logger=logging.getLogger(f"test_ops_inspection_sweep_{run_id}"),
        started_at=datetime(2026, 7, 22, 15, 0, 0),
        trigger_type="manual",
    )


class _CaptureHandler(logging.Handler):
    """把日志记录收集到 ``records`` 列表的轻量级 handler,供断言用。"""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: List[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401 - stdlib API
        self.records.append(record)


def _attach_capture(context: ScriptContext) -> _CaptureHandler:
    """给 ``context.log_logger`` 挂一个 capture handler 并返回。

    同时把 logger 级别临时降为 ``DEBUG``,避免 INFO 记录被默认 WARNING 级别过滤掉。

    参数:
        context: 脚本上下文。

    返回:
        _CaptureHandler: 已挂载的 capture handler(测试结束后需 ``detach``)。
    """
    handler = _CaptureHandler()
    logger = context.log_logger
    prev_level = logger.level
    prev_propagate = logger.propagate
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.addHandler(handler)
    handler._prev_level = prev_level  # type: ignore[attr-defined]
    handler._prev_propagate = prev_propagate  # type: ignore[attr-defined]
    return handler


def _detach_capture(context: ScriptContext, handler: _CaptureHandler) -> None:
    """卸载 capture handler 并恢复 logger 原有的 ``level / propagate`` 设置。

    参数:
        context: 脚本上下文。
        handler: ``_attach_capture`` 返回的 handler。

    返回:
        None。
    """
    logger = context.log_logger
    logger.removeHandler(handler)
    logger.setLevel(getattr(handler, "_prev_level", logging.NOTSET))
    logger.propagate = getattr(handler, "_prev_propagate", True)


def _records_text(handler: _CaptureHandler) -> List[str]:
    """把 capture handler 收集的 LogRecord 渲染为可搜索的文本列表。"""
    formatter = logging.Formatter("%(levelname)s %(message)s")
    return [formatter.format(r) for r in handler.records]


# ===== 1) 导入 / 注册 / 签名契约 =====


def test_ops_inspection_sweep_importable():
    """``ops_inspection_sweep`` 模块应可正常导入且含 ``run`` 函数。"""
    from app.scripts.ops import ops_inspection_sweep  # noqa: F401

    assert hasattr(ops_inspection_sweep, "run")
    assert callable(ops_inspection_sweep.run)


def test_ops_inspection_sweep_registered_in_registry():
    """导入后 ``ops_inspection_sweep`` 应出现在 registry,展示名为「运维巡检扫描」。"""
    from app.scripts.ops import ops_inspection_sweep  # noqa: F401
    importlib.reload(ops_inspection_sweep)

    s = get_registered_script("ops_inspection_sweep")
    assert s is not None
    assert s.display_name == "运维巡检扫描"
    assert s.name == "ops_inspection_sweep"


def test_ops_inspection_sweep_run_signature():
    """``run`` 签名应为 ``async def run(context: ScriptContext) -> str``。"""
    from app.scripts.ops import ops_inspection_sweep

    sig = inspect.signature(ops_inspection_sweep.run)
    assert list(sig.parameters.keys()) == ["context"]

    hints = typing.get_type_hints(ops_inspection_sweep.run)
    assert hints["context"] is ScriptContext
    assert hints["return"] is str


def test_ops_inspection_sweep_params_schema_declares_server_and_api():
    """``params_schema`` 应同时声明 ``server_list`` + ``api_list`` 字段,
    且 UI 扩展元数据与 ``hello_script`` 完全一致(``server-multiselect`` /
    ``api-multiselect``)。"""
    from app.scripts.ops import ops_inspection_sweep  # noqa: F401
    importlib.reload(ops_inspection_sweep)

    s = get_registered_script("ops_inspection_sweep")
    assert s is not None

    schema = s.params_schema
    properties = schema.get("properties", {})
    assert "server_list" in properties
    assert "api_list" in properties

    server_list = properties["server_list"]
    assert server_list["type"] == "array"
    assert server_list["items"]["type"] == "string"
    assert server_list["uniqueItems"] is True
    assert server_list["default"] == []
    assert server_list["x-control"] == "server-multiselect"
    assert server_list["x-source"] == "devops-servers"
    assert server_list["x-value-field"] == "business_name"

    api_list = properties["api_list"]
    assert api_list["type"] == "array"
    assert api_list["items"]["type"] == "string"
    assert api_list["uniqueItems"] is True
    assert api_list["default"] == []
    assert api_list["x-control"] == "api-multiselect"
    assert api_list["x-source"] == "api-configs"
    assert api_list["x-value-field"] == "id"


# ===== 2) 空入参行为 =====


@pytest.mark.asyncio
async def test_run_empty_args_returns_base_summary_only():
    """``server_list`` 与 ``api_list`` 均缺失时,返回值仅含任务元数据,
    不含 ``server_ops=`` / ``api_check=`` 段。"""
    from app.scripts.ops import ops_inspection_sweep

    context = _make_context(script_args={})
    handler = _attach_capture(context)
    try:
        result = await ops_inspection_sweep.run(context)
    finally:
        _detach_capture(context, handler)

    assert isinstance(result, str)
    assert "ops_inspection_sweep" in result
    assert "schedule=运维巡检任务" in result
    assert "run_id=200" in result
    assert "server_ops=" not in result
    assert "api_check=" not in result


@pytest.mark.asyncio
async def test_run_empty_args_logs_no_ops_and_no_check():
    """空入参时日志应包含「无巡检项」与「无检查项」行,便于排查「忘记配置入参」的场景。"""
    from app.scripts.ops import ops_inspection_sweep

    context = _make_context(script_args={})
    handler = _attach_capture(context)
    try:
        await ops_inspection_sweep.run(context)
    finally:
        _detach_capture(context, handler)

    texts = _records_text(handler)
    assert any("server_ops: 无巡检项" in t for t in texts), texts
    assert any("api_check: 无检查项" in t for t in texts), texts
    assert any("ops_inspection_sweep 执行完成" in t for t in texts), texts


# ===== 3) server_list 路径 =====


@pytest.mark.asyncio
async def test_run_server_list_per_field_logging(monkeypatch):
    """``server_list`` 非空时,日志应包含:
        * 「server_ops: 共 N 台」汇总行;
        * 每台服务器的「OK ... fields=K」状态行;
        * 「parsed_values=...」JSON 行;
        * 每条 ``inspection_fields`` 规则的 ``key/name_zh/value/warn/crit`` 比对明细。
    """
    from app.scripts.ops import ops_inspection_sweep

    report = ServerOpsReport(items=[
        ServerOpsItem(
            business_name="biz-A",
            success=True,
            exit_code=0,
            stdout='{"cpu_used_pct": 75.2, "disk_used_pct": 88.4}',
            stderr="",
            duration_ms=245,
            inspection_parser="json",
            parsed_values={"cpu_used_pct": 75.2, "disk_used_pct": 88.4},
            field_results=[
                {
                    "key": "cpu_used_pct",
                    "name_zh": "CPU 使用率",
                    "unit": "%",
                    "value": 75.2,
                    "status": "warn",
                    "message": "",
                    "warn": 70.0,
                    "crit": 90.0,
                    "direction": "high",
                },
                {
                    "key": "disk_used_pct",
                    "name_zh": "磁盘使用率",
                    "unit": "%",
                    "value": 88.4,
                    "status": "warn",
                    "message": "",
                    "warn": 80.0,
                    "crit": 90.0,
                    "direction": "high",
                },
            ],
            inspection_status="warn",
            inspection_error="",
        ),
    ])

    async def stub_server_ops(context):
        return report
    monkeypatch.setattr(ops_inspection_sweep, "run_server_ops", stub_server_ops)

    # api_list 走真实 run_api_checks 空入参短路,无需 stub
    context = _make_context(script_args={"server_list": ["biz-A"]})
    handler = _attach_capture(context)
    try:
        result = await ops_inspection_sweep.run(context)
    finally:
        _detach_capture(context, handler)

    # 摘要断言:含 server_ops=... 段
    assert isinstance(result, str)
    assert "server_ops=1/1 passed" in result
    assert "biz-A OK(0,245ms)" in result
    assert "inspection=pass:0,warn:1" in result

    # 日志断言:逐字段比对
    texts = _records_text(handler)
    assert any("server_ops: 共 1 台" in t for t in texts), texts
    assert any("server biz=biz-A OK" in t and "fields=2" in t for t in texts), texts
    assert any("parsed_values=" in t and "cpu_used_pct" in t and "75.2" in t
               for t in texts), texts
    assert any("field[0]" in t and "key=cpu_used_pct" in t and "value=75.2" in t
               and "warn=70.0" in t and "crit=90.0" in t and "-> WARN" in t
               for t in texts), texts
    assert any("field[1]" in t and "key=disk_used_pct" in t and "value=88.4" in t
               and "-> WARN" in t for t in texts), texts


@pytest.mark.asyncio
async def test_run_server_list_skipped_item_logs_reason_without_fields(monkeypatch):
    """``skipped`` 项只打印「业务名 + 跳过原因」,不打印字段明细。"""
    from app.scripts.ops import ops_inspection_sweep

    report = ServerOpsReport(items=[
        ServerOpsItem(
            business_name="biz-NO-SCRIPT",
            skipped=True,
            error_message="未配置巡检脚本（inspection_script 为空）",
            inspection_status="skipped",
            inspection_error="未配置巡检脚本（inspection_script 为空）",
        ),
    ])

    async def stub(context):
        return report
    monkeypatch.setattr(ops_inspection_sweep, "run_server_ops", stub)

    context = _make_context(script_args={"server_list": ["biz-NO-SCRIPT"]})
    handler = _attach_capture(context)
    try:
        result = await ops_inspection_sweep.run(context)
    finally:
        _detach_capture(context, handler)

    assert "server_ops=0/0 passed, 1 skipped" in result

    texts = _records_text(handler)
    assert any("biz-NO-SCRIPT" in t and "SKIPPED" in t for t in texts), texts
    # skipped 不打印 parsed_values / field_results
    assert not any("parsed_values=" in t and "biz-NO-SCRIPT" in t for t in texts), texts
    assert not any("field[" in t and "biz-NO-SCRIPT" in t for t in texts), texts


@pytest.mark.asyncio
async def test_run_server_list_ssh_failure_logs_error(monkeypatch):
    """SSH 失败(``success=False``)时只打印错误摘要,不打印 parsed_values / field_results。"""
    from app.scripts.ops import ops_inspection_sweep

    report = ServerOpsReport(items=[
        ServerOpsItem(
            business_name="biz-CRASH",
            success=False,
            exit_code=2,
            stdout="",
            stderr="Connection refused",
            duration_ms=300,
            error_message="RuntimeError: SSHException: connection refused",
            inspection_parser="json",
            inspection_status="crit",
            inspection_error="RuntimeError: SSHException: connection refused",
        ),
    ])

    async def stub(context):
        return report
    monkeypatch.setattr(ops_inspection_sweep, "run_server_ops", stub)

    context = _make_context(script_args={"server_list": ["biz-CRASH"]})
    handler = _attach_capture(context)
    try:
        result = await ops_inspection_sweep.run(context)
    finally:
        _detach_capture(context, handler)

    texts = _records_text(handler)
    assert any("biz-CRASH" in t and "FAIL" in t and "exit=2" in t for t in texts), texts
    # SSH 失败不打印字段明细
    assert not any("field[" in t and "biz-CRASH" in t for t in texts), texts
    # SSH 失败不打印 parsed_values
    assert not any("parsed_values=" in t and "biz-CRASH" in t for t in texts), texts


@pytest.mark.asyncio
async def test_run_server_list_no_fields_logs_unassessed(monkeypatch):
    """``inspection_fields`` 为空(``field_results=[]``)时,日志应输出「无可评估字段」。"""
    from app.scripts.ops import ops_inspection_sweep

    report = ServerOpsReport(items=[
        ServerOpsItem(
            business_name="biz-NO-FIELDS",
            success=True,
            exit_code=0,
            stdout='{"x": 1}',
            stderr="",
            duration_ms=10,
            inspection_parser="json",
            parsed_values={"x": 1},
            field_results=[],
            inspection_status="unassessed",
            inspection_error="",
        ),
    ])

    async def stub(context):
        return report
    monkeypatch.setattr(ops_inspection_sweep, "run_server_ops", stub)

    context = _make_context(script_args={"server_list": ["biz-NO-FIELDS"]})
    handler = _attach_capture(context)
    try:
        result = await ops_inspection_sweep.run(context)
    finally:
        _detach_capture(context, handler)

    texts = _records_text(handler)
    assert any("biz-NO-FIELDS" in t and "fields=0" in t for t in texts), texts
    assert any("无可评估字段" in t and "biz-NO-FIELDS" in t for t in texts), texts


# ===== 4) api_list 路径 =====


@pytest.mark.asyncio
async def test_run_api_list_per_assertion_logging(monkeypatch):
    """``api_list`` 非空时,日志应逐接口打印 ``http/duration/passed`` + 每条断言明细。"""
    from app.scripts.ops import ops_inspection_sweep

    report = ApiCheckReport(items=[
        ApiCheckItem(
            node_id=10,
            name="查询接口",
            path="业务系统",
            check_passed=True,
            http_status=200,
            duration_ms=45,
            assertion_results=[
                {"type": "status_code", "passed": True, "detail": "期望=200, 实际=200"},
                {"type": "body_contains", "passed": True, "detail": "命中子串=success"},
            ],
        ),
    ])

    async def stub(context):
        return report
    monkeypatch.setattr(ops_inspection_sweep, "run_api_checks", stub)

    context = _make_context(script_args={"api_list": ["10"]})
    handler = _attach_capture(context)
    try:
        result = await ops_inspection_sweep.run(context)
    finally:
        _detach_capture(context, handler)

    # 摘要
    assert "api_check=1/1 passed" in result
    assert "id=10 OK 200/45ms" in result

    # 日志
    texts = _records_text(handler)
    assert any("api_check: 共 1 个" in t for t in texts), texts
    assert any("api id=10" in t and "http=200" in t and "passed=True" in t
               for t in texts), texts
    assert any("assertion[0]" in t and "type=status_code" in t and "passed=True" in t
               and "期望=200" in t for t in texts), texts
    assert any("assertion[1]" in t and "type=body_contains" in t and "命中子串" in t
               for t in texts), texts


@pytest.mark.asyncio
async def test_run_api_list_missing_node_logs_only_reason(monkeypatch):
    """节点缺失(``check_passed=None``)时只打印「MISSING + 原因」,不打印断言明细。"""
    from app.scripts.ops import ops_inspection_sweep

    report = ApiCheckReport(items=[
        ApiCheckItem(
            node_id=99,
            name="",
            path="",
            check_passed=None,
            error_message="接口节点不存在或已被删除",
        ),
    ])

    async def stub(context):
        return report
    monkeypatch.setattr(ops_inspection_sweep, "run_api_checks", stub)

    context = _make_context(script_args={"api_list": ["99"]})
    handler = _attach_capture(context)
    try:
        result = await ops_inspection_sweep.run(context)
    finally:
        _detach_capture(context, handler)

    assert "api_check=0/0 passed, 1 skipped" in result
    assert "id=99 MISSING" in result

    texts = _records_text(handler)
    assert any("id=99" in t and "MISSING" in t and "接口节点不存在" in t
               for t in texts), texts
    # 缺失节点不打印 assertion
    assert not any("assertion[" in t and "id=99" in t for t in texts), texts


# ===== 5) 异常透传 =====


@pytest.mark.asyncio
async def test_run_server_service_unavailable_propagates(monkeypatch):
    """``server_list`` 非空且 ``devops_server_service`` 不可用时,异常向上透出。"""
    from app.scripts.ops import ops_inspection_sweep

    async def fake_run_server_ops(context):
        raise ScriptExecutionError(
            "devops_server_service 不可用，无法执行 server_list 巡检"
        )

    monkeypatch.setattr(ops_inspection_sweep, "run_server_ops", fake_run_server_ops)

    context = _make_context(script_args={"server_list": ["biz-A"]})
    with pytest.raises(ScriptExecutionError, match="devops_server_service"):
        await ops_inspection_sweep.run(context)


@pytest.mark.asyncio
async def test_run_api_service_unavailable_propagates(monkeypatch):
    """``api_list`` 非空且 ``api_config_service`` 不可用时,异常向上透出。"""
    from app.scripts.ops import ops_inspection_sweep

    async def fake_run_api_checks(context):
        raise ScriptExecutionError(
            "api_config_service 不可用，无法执行 api_list 健康检查"
        )

    monkeypatch.setattr(ops_inspection_sweep, "run_api_checks", fake_run_api_checks)

    context = _make_context(script_args={"api_list": ["10"]})
    with pytest.raises(ScriptExecutionError, match="api_config_service"):
        await ops_inspection_sweep.run(context)


# ===== 6) 组合路径 =====


@pytest.mark.asyncio
async def test_run_combined_server_and_api_appends_both_summaries(monkeypatch):
    """``server_list`` 与 ``api_list`` 同时非空时,摘要同时追加两段;日志同时输出。"""
    from app.scripts.ops import ops_inspection_sweep

    server_report = ServerOpsReport(items=[
        ServerOpsItem(
            business_name="biz-A",
            success=True,
            exit_code=0,
            stdout='{"cpu_used_pct": 50}',
            stderr="",
            duration_ms=10,
            inspection_parser="json",
            parsed_values={"cpu_used_pct": 50},
            field_results=[{
                "key": "cpu_used_pct", "name_zh": "CPU", "unit": "%",
                "value": 50, "status": "pass", "message": "",
                "warn": 80.0, "crit": 95.0, "direction": "high",
            }],
            inspection_status="pass",
            inspection_error="",
        ),
    ])
    api_report = ApiCheckReport(items=[
        ApiCheckItem(
            node_id=10,
            name="订单查询",
            path="",
            check_passed=True,
            http_status=200,
            duration_ms=12,
            assertion_results=[{"type": "status_code", "passed": True}],
        ),
    ])

    async def stub_server(context):
        return server_report
    async def stub_api(context):
        return api_report
    monkeypatch.setattr(ops_inspection_sweep, "run_server_ops", stub_server)
    monkeypatch.setattr(ops_inspection_sweep, "run_api_checks", stub_api)

    context = _make_context(
        script_args={"server_list": ["biz-A"], "api_list": ["10"]},
    )
    handler = _attach_capture(context)
    try:
        result = await ops_inspection_sweep.run(context)
    finally:
        _detach_capture(context, handler)

    # 摘要含 server_ops + api_check 两段
    assert "server_ops=1/1 passed" in result
    assert "api_check=1/1 passed" in result
    assert result.index("server_ops") < result.index("api_check")

    # 日志含两类
    texts = _records_text(handler)
    assert any("server biz=biz-A" in t for t in texts)
    assert any("api id=10" in t for t in texts)


# ===== 7) 工具函数单元测试 =====


def test_format_field_log_pass():
    """PASS 字段格式化为 ``-> PASS``,保留 value + warn/crit。"""
    from app.scripts.ops.ops_inspection_sweep import _format_field_log

    text = _format_field_log({
        "key": "cpu_used_pct", "name_zh": "CPU 使用率", "unit": "%",
        "value": 50, "status": "pass", "message": "",
        "warn": 80.0, "crit": 95.0, "direction": "high",
    })
    assert "key=cpu_used_pct" in text
    assert "name=CPU 使用率" in text
    assert "unit=%" in text
    assert "value=50" in text
    assert "warn=80.0" in text
    assert "crit=95.0" in text
    assert "-> PASS" in text


def test_format_field_log_missing_value():
    """字段缺失时 ``value=无值``,仍打印 key + warn/crit。"""
    from app.scripts.ops.ops_inspection_sweep import _format_field_log

    text = _format_field_log({
        "key": "disk_used_pct", "name_zh": "磁盘使用率", "unit": "%",
        "value": None, "status": "crit", "message": "字段 disk_used_pct 在解析结果中缺失",
        "warn": 80.0, "crit": 90.0, "direction": "high",
    })
    assert "value=无值" in text
    assert "-> CRIT" in text
    assert "msg=字段 disk_used_pct 在解析结果中缺失" in text


def test_safe_json_dumps_handles_none_and_dict():
    """``_safe_json_dumps`` 对 None 返回 ``null``,对 dict 返回 JSON 字符串(保留中文)。"""
    from app.scripts.ops.ops_inspection_sweep import _safe_json_dumps

    assert _safe_json_dumps(None) == "null"
    text = _safe_json_dumps({"cpu": 75.2, "msg": "中文测试"})
    assert '"cpu": 75.2' in text
    assert '"msg": "中文测试"' in text  # ensure_ascii=False


def test_safe_json_dumps_fallback_to_repr_on_unserializable():
    """不可序列化对象(如 set)降级为 ``repr``,不抛异常。"""
    from app.scripts.ops.ops_inspection_sweep import _safe_json_dumps

    text = _safe_json_dumps({1, 2, 3})
    assert "set" in text or "1" in text  # repr 形态


def test_format_assertion_log_includes_detail():
    """``_format_assertion_log`` 含 ``type / passed / detail``。"""
    from app.scripts.ops.ops_inspection_sweep import _format_assertion_log

    text = _format_assertion_log({
        "type": "status_code", "passed": True, "detail": "期望=200, 实际=200",
    })
    assert "type=status_code" in text
    assert "passed=True" in text
    assert "detail=期望=200, 实际=200" in text


def test_format_assertion_log_without_detail():
    """``detail`` 缺失时仅含 ``type / passed``。"""
    from app.scripts.ops.ops_inspection_sweep import _format_assertion_log

    text = _format_assertion_log({"type": "json_field", "passed": False})
    assert "type=json_field" in text
    assert "passed=False" in text
    assert "detail" not in text


# ===== 8) docx 附件路径解析与生成 helper (Phase D Task D1) =====


def test_resolve_attachment_path_returns_docx():
    """``_resolve_attachment_path`` 返回 ``.docx`` 后缀,且文件名遵循
    ``{YYYYMMDD_HHMMSS}_{run_id}.docx`` 模板,与
    :func:`app.core.config.paths.resolve_task_attachment_path` 对齐。"""
    from app.scripts.ops.ops_inspection_sweep import _resolve_attachment_path

    p = _resolve_attachment_path("运维巡检任务", 42, datetime(2026, 7, 22, 15, 30))
    assert p.suffix == ".docx"
    assert p.name == "20260722_153000_42.docx"


def test_generate_docx_report_produces_docx(tmp_path, monkeypatch):
    """``_generate_docx_report`` 同步生成有效 docx 文件(大小 > 1000 字节),
    且父目录自动创建,产出文件位于 ``output_path``。

    通过 monkeypatch 替换 :class:`WordReportGenerator`,断言 helper 内部按
    ``构造 → generate() → save(path)`` 顺序调用,把内容写出到 ``output_path``。
    ``app/tests/conftest.py`` 在全局 mock 了 ``docx`` 模块,故此处使用 fake
    生成器而非真实 ``python-docx``;fake 在 ``save()`` 中写出 ``> 1000`` 字节
    的占位 zip 头,验证文件确实落盘且大小满足契约。
    """
    from app.scripts.ops.ops_inspection_sweep import _generate_docx_report
    from app.scripts.ops.ops_report import (
        build_ops_report_config,
        compute_ops_alerts,
        compute_ops_summary,
        resolve_server_ip_map,
    )

    captured: Dict[str, Any] = {
        "instantiated_with_cfg": None,
        "generated": False,
        "saved_to": None,
    }

    class _FakeGenerator:
        def __init__(self, cfg):
            captured["instantiated_with_cfg"] = cfg

        def generate(self) -> None:
            captured["generated"] = True

        def save(self, path) -> None:
            captured["saved_to"] = path
            Path(path).write_bytes(b"PK\x03\x04" + b"\x00" * 1500)

    monkeypatch.setattr(
        "app.scripts.ops.ops_inspection_sweep.WordReportGenerator",
        _FakeGenerator,
    )

    srv = ServerOpsReport(items=[
        ServerOpsItem(
            business_name="A",
            success=True,
            inspection_status="pass",
        ),
    ])
    api = ApiCheckReport(items=[
        ApiCheckItem(node_id=1, name="X", path="/x", check_passed=True),
    ])
    summary = compute_ops_summary(srv, api)
    alerts = compute_ops_alerts(srv, api)
    cfg = build_ops_report_config(
        summary=summary,
        alerts=alerts,
        server_report=srv,
        api_report=api,
        ip_map=resolve_server_ip_map(None, srv),
        schedule_name="x",
        started_at=datetime(2026, 7, 22, 15, 0, 0),
    )
    output = tmp_path / "report.docx"
    _generate_docx_report(cfg, output)
    assert output.exists()
    assert output.stat().st_size > 1000
    # helper 必须按 WordReportGenerator API 顺序调用:构造 → generate → save(path)
    assert captured["instantiated_with_cfg"] is cfg
    assert captured["generated"] is True
    assert captured["saved_to"] == str(output)