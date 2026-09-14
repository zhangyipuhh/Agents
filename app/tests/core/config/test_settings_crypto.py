# -*- coding:utf-8 -*-
"""settings_crypto 单元测试

测试目标:
- bootstrap_master_key: 首次启动生成密钥落盘;已有文件时复用不覆盖
- get_master_fernet: SETTINGS_SECRET_KEY 三态(缺失→bootstrap / 合法→env / 非法→fail-loud)
- encrypt_value / decrypt_value: 往返一致;密文带 'fernet:' 前缀
- mask_value: 短值全掩;长值保留后 4 位
- is_encrypted: 前缀识别
"""
import os
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.core.config import settings_crypto
from app.core.config.paths import SETTINGS_SECRET_KEY_FILE
from app.core.config.settings_crypto import (
    bootstrap_master_key,
    decrypt_value,
    encrypt_value,
    get_master_fernet,
    is_encrypted,
    mask_value,
)


@pytest.fixture(autouse=True)
def _reset_crypto_state(tmp_path, monkeypatch):
    """每个用例前清空 get_master_fernet lru_cache,env,密钥文件状态"""
    get_master_fernet.cache_clear()
    yield
    get_master_fernet.cache_clear()


class TestBootstrapMasterKey:
    """bootstrap_master_key 行为测试(2026-09-14 新增,鸡生蛋死锁修复)"""

    def test_creates_key_file_when_missing(self, tmp_path, monkeypatch):
        """文件不存在 → 生成新密钥落盘"""
        # 重定向 SETTINGS_SECRET_KEY_FILE 到 tmp_path 避免污染真实 data/secrets/
        fake_file = tmp_path / "settings_secret.key"
        monkeypatch.setattr(settings_crypto, "SETTINGS_SECRET_KEY_FILE", str(fake_file))
        assert not fake_file.exists()

        key = bootstrap_master_key()

        assert isinstance(key, str)
        assert len(key) > 0
        # 落盘文件存在 + 内容一致
        assert fake_file.exists()
        assert fake_file.read_text(encoding="utf-8").strip() == key
        # 是合法 Fernet 密钥
        Fernet(key.encode("ascii"))  # 不抛即合法

    def test_reuses_existing_key_file(self, tmp_path, monkeypatch):
        """文件已存在 → 复用不覆盖(防止 DB 中加密字段不可逆报废)"""
        fake_file = tmp_path / "settings_secret.key"
        fake_file.parent.mkdir(parents=True, exist_ok=True)
        existing_key = Fernet.generate_key().decode("ascii")
        fake_file.write_text(existing_key, encoding="utf-8")
        monkeypatch.setattr(settings_crypto, "SETTINGS_SECRET_KEY_FILE", str(fake_file))

        returned = bootstrap_master_key()

        assert returned == existing_key
        # 内容未被改写
        assert fake_file.read_text(encoding="utf-8").strip() == existing_key

    def test_get_master_fernet_bootstraps_when_env_empty(self, tmp_path, monkeypatch):
        """env 缺失/空 → get_master_fernet 自动 bootstrap(不再 fail-loud)"""
        fake_file = tmp_path / "settings_secret.key"
        monkeypatch.setattr(settings_crypto, "SETTINGS_SECRET_KEY_FILE", str(fake_file))
        monkeypatch.delenv("SETTINGS_SECRET_KEY", raising=False)
        get_master_fernet.cache_clear()

        f = get_master_fernet()

        assert isinstance(f, Fernet)
        # bootstrap 已落盘
        assert fake_file.exists()


class TestGetMasterFernet:
    """get_master_fernet 三态测试"""

    def test_missing_env_auto_bootstraps(self, tmp_path, monkeypatch):
        """SETTINGS_SECRET_KEY 缺失 → 自动 bootstrap(2026-09-14 修订:不再 fail-loud)"""
        fake_file = tmp_path / "settings_secret.key"
        monkeypatch.setattr(settings_crypto, "SETTINGS_SECRET_KEY_FILE", str(fake_file))
        monkeypatch.delenv("SETTINGS_SECRET_KEY", raising=False)
        get_master_fernet.cache_clear()

        f = get_master_fernet()
        assert isinstance(f, Fernet)

    def test_invalid_env_still_fails_loud(self, tmp_path, monkeypatch):
        """SETTINGS_SECRET_KEY 非空但非法 → RuntimeError fail-loud(防止用错密钥静默启动)"""
        fake_file = tmp_path / "settings_secret.key"
        monkeypatch.setattr(settings_crypto, "SETTINGS_SECRET_KEY_FILE", str(fake_file))
        monkeypatch.setenv("SETTINGS_SECRET_KEY", "not-a-fernet-key")
        get_master_fernet.cache_clear()

        with pytest.raises(RuntimeError, match="SETTINGS_SECRET_KEY"):
            get_master_fernet()

    def test_valid_env_returns_fernet(self, monkeypatch):
        """SETTINGS_SECRET_KEY 合法 → Fernet 实例"""
        key = Fernet.generate_key().decode()
        monkeypatch.setenv("SETTINGS_SECRET_KEY", key)
        get_master_fernet.cache_clear()
        f = get_master_fernet()
        assert isinstance(f, Fernet)


class TestEncryptDecrypt:
    """encrypt_value / decrypt_value 往返一致性"""

    def test_roundtrip(self, monkeypatch):
        key = Fernet.generate_key().decode()
        monkeypatch.setenv("SETTINGS_SECRET_KEY", key)
        get_master_fernet.cache_clear()
        plain = "sk-secret-api-key-12345"
        cipher = encrypt_value(plain)
        assert cipher.startswith("fernet:")
        assert is_encrypted(cipher)
        assert decrypt_value(cipher) == plain

    def test_empty_string_returns_empty(self, monkeypatch):
        key = Fernet.generate_key().decode()
        monkeypatch.setenv("SETTINGS_SECRET_KEY", key)
        get_master_fernet.cache_clear()
        assert encrypt_value("") == ""
        assert decrypt_value("") == ""

    def test_decrypt_non_encrypted_returns_as_is(self, monkeypatch):
        """decrypt_value 对非 fernet: 前缀值原样返回(向后兼容)"""
        key = Fernet.generate_key().decode()
        monkeypatch.setenv("SETTINGS_SECRET_KEY", key)
        get_master_fernet.cache_clear()
        assert decrypt_value("plain-text") == "plain-text"


class TestMaskValue:
    """mask_value 脱敏"""

    def test_short_value_fully_masked(self):
        assert mask_value("abc") == "****"

    def test_long_value_keeps_last_4(self):
        assert mask_value("sk-1234567890abcdef") == "****cdef"

    def test_empty_returns_empty(self):
        assert mask_value("") == ""

    def test_encrypted_value_masked_as_cipher(self):
        """已加密值整体脱敏(不暴露密文)"""
        assert mask_value("fernet:gAAAAAB...") == "****"


class TestIsEncrypted:
    """is_encrypted 前缀识别"""

    def test_fernet_prefix_true(self):
        assert is_encrypted("fernet:gAAAAAB...") is True

    def test_plain_false(self):
        assert is_encrypted("plain") is False

    def test_empty_false(self):
        assert is_encrypted("") is False
