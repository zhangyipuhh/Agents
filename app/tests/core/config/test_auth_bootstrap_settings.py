# -*- coding:utf-8 -*-
"""
AuthBootstrapSettings 单元测试（等保三级 Task 2，2026-08-09 新增）。

覆盖：
- 类可导入与存在性；
- 默认值（bootstrap_enabled=False / default_admin_username="admin" / default_admin_password=""）；
- 环境变量映射（env 前缀 AUTH_）；
- bootstrap_enabled=True 时 default_admin_password 必须通过 ``validate_password``；
- 在 Settings 顶层可读 ``settings.auth``。
"""
from __future__ import annotations

import pytest

from app.core.config.settings import AuthBootstrapSettings, Settings


# ============================================================
# P0: 导入/存在性
# ============================================================


def test_auth_bootstrap_settings_importable():
    """P0: AuthBootstrapSettings 可导入与类属性存在性。"""
    assert AuthBootstrapSettings is not None
    field_names = set(getattr(AuthBootstrapSettings, "model_fields", {}).keys())
    expected = {
        "bootstrap_enabled",
        "default_admin_username",
        "default_admin_password",
    }
    missing = expected - field_names
    assert not missing, f"AuthBootstrapSettings 缺少字段: {missing}"


# ============================================================
# P1: 默认值契约
# ============================================================


def test_auth_bootstrap_settings_defaults(monkeypatch):
    """P1: 默认值满足安全契约。

    - bootstrap_enabled=False（默认不启用 bootstrap，避免历史弱口令被无意启用）
    - default_admin_username="admin"
    - default_admin_password=""（留空，由 lifespan 阶段校验）

    Args:
        monkeypatch: pytest monkeypatch fixture。
    """
    for env_name in (
        "AUTH_BOOTSTRAP_ENABLED",
        "AUTH_DEFAULT_ADMIN_USERNAME",
        "AUTH_DEFAULT_ADMIN_PASSWORD",
    ):
        monkeypatch.delenv(env_name, raising=False)

    cfg = AuthBootstrapSettings()
    assert cfg.bootstrap_enabled is False
    assert cfg.default_admin_username == "admin"
    assert cfg.default_admin_password == ""


# ============================================================
# P1: 环境变量映射
# ============================================================


def test_auth_bootstrap_settings_env(monkeypatch):
    """P1: AUTH_BOOTSTRAP_ENABLED / AUTH_DEFAULT_ADMIN_USERNAME / AUTH_DEFAULT_ADMIN_PASSWORD 可被环境变量覆盖。"""
    monkeypatch.setenv("AUTH_BOOTSTRAP_ENABLED", "true")
    monkeypatch.setenv("AUTH_DEFAULT_ADMIN_USERNAME", "ops")
    monkeypatch.setenv("AUTH_DEFAULT_ADMIN_PASSWORD", "P@ssword1!")

    cfg = AuthBootstrapSettings()
    assert cfg.bootstrap_enabled is True
    assert cfg.default_admin_username == "ops"
    assert cfg.default_admin_password == "P@ssword1!"


# ============================================================
# P1: bootstrap_enabled=True 时弱口令被拒绝
# ============================================================


def test_auth_bootstrap_settings_weak_password_rejected():
    """P1: bootstrap_enabled=True 且 default_admin_password="admin123" 时 Pydantic 校验失败。"""
    with pytest.raises(ValueError):
        AuthBootstrapSettings(
            bootstrap_enabled=True,
            default_admin_username="admin",
            default_admin_password="admin123",
        )


def test_auth_bootstrap_settings_short_password_rejected():
    """P1: bootstrap_enabled=True 且 default_admin_password 长度 < 8 时被拒绝。"""
    with pytest.raises(ValueError):
        AuthBootstrapSettings(
            bootstrap_enabled=True,
            default_admin_username="admin",
            default_admin_password="Ab1!",
        )


def test_auth_bootstrap_settings_disabled_allows_empty_password():
    """P1: bootstrap_enabled=False 时 default_admin_password="" 不报错（lifespan 阶段失败由 UserDB 处理）。"""
    cfg = AuthBootstrapSettings(
        bootstrap_enabled=False,
        default_admin_username="admin",
        default_admin_password="",
    )
    assert cfg.default_admin_password == ""


# ============================================================
# P1: 通过 Settings 顶层访问 auth
# ============================================================


def test_settings_exposes_auth_bootstrap():
    """P1: Settings.auth 提供 AuthBootstrapSettings 实例。"""
    s = Settings()
    assert hasattr(s, "auth")
    assert isinstance(s.auth, AuthBootstrapSettings)
    assert s.auth.default_admin_username == "admin"