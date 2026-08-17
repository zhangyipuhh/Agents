# -*- coding:utf-8 -*-
"""
InspectionQueryTools 单元测试（2026-08-17 新增）

覆盖目标：
    - 模块暴露的 ``@tool(description=...)`` 函数 ``query_inspection_records``
      能正确导入并保留工具描述
    - 函数签名含 ``runtime`` 参数（LangChain ToolRuntime 注入约定）
    - 正常路径：通过 ``runtime.context["server_inspection_record_service"]``
      注入的 stub 服务返回 mock 数据，工具收敛到白名单 + IP 剔除
    - payload 中**无**任何形式的 IP（无论 service 返回值是否含 IP 字样）
    - 错误路径：业务名为空、时间格式错误、limit 越界、service 未注入、
      server_id 找不到、越权（list_records 返回 ``None``）、
      DB 异常（service 抛 ``Exception``）
    - 审计日志契约：success/failure 路径均 emit 一条 ``LogEvent``，
      metadata 中**无** IP / host / address 字样

测试风格遵循 ``test_ssh_tools.py`` / ``test_ssh_tools_third_party.py``：
    - 顶部 docstring（中文）
    - 通过 pytest monkeypatch 注入 service 单例与 stub 服务
    - 不触碰真实 DB / paramiko
"""
from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest


def _run(callable_or_coro):
    """统一包装工具调用:若是 coroutine 则 asyncio.run,否则直接返回结果。

    InspectionQueryTools 工具函数为 ``async def``，需 ``asyncio.run`` 触发。

    Args:
        callable_or_coro: 函数调用结果或协程对象。

    Returns:
        Any: 工具执行结果（``Command`` 对象）。
    """
    if inspect.iscoroutine(callable_or_coro):
        return asyncio.run(callable_or_coro)
    return callable_or_coro


def _build_runtime(
    *,
    tool_call_id: str = "call-q-1",
    ownership_scope: Optional[Any] = None,
    extra_context: Optional[Dict[str, Any]] = None,
) -> MagicMock:
    """构造 ``ToolRuntime`` mock。

    注：服务实例通过 ``ServerInspectionRecordService.set_instance(...)``
    单例模式注入（2026-08-17 改造），**不**通过 ``runtime.context``。

    Args:
        tool_call_id: 工具调用 ID。
        ownership_scope: ``OwnershipScope`` 实例 / dict / 缺省。
        extra_context: 其它 ``context`` 字段（如 ``log_ip``）。

    Returns:
        MagicMock: 模拟的 runtime。
    """
    runtime = MagicMock(name="ToolRuntime")
    runtime.tool_call_id = tool_call_id
    ctx: Dict[str, Any] = {
        "session_id": "sess-q-1",
        "log_user_id": 42,
        "log_username": "alice",
        "log_ip": "10.99.0.1",
    }
    if ownership_scope is not None:
        ctx["ownership_scope"] = ownership_scope
    if extra_context:
        ctx.update(extra_context)
    runtime.context = ctx
    return runtime


def _patch_devops_server_service(monkeypatch, public_servers: List[Dict[str, Any]]):
    """替换 ``DevOpsServerService.get_instance()`` 单例为 stub。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        public_servers: ``list_public_servers()`` 的固定返回值。
    """
    from app.shared.utils.devops_server_service import DevOpsServerService

    fake_service = MagicMock(name="DevOpsServerService")
    fake_service.list_public_servers = MagicMock(return_value=public_servers)
    DevOpsServerService.set_instance(fake_service)
    return fake_service


def _install_record_service(monkeypatch, svc: Any) -> None:
    """把 ``ServerInspectionRecordService`` 单例注入 stub（生产模式：lifespan 注入）。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        svc: ``ServerInspectionRecordService`` 实例或 stub。
    """
    from app.shared.utils.server_inspection_record_service import ServerInspectionRecordService

    ServerInspectionRecordService.set_instance(svc)


def _make_record_service_stub(
    *,
    list_records_result: Any = None,
    list_records_side_effect: Optional[BaseException] = None,
) -> MagicMock:
    """构造 ``ServerInspectionRecordService`` stub（经 ``spec`` 让 isinstance 通过）。

    Args:
        list_records_result: ``list_records(...)`` 的固定返回。
        list_records_side_effect: ``list_records(...)`` 的异常。

    Returns:
        MagicMock: 模拟的 service 实例（``isinstance(..., ServerInspectionRecordService)`` 也会通过）。
    """
    from app.shared.utils.server_inspection_record_service import ServerInspectionRecordService

    svc = MagicMock(spec=ServerInspectionRecordService, name="ServerInspectionRecordService")
    if list_records_side_effect is not None:
        svc.list_records = AsyncMock(side_effect=list_records_side_effect)
    else:
        svc.list_records = AsyncMock(return_value=list_records_result)
    return svc


