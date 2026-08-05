# -*- coding:utf-8 -*-
"""
InspectionScriptService 单元测试（2026-08-03 新增）

覆盖目标：
    - InspectionScriptService(db, config_path) 的初始化与 singleton 行为
    - preload_all() 从 DB 加载到 _cache / _id_cache
    - scan_and_upsert() 读取 YAML、字段规范化、INSERT...ON CONFLICT 写库、刷新缓存
    - list_scripts() / get_script_detail() / get_script_by_id() / get_script_by_name()
    - resolve_script_for_server(server_type, script_name) 的默认匹配逻辑
    - 重复 name 拒绝 / 非法 parser 计入 failed / 字段规则非法计入 failed
    - 服务未初始化时 get_instance() 抛 RuntimeError

测试风格遵循项目规范：
    - 顶部 docstring（中文）
    - 通过 pytest fixture + monkeypatch 注入 db stub 与临时 YAML 文件
    - 不伪造生产 app.state 对象；singleton 通过
      InspectionScriptService.set_instance / reset 严格管理
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_db() -> MagicMock:
    """构造一个 MagicMock 作为 asyncpg pool 替身。

    生产侧 InspectionScriptService 通过 ``await db.fetch(...)`` 等异步操作访问 DB，
    因此用 ``AsyncMock`` 让 awaitable 调用返回固定值。

    Returns:
        MagicMock: db 池替身（其 fetch/fetchrow/execute 为 AsyncMock）
    """
    db = MagicMock(name="db_pool_stub")
    db.fetch = AsyncMock(return_value=[])
    db.fetchrow = AsyncMock(return_value=None)
    db.execute = AsyncMock(return_value=None)
    return db


@pytest.fixture
def tmp_yaml(tmp_path: Path) -> Path:
    """生成临时 inspection_scripts.yaml 路径（不在磁盘上预先建文件）。

    Args:
        tmp_path: pytest 临时目录

    Returns:
        Path: inspection_scripts.yaml 路径
    """
    return tmp_path / "inspection_scripts.yaml"


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


def test_inspection_script_service_constructs(tmp_yaml):
    """db 与 config_path 合法时构造 InspectionScriptService 不抛异常。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    from app.shared.utils.inspection_script_service import InspectionScriptService

    svc = InspectionScriptService(db=_make_db(), config_path=str(tmp_yaml))
    assert svc is not None
    assert svc.db is not None


def test_singleton_set_get(tmp_yaml):
    """set_instance / get_instance 是同一对象；未初始化时 get_instance 抛 RuntimeError。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    from app.shared.utils.inspection_script_service import InspectionScriptService

    svc = InspectionScriptService(db=_make_db(), config_path=str(tmp_yaml))
    InspectionScriptService.set_instance(svc)
    assert InspectionScriptService.get_instance() is svc
    # reset 后再 get 应抛 RuntimeError
    InspectionScriptService.reset()
    with pytest.raises(RuntimeError):
        InspectionScriptService.get_instance()


# ----------------------------------------------------------------------
# P1: preload_all / scan_and_upsert / list / detail / by_id / by_name
# ----------------------------------------------------------------------


def test_preload_all_loads_db_rows_into_cache(tmp_yaml):
    """preload_all() 把 db.fetch 结果映射到 _cache（按 name）与 _id_cache（按 id）。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db()
    db.fetch.return_value = [
        {
            "id": 10,
            "name": "linux-bash",
            "display_name": "Linux Bash 巡检",
            "platform": "linux",
            "version": "bash",
            "inspection_parser": "json",
            "inspection_script": "echo probe",
            "inspection_fields": [
                {"key": "disk_used_pct", "name_zh": "磁盘使用率", "unit": "%",
                 "direction": "high", "warn": 80.0, "crit": 90.0},
            ],
            "created_at": None,
            "updated_at": "2026-08-03",
        }
    ]
    svc = InspectionScriptService(db=db, config_path=str(tmp_yaml))
    asyncio.run(svc.preload_all())
    assert "linux-bash" in svc._cache
    assert svc._cache["linux-bash"]["id"] == 10
    assert 10 in svc._id_cache
    # inspection_fields 还原为 list[dict]
    fields = svc._cache["linux-bash"]["inspection_fields"]
    assert isinstance(fields, list)
    assert fields[0]["key"] == "disk_used_pct"


