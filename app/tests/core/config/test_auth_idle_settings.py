# -*- coding:utf-8 -*-
"""
AuthIdleSettings 配置测试模块（等保三级 §1.5，2026-08-12 新增）

验证 idle 超时配置的默认值、环境变量解析与总配置挂载。
"""
import pytest

from app.core.config.settings import AuthIdleSettings, Settings


def test_auth_idle_settings_defaults():
    """
    测试默认配置值

    Returns:
        None
    """
    cfg = AuthIdleSettings()
    assert cfg.timeout_seconds == 1800
    assert cfg.check_enabled is True
    assert cfg.check_exempt_paths == [
        "/api/auth/login",
        "/api/auth/refresh",
        "/api/health",
        "/health",
    ]
    assert cfg.check_fail_loud is True


def test_auth_idle_settings_parse_enabled_from_string(monkeypatch):
    """
    测试 AUTH_IDLE_CHECK_ENABLED 字符串环境变量解析为布尔值

    Args:
        monkeypatch: pytest monkeypatch fixture

    Returns:
        None
    """
    monkeypatch.setenv("AUTH_IDLE_CHECK_ENABLED", "false")
    cfg = AuthIdleSettings()
    assert cfg.check_enabled is False


def test_auth_idle_settings_parse_fail_loud_from_string(monkeypatch):
    """
    测试 AUTH_IDLE_CHECK_FAIL_LOUD 字符串环境变量解析为布尔值

    Args:
        monkeypatch: pytest monkeypatch fixture

    Returns:
        None
    """
    monkeypatch.setenv("AUTH_IDLE_CHECK_FAIL_LOUD", "0")
    cfg = AuthIdleSettings()
    assert cfg.check_fail_loud is False


def test_auth_idle_settings_timeout_override(monkeypatch):
    """
    测试 AUTH_IDLE_TIMEOUT_SECONDS 环境变量覆盖默认值

    Args:
        monkeypatch: pytest monkeypatch fixture

    Returns:
        None
    """
    monkeypatch.setenv("AUTH_IDLE_TIMEOUT_SECONDS", "600")
    cfg = AuthIdleSettings()
    assert cfg.timeout_seconds == 600


def test_auth_idle_settings_timeout_minimum_validation():
    """
    测试 timeout_seconds 必须 >= 60（ge=60 约束）

    Returns:
        None
    """
    with pytest.raises(Exception):  # pydantic ValidationError
        AuthIdleSettings(timeout_seconds=30)


def test_settings_exposes_auth_idle():
    """
    测试总配置 Settings 挂载 auth_idle 子配置

    Returns:
        None
    """
    s = Settings()
    assert hasattr(s, "auth_idle")
    assert s.auth_idle.timeout_seconds == 1800
    assert s.auth_idle.check_enabled is True
    assert s.auth_idle.check_fail_loud is True


def test_auth_idle_settings_module_importable():
    """P0: 类与实例均可访问（导入即存在性验证）。"""
    from app.core.config.settings import AuthIdleSettings, Settings

    # 类可直接 import
    assert AuthIdleSettings is not None
    # Settings 实例挂载小写属性名 auth_idle
    assert hasattr(Settings(), "auth_idle")
