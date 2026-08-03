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