def test_scan_and_upsert_inserts_new_rows(tmp_yaml):
    """YAML 中 2 条合法条目 → scanned=2, inserted=2, updated=0, failed=0。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db()
    # 每个 fetchrow 调用依次返回 RETURNING 行
    db.fetchrow.side_effect = [
        {
            "id": 1,
            "name": "linux-bash",
            "display_name": "Linux Bash 巡检",
            "platform": "linux",
            "version": "bash",
            "inspection_parser": "json",
            "inspection_script": "echo a",
            "inspection_fields": json.dumps(
                [{"key": "x", "name_zh": "X", "unit": "%", "direction": "high",
                  "warn": 80, "crit": 90}],
                ensure_ascii=False,
            ),
            "created_at": None,
            "updated_at": "2026-08-03",
            "inserted": True,
        },
        {
            "id": 2,
            "name": "windows-ps-5.1",
            "display_name": "Windows PS 5.1 巡检",
            "platform": "windows",
            "version": "ps-5.1",
            "inspection_parser": "json",
            "inspection_script": "Get-Process",
            "inspection_fields": "[]",
            "created_at": None,
            "updated_at": "2026-08-03",
            "inserted": True,
        },
    ]
    tmp_yaml.parent.mkdir(parents=True, exist_ok=True)
    tmp_yaml.write_text(
        "inspection_scripts:\n"
        "  - name: linux-bash\n"
        "    display_name: Linux Bash 巡检\n"
        "    platform: linux\n"
        "    version: bash\n"
        "    inspection_parser: json\n"
        "    inspection_script: |\n"
        "      echo a\n"
        "    inspection_fields:\n"
        "      - {key: x, name_zh: X, unit: '%', direction: high, warn: 80, crit: 90}\n"
        "  - name: windows-ps-5.1\n"
        "    display_name: Windows PS 5.1 巡检\n"
        "    platform: windows\n"
        "    version: ps-5.1\n",
        encoding="utf-8",
    )

    svc = InspectionScriptService(db=db, config_path=str(tmp_yaml))
    stats = asyncio.run(svc.scan_and_upsert())
    assert stats["scanned"] == 2
    assert stats["inserted"] == 2
    assert stats["updated"] == 0
    assert stats["failed"] == 0
    # 缓存含两条
    assert "linux-bash" in svc._cache
    assert "windows-ps-5.1" in svc._cache


def test_scan_and_upsert_rejects_duplicate_name(tmp_yaml):
    """YAML 中两条同名 → scanned=2, inserted=1, failed=1。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db()
    db.fetchrow.side_effect = [
        {
            "id": 1,
            "name": "dup",
            "display_name": "d",
            "platform": "linux",
            "version": "",
            "inspection_parser": "json",
            "inspection_script": None,
            "inspection_fields": "[]",
            "created_at": None,
            "updated_at": "2026-08-03",
            "inserted": True,
        }
    ]
    tmp_yaml.parent.mkdir(parents=True, exist_ok=True)
    tmp_yaml.write_text(
        "inspection_scripts:\n"
        "  - name: dup\n"
        "    display_name: a\n"
        "    platform: linux\n"
        "  - name: dup\n"
        "    display_name: b\n"
        "    platform: linux\n",
        encoding="utf-8",
    )

    svc = InspectionScriptService(db=db, config_path=str(tmp_yaml))
    stats = asyncio.run(svc.scan_and_upsert())
    assert stats["scanned"] == 2
    assert stats["failed"] == 1
    assert stats["inserted"] == 1


