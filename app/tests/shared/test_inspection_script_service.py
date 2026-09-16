# -*- coding:utf-8 -*-
"""
InspectionScriptService 单元测试（2026-08-03 新增；2026-09-16 重构）
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_db() -> MagicMock:
    """构造一个 MagicMock 作为 asyncpg pool 替身。

    生产侧 InspectionScriptService 通过 ``await db.fetch(...)`` 等异步操作访问 DB,
    因此用 ``AsyncMock`` 让 awaitable 调用返回固定值。

    Returns:
        MagicMock: db 池替身（其 fetch/fetchrow/execute 为 AsyncMock）
    """
    db = MagicMock(name="db_pool_stub")
    db.fetch = AsyncMock(return_value=[])
    db.fetchrow = AsyncMock(return_value=None)
    db.execute = AsyncMock(return_value=None)
    return db


@pytest.fixture(autouse=True)
def _reset_singleton():
    """每个用例前后清空 InspectionScriptService 单例。

    Returns:
        None
    """
    from app.shared.utils.inspection_script_service import InspectionScriptService

    InspectionScriptService.reset()
    yield
    InspectionScriptService.reset()


# ----------------------------------------------------------------------
# P0: 模块导入 / Singleton
# ----------------------------------------------------------------------


def test_inspection_script_service_module_importable():
    """测试 InspectionScriptService 模块可导入且含必备类与单例接口。

    Returns:
        None

    Raises:
        AssertionError: 模块不可导入或缺少必备符号时失败
    """
    import importlib

    mod = importlib.import_module("app.shared.utils.inspection_script_service")
    assert hasattr(mod, "InspectionScriptService")
    # 单例接口必须存在
    assert hasattr(mod.InspectionScriptService, "set_instance")
    assert hasattr(mod.InspectionScriptService, "get_instance")
    assert hasattr(mod.InspectionScriptService, "reset")


def test_inspection_script_service_constructs():
    """db 合法时构造 InspectionScriptService 不抛异常。

    Returns:
        None
    """
    from app.shared.utils.inspection_script_service import InspectionScriptService

    svc = InspectionScriptService(db=_make_db())
    assert svc is not None
    assert svc.db is not None


def test_singleton_set_get():
    """set_instance / get_instance 是同一对象;未初始化时 get_instance 抛 RuntimeError。

    Returns:
        None
    """
    from app.shared.utils.inspection_script_service import InspectionScriptService

    svc = InspectionScriptService(db=_make_db())
    InspectionScriptService.set_instance(svc)
    assert InspectionScriptService.get_instance() is svc
    InspectionScriptService.reset()
    with pytest.raises(RuntimeError):
        InspectionScriptService.get_instance()


# ----------------------------------------------------------------------
# P1: preload_all / list / detail / by_id / by_name / resolve
# ----------------------------------------------------------------------


def _make_db_with_group_and_segment():
    """构造 db stub:fetch 按 SQL 内容路由返回组行 / 分段行。"""
    db = MagicMock(name="db_pool_stub")
    group_row = {
        "id": 1, "name": "linux-bash", "display_name": "Linux",
        "platform": "linux", "version": "bash", "inspection_parser": "json",
        "inspection_script": None, "inspection_fields": [],
        "created_at": None, "updated_at": None,
    }
    seg_row = {
        "id": 11, "script_id": 1, "segment_key": "cpu",
        "display_name": "CPU", "sort_order": 40, "script": "echo 1",
        "enabled": True, "created_at": None, "updated_at": None,
    }

    async def _fetch(sql, *args):
        if "FROM inspection_script_segments" in sql:
            if "WHERE script_id" in sql:
                return [dict(seg_row)] if args and args[0] == 1 else []
            return [dict(seg_row)]
        return [dict(group_row)]

    db.fetch = AsyncMock(side_effect=_fetch)
    db.fetchrow = AsyncMock(return_value=None)
    db.execute = AsyncMock(return_value="DELETE 1")
    return db


def test_preload_all_attaches_segments_to_group_record():
    """preload_all 应把分段按 script_id 挂到组 rec['segments']（升序）。"""
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db_with_group_and_segment()
    svc = InspectionScriptService(db)
    asyncio.run(svc.preload_all())
    rec = svc.get_script_by_id(1)
    assert [s["segment_key"] for s in rec["segments"]] == ["cpu"]


def test_preload_all_loads_db_rows_into_cache():
    """preload_all() 把 db.fetch 结果映射到 _cache / _id_cache。"""
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db_with_group_and_segment()
    svc = InspectionScriptService(db)
    asyncio.run(svc.preload_all())
    assert "linux-bash" in svc._cache
    assert svc._cache["linux-bash"]["id"] == 1
    assert 1 in svc._id_cache


def test_list_scripts_returns_whitelist_only():
    """list_scripts() 不返回 inspection_script 原文,仅返回白名单字段。"""
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db_with_group_and_segment()
    svc = InspectionScriptService(db)
    asyncio.run(svc.preload_all())
    out = svc.list_scripts()
    assert isinstance(out, list)
    assert len(out) == 1
    item = out[0]
    assert item["name"] == "linux-bash"
    assert "inspection_script" not in item
    assert "inspection_fields" not in item


def test_get_script_detail_returns_full_content():
    """get_script_detail(id) 命中时返回完整字段（含 inspection_script / inspection_fields）。"""
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db_with_group_and_segment()
    svc = InspectionScriptService(db)
    asyncio.run(svc.preload_all())
    detail = svc.get_script_detail(1)
    assert detail is not None
    assert detail["id"] == 1
    assert detail["name"] == "linux-bash"
    assert "segments" in detail  # 2026-09-16: 详情应附加 segments


def test_get_script_detail_missing_returns_none():
    """get_script_detail(id) 未命中时返回 None。"""
    from app.shared.utils.inspection_script_service import InspectionScriptService

    svc = InspectionScriptService(db=_make_db())
    asyncio.run(svc.preload_all())
    assert svc.get_script_detail(99) is None


def test_get_script_by_id_and_name_round_trip():
    """get_script_by_id / get_script_by_name 等价访问缓存。"""
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db_with_group_and_segment()
    svc = InspectionScriptService(db)
    asyncio.run(svc.preload_all())
    by_id = svc.get_script_by_id(1)
    by_name = svc.get_script_by_name("linux-bash")
    assert by_id is by_name  # 共享同一 dict 对象
    assert by_id["name"] == "linux-bash"


def test_resolve_script_for_server_default_match():
    """server_type=linux → 默认 linux-bash;windows → windows-ps-5.1。

    Returns:
        None
    """
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db_with_group_and_segment()
    svc = InspectionScriptService(db)
    asyncio.run(svc.preload_all())
    assert svc.resolve_script_for_server("linux") == 1
    assert svc.resolve_script_for_server("linux", "") == 1
    assert svc.resolve_script_for_server("linux", "missing") is None


# ----------------------------------------------------------------------
# P2: 分段 CRUD（2026-09-16 新增）
# ----------------------------------------------------------------------


def test_upsert_segment_rejects_non_json_group():
    """组 parser != json 时 upsert_segment 抛 ValueError。"""
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db_with_group_and_segment()
    svc = InspectionScriptService(db)
    asyncio.run(svc.preload_all())
    svc._id_cache[1]["inspection_parser"] = "kv"
    with pytest.raises(ValueError):
        asyncio.run(svc.upsert_segment(1, {"segment_key": "mem", "script": "echo {}"}))


def test_upsert_segment_rejects_bad_key_and_empty_script():
    """segment_key 非法 / script 空白 → ValueError。"""
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db_with_group_and_segment()
    svc = InspectionScriptService(db)
    asyncio.run(svc.preload_all())
    with pytest.raises(ValueError):
        asyncio.run(svc.upsert_segment(1, {"segment_key": "Bad Key!", "script": "echo {}"}))
    with pytest.raises(ValueError):
        asyncio.run(svc.upsert_segment(1, {"segment_key": "ok", "script": "  "}))


def test_upsert_segment_unknown_group_returns_none():
    """upsert_segment 未知组 id → None。"""
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db_with_group_and_segment()
    svc = InspectionScriptService(db)
    asyncio.run(svc.preload_all())
    assert asyncio.run(svc.upsert_segment(999, {"segment_key": "a", "script": "echo {}"})) is None


def test_delete_segment_cache_sync():
    """delete_segment 命中后 _reload_segments 刷新组 rec['segments']。"""
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db_with_group_and_segment()
    svc = InspectionScriptService(db)
    asyncio.run(svc.preload_all())

    async def _fetch(sql, *args):
        if "FROM inspection_script_segments" in sql:
            return []
        return []

    db.fetch = AsyncMock(side_effect=_fetch)
    assert asyncio.run(svc.delete_segment(1, 11)) is True
    assert svc.get_script_by_id(1)["segments"] == []


# ----------------------------------------------------------------------
# P3: 默认组播种（2026-09-16 新增）
# ----------------------------------------------------------------------


def test_seed_default_groups_inserts_when_absent_and_idempotent():
    """空库播种：组缺失→插组+分段;二次调用 inserted=0（幂等）。

    注意：seed 内部依赖 _reload_segments 回读 segments 行;测试 stub 让 fetch 在
    第二次调用前返回非空 segments 列表,模拟"已播种过"的真实 DB 状态。
    """
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db()
    svc = InspectionScriptService(db)
    asyncio.run(svc.preload_all())
    inserted_rows = []
    seg_calls = {"n": 0}
    group_id_counter = {"v": 1}

    async def _fetchrow(sql, *args):
        if "INSERT INTO inspection_scripts " in sql and "RETURNING" in sql:
            gid = group_id_counter["v"]
            group_id_counter["v"] += 1
            row = {
                "id": gid, "name": args[0], "inspection_fields": "[]",
                "display_name": args[1], "platform": args[2], "version": args[3],
                "inspection_parser": args[4], "inspection_script": None,
                "created_at": None, "updated_at": None,
            }
            inserted_rows.append(row)
            return row
        return None

    async def _fetch(sql, *args):
        if "FROM inspection_script_segments" in sql:
            seg_calls["n"] += 1
            n = seg_calls["n"]
            if n <= 4:
                # 第一次 seed:每次 reload 都返回 [](模拟"刚插入尚未 reload")
                return []
            # 第二次 seed:模拟"已存在 segments"
            sid = args[0] if args else 1
            return [{
                "id": 100, "script_id": sid, "segment_key": "cpu",
                "display_name": "CPU", "sort_order": 40, "script": "echo 1",
                "enabled": True, "created_at": None, "updated_at": None,
            }]
        return []

    db.fetchrow = AsyncMock(side_effect=_fetchrow)
    db.execute = AsyncMock(return_value="INSERT 0 1")
    db.fetch = AsyncMock(side_effect=_fetch)

    stats1 = asyncio.run(svc.seed_default_groups())
    assert stats1["groups_inserted"] == 2
    assert stats1["segments_inserted"] == 8
    # 关键:第二次 reload 时 segments 已存在 → 触发 skipped 路径
    stats2 = asyncio.run(svc.seed_default_groups())
    assert stats2["groups_inserted"] == 0
    assert stats2["segments_inserted"] == 0
    assert stats2["skipped"] == 2


# ----------------------------------------------------------------------
# P4: delete_script 事务化 + 缓存自愈（2026-08-05 既有;2026-09-16 沿用）
# ----------------------------------------------------------------------


class _FakeAsyncContextManager:
    """提供 ``async with`` 协议的最小占位器。"""

    def __init__(self, cm):
        self._cm = cm

    async def __aenter__(self):
        return self._cm

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _build_tx_db():
    """构造 asyncpg ``Pool`` 替身:``db.acquire()`` 返回带 ``transaction()`` 的 connection。"""
    db = MagicMock(name="db_pool_stub_tx")

    conn = MagicMock(name="db_connection_stub_tx")
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value=None)

    @asynccontextmanager
    async def _tx():
        yield None

    conn.transaction = MagicMock(
        side_effect=lambda: _FakeAsyncContextManager(_tx())
    )
    db.acquire = MagicMock(
        side_effect=lambda: _FakeAsyncContextManager(conn)
    )
    return db, conn


def test_delete_script_uses_single_transaction():
    """delete_script 使用 connection 事务,SQL 顺序:SELECT FOR UPDATE → UPDATE servers → DELETE segments → DELETE scripts。"""
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db, conn = _build_tx_db()
    conn.fetchrow.side_effect = [{"name": "linux-bash"}]
    # 2026-09-16:事务内 3 次 execute(UPDATE servers / DELETE segments / DELETE scripts)
    conn.execute.side_effect = ["UPDATE 2", "DELETE 4", "DELETE 1"]
    svc = InspectionScriptService(db)
    svc._cache["linux-bash"] = {"id": 7, "name": "linux-bash"}
    svc._id_cache[7] = {"id": 7, "name": "linux-bash"}

    ok = asyncio.run(svc.delete_script(7))
    assert ok is True
    assert db.acquire.call_count == 1
    assert conn.transaction.call_count == 1
    assert 7 not in svc._id_cache
    assert "linux-bash" not in svc._cache

    executed_sqls = [c.args[0] for c in conn.execute.await_args_list]
    assert any(
        "UPDATE devops_servers SET inspection_script_id = NULL" in sql
        for sql in executed_sqls
    ), f"未发现服务器解绑 SQL: {executed_sqls}"
    assert any(
        "DELETE FROM inspection_script_segments" in sql for sql in executed_sqls
    ), "delete_script 应在事务内显式清理 segments(FK CASCADE 兜底)"
    assert any(
        "DELETE FROM inspection_scripts" in sql for sql in executed_sqls
    )


def test_delete_script_returns_false_when_no_row():
    """DB 实际无该脚本行（SELECT FOR UPDATE 未命中）→ 返回 False,缓存不动。"""
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db, conn = _build_tx_db()
    conn.fetchrow.side_effect = [None]
    conn.execute.side_effect = []
    svc = InspectionScriptService(db)
    svc._cache["linux-bash"] = {"id": 7, "name": "linux-bash"}
    svc._id_cache[7] = {"id": 7, "name": "linux-bash"}

    ok = asyncio.run(svc.delete_script(7))
    assert ok is False
    assert 7 in svc._id_cache
    assert "linux-bash" in svc._cache
    assert conn.execute.await_count == 0


def test_delete_script_invalid_id_returns_false():
    """入参非法（None / 非 int / <=0）→ 返回 False,不调 DB。"""
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db, _conn = _build_tx_db()
    svc = InspectionScriptService(db)

    assert asyncio.run(svc.delete_script(None)) is False
    assert asyncio.run(svc.delete_script(0)) is False
    assert asyncio.run(svc.delete_script(-1)) is False
    assert db.acquire.call_count == 0


def test_delete_script_db_exception_propagates_keeps_cache():
    """事务内 DB 异常向上抛出,缓存不被清。"""
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db, conn = _build_tx_db()
    conn.fetchrow.side_effect = RuntimeError("simulated asyncpg failure")
    svc = InspectionScriptService(db)
    svc._cache["linux-bash"] = {"id": 7, "name": "linux-bash"}
    svc._id_cache[7] = {"id": 7, "name": "linux-bash"}

    with pytest.raises(RuntimeError, match="simulated asyncpg failure"):
        asyncio.run(svc.delete_script(7))
    assert 7 in svc._id_cache
    assert "linux-bash" in svc._cache


# ----------------------------------------------------------------------
# P5: update_script_detail（2026-08-04 既有;2026-09-16 沿用 + parser 校验强化）
# ----------------------------------------------------------------------


def test_update_script_detail_updates_db_and_cache():
    """update_script_detail 写入 DB 并同步 _cache / _id_cache。"""
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db()
    db.fetchrow.return_value = {
        "id": 7, "name": "linux-bash", "display_name": "Linux Bash (人工编辑)",
        "platform": "linux", "version": "bash", "inspection_parser": "json",
        "inspection_script": "echo manual", "inspection_fields": "[]",
        "created_at": None, "updated_at": "2026-08-04",
    }
    svc = InspectionScriptService(db)
    asyncio.run(svc.preload_all())
    payload = {
        "display_name": "Linux Bash (人工编辑)",
        "platform": "linux", "version": "bash",
        "inspection_parser": "json", "inspection_script": "echo manual",
        "inspection_fields": [],
    }
    result = asyncio.run(svc.update_script_detail(7, payload))
    assert result is not None
    assert result["display_name"] == "Linux Bash (人工编辑)"
    assert "linux-bash" in svc._cache
    assert svc._cache["linux-bash"]["inspection_script"] == "echo manual"


def test_update_script_detail_rejects_non_json_when_segments_present():
    """组存在 enabled 分段 → 切到非 json parser 时返回 None(D3 防御)。"""
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db_with_group_and_segment()
    svc = InspectionScriptService(db)
    asyncio.run(svc.preload_all())
    # 此时 1 组下存在 enabled 分段 cpu;切到 kv parser 必须被拒
    result = asyncio.run(svc.update_script_detail(1, {
        "display_name": "X", "platform": "linux", "version": "bash",
        "inspection_parser": "kv", "inspection_script": None,
        "inspection_fields": [],
    }))
    assert result is None


def test_update_script_detail_invalid_returns_none():
    """update_script_detail 收到非法入参 → 返回 None(不抛)。"""
    from app.shared.utils.inspection_script_service import InspectionScriptService

    svc = InspectionScriptService(db=_make_db())
    assert asyncio.run(svc.update_script_detail(1, {
        "display_name": "X", "platform": "solaris", "version": "",
        "inspection_parser": "json", "inspection_script": None,
        "inspection_fields": [],
    })) is None
    assert asyncio.run(svc.update_script_detail(1, {
        "display_name": "X", "platform": "linux", "version": "",
        "inspection_parser": "yaml", "inspection_script": None,
        "inspection_fields": [],
    })) is None
    assert asyncio.run(svc.update_script_detail(1, {
        "display_name": "  ", "platform": "linux", "version": "",
        "inspection_parser": "json", "inspection_script": None,
        "inspection_fields": [],
    })) is None