@pytest.fixture(autouse=True)
def _reset_singletons():
    """每个测试前后清理 ``ServerInspectionRecordService`` / ``DevOpsServerService`` 单例。

    生产对等物：lifespan 启动时 ``set_instance``，退出时 ``reset()``（2026-08-17 新增）。
    autouse=True 是因为这两个单例都跨测试隔离，必须每个测试 reset。
    """
    from app.shared.utils.server_inspection_record_service import ServerInspectionRecordService
    from app.shared.utils.devops_server_service import DevOpsServerService

    ServerInspectionRecordService.reset()
    DevOpsServerService.reset()
    yield
    ServerInspectionRecordService.reset()
    DevOpsServerService.reset()


def _install_capturing_log_service(monkeypatch):
    """捕获 ``LogService.emit`` 调用（与 test_ssh_tools_third_party 同款）。

    Returns:
        Tuple[MagicMock, List[LogEvent]]: (fake_svc, captured_events)。
    """
    captured: List[Any] = []

    def fake_emit(event):
        captured.append(event)
        return True

    fake_svc = MagicMock(name="LogService")
    fake_svc.emit = fake_emit
    monkeypatch.setattr(
        "app.shared.utils.log_service._log_service_singleton", fake_svc, raising=False,
    )
    monkeypatch.setattr(
        "app.shared.utils.log_service.get_log_service", lambda: fake_svc, raising=False,
    )
    from app.shared.tools.skills.devops import InspectionQueryTools as _IQT

    monkeypatch.setattr(_IQT, "get_log_service", lambda: fake_svc, raising=False)
    return fake_svc, captured


# ---------------------------------------------------------------------------
# P0: 模块结构 / 工具签名
# ---------------------------------------------------------------------------