def test_scan_and_upsert_invalid_parser_records_failed(tmp_yaml):
    """非法 parser → 该条目计入 failed，不阻断其他记录。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db()
    db.fetchrow.side_effect = [
        {
            "id": 1,
            "name": "ok",
            "display_name": "ok",
            "platform": "linux",
            "version": "",
            "inspection_parser": "json",
            "inspection_script": None,
            "inspection_fields": "[]",
            "created_at": None,
            "updated_at": "2026-08-03",
            "inserted": True,
        }
    ]
    tmp_yaml.parent.mkdir(parents=True, exist_ok=True)
    tmp_yaml.write_text(
        "inspection_scripts:\n"
        "  - name: bad\n"
        "    display_name: b\n"
        "    platform: linux\n"
        "    inspection_parser: xml\n"
        "  - name: ok\n"
        "    display_name: o\n"
        "    platform: linux\n",
        encoding="utf-8",
    )

    svc = InspectionScriptService(db=db, config_path=str(tmp_yaml))
    stats = asyncio.run(svc.scan_and_upsert())
    assert stats["scanned"] == 2
    assert stats["failed"] == 1
    assert stats["inserted"] == 1
    assert "bad" not in svc._cache
    assert "ok" in svc._cache


def test_scan_and_upsert_invalid_fields_records_failed(tmp_yaml):
    """inspection_fields 非法规则 → 该条目计入 failed。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db()
    tmp_yaml.parent.mkdir(parents=True, exist_ok=True)
    tmp_yaml.write_text(
        "inspection_scripts:\n"
        "  - name: bad\n"
        "    display_name: b\n"
        "    platform: linux\n"
        "    inspection_fields:\n"
        "      - {key: x, name_zh: X, direction: bad, warn: 1, crit: 2}\n",
        encoding="utf-8",
    )

    svc = InspectionScriptService(db=db, config_path=str(tmp_yaml))
    stats = asyncio.run(svc.scan_and_upsert())
    assert stats["scanned"] == 1
    assert stats["failed"] == 1
    assert "bad" not in svc._cache


def test_scan_and_upsert_yaml_missing_returns_zero(tmp_yaml):
    """YAML 不存在时返回 4 个零，不抛异常。

    Args:
        tmp_yaml: 临时 yaml 路径（不存在）

    Returns:
        None
    """
    import asyncio
    from app.shared.utils.inspection_script_service import InspectionScriptService

    svc = InspectionScriptService(db=_make_db(), config_path=str(tmp_yaml))
    stats = asyncio.run(svc.scan_and_upsert())
    # 2026-08-04 编辑优先：返回 5 字段；skipped 增量 = 0
    assert stats == {
        "scanned": 0, "inserted": 0, "updated": 0, "failed": 0, "skipped": 0
    }


def test_scan_and_upsert_top_level_not_list_records_failed(tmp_yaml):
    """inspection_scripts 顶层非 list → failed=1，不抛异常。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db()
    tmp_yaml.parent.mkdir(parents=True, exist_ok=True)
    tmp_yaml.write_text(
        "inspection_scripts:\n  not_a_list: true\n",
        encoding="utf-8",
    )
    svc = InspectionScriptService(db=db, config_path=str(tmp_yaml))
    stats = asyncio.run(svc.scan_and_upsert())
    # 2026-08-04 编辑优先：返回 5 字段
    assert stats == {
        "scanned": 0, "inserted": 0, "updated": 0, "failed": 1, "skipped": 0
    }


def test_list_scripts_returns_whitelist_only(tmp_yaml):
    """list_scripts() 不返回 inspection_script 原文，仅返回白名单字段。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db()
    db.fetch.return_value = [
        {
            "id": 10,
            "name": "linux-bash",
            "display_name": "Linux Bash 巡检",
            "platform": "linux",
            "version": "bash",
            "inspection_parser": "json",
            "inspection_script": "echo probe",
            "inspection_fields": "[]",
            "created_at": None,
            "updated_at": "2026-08-03",
        }
    ]
    svc = InspectionScriptService(db=db, config_path=str(tmp_yaml))
    asyncio.run(svc.preload_all())
    out = svc.list_scripts()
    assert isinstance(out, list)
    assert len(out) == 1
    item = out[0]
    assert item["name"] == "linux-bash"
    assert item["display_name"] == "Linux Bash 巡检"
    assert item["platform"] == "linux"
    assert item["version"] == "bash"
    assert item["inspection_parser"] == "json"
    # 原文不进入白名单
    assert "inspection_script" not in item
    assert "inspection_fields" not in item


