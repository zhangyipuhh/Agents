# -*- coding:utf-8 -*-
"""
ServerInspectionRecordService 单元测试（2026-08-05 新增）。

覆盖目标：
    - 模块导入 / 类存在；
    - ``save_inspection_result`` 双表同事务写入、UPSERT 覆盖、未注册业务名跳过、
      db=None 抛 RuntimeError；
    - ``list_latest`` admin 分支（LEFT JOIN）与普通用户分支
      （OwnershipScope 过滤 + 同 server_id 去重 + 无快照 unknown 空态）；
    - ``list_records`` 越权 None（404）、时间过滤、limit 边界；
    - ``resolve_collect_targets`` 存在性 404、越权 403、admin 全量、去重保序；
    - 私有派生 helper（status 五路、cpu linux/windows、disk 根盘命中+回退+无盘）。

测试风格：
    - 顶部中文 docstring；
    - 通过 pytest + AsyncMock / MagicMock 注入 db / devops_server_service /
      user_server_service / inspection_script_service 替身；
    - ``_build_tx_db`` 模拟 ``pool.acquire() → conn.transaction()`` 真实链路
      （参照 test_inspection_script_service 既有模式）。
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.shared.utils.auth.ownership_scope import OwnershipScope
from app.shared.utils.server_inspection_record_service import (
    ServerInspectionNotFoundError,
    ServerInspectionPermissionError,
    ServerInspectionRecordService,
)


# ============================================================================
# FakeDb / FakeConn（最小化 asyncpg pool + connection 替身）
# ============================================================================


class _FakeAsyncContextManager:
    def __init__(self, cm):
        self._cm = cm

    async def __aenter__(self):
        return self._cm

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _build_tx_db() -> tuple:
    """构造 asyncpg ``Pool`` 替身：``db.acquire()`` 返回带 ``transaction()`` 的 connection。

    Returns:
        tuple: (db, conn) MagicMock 实例，conn 暴露
        ``fetchrow / execute / fetch`` 异步方法 + ``transaction()`` 异步 CM。
    """
    db = MagicMock(name="db_pool_stub")
    conn = MagicMock(name="db_connection_stub")
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchval = AsyncMock(return_value=False)

    @asynccontextmanager
    async def _tx():
        yield None

    conn.transaction = MagicMock(side_effect=lambda: _FakeAsyncContextManager(_tx()))
    db.acquire = MagicMock(side_effect=lambda: _FakeAsyncContextManager(conn))
    return db, conn


# ============================================================================
# 桩 service
# ============================================================================


class _StubDevopsService:
    """模拟 ``DevOpsServerService`` 暴露 ``list_public_servers``。"""

    def __init__(self, rows: Optional[List[Dict[str, Any]]] = None, fail: bool = False):
        self._rows = rows or []
        self._fail = fail

    def list_public_servers(self):
        if self._fail:
            raise RuntimeError("devops_list_failed")
        return self._rows


class _StubUserServerService:
    """模拟 ``UserServerService`` 暴露 ``list_nodes(scope)``。"""

    def __init__(self, nodes: Optional[List[Dict[str, Any]]] = None, fail: bool = False):
        self._nodes = nodes or []
        self._fail = fail

    def list_nodes(self, scope):
        if self._fail:
            raise RuntimeError("user_server_failed")
        # 简单过滤：非 admin / 非 system 仅返回 created_by_user_id 命中
        if scope.is_admin or scope.system:
            return list(self._nodes)
        return [n for n in self._nodes if n.get("created_by_user_id") == scope.user_id]


class _StubInspectionScriptService:
    """模拟 ``InspectionScriptService.get_script_by_name``。"""

    def __init__(self, mapping: Optional[Dict[str, int]] = None, fail: bool = False):
        self._mapping = mapping or {}
        self._fail = fail

    def get_script_by_name(self, name: str):
        if self._fail:
            raise RuntimeError("script_lookup_failed")
        if name not in self._mapping:
            return None
        return {"id": self._mapping[name], "name": name}


# ============================================================================
# 辅助：构造 ServerOpsItem 报告
# ============================================================================


def _make_report(items: List[Dict[str, Any]]):
    """构造含 ``items`` 属性的最小 report 替身。"""

    class _Report:
        def __init__(self, items):
            self.items = items

    return _Report(items)


def _server_ops_item(**overrides) -> Dict[str, Any]:
    """构造 ``ServerOpsItem.vars()`` 形式 dict（dataclass 兼容）。"""
    base = {
        "business_name": "biz-A",
        "success": True,
        "exit_code": 0,
        "stdout": "",
        "stderr": "",
        "duration_ms": 42,
        "error_message": "",
        "skipped": False,
        "inspection_parser": "json",
        "parsed_values": {
            "disks": [{"mount": "/", "disk_used_pct": 58}],
            "mem_used_pct": 45.0,
            "cpu_idle_pct": 76.5,
            "load_1m": 0.5,
        },
        "field_results": [
            {"key": "cpu_idle_pct", "name_zh": "CPU空闲率", "value": 76.5,
             "status": "pass", "message": "", "warn": 20, "crit": 10, "unit": "%"},
        ],
        "inspection_status": "pass",
        "inspection_error": "",
        "inspection_script_name": "linux-bash",
        "inspection_script_display_name": "Linux Bash",
        "inspection_script_platform": "linux",
        "inspection_script_version": "",
    }
    base.update(overrides)
    return base


# ============================================================================
# P0：模块 / 类
# ============================================================================


def test_module_importable():
    """模块可导入，核心类/异常可访问。"""
    from app.shared.utils import server_inspection_record_service as mod

    assert hasattr(mod, "ServerInspectionRecordService")
    assert hasattr(mod, "ServerInspectionNotFoundError")
    assert hasattr(mod, "ServerInspectionPermissionError")


def test_service_constructable():
    """默认构造参数全部可选；不传 db 时仍可实例化（降级模式）。"""
    svc = ServerInspectionRecordService()
    assert svc._db is None
    assert svc._devops_server_service is None


# ============================================================================
# save_inspection_result
# ============================================================================


def _setup_save_env(items=None, biz_rows=None, script_map=None,
                    devops_fail=False, script_fail=False):
    """统一构造 save 链路所需的 db + 服务桩。

    Returns:
        tuple: (db, conn, svc, devops_stub, script_stub)
    """
    db, conn = _build_tx_db()
    # 业务名 → id 映射（devops_servers 内存缓存替身）
    biz_rows = biz_rows or [{"id": 1, "business_name": "biz-A", "server_type": "linux"}]
    devops = _StubDevopsService(biz_rows, fail=devops_fail)
    script = _StubInspectionScriptService(script_map or {"linux-bash": 7}, fail=script_fail)
    items = items or [_server_ops_item()]
    report = _make_report(items)
    svc = ServerInspectionRecordService(
        db=db,
        devops_server_service=devops,
        inspection_script_service=script,
    )
    # 第一个 fetchrow 返回 records INSERT 拿到的 id；后续任意
    conn.fetchrow.return_value = {"id": 100}
    return db, conn, svc, devops, script


def test_save_inserts_records_and_upserts_snapshot_in_one_transaction():
    """单条采集：INSERT records RETURNING id + UPSERT snapshot；同一事务。"""
    db, conn, svc, devops, script = _setup_save_env()
    saved = asyncio.run(svc.save_inspection_result(
        _make_report([_server_ops_item()]),
        schedule_id=10,
        run_id=20,
    ))
    assert saved == 1
    # acquire + transaction 都只调用一次（单事务）
    assert db.acquire.call_count == 1
    assert conn.transaction.call_count == 1
    # fetchrow (records INSERT) + execute (snapshot UPSERT) 各一次
    assert conn.fetchrow.await_count == 1
    assert conn.execute.await_count == 1


def test_save_uses_upsert_on_conflict_for_snapshot():
    """snapshot 写入必须含 ``ON CONFLICT (server_id) DO UPDATE``（幂等覆盖）。"""
    db, conn, svc, devops, script = _setup_save_env()
    asyncio.run(svc.save_inspection_result(
        _make_report([_server_ops_item()]),
    ))
    upsert_sql = conn.execute.await_args.args[0]
    assert "ON CONFLICT (server_id) DO UPDATE" in upsert_sql
    assert "EXCLUDED.record_id" in upsert_sql
    assert "EXCLUDED.collected_at" in upsert_sql


def test_save_records_sql_includes_all_sixteen_columns():
    """records INSERT 字段齐全（含溯源 4 列 + 审计 1 列）。"""
    db, conn, svc, devops, script = _setup_save_env()
    asyncio.run(svc.save_inspection_result(
        _make_report([_server_ops_item()]),
        schedule_id=10, run_id=20, created_by_user_id=99,
    ))
    insert_sql = conn.fetchrow.await_args.args[0]
    expected_cols = [
        "server_id", "business_name", "collected_at",
        "schedule_id", "run_id", "inspection_script_id", "created_by_user_id",
        "success", "skipped", "exit_code", "duration_ms",
        "inspection_status", "error_message", "inspection_error",
        "parsed_values", "field_results",
    ]
    for col in expected_cols:
        assert col in insert_sql, f"records INSERT 缺少字段 {col}"
    # 参数顺序：$1..$16 对应 cols 顺序
    params = conn.fetchrow.await_args.args[1:]
    assert params[0] == 1                # server_id
    assert params[1] == "biz-A"          # business_name
    assert params[3] == 10               # schedule_id
    assert params[4] == 20               # run_id
    assert params[5] == 7                # inspection_script_id（由 script_stub 反查）
    assert params[6] == 99               # created_by_user_id
    assert params[9] == 0                # exit_code
    assert params[10] == 42              # duration_ms
    assert params[11] == "pass"          # inspection_status
    # parsed_values / field_results 应为 JSON 字符串
    parsed = json.loads(params[14])
    assert parsed["mem_used_pct"] == 45.0
    fields = json.loads(params[15])
    assert fields[0]["key"] == "cpu_idle_pct"


def test_save_skips_unknown_business_name_without_aborting():
    """未注册业务名记 warning + 跳过，不中断整体（其余仍落库）。"""
    db, conn, svc, devops, script = _setup_save_env(
        items=[
            _server_ops_item(business_name="biz-unknown"),
            _server_ops_item(business_name="biz-A"),
        ],
    )
    saved = asyncio.run(svc.save_inspection_result(_make_report([
        _server_ops_item(business_name="biz-unknown"),
        _server_ops_item(business_name="biz-A"),
    ])))
    assert saved == 1
    # 只有 biz-A 落库 → 1 次 fetchrow + 1 次 execute
    assert conn.fetchrow.await_count == 1
    assert conn.execute.await_count == 1


def test_save_empty_items_returns_zero():
    """空报告 / 空 items → 0，不开事务。"""
    db, conn, svc, devops, script = _setup_save_env(items=[])
    report = _make_report([])
    saved = asyncio.run(svc.save_inspection_result(report))
    assert saved == 0
    assert db.acquire.call_count == 0


def test_save_db_none_raises_runtime_error():
    """db=None 时写入抛 RuntimeError。"""
    svc = ServerInspectionRecordService(db=None, devops_server_service=_StubDevopsService())
    with pytest.raises(RuntimeError):
        asyncio.run(svc.save_inspection_result(_make_report([_server_ops_item()])))


def test_save_without_devops_service_skips_items():
    """未注入 devops_server_service：所有业务名都无法解析 → 全部跳过，返回 0。

    此时会开事务但循环内零次落库（acquire=1, fetchrow=0, execute=0）。
    """
    db, conn = _build_tx_db()
    svc = ServerInspectionRecordService(db=db)
    saved = asyncio.run(svc.save_inspection_result(_make_report([_server_ops_item()])))
    assert saved == 0
    assert db.acquire.call_count == 1
    assert conn.fetchrow.await_count == 0
    assert conn.execute.await_count == 0


def test_save_handles_devops_service_failure_gracefully():
    """devops 列表读取抛异常 → 当作空映射处理；剩余项继续落库。"""
    db, conn, svc, devops, script = _setup_save_env(devops_fail=True)
    saved = asyncio.run(svc.save_inspection_result(_make_report([_server_ops_item()])))
    assert saved == 0


def test_save_resolves_inspection_script_id_via_stub():
    """inspection_script_service.get_script_by_name 返回 None → inspection_script_id 写 NULL。"""
    db, conn, svc, devops, script = _setup_save_env(
        items=[_server_ops_item(inspection_script_name="ghost")],
        script_map={"linux-bash": 7},  # ghost 不在映射中
    )
    asyncio.run(svc.save_inspection_result(_make_report([
        _server_ops_item(inspection_script_name="ghost"),
    ])))
    params = conn.fetchrow.await_args.args[1:]
    assert params[5] is None  # inspection_script_id


def test_save_handles_inspection_script_service_failure():
    """inspection_script_service 抛异常 → inspection_script_id 写 NULL，不中断整体。"""
    db, conn, svc, devops, script = _setup_save_env(script_fail=True)
    saved = asyncio.run(svc.save_inspection_result(_make_report([_server_ops_item()])))
    assert saved == 1
    params = conn.fetchrow.await_args.args[1:]
    assert params[5] is None


# ============================================================================
# list_latest
# ============================================================================


def test_list_latest_db_none_returns_empty():
    """db=None 时返回空列表（不影响响应结构）。"""
    svc = ServerInspectionRecordService()
    scope = OwnershipScope.for_user(1)
    items = asyncio.run(svc.list_latest(scope))
    assert items == []


def _setup_list_env(scope, devops_rows=None, snapshot_rows=None, nodes=None,
                    user_svc=None):
    """构造 list_latest / list_records 链路：db + 桩 services。

    注：service 调用 ``self._db.fetch / fetchval``，与 ``self._db.acquire()``
    是两条不同的调用路径，故 AsyncMock 必须挂在 db（pool）而非 conn。
    """
    db, conn = _build_tx_db()
    devops = _StubDevopsService(devops_rows or [])
    user = user_svc or _StubUserServerService(nodes or [])
    svc = ServerInspectionRecordService(
        db=db,
        devops_server_service=devops,
        user_server_service=user,
    )
    db.fetch = AsyncMock(return_value=snapshot_rows or [])
    db.fetchval = AsyncMock(return_value=False)
    return db, conn, svc


def test_list_latest_admin_uses_left_join_query():
    """admin 走 ``devops_servers LEFT JOIN server_latest_snapshot``；ORDER BY ds.id。"""
    db, conn, svc = _setup_list_env(
        OwnershipScope.system_scope(),
        devops_rows=[
            {"id": 1, "business_name": "biz-A", "server_type": "linux"},
            {"id": 2, "business_name": "biz-B", "server_type": "windows"},
        ],
    )
    # admin LEFT JOIN 返回 2 行：server 1 有快照、server 2 无快照
    admin_rows = [
        {
            "node_id": None,
            "node_name": "biz-A",
            "server_id": 1,
            "business_name": "biz-A",
            "server_type": "linux",
            "collected_at": datetime(2026, 8, 5, 10, 0, 0),
            "success": True,
            "inspection_status": "pass",
            "duration_ms": 42,
            "error_message": None,
            "parsed_values": json.dumps({"disks": [{"mount": "/", "disk_used_pct": 58}],
                                          "mem_used_pct": 45.0, "cpu_idle_pct": 76.5}),
            "field_results": json.dumps([]),
        },
        {
            "node_id": None,
            "node_name": "biz-B",
            "server_id": 2,
            "business_name": "biz-B",
            "server_type": "windows",
            "collected_at": None,
            "success": None,
            "inspection_status": None,
            "duration_ms": None,
            "error_message": None,
            "parsed_values": None,
            "field_results": None,
        },
    ]
    db.fetch = AsyncMock(return_value=admin_rows)
    items = asyncio.run(svc.list_latest(OwnershipScope.system_scope()))
    sql = db.fetch.await_args.args[0]
    assert "FROM devops_servers ds" in sql
    assert "LEFT JOIN server_latest_snapshot s" in sql
    assert "ORDER BY ds.id" in sql
    assert len(items) == 2
    biz_a = next(it for it in items if it["business_name"] == "biz-A")
    assert biz_a["status"] == "ok"
    assert biz_a["metrics"]["cpu"] == 23.5   # 100 - 76.5
    assert biz_a["metrics"]["mem"] == 45.0
    assert biz_a["metrics"]["disk"] == 58.0
    biz_b = next(it for it in items if it["business_name"] == "biz-B")
    assert biz_b["status"] == "unknown"      # 无快照


def test_list_latest_user_filters_by_user_server_nodes():
    """普通用户仅看到自己节点关联的服务器；非自己节点被过滤。"""
    db, conn, svc = _setup_list_env(
        OwnershipScope.for_user(1, is_admin=False),
        devops_rows=[
            {"id": 1, "business_name": "biz-A", "server_type": "linux"},
            {"id": 2, "business_name": "biz-B", "server_type": "linux"},
        ],
        snapshot_rows=[],
        user_svc=_StubUserServerService(nodes=[
            # 用户 1 只添加了 biz-A
            {"id": 11, "node_type": "server", "name": "MyA",
             "source_devops_server_id": 1, "created_by_user_id": 1,
             "parent_id": None, "sort_order": 0,
             "business_name": "biz-A", "server_type": "linux"},
        ]),
    )
    items = asyncio.run(svc.list_latest(OwnershipScope.for_user(1, is_admin=False)))
    assert len(items) == 1
    assert items[0]["server_id"] == 1
    assert items[0]["node_name"] == "MyA"
    assert items[0]["status"] == "unknown"


def test_list_latest_user_dedup_same_server_in_two_folders():
    """同一 server 在两个文件夹下重复引用 → 去重，按 sort_order,node_id 字典序最小节点取胜。"""
    db, conn, svc = _setup_list_env(
        OwnershipScope.for_user(1, is_admin=False),
        devops_rows=[
            {"id": 1, "business_name": "biz-A", "server_type": "linux"},
        ],
        snapshot_rows=[{
            "server_id": 1,
            "snapshot_business_name": "biz-A",
            "collected_at": datetime(2026, 8, 5, 10, 0, 0),
            "success": False,
            "inspection_status": "crit",
            "duration_ms": 10,
            "error_message": "remote timeout",
            "parsed_values": json.dumps({"disks": [{"mount": "/", "disk_used_pct": 92}],
                                          "mem_used_pct": 81.0}),
            "field_results": json.dumps([]),
        }],
        user_svc=_StubUserServerService(nodes=[
            {"id": 11, "node_type": "server", "name": "FolderA版",
             "source_devops_server_id": 1, "created_by_user_id": 1,
             "parent_id": None, "sort_order": 0,
             "business_name": "biz-A", "server_type": "linux"},
            {"id": 12, "node_type": "server", "name": "FolderB版",
             "source_devops_server_id": 1, "created_by_user_id": 1,
             "parent_id": None, "sort_order": 1,
             "business_name": "biz-A", "server_type": "linux"},
        ]),
    )
    items = asyncio.run(svc.list_latest(OwnershipScope.for_user(1, is_admin=False)))
    assert len(items) == 1
    # sort_order 较小的 (0, 11) 胜出
    assert items[0]["node_name"] == "FolderA版"
    assert items[0]["status"] == "err"   # success=False → err


def test_list_latest_does_not_return_ip_field():
    """响应字段白名单不含 ip / port / password 等敏感字段。"""
    db, conn, svc = _setup_list_env(
        OwnershipScope.system_scope(),
        devops_rows=[{"id": 1, "business_name": "biz-A", "server_type": "linux"}],
        snapshot_rows=[],
    )
    items = asyncio.run(svc.list_latest(OwnershipScope.system_scope()))
    forbidden = {"ip", "port", "username", "password", "password_encrypted"}
    for it in items:
        for key in forbidden:
            assert key not in it, f"list_latest 不应返回敏感字段 {key}"


# ============================================================================
# list_records
# ============================================================================


def test_list_records_returns_none_when_server_not_visible():
    """不存在 / 越权 → None（router 映 404）。"""
    db, conn, svc = _setup_list_env(
        OwnershipScope.for_user(1, is_admin=False),
        user_svc=_StubUserServerService(nodes=[]),
    )
    conn.fetchval = AsyncMock(return_value=False)   # devops_servers 不存在
    res = asyncio.run(svc.list_records(server_id=999, scope=OwnershipScope.for_user(1)))
    assert res is None


def test_list_records_visibility_for_non_admin():
    """普通用户：server 不在自己可见节点集 → None。"""
    db, conn, svc = _setup_list_env(
        OwnershipScope.for_user(1, is_admin=False),
        user_svc=_StubUserServerService(nodes=[
            {"id": 11, "node_type": "server", "name": "MyA",
             "source_devops_server_id": 1, "created_by_user_id": 1,
             "parent_id": None, "sort_order": 0,
             "business_name": "biz-A", "server_type": "linux"},
        ]),
    )
    conn.fetchval = AsyncMock(return_value=True)    # 99 存在于 devops_servers
    res = asyncio.run(svc.list_records(server_id=99, scope=OwnershipScope.for_user(1)))
    assert res is None


def test_list_records_admin_passes_visibility_check():
    """admin：只要 server 存在即放行。"""
    db, conn, svc = _setup_list_env(OwnershipScope.system_scope())
    db.fetchval = AsyncMock(return_value=True)
    db.fetch = AsyncMock(return_value=[])
    res = asyncio.run(svc.list_records(server_id=7, scope=OwnershipScope.system_scope()))
    assert res == []


def test_list_records_with_time_range_and_limit():
    """start/end/limit 正确写入 SQL 参数。"""
    db, conn, svc = _setup_list_env(OwnershipScope.system_scope())
    db.fetchval = AsyncMock(return_value=True)
    db.fetch = AsyncMock(return_value=[{"id": 1, "server_id": 7,
                                          "collected_at": datetime(2026, 8, 5),
                                          "parsed_values": None,
                                          "field_results": "[]"}])
    start = datetime(2026, 8, 1)
    end = datetime(2026, 8, 6)
    res = asyncio.run(svc.list_records(7, OwnershipScope.system_scope(),
                                       start=start, end=end, limit=200))
    sql = db.fetch.await_args.args[0]
    params = db.fetch.await_args.args[1:]
    assert "collected_at >= $" in sql
    assert "collected_at <= $" in sql
    assert "ORDER BY collected_at DESC" in sql
    # 参数顺序：server_id, start, end, limit
    assert params[0] == 7
    assert params[1] == start
    assert params[2] == end
    assert params[3] == 200
    assert len(res) == 1


def test_list_records_limit_validation():
    """limit 超出 1~1000 抛 ValueError（router 映 400）。"""
    db, conn, svc = _setup_list_env(OwnershipScope.system_scope())
    with pytest.raises(ValueError):
        asyncio.run(svc.list_records(1, OwnershipScope.system_scope(), limit=0))
    with pytest.raises(ValueError):
        asyncio.run(svc.list_records(1, OwnershipScope.system_scope(), limit=1001))


# ============================================================================
# resolve_collect_targets
# ============================================================================


def test_resolve_collect_targets_admin_full_access():
    """admin：任意已存在 server_id → business_names（保序去重）。"""
    db, conn, svc = _setup_list_env(
        OwnershipScope.system_scope(),
        devops_rows=[
            {"id": 1, "business_name": "biz-A", "server_type": "linux"},
            {"id": 2, "business_name": "biz-B", "server_type": "linux"},
        ],
    )
    scope = OwnershipScope.system_scope()
    names = svc.resolve_collect_targets([1, 2, 1], scope)   # 重复 1
    assert names == ["biz-A", "biz-B"]


def test_resolve_collect_targets_missing_id_raises_not_found():
    """任一 server_id 不存在 → ServerInspectionNotFoundError。"""
    db, conn, svc = _setup_list_env(
        OwnershipScope.system_scope(),
        devops_rows=[{"id": 1, "business_name": "biz-A", "server_type": "linux"}],
    )
    with pytest.raises(ServerInspectionNotFoundError):
        svc.resolve_collect_targets([1, 999], OwnershipScope.system_scope())


def test_resolve_collect_targets_unauthorized_raises_permission():
    """普通用户：server_id 不在可见节点集 → ServerInspectionPermissionError。"""
    db, conn, svc = _setup_list_env(
        OwnershipScope.for_user(1, is_admin=False),
        devops_rows=[
            {"id": 1, "business_name": "biz-A", "server_type": "linux"},
            {"id": 2, "business_name": "biz-B", "server_type": "linux"},
        ],
        user_svc=_StubUserServerService(nodes=[
            {"id": 11, "node_type": "server", "name": "A",
             "source_devops_server_id": 1, "created_by_user_id": 1,
             "parent_id": None, "sort_order": 0,
             "business_name": "biz-A", "server_type": "linux"},
        ]),
    )
    with pytest.raises(ServerInspectionPermissionError):
        svc.resolve_collect_targets([1, 2], OwnershipScope.for_user(1))


def test_resolve_collect_targets_user_in_visible_set_passes():
    """普通用户：所有 server_id 都在自己的节点集 → 通过。"""
    db, conn, svc = _setup_list_env(
        OwnershipScope.for_user(1, is_admin=False),
        devops_rows=[
            {"id": 1, "business_name": "biz-A", "server_type": "linux"},
        ],
        user_svc=_StubUserServerService(nodes=[
            {"id": 11, "node_type": "server", "name": "A",
             "source_devops_server_id": 1, "created_by_user_id": 1,
             "parent_id": None, "sort_order": 0,
             "business_name": "biz-A", "server_type": "linux"},
        ]),
    )
    names = svc.resolve_collect_targets([1], OwnershipScope.for_user(1))
    assert names == ["biz-A"]


def test_resolve_collect_targets_db_none_raises():
    """db=None → RuntimeError。"""
    svc = ServerInspectionRecordService()
    with pytest.raises(RuntimeError):
        svc.resolve_collect_targets([1], OwnershipScope.system_scope())


# ============================================================================
# 私有派生 helper
# ============================================================================


class TestDeriveStatus:
    """``_derive_status`` 五路覆盖。"""

    def test_pass_returns_ok(self):
        assert ServerInspectionRecordService._derive_status(True, False, "pass") == "ok"

    def test_warn_returns_err(self):
        assert ServerInspectionRecordService._derive_status(True, False, "warn") == "err"

    def test_crit_returns_err(self):
        assert ServerInspectionRecordService._derive_status(True, False, "crit") == "err"

    def test_success_false_returns_err(self):
        # success is False 即 SSH 失败 → err（即便 inspection_status 是 pass）
        assert ServerInspectionRecordService._derive_status(False, False, "pass") == "err"

    def test_skipped_returns_unknown(self):
        assert ServerInspectionRecordService._derive_status(None, True, "pass") == "unknown"

    def test_unassessed_returns_unknown(self):
        assert ServerInspectionRecordService._derive_status(True, False, "unassessed") == "unknown"

    def test_success_none_returns_unknown(self):
        assert ServerInspectionRecordService._derive_status(None, False, "pass") == "unknown"


class TestDeriveCpu:
    """``_derive_cpu`` linux/windows 派生口径。"""

    def test_linux_uses_100_minus_idle(self):
        cpu = ServerInspectionRecordService._derive_cpu("linux", {"cpu_idle_pct": 23.5})
        assert cpu == 76.5

    def test_linux_missing_idle_falls_back_to_used(self):
        cpu = ServerInspectionRecordService._derive_cpu("linux", {"cpu_used_pct": 50.0})
        assert cpu == 50.0

    def test_windows_uses_cpu_used(self):
        cpu = ServerInspectionRecordService._derive_cpu("windows", {"cpu_used_pct": 75.0})
        assert cpu == 75.0

    def test_windows_ignores_cpu_idle(self):
        # windows 不应该用 idle 反推
        cpu = ServerInspectionRecordService._derive_cpu("windows", {"cpu_idle_pct": 25.0})
        assert cpu is None

    def test_returns_none_when_no_data(self):
        assert ServerInspectionRecordService._derive_cpu("linux", {}) is None
        assert ServerInspectionRecordService._derive_cpu("windows", {}) is None


class TestPickRootDisk:
    """``_pick_root_disk_pct`` 系统盘 + 回退 + 空态。"""

    def test_linux_root_mount(self):
        disks = [{"mount": "/data", "disk_used_pct": 50},
                 {"mount": "/", "disk_used_pct": 80}]
        assert ServerInspectionRecordService._pick_root_disk_pct(disks, "linux") == 80

    def test_linux_no_root_falls_back_to_first(self):
        disks = [{"mount": "/data", "disk_used_pct": 60},
                 {"mount": "/var", "disk_used_pct": 70}]
        assert ServerInspectionRecordService._pick_root_disk_pct(disks, "linux") == 60

    def test_windows_c_backslash(self):
        disks = [{"mount": "D:\\", "disk_used_pct": 50},
                 {"mount": "C:\\", "disk_used_pct": 75}]
        assert ServerInspectionRecordService._pick_root_disk_pct(disks, "windows") == 75

    def test_windows_c_colon(self):
        disks = [{"mount": "C:", "disk_used_pct": 30}]
        assert ServerInspectionRecordService._pick_root_disk_pct(disks, "windows") == 30

    def test_windows_c_slash(self):
        disks = [{"mount": "C:/", "disk_used_pct": 88}]
        assert ServerInspectionRecordService._pick_root_disk_pct(disks, "windows") == 88

    def test_windows_case_insensitive(self):
        disks = [{"mount": "c:\\", "disk_used_pct": 22}]
        assert ServerInspectionRecordService._pick_root_disk_pct(disks, "windows") == 22

    def test_no_disks_returns_none(self):
        assert ServerInspectionRecordService._pick_root_disk_pct([], "linux") is None
        assert ServerInspectionRecordService._pick_root_disk_pct(None, "linux") is None

    def test_skips_non_dict_elements(self):
        disks = ["bad", None, {"mount": "/", "disk_used_pct": 12}]
        assert ServerInspectionRecordService._pick_root_disk_pct(disks, "linux") == 12


class TestCoerceFloat:
    """``_coerce_float`` 边界。"""

    def test_none_returns_none(self):
        assert ServerInspectionRecordService._coerce_float(None) is None

    def test_bool_returns_none(self):
        # bool 是 int 子类，此处显式拒绝
        assert ServerInspectionRecordService._coerce_float(True) is None
        assert ServerInspectionRecordService._coerce_float(False) is None

    def test_numeric_string_returns_float(self):
        assert ServerInspectionRecordService._coerce_float("42.5") == 42.5

    def test_garbage_string_returns_none(self):
        assert ServerInspectionRecordService._coerce_float("abc") is None

    def test_int_returns_float(self):
        assert ServerInspectionRecordService._coerce_float(10) == 10.0


# ============================================================================
# 集成：save → list_latest 端到端
# ============================================================================


def test_save_then_list_latest_round_trip():
    """落库后 list_latest 立即可见；status / metrics 派生正确。"""
    db, conn = _build_tx_db()
    devops = _StubDevopsService([
        {"id": 1, "business_name": "biz-A", "server_type": "linux"},
    ])
    svc = ServerInspectionRecordService(db=db, devops_server_service=devops)
    # 1) save → 模拟 records fetchrow 返回 id=1
    conn.fetchrow.return_value = {"id": 1}
    saved = asyncio.run(svc.save_inspection_result(
        _make_report([_server_ops_item(
            parsed_values={
                "disks": [{"mount": "/", "disk_used_pct": 80}],
                "mem_used_pct": 90.0,
                "cpu_idle_pct": 50.0,
            },
            field_results=[],
            inspection_status="warn",
        )]),
    ))
    assert saved == 1

    # 2) list_latest → db.fetch 返回 snapshot 行
    db.fetch = AsyncMock(return_value=[{
        "server_id": 1,
        "snapshot_business_name": "biz-A",
        "collected_at": datetime(2026, 8, 5),
        "success": True,
        "inspection_status": "warn",
        "duration_ms": 42,
        "error_message": None,
        "parsed_values": json.dumps({"disks": [{"mount": "/", "disk_used_pct": 80}],
                                      "mem_used_pct": 90.0, "cpu_idle_pct": 50.0}),
        "field_results": json.dumps([]),
    }])
    items = asyncio.run(svc.list_latest(OwnershipScope.system_scope()))
    assert len(items) == 1
    assert items[0]["status"] == "err"           # warn → err
    assert items[0]["metrics"]["cpu"] == 50.0    # 100 - 50
    assert items[0]["metrics"]["mem"] == 90.0
    assert items[0]["metrics"]["disk"] == 80.0


def test_save_pydantic_item_compatibility():
    """``ServerOpsItem`` dataclass 实例（非 dict）也能被识别落库。"""
    db, conn = _build_tx_db()
    devops = _StubDevopsService([{"id": 1, "business_name": "biz-A", "server_type": "linux"}])
    svc = ServerInspectionRecordService(db=db, devops_server_service=devops)
    conn.fetchrow.return_value = {"id": 5}

    from app.scripts.server_ops import ServerOpsItem
    item = ServerOpsItem(
        business_name="biz-A",
        success=True,
        exit_code=0,
        duration_ms=10,
        parsed_values={"disks": [{"mount": "/", "disk_used_pct": 12}], "mem_used_pct": 5},
        field_results=[],
        inspection_status="pass",
        inspection_script_name="linux-bash",
    )

    saved = asyncio.run(svc.save_inspection_result(_make_report([item])))
    assert saved == 1
    params = conn.fetchrow.await_args.args[1:]
    assert params[1] == "biz-A"
    assert params[10] == 10            # duration_ms
    assert params[11] == "pass"        # inspection_status