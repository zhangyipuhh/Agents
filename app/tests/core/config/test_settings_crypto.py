# -*- coding:utf-8 -*-
"""settings_crypto 单元测试

测试目标:
- get_master_fernet: SETTINGS_SECRET_KEY 缺失/非法/合法三态
- encrypt_value / decrypt_value: 往返一致;密文带 'fernet:' 前缀
- mask_value: 短值全掩;长值保留后 4 位
- is_encrypted: 前缀识别
"""
import pytest
from cryptography.fernet import Fernet

from app.core.config.settings_crypto import (
    decrypt_value,
    encrypt_value,
    get_master_fernet,
    is_encrypted,
    mask_value,
)


class TestGetMasterFernet:
    """get_master_fernet 三态测试"""

    def test_missing_key_raises_runtime_error(self, monkeypatch):
        """SETTINGS_SECRET_KEY 缺失 → RuntimeError fail-loud"""
        monkeypatch.delenv("SETTINGS_SECRET_KEY", raising=False)
        get_master_fernet.cache_clear()
        with pytest.raises(RuntimeError, match="SETTINGS_SECRET_KEY"):
            get_master_fernet()

    def test_invalid_key_raises_runtime_error(self, monkeypatch):
        """SETTINGS_SECRET_KEY 非法 → RuntimeError fail-loud"""
        monkeypatch.setenv("SETTINGS_SECRET_KEY", "not-a-fernet-key")
        get_master_fernet.cache_clear()
        with pytest.raises(RuntimeError, match="SETTINGS_SECRET_KEY"):
            get_master_fernet()

    def test_valid_key_returns_fernet(self, monkeypatch):
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