def test_get_script_detail_returns_full_content(tmp_yaml):
    """get_script_detail(id) 命中时返回完整字段（含 inspection_script / inspection_fields）。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db()
    db.fetch.return_value = [
        {
            "id": 10,
            "name": "linux-bash",
            "display_name": "Linux Bash 巡检",
            "platform": "linux",
            "version": "bash",
            "inspection_parser": "json",
            "inspection_script": "echo probe",
            "inspection_fields": json.dumps(
                [{"key": "disk_used_pct", "name_zh": "磁盘使用率", "unit": "%",
                  "direction": "high", "warn": 80, "crit": 90}],
                ensure_ascii=False,
            ),
            "created_at": None,
            "updated_at": "2026-08-03",
        }
    ]
    svc = InspectionScriptService(db=db, config_path=str(tmp_yaml))
    asyncio.run(svc.preload_all())
    detail = svc.get_script_detail(10)
    assert detail is not None
    assert detail["id"] == 10
    assert detail["name"] == "linux-bash"
    assert detail["inspection_script"] == "echo probe"
    assert detail["inspection_fields"][0]["key"] == "disk_used_pct"


def test_get_script_detail_missing_returns_none(tmp_yaml):
    """get_script_detail(id) 未命中时返回 None。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db()
    db.fetch.return_value = []
    svc = InspectionScriptService(db=db, config_path=str(tmp_yaml))
    asyncio.run(svc.preload_all())
    assert svc.get_script_detail(99) is None


def test_get_script_by_id_returns_full_content(tmp_yaml):
    """get_script_by_id(id) 与 get_script_detail 等价（内部使用）。"""
    import asyncio
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db()
    db.fetch.return_value = [
        {
            "id": 10,
            "name": "linux-bash",
            "display_name": "Linux Bash 巡检",
            "platform": "linux",
            "version": "bash",
            "inspection_parser": "json",
            "inspection_script": "echo probe",
            "inspection_fields": "[]",
            "created_at": None,
            "updated_at": "2026-08-03",
        }
    ]
    svc = InspectionScriptService(db=db, config_path=str(tmp_yaml))
    asyncio.run(svc.preload_all())
    rec = svc.get_script_by_id(10)
    assert rec is not None
    assert rec["name"] == "linux-bash"
    assert rec["inspection_script"] == "echo probe"


def test_get_script_by_name_returns_full_content(tmp_yaml):
    """get_script_by_name(name) 返回完整内容。"""
    import asyncio
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db()
    db.fetch.return_value = [
        {
            "id": 10,
            "name": "linux-bash",
            "display_name": "Linux Bash 巡检",
            "platform": "linux",
            "version": "bash",
            "inspection_parser": "json",
            "inspection_script": "echo probe",
            "inspection_fields": "[]",
            "created_at": None,
            "updated_at": "2026-08-03",
        }
    ]
    svc = InspectionScriptService(db=db, config_path=str(tmp_yaml))
    asyncio.run(svc.preload_all())
    rec = svc.get_script_by_name("linux-bash")
    assert rec is not None
    assert rec["id"] == 10
    assert rec["name"] == "linux-bash"
    assert svc.get_script_by_name("missing") is None


def test_resolve_script_for_server_explicit_name(tmp_yaml):
    """resolve_script_for_server(server_type, script_name) 显式名称优先。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db()
    db.fetch.return_value = [
        {
            "id": 11,
            "name": "linux-bash",
            "display_name": "Linux Bash",
            "platform": "linux",
            "version": "bash",
            "inspection_parser": "json",
            "inspection_script": "echo",
            "inspection_fields": "[]",
            "created_at": None,
            "updated_at": "2026-08-03",
        },
        {
            "id": 22,
            "name": "windows-ps-5.1",
            "display_name": "Windows PS 5.1",
            "platform": "windows",
            "version": "ps-5.1",
            "inspection_parser": "json",
            "inspection_script": "Get-Process",
            "inspection_fields": "[]",
            "created_at": None,
            "updated_at": "2026-08-03",
        },
    ]
    svc = InspectionScriptService(db=db, config_path=str(tmp_yaml))
    asyncio.run(svc.preload_all())
    # 显式 script_name 命中
    assert svc.resolve_script_for_server("linux", "linux-bash") == 11
    # 显式不存在 → None
    assert svc.resolve_script_for_server("linux", "missing") is None


def test_resolve_script_for_server_default_match(tmp_yaml):
    """server_type=linux 且 script_name 为空 → 默认 linux-bash；windows → windows-ps-5.1。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db()
    db.fetch.return_value = [
        {
            "id": 11,
            "name": "linux-bash",
            "display_name": "Linux Bash",
            "platform": "linux",
            "version": "bash",
            "inspection_parser": "json",
            "inspection_script": "echo",
            "inspection_fields": "[]",
            "created_at": None,
            "updated_at": "2026-08-03",
        },
        {
            "id": 22,
            "name": "windows-ps-5.1",
            "display_name": "Windows PS 5.1",
            "platform": "windows",
            "version": "ps-5.1",
            "inspection_parser": "json",
            "inspection_script": "Get-Process",
            "inspection_fields": "[]",
            "created_at": None,
            "updated_at": "2026-08-03",
        },
    ]
    svc = InspectionScriptService(db=db, config_path=str(tmp_yaml))
    asyncio.run(svc.preload_all())
    # 默认匹配：linux → linux-bash
    assert svc.resolve_script_for_server("linux") == 11
    # 默认匹配：windows → windows-ps-5.1
    assert svc.resolve_script_for_server("windows") == 22
    # 空字符串 script_name 等价于不传，走默认匹配：linux → linux-bash
    assert svc.resolve_script_for_server("linux", "") == 11
    # 空字符串 script_name 等价于不传，走默认匹配：windows → windows-ps-5.1
    assert svc.resolve_script_for_server("windows", "") == 22
    # 未知 server_type → None（无默认映射）
    assert svc.resolve_script_for_server("aix", None) is None