def test_module_exposes_one_tool():
    """InspectionQueryTools 模块应仅暴露一个工具 ``query_inspection_records``。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.InspectionQueryTools import query_inspection_records

    assert callable(query_inspection_records)
    assert query_inspection_records.__name__ == "query_inspection_records"


def test_tool_has_runtime_param():
    """``query_inspection_records`` 函数签名含 ``runtime`` 参数（LangChain 注入约定）。

    Returns:
        None
    """
    import inspect

    from app.shared.tools.skills.devops.InspectionQueryTools import query_inspection_records

    sig = inspect.signature(query_inspection_records)
    assert "runtime" in sig.parameters
    # runtime 必须位于最后（与 SSHTools 风格一致）
    params_list = list(sig.parameters.keys())
    assert params_list[-1] == "runtime"


# ---------------------------------------------------------------------------
# P1: 成功路径
# ---------------------------------------------------------------------------


def test_query_success_returns_records_without_ip(monkeypatch):
    """正常路径：service 返回 mock 数据 → 工具收敛到白名单 + IP 剔除 + emit success 日志。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    _, captured = _install_capturing_log_service(monkeypatch)
    _patch_devops_server_service(
        monkeypatch,
        public_servers=[{"id": 7, "business_name": "alpha", "server_type": "linux"}],
    )
    # service 返回 2 行，其中 parsed_values 故意塞 IP 残留（应被剔除）
    mock_rows = [
        {
            "id": 100,
            "server_id": 7,
            "business_name": "alpha",
            "collected_at": "2026-08-17T10:00:00+00:00",
            "success": True,
            "skipped": False,
            "exit_code": 0,
            "duration_ms": 1234,
            "inspection_status": "pass",
            "error_message": None,
            "inspection_error": None,
            "parsed_values": {
                "cpu_used_pct": 12.5,
                "ip": "10.0.0.99",  # 应被剔除
                "ssh_ip": "10.0.0.100",  # 应被剔除
                "disks": [{"mount": "/", "ip_address": "10.0.0.200"}],  # 应被剔除
            },
            "field_results": [
                {"field": "cpu", "status": "pass", "value": 12.5, "host": "alpha.local"},  # 应被剔除
            ],
            "created_at": "2026-08-17T10:00:01+00:00",
            # 故意混入敏感字段：不应出现在 payload 中
            "sensitive_secret": "should-not-leak",
        },
        {
            "id": 101,
            "server_id": 7,
            "business_name": "alpha",
            "collected_at": "2026-08-17T11:00:00+00:00",
            "success": False,
            "skipped": False,
            "exit_code": 1,
            "duration_ms": 567,
            "inspection_status": "crit",
            "error_message": "boom",
            "inspection_error": None,
            "parsed_values": {"mem_used_pct": 95.0},
            "field_results": [],
            "created_at": "2026-08-17T11:00:01+00:00",
        },
    ]
    service = _make_record_service_stub(list_records_result=mock_rows)
    _install_record_service(monkeypatch, service)

    from app.shared.tools.skills.devops.InspectionQueryTools import query_inspection_records

    runtime = _build_runtime()
    out = _run(
        query_inspection_records(
            business_name="alpha",
            start="2026-08-17T00:00:00",
            end="2026-08-17T23:59:59",
            limit=50,
            latest_only=False,
            runtime=runtime,
        )
    )
    payload = json.loads(out.update["messages"][0].content)
    assert payload["success"] is True
    assert payload["business_name"] == "alpha"
    assert payload["server_id"] == 7
    assert payload["count"] == 2
    assert len(payload["items"]) == 2
    # ===== 关键断言：payload 不含任何形式的 IP / host / sensitive 字段 =====
    raw_text = out.update["messages"][0].content
    for needle in (
        "10.0.0.99", "10.0.0.100", "10.0.0.200",  # IP 数值残留
        "alpha.local",  # host 字段残留
        "sensitive_secret",  # 非白名单字段
        "should-not-leak",
    ):
        assert needle not in raw_text, f"payload 泄漏了 {needle!r}"
    # 字段白名单收敛
    item0 = payload["items"][0]
    assert set(item0.keys()) == {
        "id", "server_id", "business_name", "collected_at",
        "success", "skipped", "exit_code", "duration_ms",
        "inspection_status", "error_message", "inspection_error",
        "parsed_values", "field_results", "created_at",
        "schedule_id", "run_id", "inspection_script_id", "created_by_user_id",
    } or set(item0.keys()).issubset({
        "id", "server_id", "business_name", "collected_at",
        "success", "skipped", "exit_code", "duration_ms",
        "inspection_status", "error_message", "inspection_error",
        "parsed_values", "field_results", "created_at",
        "schedule_id", "run_id", "inspection_script_id", "created_by_user_id",
    })
    # parsed_values 已剔除 ip / ssh_ip / ip_address
    assert "ip" not in item0["parsed_values"]
    assert "ssh_ip" not in item0["parsed_values"]
    assert item0["parsed_values"]["disks"][0].get("ip_address") is None
    # field_results 顶层 host 被剔除
    assert "host" not in item0["field_results"][0]
    # ===== 审计日志断言 =====
    assert len(captured) == 1
    evt = captured[0]
    assert evt.action == "inspection_query_records"
    assert evt.result == "success"
    assert evt.source == "inspection_query_tools"
    assert evt.target_name == "alpha"
    assert evt.target_id == "7"
    assert evt.user_id == 42
    assert evt.username == "alice"
    assert evt.ip_address == "10.99.0.1"
    assert evt.metadata["row_count"] == 2
    # 审计 metadata 中无 IP 字面量
    md_str = str(evt.metadata)
    for needle in ("10.0.0.99", "10.0.0.100", "10.0.0.200"):
        assert needle not in md_str
    # service.list_records 调用入参校验
    service.list_records.assert_awaited_once()
    call_args = service.list_records.call_args
    assert call_args.args[0] == 7  # server_id
    assert call_args.kwargs["start"].isoformat().startswith("2026-08-17")
    assert call_args.kwargs["end"].isoformat().startswith("2026-08-17")
    assert call_args.kwargs["limit"] == 50


# ---------------------------------------------------------------------------
# P1: 失败路径
# ---------------------------------------------------------------------------


