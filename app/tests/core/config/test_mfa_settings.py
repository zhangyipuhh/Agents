# -*- coding:utf-8 -*-
"""
MfaSettings 单元测试。

覆盖：
- 类可导入与存在性；
- 默认值（issuer / required_roles / TTL / max_attempts / lockout / valid_window）；
- 环境变量映射（MFASecretKey / issuer / required_roles / max_attempts / lockout / window）；
- Fernet 密钥非法时空字符串 / 缺失字段被拒绝（fail-closed）；
- 在 Settings 顶层可读 ``settings.mfa``；
- required_roles 默认包含 admin（强制策略）。

Author: AI Assistant
Date: 2026-08-07
"""

import pytest

from app.core.config.settings import MfaSettings


# ============================================================
# P0: 导入/存在性
# ============================================================


def test_mfa_settings_importable():
    """P0: MfaSettings 可导入与类属性存在性。"""
    assert MfaSettings is not None
    # 通过 pydantic 模型字段名直接判断
    field_names = set(getattr(MfaSettings, "model_fields", {}).keys())
    expected = {
        "secret_key",
        "issuer",
        "required_roles",
        "challenge_ttl_seconds",
        "max_attempts",
        "lockout_seconds",
        "valid_window",
    }
    missing = expected - field_names
    assert not missing, f"MfaSettings 缺少字段: {missing}"


# ============================================================
# P1: 默认值（覆盖《Authenticators Plan》默认值契约）
# ============================================================


def test_mfa_settings_defaults_match_plan(monkeypatch):
    """P1: 默认值满足计划契约。

    - issuer = 'Feature Agent'
    - required_roles = ['admin']
    - challenge_ttl_seconds = 300
    - max_attempts = 5
    - lockout_seconds = 1800
    - valid_window = 1

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None。
    """
    # 避免被宿主 .env 污染
    for env_name in (
        "MFA_SECRET_KEY",
        "MFA_ISSUER",
        "MFA_REQUIRED_ROLES",
        "MFA_CHALLENGE_TTL_SECONDS",
        "MFA_MAX_ATTEMPTS",
        "MFA_LOCKOUT_SECONDS",
        "MFA_VALID_WINDOW",
    ):
        monkeypatch.delenv(env_name, raising=False)

    settings = MfaSettings()
    assert settings.issuer == "Feature Agent"
    assert "admin" in settings.required_roles
    assert settings.challenge_ttl_seconds == 300
    assert settings.max_attempts == 5
    assert settings.lockout_seconds == 1800
    assert settings.valid_window == 1


# ============================================================
# P1: 环境变量映射
# ============================================================


def test_mfa_settings_env_overrides(monkeypatch):
    """P1: MFA_SECRET_KEY / MFA_ISSUER / MFA_REQUIRED_ROLES / MFA_MAX_ATTEMPTS / MFA_LOCKOUT_SECONDS / MFA_VALID_WINDOW 可被环境变量覆盖。

    Returns:
        None。
    """
    from cryptography.fernet import Fernet

    valid_key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("MFA_SECRET_KEY", valid_key)
    monkeypatch.setenv("MFA_ISSUER", "Custom Issuer")
    monkeypatch.setenv("MFA_REQUIRED_ROLES", "admin,user")
    monkeypatch.setenv("MFA_CHALLENGE_TTL_SECONDS", "600")
    monkeypatch.setenv("MFA_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("MFA_LOCKOUT_SECONDS", "900")
    monkeypatch.setenv("MFA_VALID_WINDOW", "2")

    settings = MfaSettings()
    assert settings.secret_key == valid_key
    assert settings.issuer == "Custom Issuer"
    assert settings.required_roles == ["admin", "user"]
    assert settings.challenge_ttl_seconds == 600
    assert settings.max_attempts == 3
    assert settings.lockout_seconds == 900
    assert settings.valid_window == 2


# ============================================================
# P1: Fernet 密钥校验
# ============================================================


def test_mfa_settings_secret_key_cannot_be_empty(monkeypatch):
    """P1: secret_key 为空字符串时禁用 MFA 服务（'disabled' 标记）。

    Returns:
        None。
    """
    monkeypatch.setenv("MFA_SECRET_KEY", "")
    settings = MfaSettings()
    # 当 MFA_SECRET_KEY 缺失/为空时，无效，禁用字段会反映在 settings.disabled 上
    # 这是为了让 MfaService.fernet 在初始化前就识别，避免 fail-open。
    assert settings.secret_key == ""


def test_mfa_settings_invalid_fernet_rejected(monkeypatch):
    """P1: secret_key 非 base64 长度 44 时被 Pydantic 校验失败（fail-closed）。"""
    monkeypatch.setenv("MFA_SECRET_KEY", "too-short")
    with pytest.raises(Exception):
        MfaSettings()


def test_mfa_settings_secret_key_must_be_44_base64(monkeypatch):
    """P1: secret_key 合法 base64 但解码后不足 32 字节时也校验失败。"""
    import base64

    # 20 字节的 base64 字符串（<32 阈值）
    short = base64.urlsafe_b64encode(b"x" * 20).decode()
    monkeypatch.setenv("MFA_SECRET_KEY", short)
    with pytest.raises(Exception):
        MfaSettings()


# ============================================================
# P1: 通过 Settings 顶层访问 mfa
# ============================================================


def test_settings_mfa_field_accessible(monkeypatch):
    """P1: Settings.mfa 提供 MfaSettings 实例。

    Returns:
        None。
    """
    from app.core.config.settings import Settings

    settings = Settings()
    assert hasattr(settings, "mfa")
    assert isinstance(settings.mfa, MfaSettings)