# ----------------------------------------------------------------------
# P4: delete_script（2026-08-04 新增）
# ----------------------------------------------------------------------


def test_delete_script_removes_from_caches(tmp_yaml):
    """delete_script 命中 DB 时从 ``_cache`` / ``_id_cache`` 同步移除（2026-08-05 事务化）。

    单事务内：SELECT name FOR UPDATE → UPDATE devops_servers → DELETE inspection_scripts。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _build_tx_db()
    db.fetchrow.side_effect = [{"name": "linux-bash"}]
    db.execute.side_effect = ["UPDATE 1", "DELETE 1"]
    svc = InspectionScriptService(db=db, config_path=str(tmp_yaml))
    # 直接构造缓存，避免依赖 preload_all 的 DB fetch 桩
    svc._cache["linux-bash"] = {"id": 11, "name": "linux-bash"}
    svc._id_cache[11] = {"id": 11, "name": "linux-bash"}

    ok = asyncio.run(svc.delete_script(11))
    assert ok is True
    # _id_cache / _cache 都被清除
    assert 11 not in svc._id_cache
    assert "linux-bash" not in svc._cache
    # 事务内 SQL 顺序：先 SELECT name FOR UPDATE，再 UPDATE servers，再 DELETE scripts
    assert db.transaction.call_count == 1
    assert db.fetchrow.await_count == 1
    assert db.execute.await_count == 2
    delete_sql = next(
        c.args[0] for c in db.execute.await_args_list
        if "DELETE FROM inspection_scripts" in c.args[0]
    )
    assert "DELETE FROM inspection_scripts" in delete_sql
    # DELETE SQL 第二个参数是 11
    delete_call = next(
        c for c in db.execute.await_args_list
        if "DELETE FROM inspection_scripts" in c.args[0]
    )
    assert delete_call.args[1] == 11


def test_delete_script_returns_false_when_no_row(tmp_yaml):
    """DB 实际无该脚本行（SELECT FOR UPDATE 未命中）→ 返回 False，缓存不动。

    2026-08-05 事务化改造：DB 删行之前先用 SELECT FOR UPDATE 判定脚本是否存在；
    不存在时不解绑服务器、不删脚本行、不动缓存。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _build_tx_db()
    db.fetchrow.side_effect = [None]  # SELECT name FOR UPDATE 未命中
    db.execute.side_effect = []  # 不应触发 UPDATE / DELETE
    svc = InspectionScriptService(db=db, config_path=str(tmp_yaml))
    svc._cache["linux-bash"] = {"id": 11, "name": "linux-bash"}
    svc._id_cache[11] = {"id": 11, "name": "linux-bash"}

    ok = asyncio.run(svc.delete_script(11))
    assert ok is False
    # 缓存保持原样
    assert 11 in svc._id_cache
    assert "linux-bash" in svc._cache
    # 关键：服务器解绑 SQL 不应被执行（脚本都不存在时不应盲目 UPDATE）
    assert db.execute.await_count == 0