def test_query_rejects_empty_business_name(monkeypatch):
    """业务名为空 / 纯空白 → 拒绝，不调 service，不调 DevOpsServerService。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    _, captured = _install_capturing_log_service(monkeypatch)
    devops_svc = _patch_devops_server_service(monkeypatch, public_servers=[])
    service = _make_record_service_stub(list_records_result=[])
    _install_record_service(monkeypatch, service)

    from app.shared.tools.skills.devops.InspectionQueryTools import query_inspection_records

    for empty_name in ("", "   ", None):
        runtime = _build_runtime()
        out = _run(
            query_inspection_records(
                business_name=empty_name,
                start="2026-08-01T00:00:00",
                end="2026-08-02T00:00:00",
                latest_only=False,
                runtime=runtime,
            )
        )
        payload = json.loads(out.update["messages"][0].content)
        assert payload["success"] is False
        assert "business_name" in payload["error"]
    # service / devops 都未被调用
    service.list_records.assert_not_awaited()
    devops_svc.list_public_servers.assert_not_called()
    # 失败审计日志：每条调用 emit 一条
    assert len(captured) == 3
    assert all(e.action == "inspection_query_records" for e in captured)
    assert all(e.result == "failure" for e in captured)
    assert all(e.metadata.get("error_code") == "invalid_business_name" for e in captured)


def test_query_rejects_invalid_time_format(monkeypatch):
    """start / end 解析失败 → 拒绝，不调 service。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    _, captured = _install_capturing_log_service(monkeypatch)
    _patch_devops_server_service(
        monkeypatch,
        public_servers=[{"id": 1, "business_name": "alpha", "server_type": "linux"}],
    )
    service = _make_record_service_stub(list_records_result=[])
    _install_record_service(monkeypatch, service)

    from app.shared.tools.skills.devops.InspectionQueryTools import query_inspection_records

    runtime = _build_runtime()
    out = _run(
        query_inspection_records(
            business_name="alpha",
            start="not-a-date",
            end="2026-08-02T00:00:00",
            latest_only=False,
            runtime=runtime,
        )
    )
    payload = json.loads(out.update["messages"][0].content)
    assert payload["success"] is False
    assert "起始时间格式错误" in payload["error"]
    service.list_records.assert_not_awaited()
    assert captured[-1].metadata["error_code"] == "invalid_time"

    # end 解析失败同样拒绝
    runtime2 = _build_runtime()
    out2 = _run(
        query_inspection_records(
            business_name="alpha",
            start="2026-08-01T00:00:00",
            end="bad-end",
            latest_only=False,
            runtime=runtime2,
        )
    )
    payload2 = json.loads(out2.update["messages"][0].content)
    assert payload2["success"] is False
    assert "截止时间格式错误" in payload2["error"]


def test_query_accepts_space_separated_datetime(monkeypatch):
    """容错：``2026-08-01 00:00:00``（空格分隔）应被接受（空格替换为 T）。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    _, captured = _install_capturing_log_service(monkeypatch)
    _patch_devops_server_service(
        monkeypatch,
        public_servers=[{"id": 1, "business_name": "alpha", "server_type": "linux"}],
    )
    service = _make_record_service_stub(list_records_result=[])
    _install_record_service(monkeypatch, service)

    from app.shared.tools.skills.devops.InspectionQueryTools import query_inspection_records

    runtime = _build_runtime()
    _run(
        query_inspection_records(
            business_name="alpha",
            start="2026-08-01 00:00:00",
            end="2026-08-02 00:00:00",
            latest_only=False,
            runtime=runtime,
        )
    )
    service.list_records.assert_awaited_once()
    assert captured[-1].result == "success"  # 走到 service 即为 success（空列表）


def test_query_clamps_oversized_limit(monkeypatch):
    """limit > 1000 / < 1 → 钳制到合法区间，**不**拒绝；limit 非 int → 兜底为 100。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    _, _captured = _install_capturing_log_service(monkeypatch)
    _patch_devops_server_service(
        monkeypatch,
        public_servers=[{"id": 1, "business_name": "alpha", "server_type": "linux"}],
    )
    service = _make_record_service_stub(list_records_result=[])
    _install_record_service(monkeypatch, service)

    from app.shared.tools.skills.devops.InspectionQueryTools import query_inspection_records

    # limit = 99999 → 钳制为 1000
    runtime = _build_runtime()
    _run(
        query_inspection_records(
            business_name="alpha",
            start="2026-08-01T00:00:00",
            end="2026-08-02T00:00:00",
            limit=99999,
            latest_only=False,
            runtime=runtime,
        )
    )
    assert service.list_records.call_args.kwargs["limit"] == 1000
    # limit = 0 → 钳制为 1
    runtime2 = _build_runtime()
    _run(
        query_inspection_records(
            business_name="alpha",
            start="2026-08-01T00:00:00",
            end="2026-08-02T00:00:00",
            limit=0,
            latest_only=False,
            runtime=runtime2,
        )
    )
    assert service.list_records.call_args.kwargs["limit"] == 1


