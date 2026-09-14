# -*- coding:utf-8 -*-
"""SystemConfigService 单元测试

测试目标:
- seed_from_settings / load_all / get_group / list_groups / update_group / reset_group
- 敏感字段加密落库 + 脱敏返回
- pydantic 校验失败 → ValueError
"""
import json
from datetime import datetime
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config.settings_crypto import encrypt_value, get_master_fernet
from app.core.services.system_config_registry import SystemConfigRegistry
from app.core.services.system_config_service import SystemConfigService


class _FakeConn:
    """_FakeConnection: 形状层 fake,只模拟 fetchrow / fetch / execute 协议"""

    def __init__(self, rows: Optional[Dict[str, dict]] = None):
        self.rows: Dict[str, dict] = rows or {}
        self.executed: list = []

    async def fetchrow(self, sql: str, *args):
        group_key = args[0] if args else None
        row = self.rows.get(group_key)
        if row is None:
            return None
        return {
            "group_key": group_key,
            "config": row["config"],
            "updated_at": row.get("updated_at", datetime(2026, 9, 14)),
            "updated_by": row.get("updated_by", "admin"),
        }

    async def fetch(self, sql: str, *args):
        return [
            {
                "group_key": k,
                "config": v["config"],
                "updated_at": v.get("updated_at", datetime(2026, 9, 14)),
                "updated_by": v.get("updated_by", "admin"),
            }
            for k, v in self.rows.items()
        ]

    async def execute(self, sql: str, *args):
        self.executed.append((sql, args))
        # UPSERT: 解析 args
        if "INSERT INTO system_settings_groups" in sql:
            group_key, config_json, updated_by = args[0], args[1], args[2]
            self.rows[group_key] = {
                "config": json.loads(config_json) if isinstance(config_json, str) else config_json,
                "updated_by": updated_by,
            }
        return "INSERT 0 1"


class _FakePool:
    def __init__(self, conn: _FakeConn):
        self._conn = conn

    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self):
                return pool._conn

            async def __aexit__(self, *a):
                return False

        return _Ctx()


class _LLMSettings(BaseModel):
    """测试用 Settings:BaseModel 而非 BaseSettings,完全不走 env

    SystemConfigService._validate_config 用 meta.settings_cls(**config)
    校验,只要求是 BaseModel 即可,不要求从 env 读取。
    """
    model_name: str = "default-model"
    model_api_key: str = ""
    model_temperature: float = 0.2


class _CORSSettings(BaseModel):
    """测试用 Settings:BaseModel 而非 BaseSettings,完全不走 env"""
    allowed_origins: list = []


@pytest.fixture(autouse=True)
def _reset_registry():
    SystemConfigRegistry.clear()
    yield
    SystemConfigRegistry.clear()


@pytest.fixture
def fernet_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("SETTINGS_SECRET_KEY", key)
    get_master_fernet.cache_clear()
    return key


@pytest.fixture
def fake_settings(monkeypatch):
    """模拟 settings 单例(完全隔离 .env 污染)

    通过 monkeypatch 清理相关 env 变量,确保 _LLMSettings() 实例化时不读 .env
    """
    # 清空所有会影响 _LLMSettings 字段的 env
    for k in [
        "MODEL_NAME", "MODEL_TYPE", "MODEL_API_KEY", "MODEL_API_BASE",
        "MODEL_TEMPERATURE", "IS_MULTIMODAL", "PARALLEL_TOOL_CALLS",
        "OLLAMA_REASONING", "OLLAMA_TIMEOUT",
        "ALLOWED_ORIGINS", "CORS_ALLOWED_ORIGINS",
    ]:
        monkeypatch.delenv(k, raising=False)
    s = MagicMock()
    s.llm = _LLMSettings()
    s.cors = _CORSSettings()
    return s


class TestSeedFromSettings:
    @pytest.mark.asyncio
    async def test_seed_empty_table(self, fernet_key, fake_settings):
        SystemConfigRegistry.register(
            group_key="llm", tab="llm", label="主模型",
            settings_cls=_LLMSettings, sensitive_fields=["model_api_key"],
        )
        fake_settings.llm.model_api_key = "sk-secret-123"
        conn = _FakeConn()
        svc = SystemConfigService(pool=_FakePool(conn), settings=fake_settings)
        await svc.seed_from_settings()
        assert "llm" in conn.rows
        # 敏感字段已加密
        assert conn.rows["llm"]["config"]["model_api_key"].startswith("fernet:")
        assert conn.rows["llm"]["config"]["model_name"] == "default-model"

    @pytest.mark.asyncio
    async def test_seed_skips_existing(self, fernet_key, fake_settings):
        SystemConfigRegistry.register(
            group_key="llm", tab="llm", label="主模型",
            settings_cls=_LLMSettings, sensitive_fields=["model_api_key"],
        )
        conn = _FakeConn(rows={"llm": {"config": {"model_name": "existing"}}})
        svc = SystemConfigService(pool=_FakePool(conn), settings=fake_settings)
        await svc.seed_from_settings()
        # 已有行不被覆盖
        assert conn.rows["llm"]["config"]["model_name"] == "existing"