def test_delete_script_invalid_id_returns_false(tmp_yaml):
    """入参非法（None / 非 int / <=0）→ 返回 False，不调 DB。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db()
    svc = InspectionScriptService(db=db, config_path=str(tmp_yaml))

    assert asyncio.run(svc.delete_script(None)) is False
    assert asyncio.run(svc.delete_script(0)) is False
    assert asyncio.run(svc.delete_script(-1)) is False
    # bool 是 int 的子类，单独验证应当走校验通过路径之外：仍被允许（仅校验 > 0）
    # 这里只覆盖「必须被短路」的三种形态
    db.execute.assert_not_called()


def test_delete_script_db_exception_propagates(tmp_yaml):
    """事务内 DB 异常向上抛出（2026-08-05 改造），缓存不被清。

    业务语义：``delete_script`` 不吞 DB 异常，由上层路由映射为通用 500；
    缓存保持原样，下次重试或运维排查时仍能命中现有数据。
    """
    import asyncio
    import pytest
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _build_tx_db()
    db.fetchrow.side_effect = RuntimeError("simulated DB failure")
    svc = InspectionScriptService(db=db, config_path=str(tmp_yaml))
    svc._cache["linux-bash"] = {"id": 11, "name": "linux-bash"}
    svc._id_cache[11] = {"id": 11, "name": "linux-bash"}

    with pytest.raises(RuntimeError, match="simulated DB failure"):
        asyncio.run(svc.delete_script(11))
    # 缓存保持
    assert 11 in svc._id_cache
    assert "linux-bash" in svc._cache


# ----------------------------------------------------------------------
# P5: delete_script 事务化 + 缓存自愈（2026-08-05 新增）
# ----------------------------------------------------------------------
# 触发原因：用户反馈「巡检脚本不存在」选项实际存在 → 定位到删除路径在某些
# 漂移场景下只清理部分缓存 key。修复要求 delete_script 在单事务内：
# 1) SELECT ... FOR UPDATE 锁住脚本行；
# 2) UPDATE devops_servers SET inspection_script_id=NULL；
# 3) DELETE FROM inspection_scripts WHERE id=$1；
# 事务成功提交后，用本次事务内读到的 name 清空 _id_cache 与 _cache，并
# 清理同 name 漂移到其它 id 的残留。
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
    """构造支持 ``db.transaction()`` 异步上下文管理器的 db stub。

    Returns:
        MagicMock: db 替身；``db.transaction()`` 返回可 await 的 CM，
        ``db.fetchrow`` / ``db.execute`` 为 AsyncMock。
    """
    from contextlib import asynccontextmanager
    db = MagicMock(name="db_pool_stub_tx")
    db.fetch = AsyncMock(return_value=[])
    db.fetchrow = AsyncMock(return_value=None)
    db.execute = AsyncMock(return_value=None)

    @asynccontextmanager
    async def _tx():
        yield None

    db.transaction = MagicMock(side_effect=lambda: _FakeAsyncContextManager(_tx()))
    return db


def test_delete_script_uses_single_transaction(tmp_yaml):
    """delete_script 必须调用 ``db.transaction()`` 且 SQL 顺序锁定。

    验证：
    - 事务上下文被使用一次；
    - 事务内 SQL 顺序：SELECT name FOR UPDATE → UPDATE devops_servers → DELETE inspection_scripts；
    - 事务提交后缓存才被清。
    """
    import asyncio
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _build_tx_db()
    db.fetchrow.side_effect = [
        {"name": "linux-bash"},  # SELECT name FROM inspection_scripts ... FOR UPDATE
    ]
    db.execute.side_effect = [
        "UPDATE 2",  # UPDATE devops_servers SET inspection_script_id = NULL
        "DELETE 1",  # DELETE FROM inspection_scripts WHERE id = $1
    ]
    svc = InspectionScriptService(db=db, config_path=str(tmp_yaml))
    svc._cache["linux-bash"] = {"id": 7, "name": "linux-bash"}
    svc._id_cache[7] = {"id": 7, "name": "linux-bash"}

    ok = asyncio.run(svc.delete_script(7))
    assert ok is True

    # 1) 事务上下文被调用一次
    assert db.transaction.call_count == 1
    # 2) 全部 SQL 在事务内按序执行
    assert db.fetchrow.await_count == 1
    assert db.execute.await_count == 2

    # 3) 缓存被清理
    assert 7 not in svc._id_cache
    assert "linux-bash" not in svc._cache

    # 4) 事务内 SQL 顺序：先 UPDATE 服务器、再 DELETE 脚本
    executed_sqls = [c.args[0] for c in db.execute.await_args_list]
    assert any(
        "UPDATE devops_servers SET inspection_script_id = NULL" in sql
        and "WHERE inspection_script_id = $1" in sql
        for sql in executed_sqls
    ), f"未发现服务器解绑 SQL: {executed_sqls}"
    delete_sql = next(
        sql for sql in executed_sqls if "DELETE FROM inspection_scripts" in sql
    )
    assert delete_sql is not None
    # 服务器解绑 SQL 必须先于脚本删除 SQL
    unbind_idx = next(
        i for i, sql in enumerate(executed_sqls)
        if "UPDATE devops_servers" in sql
    )
    delete_idx = next(
        i for i, sql in enumerate(executed_sqls)
        if "DELETE FROM inspection_scripts" in sql
    )
    assert unbind_idx < delete_idx


def test_delete_script_clears_drifted_same_name_id_cache(tmp_yaml):
    """同 name 漂移到多条 _id_cache（人为制造漂移）时：
    删除其中一条 id，事务内读到的 name 把另一条同 name 的 id 索引一并清理。
    """
    import asyncio
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _build_tx_db()
    # 真实 DB 中只有 id=7（linux-bash）；id=99 是历史漂移残留
    db.fetchrow.side_effect = [{"name": "linux-bash"}]
    db.execute.side_effect = ["UPDATE 1", "DELETE 1"]
    svc = InspectionScriptService(db=db, config_path=str(tmp_yaml))
    # 漂移场景：_id_cache 同时含 7 与 99，都指向 linux-bash
    svc._cache["linux-bash"] = {"id": 7, "name": "linux-bash"}
    svc._id_cache[7] = {"id": 7, "name": "linux-bash"}
    svc._id_cache[99] = {"id": 7, "name": "linux-bash"}  # 同 name 漂移到 99

    ok = asyncio.run(svc.delete_script(7))
    assert ok is True

    # 7 与 99 都应被清；_cache["linux-bash"] 被清
    assert 7 not in svc._id_cache
    assert 99 not in svc._id_cache
    assert "linux-bash" not in svc._cache


def test_delete_script_returns_false_when_db_row_missing(tmp_yaml):
    """事务内 SELECT 未命中（DB 实际无该 id）→ 返回 False，缓存不动。"""
    import asyncio
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _build_tx_db()
    db.fetchrow.side_effect = [None]  # SELECT name FOR UPDATE 未命中
    db.execute.side_effect = []  # 不应触发 UPDATE / DELETE
    svc = InspectionScriptService(db=db, config_path=str(tmp_yaml))
    svc._cache["linux-bash"] = {"id": 7, "name": "linux-bash"}
    svc._id_cache[7] = {"id": 7, "name": "linux-bash"}

    ok = asyncio.run(svc.delete_script(7))
    assert ok is False
    # 缓存保持原样
    assert 7 in svc._id_cache
    assert "linux-bash" in svc._cache
    # 关键：服务器解绑 SQL 不应被执行（脚本都不存在时不应盲目 UPDATE）
    assert db.execute.await_count == 0


def test_delete_script_db_failure_propagates_keeps_cache(tmp_yaml):
    """事务内 DB 异常向上抛出，缓存不被清。

    业务语义：``delete_script`` 不吞 DB 异常，由上层路由映射为通用 500；
    缓存保持原样，下次重试或运维排查时仍能命中现有数据。
    """
    import asyncio
    import pytest
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _build_tx_db()
    db.fetchrow.side_effect = RuntimeError("simulated asyncpg failure")
    svc = InspectionScriptService(db=db, config_path=str(tmp_yaml))
    svc._cache["linux-bash"] = {"id": 7, "name": "linux-bash"}
    svc._id_cache[7] = {"id": 7, "name": "linux-bash"}

    with pytest.raises(RuntimeError, match="simulated asyncpg failure"):
        asyncio.run(svc.delete_script(7))
    # 缓存保持
    assert 7 in svc._id_cache
    assert "linux-bash" in svc._cache


def test_scan_and_upsert_mixed_insert_update(tmp_yaml):
    """同名条目再次扫描（2026-08-04 改造为编辑优先）：
    第一次 insert 成功 → cache 含 linux-bash；第二次同 name 命中 cache → skipped=1，
    不调用 fetchrow，不再更新。保留对原契约的回归保护。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db()
    # 仅第一次返回 RETURNING 行（inserted=True）；第二次不应再调用 fetchrow
    db.fetchrow.side_effect = [
        {
            "id": 1,
            "name": "linux-bash",
            "display_name": "Linux Bash",
            "platform": "linux",
            "version": "bash",
            "inspection_parser": "json",
            "inspection_script": None,
            "inspection_fields": "[]",
            "created_at": None,
            "updated_at": "2026-08-03",
            "inserted": True,
        },
    ]
    tmp_yaml.parent.mkdir(parents=True, exist_ok=True)
    tmp_yaml.write_text(
        "inspection_scripts:\n"
        "  - name: linux-bash\n"
        "    display_name: Linux Bash\n"
        "    platform: linux\n",
        encoding="utf-8",
    )

    svc = InspectionScriptService(db=db, config_path=str(tmp_yaml))
    stats1 = asyncio.run(svc.scan_and_upsert())
    assert stats1["inserted"] == 1
    assert stats1["skipped"] == 0
    # 第二次扫描：cache 已有 linux-bash → skipped=1，不触发 fetchrow
    fetch_call_count_before = db.fetchrow.await_count
    stats2 = asyncio.run(svc.scan_and_upsert())
    assert stats2["skipped"] == 1
    assert stats2["inserted"] == 0
    assert stats2["updated"] == 0
    # 关键：编辑优先模式下不调用 DB
    assert db.fetchrow.await_count == fetch_call_count_before