def test_query_server_not_found(monkeypatch):
    """业务名在 ``list_public_servers`` 找不到 → 报错，不调 service.list_records。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    _, captured = _install_capturing_log_service(monkeypatch)
    _patch_devops_server_service(monkeypatch, public_servers=[])
    service = _make_record_service_stub(list_records_result=[])
    _install_record_service(monkeypatch, service)

    from app.shared.tools.skills.devops.InspectionQueryTools import query_inspection_records

    runtime = _build_runtime()
    out = _run(
        query_inspection_records(
            business_name="missing",
            start="2026-08-01T00:00:00",
            end="2026-08-02T00:00:00",
            latest_only=False,
            runtime=runtime,
        )
    )
    payload = json.loads(out.update["messages"][0].content)
    assert payload["success"] is False
    assert "未找到业务名对应的服务器" in payload["error"]
    service.list_records.assert_not_awaited()
    assert captured[-1].metadata["error_code"] == "server_not_found"


def test_query_service_unavailable(monkeypatch):
    """``runtime.context["server_inspection_record_service"]`` 未注入 → 报错。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    _, captured = _install_capturing_log_service(monkeypatch)
    _patch_devops_server_service(
        monkeypatch,
        public_servers=[{"id": 1, "business_name": "alpha", "server_type": "linux"}],
    )

    from app.shared.tools.skills.devops.InspectionQueryTools import query_inspection_records

    runtime = _build_runtime()
    # 不调用 _install_record_service → singleton 未初始化 → 服务不可用
    out = _run(
        query_inspection_records(
            business_name="alpha",
            start="2026-08-01T00:00:00",
            end="2026-08-02T00:00:00",
            latest_only=False,
            runtime=runtime,
        )
    )
    payload = json.loads(out.update["messages"][0].content)
    assert payload["success"] is False
    assert "服务不可用" in payload["error"]
    assert captured[-1].metadata["error_code"] == "service_unavailable"


def test_query_server_visible_none_treated_as_not_visible(monkeypatch):
    """普通用户 ``list_records`` 返回 ``None``（越权 / 不可见）→ 404 风格错误。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    _, captured = _install_capturing_log_service(monkeypatch)
    _patch_devops_server_service(
        monkeypatch,
        public_servers=[{"id": 1, "business_name": "alpha", "server_type": "linux"}],
    )
    service = _make_record_service_stub(list_records_result=None)
    _install_record_service(monkeypatch, service)

    from app.shared.tools.skills.devops.InspectionQueryTools import query_inspection_records

    from app.shared.utils.auth.ownership_scope import OwnershipScope

    scope = OwnershipScope.for_user(user_id=99, is_admin=False)
    runtime = _build_runtime(ownership_scope=scope)
    out = _run(
        query_inspection_records(
            business_name="alpha",
            start="2026-08-01T00:00:00",
            end="2026-08-02T00:00:00",
            latest_only=False,
            runtime=runtime,
        )
    )
    payload = json.loads(out.update["messages"][0].content)
    assert payload["success"] is False
    assert "不存在或不可见" in payload["error"]
    # 不回显 server_id
    assert "server_id" not in payload or payload.get("server_id") != 1
    assert captured[-1].metadata["error_code"] == "not_visible"


def test_query_emits_failure_log_on_db_error(monkeypatch):
    """service.list_records 抛异常 → emit failure 日志 + 返回通用错误（不泄漏 DB 细节）。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    _, captured = _install_capturing_log_service(monkeypatch)
    _patch_devops_server_service(
        monkeypatch,
        public_servers=[{"id": 1, "business_name": "alpha", "server_type": "linux"}],
    )
    service = _make_record_service_stub(
        list_records_side_effect=RuntimeError("asyncpg connection refused at 10.99.0.50:5432"),
    )
    _install_record_service(monkeypatch, service)

    from app.shared.tools.skills.devops.InspectionQueryTools import query_inspection_records

    runtime = _build_runtime()
    out = _run(
        query_inspection_records(
            business_name="alpha",
            start="2026-08-01T00:00:00",
            end="2026-08-02T00:00:00",
            latest_only=False,
            runtime=runtime,
        )
    )
    payload = json.loads(out.update["messages"][0].content)
    assert payload["success"] is False
    assert payload["error"] == "查询巡检记录失败"
    # 不泄漏 DB 内部细节
    raw = out.update["messages"][0].content
    assert "asyncpg" not in raw
    assert "10.99.0.50" not in raw
    assert "5432" not in raw
    # 审计日志标记 db_error
    assert captured[-1].metadata["error_code"] == "db_error"
    assert captured[-1].result == "failure"


