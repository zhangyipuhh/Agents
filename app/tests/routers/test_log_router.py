# -*- coding:utf-8 -*-
"""
``app/routers/log_router.py`` 单元测试模块（2026-07-29 新增）。

覆盖目标：
    - GET /api/admin/logs  支持 log_type / action / result / level / source /
      user_id / username / session_id / request_id / tool_call_id /
      correlation_id / target_type / target_id / target_name / created_from /
      created_to 多过滤器查询 + limit(1..200) + offset(>=0) 分页
    - 响应结构 ``{items,total,limit,offset}`` 信封
    - 响应字段白名单（id / log_type / result / level / source / action /
      message / session_id / request_id / tool_call_id / correlation_id /
      target_type / target_id / target_name / user_id / username / ip_address /
      metadata / created_at）
    - GET /api/admin/logs/{log_id} 单条详情；不存在 → 404；
      含 correlation_id 时附带 related_logs
    - router 级 Depends(require_admin)：非 admin 返回 403
    - app.state.log_service 缺失 → 503
    - 响应字段不含 password / 原命令 / IP / 用户名等敏感值
    - 走真实 LogService emit → consume_loop → query_logs 链路（2026-07-29 修订）

依赖：
    - tests/conftest.py::client / admin_headers / user_headers 提供；
    - tests/routers/conftest.py autouse fixture 已注入多个 service；
      本测试按生产对等原则,通过 fixture 显式注入「真实 LogService(memory_only=True)」
      实例（而不是用 MagicMock 直接挂到 app.state.log_service），
      避免触发「禁止在测试中虚构生产不存在的依赖」反模式。
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytest


# =============================================================================
# 1. fixtures：注入真实 LogService 实例（生产对等）
# =============================================================================


@pytest.fixture
def memory_log_service_fixture(app):
    """在测试会话内注入未启动的 ``LogService(memory_only=True)`` 并挂到 ``app.state.log_service``。

    生产对等初始化点：``app/core/server.py::lifespan`` 中
    ``app.state.log_service = LogService(db_pool=DatabasePool._pool)`` + ``await log_service.start()``。
    测试环境 db=None → memory_only 自动 True,不依赖 PostgreSQL。

    **生命周期与查询语义（2026-07-30 修订）**:
    - 本 fixture **不再** 在自身 ``asyncio.run`` 内启动后台消费协程,避免「fixture 启 loop → 测试
      emit → 测试发起新的 ``asyncio.run``」跨 loop 资源冲突
    - 测试种子统一通过 ``_seed_via_emit_sync(svc, events)`` 在 **同一 ``asyncio.run`` 周期** 内
      完成 ``start → emit × N → await sleep / stop → query_logs``,完整覆盖真实 emit → consume_loop
      → _store_memory → query_logs 链路
    - query_logs / count_logs 是 async 方法,可在 stop() 之后的任意 event loop 内调用
      (仅读 ``_memory_lock`` 保护的 ``_memory_records``,不依赖已关闭的 queue)
    - 已删除原 ``_seed_events`` 旁路（直接 ``_store_memory``）—— 全部测试改走真实 emit 链路
    """
    from app.shared.utils.log_service import (
        LogEvent,
        LogService,
        reset_log_service,
        set_log_service,
    )

    svc = LogService(memory_only=True, flush_interval_seconds=0.05, batch_size=10)

    saved_state = getattr(app.state, "log_service", None)
    app.state.log_service = svc
    set_log_service(svc)

    try:
        yield svc
    finally:
        # 兜底:如果测试结束后 svc 仍在跑,强制 stop + 清空(可能产生跨 loop 异常,忽略)
        try:
            if svc._consumer_started and svc._loop is not None and not svc._loop.is_closed():

                async def _shutdown():
                    await svc.stop()

                asyncio.run(_shutdown())
        except Exception:
            pass
        app.state.log_service = saved_state
        reset_log_service()


def _seed_via_emit_sync(svc, events):
    """同步入口:在新的 ``asyncio.run`` 周期内完成 start → emit × N → await sleep → stop。

    Args:
        svc: LogService 实例(未启动)
        events: 待写入的 LogEvent 列表

    Returns:
        None
    """

    async def _runner():
        await svc.start()
        for evt in events:
            svc.emit(evt)
        # 等待 consume_loop 把队列事件全部落库
        await asyncio.sleep(0.1)
        await svc.stop()

    asyncio.run(_runner())


def _make_event(
    *,
    action: str = "ssh_execute_command",
    log_type: str = "ssh",
    result: str = "success",
    level: str = "info",
    source: str = "ssh_executor",
    message: Optional[str] = None,
    session_id: Optional[str] = None,
    request_id: Optional[str] = None,
    tool_call_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    target_type: Optional[str] = "devops_server",
    target_id: Optional[str] = None,
    target_name: Optional[str] = None,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    ip_address: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    timestamp: Optional[datetime] = None,
) -> Any:
    """构造一个 ``LogEvent`` 用于测试种子数据。"""
    from app.shared.utils.log_service import LogEvent

    return LogEvent(
        action=action,
        log_type=log_type,
        result=result,
        level=level,
        source=source,
        message=message or action,
        session_id=session_id,
        request_id=request_id,
        tool_call_id=tool_call_id,
        correlation_id=correlation_id,
        target_type=target_type,
        target_id=target_id,
        target_name=target_name,
        user_id=user_id,
        username=username,
        ip_address=ip_address,
        metadata=metadata or {},
        timestamp=timestamp or datetime(2026, 7, 29, 10, 0, 0),
    )


# =============================================================================
# 2. 模块 / 路由注册
# =============================================================================


def test_log_router_importable():
    """``app/routers/log_router`` 模块可导入并暴露 ``router``。"""
    from app.routers import log_router

    assert hasattr(log_router, "router")


def test_list_endpoint_registered(client, memory_log_service_fixture):
    """GET /api/admin/logs 路由已注册到 FastAPI app。"""
    paths = [r.path for r in client.app.routes]
    assert "/api/admin/logs" in paths


def test_detail_endpoint_registered(client, memory_log_service_fixture):
    """GET /api/admin/logs/{log_id} 路由已注册。"""
    paths = [r.path for r in client.app.routes]
    assert "/api/admin/logs/{log_id}" in paths


# =============================================================================
# 3. 权限：require_admin 守卫
# =============================================================================


def test_list_endpoint_requires_admin(client, memory_log_service_fixture, user_headers):
    """非 admin 用户 → 403。"""
    resp = client.get("/api/admin/logs", headers=user_headers)
    assert resp.status_code == 403


def test_detail_endpoint_requires_admin(client, memory_log_service_fixture, user_headers):
    """非 admin 用户 → 403（即使 log_id 不存在也先被权限拦截）。"""
    resp = client.get("/api/admin/logs/1", headers=user_headers)
    assert resp.status_code == 403


def test_list_endpoint_admin_allowed(client, memory_log_service_fixture, admin_headers):
    """admin 用户 → 200 + JSON 信封 ``{items,total,limit,offset}``。"""
    resp = client.get("/api/admin/logs", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict)
    assert set(body.keys()) == {"items", "total", "limit", "offset"}


# =============================================================================
# 4. 服务缺失 → 503
# =============================================================================


def test_list_endpoint_503_when_log_service_missing(client, admin_headers):
    """``app.state.log_service`` 未初始化 → 503。"""
    app = client.app
    saved = getattr(app.state, "log_service", None)
    app.state.log_service = None
    try:
        resp = client.get("/api/admin/logs", headers=admin_headers)
        assert resp.status_code == 503
        assert "log_service" in resp.text.lower()
    finally:
        app.state.log_service = saved


def test_detail_endpoint_503_when_log_service_missing(client, admin_headers):
    """detail 端点在服务缺失时也走 503（而不是 404）。"""
    app = client.app
    saved = getattr(app.state, "log_service", None)
    app.state.log_service = None
    try:
        resp = client.get("/api/admin/logs/1", headers=admin_headers)
        assert resp.status_code == 503
    finally:
        app.state.log_service = saved


# =============================================================================
# 5. 入参校验：limit / offset 边界 + 时间格式
# =============================================================================


def test_list_rejects_limit_below_1(client, memory_log_service_fixture, admin_headers):
    """``limit=0`` 触发 422（必须 1..200）。"""
    resp = client.get("/api/admin/logs?limit=0", headers=admin_headers)
    assert resp.status_code == 422


def test_list_rejects_limit_above_200(client, memory_log_service_fixture, admin_headers):
    """``limit=201`` 触发 422（上限 200）。"""
    resp = client.get("/api/admin/logs?limit=201", headers=admin_headers)
    assert resp.status_code == 422


def test_list_rejects_negative_offset(client, memory_log_service_fixture, admin_headers):
    """``offset=-1`` 触发 422（必须 >=0）。"""
    resp = client.get("/api/admin/logs?offset=-1", headers=admin_headers)
    assert resp.status_code == 422


def test_list_accepts_limit_boundary(client, memory_log_service_fixture, admin_headers):
    """``limit=1`` 与 ``limit=200`` 边界合法。"""
    r1 = client.get("/api/admin/logs?limit=1", headers=admin_headers)
    r200 = client.get("/api/admin/logs?limit=200", headers=admin_headers)
    assert r1.status_code == 200
    assert r200.status_code == 200


def test_list_rejects_invalid_created_from(client, memory_log_service_fixture, admin_headers):
    """``created_from`` 不是 ISO 时间字符串 → 422。"""
    resp = client.get(
        "/api/admin/logs?created_from=not-a-date", headers=admin_headers
    )
    assert resp.status_code == 422


# =============================================================================
# 6. 列表查询 + 字段白名单
# =============================================================================


def test_list_returns_whitelisted_fields(client, memory_log_service_fixture, admin_headers):
    """列表响应字段严格白名单（不返回 db 内幕字段）。"""
    _seed_via_emit_sync(
        memory_log_service_fixture,
        [
            _make_event(
                action="ssh_execute_command",
                target_name="alpha",
                metadata={"server_type": "linux", "command_redacted": "echo hello"},
            )
        ],
    )
    resp = client.get("/api/admin/logs", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    item = body["items"][0]
    expected = {
        "id",
        "log_type",
        "result",
        "level",
        "source",
        "action",
        "message",
        "session_id",
        "request_id",
        "tool_call_id",
        "correlation_id",
        "target_type",
        "target_id",
        "target_name",
        "user_id",
        "username",
        "ip_address",
        "metadata",
        "created_at",
    }
    assert set(item.keys()) == expected, f"多余或缺失字段: {set(item.keys()) ^ expected}"


def test_list_does_not_leak_sensitive_metadata(client, memory_log_service_fixture, admin_headers):
    """列表 metadata 已由 LogService.emit 时递归 redact_metadata,
    不应回显 password / token 等原值;但 metadata 自身是 dict,字段名固定白名单,
    敏感键值在 emit 端已被替换为 ``***REDACTED***``。
    """
    _seed_via_emit_sync(
        memory_log_service_fixture,
        [
            _make_event(
                action="ssh_execute_command",
                metadata={
                    "password": "verysecret-xyz",
                    "stdout_size": 5,
                    "command_redacted": "echo hi",
                },
            )
        ],
    )
    resp = client.get("/api/admin/logs", headers=admin_headers)
    body = resp.json()
    # 密码字段若被保留(因为 _store_memory 内部已脱敏),也不应包含明文
    meta_str = str(body["items"][0].get("metadata"))
    assert "verysecret-xyz" not in meta_str


def test_list_created_at_is_naive_utc_iso(client, memory_log_service_fixture, admin_headers):
    """``created_at`` 序列化按 Pydantic JSON 自动转为 naive UTC ISO 格式(无 tz)。"""
    _seed_via_emit_sync(
        memory_log_service_fixture,
        [_make_event(timestamp=datetime(2026, 7, 29, 10, 0, 0))],
    )
    resp = client.get("/api/admin/logs", headers=admin_headers)
    body = resp.json()
    assert "2026-07-29T10:00:00" in body["items"][0]["created_at"]
    # 序列化结果不包含 tz 信息(naive UTC)
    assert "+00:00" not in body["items"][0]["created_at"]
    assert "Z" not in body["items"][0]["created_at"].split(".")[-1]


# =============================================================================
# 6.5 列表返回结构：items / total / limit / offset
# =============================================================================


def test_list_returns_items_total_limit_offset_envelope(client, memory_log_service_fixture, admin_headers):
    """``GET /api/admin/logs`` 响应必须是 ``{items,total,limit,offset}`` 信封结构。

    验证:
    - 同一 filters 同时用于 ``query_logs`` 与 ``count_logs``,结果一致
    - ``items`` 是数组、``total`` 是总数、``limit`` / ``offset`` 回显入参
    - ``items`` 内是白名单字段(见下条用例)
    """
    _seed_via_emit_sync(
        memory_log_service_fixture,
        [
            _make_event(action="ssh_execute_command", target_name="alpha"),
            _make_event(action="ssh_execute_command", target_name="beta"),
            _make_event(action="ssh_execute_command", target_name="gamma"),
        ],
    )
    resp = client.get("/api/admin/logs?limit=2&offset=0", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    # 信封字段必须存在且类型正确
    assert set(body.keys()) == {"items", "total", "limit", "offset"}
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert body["total"] == 3
    assert len(body["items"]) == 2


def test_list_envelope_total_matches_count_for_same_filters(
    client, memory_log_service_fixture, admin_headers
):
    """``total`` 必须与 ``count_logs(<同 filter>)`` 一致,保证同一过滤器语义统一。"""
    _seed_via_emit_sync(
        memory_log_service_fixture,
        [
            _make_event(action="a-1", log_type="ssh"),
            _make_event(action="a-2", log_type="ssh"),
            _make_event(action="b-1", log_type="auth"),
        ],
    )
    resp = client.get("/api/admin/logs?log_type=ssh", headers=admin_headers)
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert all(item["log_type"] == "ssh" for item in body["items"])


def test_list_envelope_empty_when_no_events(client, memory_log_service_fixture, admin_headers):
    """空数据 → ``items=[]`` / ``total=0``,``limit/offset`` 回显入参。"""
    resp = client.get("/api/admin/logs?limit=10&offset=0", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"items": [], "total": 0, "limit": 10, "offset": 0}


# =============================================================================
# 7. 过滤器：log_type / action / result / level / source / user_id / username
# =============================================================================


def test_list_filter_log_type(client, memory_log_service_fixture, admin_headers):
    """``log_type=ssh`` 过滤。"""
    _seed_via_emit_sync(
        memory_log_service_fixture,
        [
            _make_event(action="login", log_type="auth", source="auth_router"),
            _make_event(action="ssh_execute_command", log_type="ssh"),
            _make_event(action="ssh_get_system_logs", log_type="ssh"),
        ],
    )
    resp = client.get("/api/admin/logs?log_type=ssh", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert all(item["log_type"] == "ssh" for item in body["items"])


def test_list_filter_action(client, memory_log_service_fixture, admin_headers):
    """``action=ssh_execute_command`` 过滤。"""
    _seed_via_emit_sync(
        memory_log_service_fixture,
        [
            _make_event(action="ssh_execute_command"),
            _make_event(action="ssh_get_system_logs"),
        ],
    )
    resp = client.get("/api/admin/logs?action=ssh_execute_command", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["action"] == "ssh_execute_command"


def test_list_filter_result_and_level(client, memory_log_service_fixture, admin_headers):
    """``result=blocked`` 与 ``level=warning`` 过滤。"""
    _seed_via_emit_sync(
        memory_log_service_fixture,
        [
            _make_event(result="success", level="info"),
            _make_event(result="blocked", level="warning"),
            _make_event(result="blocked", level="warning"),
        ],
    )
    resp = client.get(
        "/api/admin/logs?result=blocked&level=warning", headers=admin_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2


def test_list_filter_user(client, memory_log_service_fixture, admin_headers):
    """``user_id`` / ``username`` 过滤。"""
    _seed_via_emit_sync(
        memory_log_service_fixture,
        [
            _make_event(user_id=1, username="alice"),
            _make_event(user_id=2, username="bob"),
            _make_event(user_id=2, username="bob"),
        ],
    )
    resp = client.get("/api/admin/logs?user_id=2&username=bob", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert all(item["username"] == "bob" and item["user_id"] == 2 for item in body["items"])


def test_list_filter_target(client, memory_log_service_fixture, admin_headers):
    """``target_type`` / ``target_id`` / ``target_name`` 过滤。"""
    _seed_via_emit_sync(
        memory_log_service_fixture,
        [
            _make_event(target_type="devops_server", target_id="srv-1", target_name="alpha"),
            _make_event(target_type="devops_server", target_id="srv-2", target_name="beta"),
        ],
    )
    resp = client.get(
        "/api/admin/logs?target_type=devops_server&target_name=alpha", headers=admin_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["target_name"] == "alpha"


def test_list_filter_correlation_and_tool_call(client, memory_log_service_fixture, admin_headers):
    """``correlation_id`` / ``tool_call_id`` / ``session_id`` / ``request_id`` 过滤。"""
    _seed_via_emit_sync(
        memory_log_service_fixture,
        [
            _make_event(
                correlation_id="cid-A",
                tool_call_id="call-1",
                session_id="sess-1",
                request_id="req-1",
            ),
            _make_event(
                correlation_id="cid-B",
                tool_call_id="call-2",
                session_id="sess-2",
                request_id="req-2",
            ),
        ],
    )
    resp = client.get(
        "/api/admin/logs?correlation_id=cid-A&tool_call_id=call-1"
        "&session_id=sess-1&request_id=req-1",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1


# =============================================================================
# 8. 分页：limit / offset
# =============================================================================


def test_list_pagination_limit_and_offset(client, memory_log_service_fixture, admin_headers):
    """分页:limit=2 / offset=1 跳过首条。"""
    _seed_via_emit_sync(
        memory_log_service_fixture,
        [
            _make_event(action="a-1", timestamp=datetime(2026, 7, 29, 10, 0, 0)),
            _make_event(action="a-2", timestamp=datetime(2026, 7, 29, 10, 0, 1)),
            _make_event(action="a-3", timestamp=datetime(2026, 7, 29, 10, 0, 2)),
        ],
    )
    resp = client.get("/api/admin/logs?limit=2&offset=1", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    # 按 created_at 倒序,offset=1 跳过最新一条(a-3),剩余 a-2 / a-1
    actions = [item["action"] for item in body["items"]]
    assert "a-3" not in actions  # 最新一条被跳过
    assert set(actions) == {"a-1", "a-2"}


def test_list_default_limit_is_50(client, memory_log_service_fixture, admin_headers):
    """默认 limit = 50。"""
    # 写入 60 条
    _seed_via_emit_sync(
        memory_log_service_fixture,
        [_make_event(action=f"act-{i}", timestamp=datetime(2026, 7, 29, 10, 0, i % 60)) for i in range(60)],
    )
    resp = client.get("/api/admin/logs", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 60
    assert len(body["items"]) == 50


# =============================================================================
# 9. created_from / created_to 时间范围
# =============================================================================


def test_list_created_range_filter(client, memory_log_service_fixture, admin_headers):
    """``created_from`` / ``created_to`` 时间范围过滤。"""
    _seed_via_emit_sync(
        memory_log_service_fixture,
        [
            _make_event(action="early", timestamp=datetime(2026, 7, 1, 0, 0, 0)),
            _make_event(action="middle", timestamp=datetime(2026, 7, 15, 0, 0, 0)),
            _make_event(action="late", timestamp=datetime(2026, 7, 30, 0, 0, 0)),
        ],
    )
    resp = client.get(
        "/api/admin/logs?created_from=2026-07-10T00:00:00&created_to=2026-07-20T00:00:00",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    actions = [item["action"] for item in body["items"]]
    assert actions == ["middle"]


# =============================================================================
# 10. 详情：GET /api/admin/logs/{log_id}
# =============================================================================


def test_detail_returns_log_when_exists(client, memory_log_service_fixture, admin_headers):
    """存在 log_id → 200 + 单条详情。"""
    _seed_via_emit_sync(
        memory_log_service_fixture,
        [
            _make_event(action="alpha", target_name="x"),
            _make_event(action="beta", target_name="y"),
        ],
    )
    resp = client.get("/api/admin/logs/1", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 1
    assert body["action"] == "alpha"


def test_detail_returns_404_when_missing(client, memory_log_service_fixture, admin_headers):
    """log_id 不存在 → 404。"""
    _seed_via_emit_sync(memory_log_service_fixture, [_make_event()])
    resp = client.get("/api/admin/logs/9999", headers=admin_headers)
    assert resp.status_code == 404


def test_detail_includes_related_logs_when_correlation_id_present(
    client, memory_log_service_fixture, admin_headers
):
    """详情含 correlation_id 时,响应附带 related_logs（同 correlation_id 的其它日志）。"""
    _seed_via_emit_sync(
        memory_log_service_fixture,
        [
            _make_event(action="batch-summary", correlation_id="cid-X", target_name="theta"),
            _make_event(action="child-1", correlation_id="cid-X", target_name="theta"),
            _make_event(action="child-2", correlation_id="cid-X", target_name="theta"),
            _make_event(action="unrelated", correlation_id="cid-Y", target_name="theta"),
        ],
    )
    resp = client.get("/api/admin/logs/1", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 1
    assert body["correlation_id"] == "cid-X"
    # related_logs 存在且含至少 2 条同 cid 的关联
    assert "related_logs" in body
    related = body["related_logs"]
    assert isinstance(related, list)
    related_ids = [r["id"] for r in related]
    # 当前条目 id=1 出现一次,另两条 child 出现 → 3 条
    assert related_ids.count(1) >= 1
    assert 2 in related_ids
    assert 3 in related_ids
    # unrelated 不应出现
    assert 4 not in related_ids


def test_detail_no_related_logs_when_correlation_missing(
    client, memory_log_service_fixture, admin_headers
):
    """无 correlation_id 时,related_logs 为空列表。"""
    _seed_via_emit_sync(
        memory_log_service_fixture,
        [_make_event(correlation_id=None)],
    )
    resp = client.get("/api/admin/logs/1", headers=admin_headers)
    body = resp.json()
    assert body["related_logs"] == []


def test_detail_rejects_invalid_log_id(client, memory_log_service_fixture, admin_headers):
    """非整数 log_id → 422。"""
    resp = client.get("/api/admin/logs/abc", headers=admin_headers)
    assert resp.status_code == 422


# =============================================================================
# 11. 空数据
# =============================================================================


def test_list_empty_when_no_events(client, memory_log_service_fixture, admin_headers):
    """空内存表 → 200 + ``{items:[], total:0, limit, offset}``(非 404)。"""
    resp = client.get("/api/admin/logs", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}


# =============================================================================
# 12. log_router 已注册到 main.register_routers
# =============================================================================


def test_log_router_registered_in_main():
    """``app/main.py`` 的 ``register_routers`` 必须包含 log_router。"""
    from app.main import register_routers
    import inspect

    src = inspect.getsource(register_routers)
    assert "log_router" in src, (
        "app/main.py::register_routers 必须 include_router log_router"
    )