class TestLoadAll:
    @pytest.mark.asyncio
    async def test_load_overrides_settings(self, fernet_key, fake_settings):
        SystemConfigRegistry.register(
            group_key="llm", tab="llm", label="主模型",
            settings_cls=_LLMSettings, sensitive_fields=["model_api_key"],
        )
        cipher = encrypt_value("sk-from-db")
        conn = _FakeConn(rows={
            "llm": {"config": {
                "model_name": "db-model",
                "model_api_key": cipher,
                "model_temperature": 0.5,
            }},
        })
        svc = SystemConfigService(pool=_FakePool(conn), settings=fake_settings)
        await svc.load_all()
        assert fake_settings.llm.model_name == "db-model"
        assert fake_settings.llm.model_api_key == "sk-from-db"  # 已解密
        assert fake_settings.llm.model_temperature == 0.5

    @pytest.mark.asyncio
    async def test_load_skips_unknown_group(self, fernet_key, fake_settings):
        """DB 里有未注册 group → 跳过(不报错,向后兼容)"""
        conn = _FakeConn(rows={"unknown": {"config": {"x": 1}}})
        svc = SystemConfigService(pool=_FakePool(conn), settings=fake_settings)
        await svc.load_all()  # 不抛异常


class TestGetGroup:
    @pytest.mark.asyncio
    async def test_get_group_masks_sensitive(self, fernet_key, fake_settings):
        SystemConfigRegistry.register(
            group_key="llm", tab="llm", label="主模型",
            settings_cls=_LLMSettings, sensitive_fields=["model_api_key"],
        )
        cipher = encrypt_value("sk-1234567890abcdef")
        conn = _FakeConn(rows={
            "llm": {"config": {
                "model_name": "m",
                "model_api_key": cipher,
                "model_temperature": 0.2,
            }},
        })
        svc = SystemConfigService(pool=_FakePool(conn), settings=fake_settings)
        result = await svc.get_group("llm")
        assert result["group_key"] == "llm"
        assert result["config"]["model_api_key"] == "****"
        assert result["config"]["model_name"] == "m"
        assert "updated_at" in result

    @pytest.mark.asyncio
    async def test_get_group_returns_default_when_missing(self, fernet_key, fake_settings):
        """DB 无行 → 返回 settings 现值脱敏版"""
        SystemConfigRegistry.register(
            group_key="llm", tab="llm", label="主模型",
            settings_cls=_LLMSettings, sensitive_fields=["model_api_key"],
        )
        fake_settings.llm.model_api_key = "sk-local-env"
        conn = _FakeConn()
        svc = SystemConfigService(pool=_FakePool(conn), settings=fake_settings)
        result = await svc.get_group("llm")
        assert result["config"]["model_api_key"] == "****-env"  # 脱敏后保留后 4 位


class TestUpdateGroup:
    @pytest.mark.asyncio
    async def test_update_encrypts_sensitive(self, fernet_key, fake_settings):
        SystemConfigRegistry.register(
            group_key="llm", tab="llm", label="主模型",
            settings_cls=_LLMSettings, sensitive_fields=["model_api_key"],
        )
        conn = _FakeConn()
        svc = SystemConfigService(pool=_FakePool(conn), settings=fake_settings)
        await svc.update_group(
            "llm",
            {"model_name": "new-model", "model_api_key": "sk-new-secret"},
            operator="admin",
        )
        assert conn.rows["llm"]["config"]["model_name"] == "new-model"
        assert conn.rows["llm"]["config"]["model_api_key"].startswith("fernet:")

    @pytest.mark.asyncio
    async def test_update_masked_value_keeps_original(self, fernet_key, fake_settings):
        """敏感字段传 '****' 前缀 → 保持 DB 原值不变"""
        SystemConfigRegistry.register(
            group_key="llm", tab="llm", label="主模型",
            settings_cls=_LLMSettings, sensitive_fields=["model_api_key"],
        )
        old_cipher = encrypt_value("sk-old")
        conn = _FakeConn(rows={
            "llm": {"config": {"model_api_key": old_cipher, "model_name": "m"}},
        })
        svc = SystemConfigService(pool=_FakePool(conn), settings=fake_settings)
        await svc.update_group(
            "llm",
            {"model_api_key": "****", "model_temperature": 0.9},
            operator="admin",
        )
        assert conn.rows["llm"]["config"]["model_api_key"] == old_cipher
        assert conn.rows["llm"]["config"]["model_temperature"] == 0.9

    @pytest.mark.asyncio
    async def test_update_unknown_group_raises(self, fernet_key, fake_settings):
        conn = _FakeConn()
        svc = SystemConfigService(pool=_FakePool(conn), settings=fake_settings)
        with pytest.raises(KeyError):
            await svc.update_group("unknown", {}, operator="admin")

    @pytest.mark.asyncio
    async def test_update_validation_failure_raises(self, fernet_key, fake_settings):
        """pydantic 校验失败 → ValueError"""
        SystemConfigRegistry.register(
            group_key="llm", tab="llm", label="主模型",
            settings_cls=_LLMSettings, sensitive_fields=["model_api_key"],
        )
        conn = _FakeConn()
        svc = SystemConfigService(pool=_FakePool(conn), settings=fake_settings)
        with pytest.raises(ValueError):
            await svc.update_group(
                "llm", {"model_temperature": "not-a-float"}, operator="admin"
            )


class TestResetGroup:
    @pytest.mark.asyncio
    async def test_reset_to_default(self, fernet_key, fake_settings):
        SystemConfigRegistry.register(
            group_key="llm", tab="llm", label="主模型",
            settings_cls=_LLMSettings, sensitive_fields=["model_api_key"],
        )
        conn = _FakeConn(rows={"llm": {"config": {"model_name": "custom"}}})
        svc = SystemConfigService(pool=_FakePool(conn), settings=fake_settings)
        await svc.reset_group("llm", operator="admin")
        assert conn.rows["llm"]["config"]["model_name"] == "default-model"