def test_query_emits_audit_log_metadata_without_ip(monkeypatch):
    """审计日志 metadata 字段展开为字符串后**不含** IP 字面量（10.0.0.x 等）。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    _, captured = _install_capturing_log_service(monkeypatch)
    _patch_devops_server_service(
        monkeypatch,
        public_servers=[{"id": 5, "business_name": "alpha", "server_type": "linux"}],
    )
    # service 故意返回包含 IP 字符串的 mock 行
    mock_rows = [
        {
            "id": 200,
            "server_id": 5,
            "business_name": "alpha",
            "collected_at": "2026-08-17T10:00:00+00:00",
            "success": True,
            "skipped": False,
            "exit_code": 0,
            "duration_ms": 100,
            "inspection_status": "pass",
            "error_message": None,
            "inspection_error": None,
            "parsed_values": {
                "cpu_used_pct": 5.0,
                "ip": "172.16.5.99",  # 应被剔除
                "ssh_ip": "172.16.5.100",  # 应被剔除
            },
            "field_results": [],
            "created_at": "2026-08-17T10:00:01+00:00",
        },
    ]
    service = _make_record_service_stub(list_records_result=mock_rows)
    _install_record_service(monkeypatch, service)

    from app.shared.tools.skills.devops.InspectionQueryTools import query_inspection_records

    runtime = _build_runtime()
    _run(
        query_inspection_records(
            business_name="alpha",
            start="2026-08-17T00:00:00",
            end="2026-08-17T23:59:59",
            latest_only=False,
            runtime=runtime,
        )
    )
    evt = captured[-1]
    md_str = str(evt.metadata)
    # 不含被剔除的 IP（即使出现在 parsed_values 也不应逃逸到日志）
    for needle in ("172.16.5.99", "172.16.5.100"):
        assert needle not in md_str
    # metadata 应含 success 路径标准字段
    assert evt.metadata["error_code"] is None
    assert evt.metadata["row_count"] == 1
    assert evt.metadata["limit"] == 100
    assert "2026-08-17" in evt.metadata["time_range_start"]
    assert "2026-08-17" in evt.metadata["time_range_end"]


def test_query_scrubs_ip_from_parsed_values(monkeypatch):
    """_scrub_ip 单元级：递归剔除 dict / list 中的 IP 残留键。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.InspectionQueryTools import _scrub_ip

    raw = {
        "cpu_used_pct": 10.0,
        "ip": "10.1.1.1",
        "IP_Address": "10.1.1.2",  # 大小写不敏感
        "ssh_ip": "10.1.1.3",
        "disks": [
            {"mount": "/", "disk_used_pct": 50.0, "ip_address": "10.1.1.4"},
            {"mount": "/data", "disk_used_pct": 60.0, "host": "data.local"},
        ],
        "nested": {
            "deep": {
                "ip": "10.1.1.5",
                "value": 42,
            },
            "list": [{"address": "addr-1"}, {"safe": "yes"}],
        },
    }
    cleaned = _scrub_ip(raw)
    # 原始对象未被 mutate
    assert "ip" in raw
    # 清洗结果不含 ip 家族键
    assert "ip" not in cleaned
    assert "IP_Address" not in cleaned
    assert "ssh_ip" not in cleaned
    # 嵌套也清掉
    assert "ip_address" not in cleaned["disks"][0]
    assert "host" not in cleaned["disks"][1]
    assert "ip" not in cleaned["nested"]["deep"]
    assert "address" not in cleaned["nested"]["list"][0]
    assert cleaned["nested"]["list"][1]["safe"] == "yes"
    # 合法字段保留
    assert cleaned["cpu_used_pct"] == 10.0
    assert cleaned["disks"][0]["disk_used_pct"] == 50.0
    assert cleaned["nested"]["deep"]["value"] == 42


# ---------------------------------------------------------------------------
# P1: latest_only 模式（2026-08-17 新增）
# ---------------------------------------------------------------------------


