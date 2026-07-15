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


def _make_service():
    """构造一个 DevOpsServerService 测试实例。

    Returns:
        DevOpsServerService: 单例实例(未挂入全局)
    """
    from app.shared.utils.devops_server_service import DevOpsServerService

    key = Fernet.generate_key().decode("ascii")
    db = MagicMock(name="db_pool_stub")
    return DevOpsServerService(db=db, config_path="unused.yaml", credential_key=key)


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
    """``list_public_servers`` 严格只返回 id / business_name / server_type / updated_at。"""
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