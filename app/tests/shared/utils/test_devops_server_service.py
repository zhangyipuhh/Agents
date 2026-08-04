# -*- coding:utf-8 -*-
"""
DevOpsServerService 单元测试（2026-07-15 新增）

覆盖目标：
    - 单例生命周期:``set_instance`` / ``get_instance`` / ``reset``
    - ``credential_key`` 校验:空 / 非法 base64 一律抛 ValueError
    - ``get_connection_config`` 内部解密,严格不回显业务名细节
    - ``preload_all`` 写入路径持有 ``_write_lock``(Bug-6 修复回归)
    - ``scan_and_upsert`` 写入路径持有 ``_write_lock``(Bug-6 修复回归)
    - 并发 ``scan_and_upsert`` 调用串行,最终 _cache 一致
    - 防御性还原:_ensure_list 兼容 list / dict / str(JSON) / None

注意：
    - 测试环境不依赖真实 DB,用 ``MagicMock`` 模拟 ``db.fetch`` / ``db.fetchrow``
    - ``credential_key`` 使用 cryptography.fernet.Fernet.generate_key() 动态生成
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet


def _make_inspection_script_service():
    """构造 InspectionScriptService 替身（含 linux-bash 默认条目）。

    Returns:
        MagicMock: 替身实例
    """
    svc = MagicMock(name="inspection_script_service_stub")
    svc._cache = {
        "linux-bash": {
            "id": 1,
            "name": "linux-bash",
            "display_name": "Linux Bash 巡检",
            "platform": "linux",
            "version": "bash",
            "inspection_parser": "json",
            "inspection_script": "echo linux",
            "inspection_fields": [],
        },
        # 2026-08-04 新增：set_inspection_script 测试需要的「ID=42 linux-bash-alt」脚本
        "linux-bash-alt": {
            "id": 42,
            "name": "linux-bash-alt",
            "display_name": "Linux Bash 巡检（备用）",
            "platform": "linux",
            "version": "bash",
            "inspection_parser": "json",
            "inspection_script": "echo alt",
            "inspection_fields": [],
        },
    }
    svc._id_cache = {rec["id"]: rec for rec in svc._cache.values()}

    def _resolve(server_type, script_name=None):
        if script_name:
            rec = svc._cache.get(script_name)
            return rec["id"] if rec else None
        defaults = {"linux": "linux-bash", "windows": "windows-ps-5.1"}
        default_name = defaults.get((server_type or "").lower())
        if default_name and default_name in svc._cache:
            return svc._cache[default_name]["id"]
        return None

    svc.resolve_script_for_server.side_effect = _resolve
    svc.get_script_by_id.side_effect = lambda _id: svc._id_cache.get(_id)
    svc.get_script_by_name.side_effect = lambda _name: svc._cache.get(_name)
    return svc


def _make_service():
    """构造一个 DevOpsServerService 测试实例。

    Returns:
        DevOpsServerService: 单例实例(未挂入全局)
    """
    from app.shared.utils.devops_server_service import DevOpsServerService

    key = Fernet.generate_key().decode("ascii")
    db = MagicMock(name="db_pool_stub")
    return DevOpsServerService(
        db=db,
        config_path="unused.yaml",
        credential_key=key,
        inspection_script_service=_make_inspection_script_service(),
    )


# ----------------------------------------------------------------------
# 单例 / 构造
# ----------------------------------------------------------------------


def test_singleton_set_get_reset():
    """单例:``set_instance`` 后 ``get_instance`` 返回同一实例,``reset`` 后取不到。"""
    from app.shared.utils.devops_server_service import DevOpsServerService

    svc = _make_service()
    DevOpsServerService.set_instance(svc)
    assert DevOpsServerService.get_instance() is svc
    DevOpsServerService.reset()
    with pytest.raises(RuntimeError):
        DevOpsServerService.get_instance()


def test_empty_credential_key_raises():
    """credential_key 为空 → ValueError。"""
    from app.shared.utils.devops_server_service import DevOpsServerService

    db = MagicMock()
    with pytest.raises(ValueError, match="credential_key 不能为空"):
        DevOpsServerService(db=db, config_path="x", credential_key="")


def test_invalid_credential_key_raises():
    """credential_key 非法 base64 → ValueError。"""
    from app.shared.utils.devops_server_service import DevOpsServerService

    db = MagicMock()
    with pytest.raises(ValueError, match="credential_key 不是合法 Fernet base64 密钥"):
        DevOpsServerService(db=db, config_path="x", credential_key="not-valid-base64!@#")


def test_write_lock_is_asyncio_lock():
    """Bug-6 回归:构造后 ``_write_lock`` 是 ``asyncio.Lock`` 实例。"""
    svc = _make_service()
    assert isinstance(svc._write_lock, asyncio.Lock)


# ----------------------------------------------------------------------
# preload_all Bug-6 回归
# ----------------------------------------------------------------------


def test_preload_all_uses_write_lock():
    """Bug-6 回归:``preload_all`` 写入 _cache 段被 ``_write_lock`` 包裹。"""
    svc = _make_service()
    fake_row = {
        "id": 1,
        "business_name": "alpha",
        "ip": "10.0.0.1",
        "port": 22,
        "username": "u",
        "password_encrypted": b"\x00\x01\x02",
        "server_type": "linux",
        "blacklist": [],
        "whitelist": ["ls"],
        "created_at": None,
        "updated_at": None,
    }
    svc.db = MagicMock()
    svc.db.fetch = AsyncMock(return_value=[fake_row])

    # 把 _write_lock 替换为可观测的 mock,确认 preload_all 走 with 路径
    captured = {"used": False}
    original_lock = svc._write_lock

    class _ObservedLock:
        async def __aenter__(self):
            captured["used"] = True
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    svc._write_lock = _ObservedLock()

    asyncio.run(svc.preload_all())
    assert captured["used"] is True
    assert "alpha" in svc._cache


# ----------------------------------------------------------------------
# scan_and_upsert Bug-6 回归
# ----------------------------------------------------------------------


def test_scan_and_upsert_uses_write_lock(tmp_path, monkeypatch):
    """Bug-6 回归:``scan_and_upsert`` 写 _cache 段被 ``_write_lock`` 包裹。

    Args:
        tmp_path: pytest tmp_path fixture
        monkeypatch: pytest monkeypatch fixture
    """
    svc = _make_service()

    # 准备 servers.yaml
    yaml_path = tmp_path / "servers.yaml"
    yaml_path.write_text(
        "- business_name: biz\n"
        "  ip: 10.0.0.5\n"
        "  port: 22\n"
        "  username: u\n"
        "  password: pw\n"
        "  server_type: linux\n"
        "  blacklist: []\n"
        "  whitelist: ['ls']\n",
        encoding="utf-8",
    )
    svc.config_path = str(yaml_path)

    # mock db.fetchrow 返回 (inserted=True, row) 元组:fetchrow 返回 dict-like row
    fake_row = MagicMock()
    fake_row.get = lambda k, d=None: {
        "id": 1,
        "inserted": True,
        "business_name": "biz",
        "ip": "10.0.0.5",
        "port": 22,
        "username": "u",
        "password_encrypted": b"\xff\xff",
        "server_type": "linux",
        "blacklist": "[]",
        "whitelist": '["ls"]',
        "created_at": None,
        "updated_at": None,
    }.get(k, d)
    svc.db = MagicMock()
    svc.db.fetchrow = AsyncMock(return_value=fake_row)

    # 观测锁使用
    captured = {"used": False}

    class _ObservedLock:
        async def __aenter__(self):
            captured["used"] = True
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    svc._write_lock = _ObservedLock()

    stats = asyncio.run(svc.scan_and_upsert())
    assert captured["used"] is True
    assert stats == {"scanned": 1, "inserted": 1, "updated": 0, "failed": 0}
    assert "biz" in svc._cache


# ----------------------------------------------------------------------
# 并发安全:Bug-6 写锁序列化
# ----------------------------------------------------------------------


def test_concurrent_scan_and_upsert_serializes_writes(tmp_path):
    """Bug-6 回归:并发 ``scan_and_upsert`` 调用写路径串行,最终 _cache 一致。"""
    svc = _make_service()

    # 准备 2 个 business_name 的 YAML
    yaml_path = tmp_path / "servers.yaml"
    yaml_path.write_text(
        "- business_name: a\n"
        "  ip: 10.0.0.1\n"
        "  port: 22\n"
        "  username: u\n"
        "  password: pwa\n"
        "  server_type: linux\n"
        "  blacklist: []\n"
        "  whitelist: ['ls']\n"
        "- business_name: b\n"
        "  ip: 10.0.0.2\n"
        "  port: 22\n"
        "  username: u\n"
        "  password: pwb\n"
        "  server_type: linux\n"
        "  blacklist: []\n"
        "  whitelist: ['ls']\n",
        encoding="utf-8",
    )
    svc.config_path = str(yaml_path)

    counter = {"n": 0}

    async def fake_fetchrow(*args, **kwargs):
        counter["n"] += 1
        biz_name = args[0] if args else kwargs.get("business_name")
        row = MagicMock()
        row.get = lambda k, d=None: {
            "id": counter["n"],
            "inserted": True,
            "business_name": biz_name,
            "ip": "10.0.0.1",
            "port": 22,
            "username": "u",
            "password_encrypted": b"\xff",
            "server_type": "linux",
            "blacklist": "[]",
            "whitelist": '["ls"]',
            "created_at": None,
            "updated_at": None,
        }.get(k, d)
        return row

    svc.db = MagicMock()
    svc.db.fetchrow = fake_fetchrow

    # 用 asyncio.gather 并发跑两次 scan_and_upsert
    async def runner():
        return await asyncio.gather(svc.scan_and_upsert(), svc.scan_and_upsert())

    results = asyncio.run(runner())
    # 两个 scan 都应统计到 2 个
    for stats in results:
        assert stats["scanned"] == 2
        assert stats["inserted"] == 2
    # _cache 应包含两个业务名,各一份
    assert set(svc._cache.keys()) == {"a", "b"}


# ----------------------------------------------------------------------
# _ensure_list 防御性还原
# ----------------------------------------------------------------------


def test_ensure_list_handles_various_inputs():
    """``_ensure_list`` 兼容 list / dict / str(JSON) / None。"""
    from app.shared.utils.devops_server_service import _ensure_list

    assert _ensure_list(["a", "b"]) == ["a", "b"]
    assert _ensure_list({"k": "v"}) == [{"k": "v"}]
    assert _ensure_list('["x","y"]') == ["x", "y"]
    assert _ensure_list('{"k":"v"}') == [{"k": "v"}]
    assert _ensure_list(None) == []
    assert _ensure_list("garbage not json") == []
    assert _ensure_list(123) == []


# ----------------------------------------------------------------------
# 公开字段严格白名单
# ----------------------------------------------------------------------


def test_list_public_servers_only_returns_whitelisted_fields():
    """``list_public_servers`` 严格只返回 7 字段白名单（2026-08-04 改造）。

    含 inspection_script_id / inspection_script_name / inspection_script_display_name
    三个 binding 元数据；未配置 / 脚本库未注入时三字段统一回退为 None。
    """
    svc = _make_service()
    svc._cache = {
        "alpha": {
            "id": 1,
            "business_name": "alpha",
            "ip": "10.0.0.1",
            "port": 22,
            "username": "u",
            "password_encrypted": b"\xff",
            "server_type": "linux",
            "blacklist": ["rm "],
            "whitelist": ["ls"],
            "inspection_script_id": None,
            "created_at": None,
            "updated_at": "2026-07-15",
        }
    }
    result = svc.list_public_servers()
    assert result == [
        {
            "id": 1,
            "business_name": "alpha",
            "server_type": "linux",
            "updated_at": "2026-07-15",
            "inspection_script_id": None,
            "inspection_script_name": None,
            "inspection_script_display_name": None,
        }
    ]
    # 绝不外泄
    raw = json.dumps(result)
    assert "10.0.0.1" not in raw
    assert "password" not in raw
    assert "rm " not in raw


# ----------------------------------------------------------------------
# get_connection_config 解密 + 错误传播
# ----------------------------------------------------------------------


def test_get_connection_config_unknown_business_name_raises_keyerror():
    """未注册的 business_name → KeyError。"""
    svc = _make_service()
    svc._cache = {}
    with pytest.raises(KeyError):
        svc.get_connection_config("ghost")


# ----------------------------------------------------------------------
# set_inspection_script 绑定/解绑（2026-08-04 新增）
# ----------------------------------------------------------------------


class _ScriptNotFoundError(Exception):
    """约定的脚本不存在错误类型，供 service 抛出来标识 404 场景。"""


def test_set_inspection_script_binds_existing_script_to_existing_server():
    """set_inspection_script 绑定有效脚本：DB UPDATE 参数正确；缓存同步；返回安全记录。

    Args:
        无
    """
    svc = _make_service()
    svc._cache = {
        "alpha": {
            "id": 1,
            "business_name": "alpha",
            "ip": "10.0.0.1",
            "port": 22,
            "username": "u",
            "password_encrypted": b"\xff",
            "server_type": "linux",
            "blacklist": [],
            "whitelist": ["ls"],
            "inspection_script_id": None,
            "created_at": None,
            "updated_at": None,
        }
    }

    # db.execute / db.fetchrow 返回更新后行
    updated_at = "2026-08-04T12:00:00"
    fetched_row = {
        "id": 1,
        "business_name": "alpha",
        "server_type": "linux",
        "updated_at": updated_at,
    }

    async def fake_fetchrow(*args, **kwargs):
        return fetched_row

    async def fake_execute(*args, **kwargs):
        return "UPDATE 1"

    svc.db = MagicMock()
    svc.db.fetchrow = fake_fetchrow
    svc.db.execute = fake_execute

    # 捕获 UPDATE SQL & 参数
    captured = {"sql": None, "args": None}

    async def capturing_fetchrow(sql, *args, **kwargs):
        captured["sql"] = sql
        captured["args"] = args
        # 返回完整 RETURNING 行
        return fetched_row

    svc.db.fetchrow = capturing_fetchrow

    result = asyncio.run(svc.set_inspection_script(1, 42))

    # UPDATE SQL 应只写 inspection_script_id
    assert "UPDATE devops_servers" in captured["sql"]
    assert "inspection_script_id" in captured["sql"]
    assert captured["args"][0] == 42
    assert captured["args"][1] == 1

    # 返回安全记录（仅含白名单字段）
    assert isinstance(result, dict)
    assert result["id"] == 1
    assert result["business_name"] == "alpha"
    assert result["server_type"] == "linux"
    assert result["inspection_script_id"] == 42
    # 同步缓存
    assert svc._cache["alpha"]["inspection_script_id"] == 42


def test_set_inspection_script_unbinds_when_id_is_none():
    """set_inspection_script(server_id, None) → DB 写入 NULL；缓存同步为 None。"""
    svc = _make_service()
    svc._cache = {
        "alpha": {
            "id": 1,
            "business_name": "alpha",
            "ip": "10.0.0.1",
            "port": 22,
            "username": "u",
            "password_encrypted": b"\xff",
            "server_type": "linux",
            "blacklist": [],
            "whitelist": ["ls"],
            "inspection_script_id": 42,
            "created_at": None,
            "updated_at": None,
        }
    }
    captured = {"args": None}

    async def capturing_fetchrow(sql, *args, **kwargs):
        captured["args"] = args
        return {"business_name": "alpha"}

    svc.db = MagicMock()
    svc.db.fetchrow = capturing_fetchrow

    result = asyncio.run(svc.set_inspection_script(1, None))

    assert captured["args"][0] is None
    assert captured["args"][1] == 1
    assert svc._cache["alpha"]["inspection_script_id"] is None
    assert result is not None


def test_set_inspection_script_unknown_server_returns_none():
    """未知 server_id 时返回 None（不抛异常）。"""
    svc = _make_service()
    svc._cache = {}  # 缓存为空

    async def fake_fetchrow(*args, **kwargs):
        # 模拟 UPDATE WHERE id=$2 影响 0 行：fetchrow 返回 None
        return None

    svc.db = MagicMock()
    svc.db.fetchrow = fake_fetchrow

    result = asyncio.run(svc.set_inspection_script(9999, 42))
    assert result is None


def test_set_inspection_script_unknown_script_raises_distinguishable_error():
    """传入的 inspection_script_id 不存在 → service 抛出可识别错误（约定为 ScriptNotFoundError 类型）。"""

    from unittest.mock import AsyncMock

    class _LocalScriptNotFoundError(Exception):
        pass

    # 注入一个独立的 InspectionScriptService 替身：脚本查找永远为 None
    inspection = MagicMock(name="inspection_script_service_stub")
    # 显式指定 return_value/side_effect，避免 MagicMock 默认返回 MagicMock 实例
    inspection.get_script_by_id = MagicMock(return_value=None)
    inspection.get_script_by_name = MagicMock(return_value=None)
    inspection.resolve_script_for_server = MagicMock(return_value=None)
    inspection._id_cache = {}
    inspection._cache = {}

    from app.shared.utils.devops_server_service import DevOpsServerService

    key = Fernet.generate_key().decode("ascii")
    db = MagicMock(name="db_pool_stub")
    db.fetchrow = AsyncMock()  # 用 AsyncMock 替换，确保 await_count 是数字
    svc = DevOpsServerService(
        db=db,
        config_path="unused.yaml",
        credential_key=key,
        inspection_script_service=inspection,
    )
    # 替换类的 ScriptNotFoundError 用本地异常类便于断言
    svc.ScriptNotFoundError = _LocalScriptNotFoundError

    with pytest.raises(_LocalScriptNotFoundError):
        asyncio.run(svc.set_inspection_script(1, 9999))

    # 确保不会在脚本不存在时意外写入 DB（被前置校验拦截）
    assert db.fetchrow.await_count == 0, (
        "脚本校验失败时不应触发 DB UPDATE；"
        f"实际 fetchrow 被调用 {db.fetchrow.await_count} 次"
    )


def test_set_inspection_script_db_failure_propagates():
    """DB UPDATE 抛异常时，service 不吞，向上抛。"""
    svc = _make_service()

    async def fake_fetchrow(*args, **kwargs):
        raise RuntimeError(
            "asyncpg UPDATE failed: server_id=1 leaked_ip=__LEAKED_ip_xyz__"
        )

    svc.db = MagicMock()
    svc.db.fetchrow = fake_fetchrow

    with pytest.raises(RuntimeError):
        asyncio.run(svc.set_inspection_script(1, 42))


def test_set_inspection_script_updates_cache_for_inspection_script_fields():
    """成功后 _cache 中除 inspection_script_id 外，原字段保留；新写入 inspection_script_id。"""
    svc = _make_service()
    svc._cache = {
        "alpha": {
            "id": 1,
            "business_name": "alpha",
            "ip": "10.0.0.99",
            "port": 22,
            "username": "rootX",
            "password_encrypted": b"\xff",
            "server_type": "linux",
            "blacklist": ["rm -rf"],
            "whitelist": ["ls"],
            "inspection_script_id": None,
            "created_at": None,
            "updated_at": "2026-08-04T00:00:00",
        }
    }

    async def fake_fetchrow(sql, *args, **kwargs):
        return {"business_name": "alpha"}

    svc.db = MagicMock()
    svc.db.fetchrow = fake_fetchrow

    result = asyncio.run(svc.set_inspection_script(1, 42))
    assert result is not None
    # 原 ip / port / username / password / blacklist / whitelist 等保持不变
    rec = svc._cache["alpha"]
    assert rec["ip"] == "10.0.0.99"
    assert rec["port"] == 22
    assert rec["username"] == "rootX"
    assert rec["blacklist"] == ["rm -rf"]
    assert rec["whitelist"] == ["ls"]
    assert rec["inspection_script_id"] == 42
    # 返回的 dict 不应泄露敏感字段
    for sensitive_key in (
        "ip",
        "port",
        "username",
        "password",
        "password_encrypted",
        "blacklist",
    ):
        assert sensitive_key not in result, f"leak: {sensitive_key}"


def test_set_inspection_script_syncs_three_binding_fields_in_cache():
    """set_inspection_script 成功后 _cache 同步三个 binding 元数据字段（2026-08-04 修复）。

    三个字段必须同时更新，避免列表端点（如 list_public_servers）从缓存中
    读到不一致的「id 已绑 / name 还显示旧值」。
    """
    svc = _make_service()
    svc._cache = {
        "alpha": {
            "id": 1,
            "business_name": "alpha",
            "ip": "10.0.0.1",
            "port": 22,
            "username": "u",
            "password_encrypted": b"\xff",
            "server_type": "linux",
            "blacklist": [],
            "whitelist": ["ls"],
            "inspection_script_id": None,
            "inspection_script_name": None,
            "inspection_script_display_name": None,
            "created_at": None,
            "updated_at": "2026-08-04T00:00:00",
        }
    }

    async def fake_fetchrow(sql, *args, **kwargs):
        return {"business_name": "alpha"}

    svc.db = MagicMock()
    svc.db.fetchrow = fake_fetchrow

    result = asyncio.run(svc.set_inspection_script(1, 42))

    # 三字段同步：id / name / display_name 都更新到缓存
    rec = svc._cache["alpha"]
    assert rec["inspection_script_id"] == 42
    assert rec["inspection_script_name"] == "linux-bash-alt"
    assert rec["inspection_script_display_name"] == "Linux Bash 巡检（备用）"
    # 返回字典也带三字段
    assert result["inspection_script_id"] == 42
    assert result["inspection_script_name"] == "linux-bash-alt"
    assert result["inspection_script_display_name"] == "Linux Bash 巡检（备用）"


def test_set_inspection_script_unbind_syncs_three_binding_fields_to_none():
    """解绑（inspection_script_id=None）后三个 binding 元数据同步置 None。

    避免缓存中保留旧 name / display_name 但 id 已是 None 的半残状态。
    """
    svc = _make_service()
    svc._cache = {
        "alpha": {
            "id": 1,
            "business_name": "alpha",
            "ip": "10.0.0.1",
            "port": 22,
            "username": "u",
            "password_encrypted": b"\xff",
            "server_type": "linux",
            "blacklist": [],
            "whitelist": ["ls"],
            "inspection_script_id": 42,
            "inspection_script_name": "linux-bash-alt",
            "inspection_script_display_name": "Linux Bash 巡检（备用）",
            "created_at": None,
            "updated_at": "2026-08-04T00:00:00",
        }
    }

    async def fake_fetchrow(sql, *args, **kwargs):
        return {"business_name": "alpha"}

    svc.db = MagicMock()
    svc.db.fetchrow = fake_fetchrow

    result = asyncio.run(svc.set_inspection_script(1, None))

    rec = svc._cache["alpha"]
    # 三字段同时置 None
    assert rec["inspection_script_id"] is None
    assert rec["inspection_script_name"] is None
    assert rec["inspection_script_display_name"] is None
    # 返回字典同样为 None
    assert result["inspection_script_id"] is None
    assert result["inspection_script_name"] is None
    assert result["inspection_script_display_name"] is None


def test_set_inspection_script_raises_unavailable_when_inspection_service_missing():
    """InspectionScriptService 未注入时抛 InspectionScriptServiceUnavailable（2026-08-04 修复）。

    与 ScriptNotFoundError 区分：缺失服务是配置类问题，不应被映射为 404「脚本不存在」。
    Router 层会把 InspectionScriptServiceUnavailable 映射为脱敏 500。
    """
    from app.shared.utils.devops_server_service import DevOpsServerService
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode("ascii")
    db = MagicMock(name="db_pool_stub")
    db.fetchrow = AsyncMock()

    # 关键：inspection_script_service=None 模拟强依赖缺失
    svc = DevOpsServerService(
        db=db,
        config_path="unused.yaml",
        credential_key=key,
        inspection_script_service=None,
    )

    with pytest.raises(DevOpsServerService.InspectionScriptServiceUnavailable):
        asyncio.run(svc.set_inspection_script(1, 42))

    # 关键：DB 一次也不应被调用（校验阶段就被拦截）
    assert db.fetchrow.await_count == 0


def test_list_public_servers_returns_seven_fields_with_binding_metadata():
    """list_public_servers 返回 7 字段，binding 元数据通过 script_id 解析（2026-08-04 新增）。

    命中 InspectionScriptService 缓存 → 三字段同步返回；
    未命中（脚本被删除 / 脚本库未注入）→ 三字段统一为 None。
    """
    svc = _make_service()
    svc._cache = {
        "alpha": {
            "id": 1,
            "business_name": "alpha",
            "ip": "10.0.0.1",
            "port": 22,
            "username": "u",
            "password_encrypted": b"\xff",
            "server_type": "linux",
            "blacklist": [],
            "whitelist": ["ls"],
            "inspection_script_id": 42,  # 命中 InspectionScriptService._id_cache
            "created_at": None,
            "updated_at": "2026-08-04T10:00:00",
        },
        "beta": {
            "id": 2,
            "business_name": "beta",
            "ip": "10.0.0.2",
            "port": 22,
            "username": "u",
            "password_encrypted": b"\xff",
            "server_type": "linux",
            "blacklist": [],
            "whitelist": ["ls"],
            "inspection_script_id": 9999,  # 脚本库已删除该 id
            "created_at": None,
            "updated_at": "2026-08-04T10:00:00",
        },
        "gamma": {
            "id": 3,
            "business_name": "gamma",
            "ip": "10.0.0.3",
            "port": 22,
            "username": "u",
            "password_encrypted": b"\xff",
            "server_type": "linux",
            "blacklist": [],
            "whitelist": ["ls"],
            "inspection_script_id": None,  # 未配置
            "created_at": None,
            "updated_at": "2026-08-04T10:00:00",
        },
    }
    result = svc.list_public_servers()
    by_name = {row["business_name"]: row for row in result}
    # alpha: 三字段齐全
    assert by_name["alpha"]["inspection_script_id"] == 42
    assert by_name["alpha"]["inspection_script_name"] == "linux-bash-alt"
    assert by_name["alpha"]["inspection_script_display_name"] == "Linux Bash 巡检（备用）"
    # beta: 脚本已被删除 → 三字段统一 None
    assert by_name["beta"]["inspection_script_id"] == 9999
    assert by_name["beta"]["inspection_script_name"] is None
    assert by_name["beta"]["inspection_script_display_name"] is None
    # gamma: 未配置 → 三字段 None
    assert by_name["gamma"]["inspection_script_id"] is None
    assert by_name["gamma"]["inspection_script_name"] is None
    assert by_name["gamma"]["inspection_script_display_name"] is None