def test_query_latest_only_default_skips_time_range(monkeypatch):
    """默认 latest_only=True 时，start / end 可空，工具返回最新一条记录。

    这是用户实际使用模式："查询共享数据库11最近一次巡检记录"。
    无需先调 ``get_current_time`` 计算时间范围。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    _, captured = _install_capturing_log_service(monkeypatch)
    _patch_devops_server_service(
        monkeypatch,
        public_servers=[{"id": 7, "business_name": "alpha", "server_type": "linux"}],
    )
    mock_rows = [
        {
            "id": 999,
            "server_id": 7,
            "business_name": "alpha",
            "collected_at": "2026-08-17T20:00:00+00:00",
            "success": True,
            "skipped": False,
            "exit_code": 0,
            "duration_ms": 432,
            "inspection_status": "pass",
            "error_message": None,
            "inspection_error": None,
            "parsed_values": {"cpu_used_pct": 12.0},
            "field_results": [],
            "created_at": "2026-08-17T20:00:01+00:00",
        },
    ]
    service = _make_record_service_stub(list_records_result=mock_rows)
    _install_record_service(monkeypatch, service)

    from app.shared.tools.skills.devops.InspectionQueryTools import query_inspection_records

    # 默认 latest_only=True,start/end 不传
    runtime = _build_runtime()
    out = _run(
        query_inspection_records(
            business_name="alpha",
            runtime=runtime,
        )
    )
    payload = json.loads(out.update["messages"][0].content)
    assert payload["success"] is True
    assert payload["business_name"] == "alpha"
    assert payload["server_id"] == 7
    assert payload["count"] == 1
    assert payload["latest_only"] is True
    assert "time_range" not in payload  # latest_only 模式不返回 time_range
    assert len(payload["items"]) == 1
    # 关键：list_records 调用时 limit=1 / start=None / end=None
    service.list_records.assert_awaited_once()
    call_args = service.list_records.call_args
    assert call_args.kwargs["limit"] == 1
    assert call_args.kwargs["start"] is None
    assert call_args.kwargs["end"] is None
    # 审计日志
    evt = captured[-1]
    assert evt.result == "success"
    assert evt.metadata["latest_only"] is True
    assert evt.metadata["limit"] == 1
    assert "time_range_start" not in evt.metadata
    assert "time_range_end" not in evt.metadata


def test_query_latest_only_false_without_time_range_returns_latest_limit(monkeypatch):
    """latest_only=False 且 start/end 双缺 → 透传 None/None 给 list_records，返回最近 limit 条。

    2026-08-17 根因修复（ops-detect 智能检测窗口死循环）：
        原契约要求 start/end 必填，LLM 在「最近N天」相对时间面前常不传绝对区间，
        收到死胡同错误后原地重试至 recursion_limit=100，表现为 agent 死循环。
        新契约：缺省视为不限界（服务层 list_records 已支持 None=不限界），
        审计 metadata 加 ``time_range_defaulted=True`` 标记，payload 中同步输出
        ``time_range_defaulted`` 字段供 LLM 了解区间被默认放宽。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    _, captured = _install_capturing_log_service(monkeypatch)
    _patch_devops_server_service(
        monkeypatch,
        public_servers=[{"id": 7, "business_name": "alpha", "server_type": "linux"}],
    )
    mock_rows = [
        {
            "id": 901,
            "server_id": 7,
            "business_name": "alpha",
            "collected_at": "2026-08-17T18:00:00+00:00",
            "success": True,
            "skipped": False,
            "exit_code": 0,
            "duration_ms": 100,
            "inspection_status": "pass",
            "error_message": None,
            "inspection_error": None,
            "parsed_values": {},
            "field_results": [],
            "created_at": "2026-08-17T18:00:01+00:00",
        },
        {
            "id": 900,
            "server_id": 7,
            "business_name": "alpha",
            "collected_at": "2026-08-17T09:00:00+00:00",
            "success": True,
            "skipped": False,
            "exit_code": 0,
            "duration_ms": 90,
            "inspection_status": "pass",
            "error_message": None,
            "inspection_error": None,
            "parsed_values": {},
            "field_results": [],
            "created_at": "2026-08-17T09:00:01+00:00",
        },
    ]
    service = _make_record_service_stub(list_records_result=mock_rows)
    _install_record_service(monkeypatch, service)

    from app.shared.tools.skills.devops.InspectionQueryTools import query_inspection_records

    runtime = _build_runtime()
    out = _run(
        query_inspection_records(
            business_name="alpha",
            latest_only=False,
            runtime=runtime,
        )
    )
    payload = json.loads(out.update["messages"][0].content)
    assert payload["success"] is True
    assert payload["count"] == 2
    assert payload["latest_only"] is False
    assert payload["time_range_defaulted"] is True
    assert "time_range" not in payload  # 双缺视为不限界，不构造 time_range 字段
    # list_records 接收 None/None
    service.list_records.assert_awaited_once()
    call_args = service.list_records.call_args
    assert call_args.kwargs["start"] is None
    assert call_args.kwargs["end"] is None
    assert call_args.kwargs["limit"] == 100  # 默认上限
    # 审计日志：time_range_defaulted=True + 不含具体 time_range_start/end
    evt = captured[-1]
    assert evt.result == "success"
    assert evt.metadata["time_range_defaulted"] is True
    assert "time_range_start" not in evt.metadata
    assert "time_range_end" not in evt.metadata