def test_update_script_detail_updates_db_and_cache(tmp_yaml):
    """update_script_detail 写入 DB 并同步 _cache / _id_cache（2026-08-04 新增）。"""
    import asyncio
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db()
    db.fetchrow.return_value = {
        "id": 7,
        "name": "linux-bash",
        "display_name": "Linux Bash (人工编辑)",
        "platform": "linux",
        "version": "bash",
        "inspection_parser": "json",
        "inspection_script": "echo manual",
        "inspection_fields": "[]",
        "created_at": None,
        "updated_at": "2026-08-04",
    }
    svc = InspectionScriptService(db=db, config_path=str(tmp_yaml))
    asyncio.run(svc.preload_all())
    payload = {
        "display_name": "Linux Bash (人工编辑)",
        "platform": "linux",
        "version": "bash",
        "inspection_parser": "json",
        "inspection_script": "echo manual",
        "inspection_fields": [],
    }
    result = asyncio.run(svc.update_script_detail(7, payload))
    assert result is not None
    assert result["display_name"] == "Linux Bash (人工编辑)"
    assert "linux-bash" in svc._cache
    assert svc._cache["linux-bash"]["inspection_script"] == "echo manual"
    # _id_cache 也同步
    assert 7 in svc._id_cache


def test_update_script_detail_invalid_returns_none(tmp_yaml):
    """update_script_detail 收到非法入参 → 返回 None（不抛）。"""
    import asyncio
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db()
    svc = InspectionScriptService(db=db, config_path=str(tmp_yaml))
    # platform 非法
    assert asyncio.run(svc.update_script_detail(1, {
        "display_name": "X", "platform": "solaris", "version": "",
        "inspection_parser": "json", "inspection_script": None,
        "inspection_fields": [],
    })) is None
    # inspection_parser 非法
    assert asyncio.run(svc.update_script_detail(1, {
        "display_name": "X", "platform": "linux", "version": "",
        "inspection_parser": "yaml", "inspection_script": None,
        "inspection_fields": [],
    })) is None
    # display_name 空
    assert asyncio.run(svc.update_script_detail(1, {
        "display_name": "  ", "platform": "linux", "version": "",
        "inspection_parser": "json", "inspection_script": None,
        "inspection_fields": [],
    })) is None


def test_update_script_detail_missing_id_returns_none(tmp_yaml):
    """script_id 不存在（DB 未返回行）→ 返回 None。"""
    import asyncio
    from app.shared.utils.inspection_script_service import InspectionScriptService

    db = _make_db()
    db.fetchrow.return_value = None
    svc = InspectionScriptService(db=db, config_path=str(tmp_yaml))
    result = asyncio.run(svc.update_script_detail(9999, {
        "display_name": "X", "platform": "linux", "version": "",
        "inspection_parser": "json", "inspection_script": None,
        "inspection_fields": [],
    }))
    assert result is None