def test_query_latest_only_false_with_only_start_passes_end_as_none(monkeypatch):
    """latest_only=False 只传 start → end 缺省透传 None；时间区间按 start ~ 至今。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    _, captured = _install_capturing_log_service(monkeypatch)
    _patch_devops_server_service(
        monkeypatch,
        public_servers=[{"id": 7, "business_name": "alpha", "server_type": "linux"}],
    )
    service = _make_record_service_stub(list_records_result=[])
    _install_record_service(monkeypatch, service)

    from app.shared.tools.skills.devops.InspectionQueryTools import query_inspection_records

    runtime = _build_runtime()
    _run(
        query_inspection_records(
            business_name="alpha",
            start="2026-08-15T00:00:00",
            latest_only=False,
            runtime=runtime,
        )
    )
    service.list_records.assert_awaited_once()
    call_args = service.list_records.call_args
    assert call_args.kwargs["start"].isoformat().startswith("2026-08-15")
    assert call_args.kwargs["end"] is None
    evt = captured[-1]
    assert evt.metadata["time_range_defaulted"] is False
    assert evt.metadata["time_range_start"].startswith("2026-08-15")


def test_query_latest_only_false_with_only_end_passes_start_as_none(monkeypatch):
    """latest_only=False 只传 end → start 缺省透传 None；时间区间按历史至 end。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    _, captured = _install_capturing_log_service(monkeypatch)
    _patch_devops_server_service(
        monkeypatch,
        public_servers=[{"id": 7, "business_name": "alpha", "server_type": "linux"}],
    )
    service = _make_record_service_stub(list_records_result=[])
    _install_record_service(monkeypatch, service)

    from app.shared.tools.skills.devops.InspectionQueryTools import query_inspection_records

    runtime = _build_runtime()
    _run(
        query_inspection_records(
            business_name="alpha",
            end="2026-08-17T23:59:59",
            latest_only=False,
            runtime=runtime,
        )
    )
    service.list_records.assert_awaited_once()
    call_args = service.list_records.call_args
    assert call_args.kwargs["start"] is None
    assert call_args.kwargs["end"].isoformat().startswith("2026-08-17")
    evt = captured[-1]
    assert evt.metadata["time_range_defaulted"] is False
    assert evt.metadata["time_range_end"].startswith("2026-08-17")


def test_query_resolves_scope_from_dict_form(monkeypatch):
    """``agent_router.chat`` 注入的 ``ownership_scope`` 是字典形态，工具侧还原。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    _, _captured = _install_capturing_log_service(monkeypatch)
    _patch_devops_server_service(
        monkeypatch,
        public_servers=[{"id": 1, "business_name": "alpha", "server_type": "linux"}],
    )
    # 普通用户：scope dict 含 user_id=99, is_admin=False
    service = _make_record_service_stub(list_records_result=None)
    _install_record_service(monkeypatch, service)

    from app.shared.tools.skills.devops.InspectionQueryTools import query_inspection_records

    runtime = _build_runtime(
        ownership_scope={"user_id": 99, "is_admin": False, "system": False},
    )
    _run(
        query_inspection_records(
            business_name="alpha",
            runtime=runtime,
        )
    )
    # 普通用户越权 → list_records 返 None → "服务器不存在或不可见"
    service.list_records.assert_awaited_once()
    scope_arg = service.list_records.call_args.args[1]
    assert scope_arg.user_id == 99
    assert scope_arg.is_admin is False
    assert scope_arg.system is False


def test_query_resolves_scope_from_missing_context_defaults_to_system(monkeypatch):
    """``ownership_scope`` 缺失时兜底为 ``OwnershipScope.system_scope()``。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    _, _captured = _install_capturing_log_service(monkeypatch)
    _patch_devops_server_service(
        monkeypatch,
        public_servers=[{"id": 1, "business_name": "alpha", "server_type": "linux"}],
    )
    mock_rows = [
        {
            "id": 1,
            "server_id": 1,
            "business_name": "alpha",
            "collected_at": "2026-08-17T10:00:00",
            "success": True,
            "skipped": False,
            "exit_code": 0,
            "duration_ms": 100,
            "inspection_status": "pass",
            "error_message": None,
            "inspection_error": None,
            "parsed_values": {},
            "field_results": [],
            "created_at": "2026-08-17T10:00:01",
        },
    ]
    service = _make_record_service_stub(list_records_result=mock_rows)
    _install_record_service(monkeypatch, service)

    from app.shared.tools.skills.devops.InspectionQueryTools import query_inspection_records

    # 不传 ownership_scope，_build_runtime 默认不放入 ctx
    runtime = _build_runtime()
    out = _run(
        query_inspection_records(
            business_name="alpha",
            runtime=runtime,
        )
    )
    payload = json.loads(out.update["messages"][0].content)
    assert payload["success"] is True  # system_scope 全量放行
    scope_arg = service.list_records.call_args.args[1]
    assert scope_arg.system is True
    assert scope_arg.user_id is None
    assert scope_arg.is_admin is False
