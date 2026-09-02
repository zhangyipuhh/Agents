# -*- coding:utf-8 -*-
"""
RegistrationSecuritySettings 配置测试模块（等保三级 §7.1.3 访问控制，2026-08-30 新增）

验证注册审批 + IP 白名单配置的默认值、JSON list 解析、布尔字符串解析与总配置挂载。
"""
import pytest


def test_registration_security_settings_defaults():
    """
    测试默认配置值（所有字段均为安全默认值）

    Returns:
        None
    """
    from app.core.config.settings import RegistrationSecuritySettings

    cfg = RegistrationSecuritySettings()
    assert cfg.enabled is False
    assert cfg.ip_whitelist == []
    assert cfg.admin_notification_emails == []
    assert cfg.feishu_notify_enabled is False


def test_registration_security_settings_parse_enabled_from_string(monkeypatch):
    """
    测试 REGISTRATION_SECURITY_ENABLED 字符串环境变量解析为布尔值

    Args:
        monkeypatch: pytest monkeypatch fixture

    Returns:
        None
    """
    from app.core.config.settings import RegistrationSecuritySettings

    monkeypatch.setenv("REGISTRATION_SECURITY_ENABLED", "true")
    cfg = RegistrationSecuritySettings()
    assert cfg.enabled is True

    monkeypatch.setenv("REGISTRATION_SECURITY_ENABLED", "false")
    cfg = RegistrationSecuritySettings()
    assert cfg.enabled is False


def test_registration_security_settings_ip_whitelist_json(monkeypatch):
    """
    测试 REGISTRATION_SECURITY_IP_WHITELIST JSON 列表解析

    Args:
        monkeypatch: pytest monkeypatch fixture

    Returns:
        None
    """
    from app.core.config.settings import RegistrationSecuritySettings

    monkeypatch.setenv(
        "REGISTRATION_SECURITY_IP_WHITELIST",
        '["192.168.1.10", "10.0.0.0/8", "172.16.5.5"]',
    )
    cfg = RegistrationSecuritySettings()
    assert cfg.ip_whitelist == [
        "192.168.1.10",
        "10.0.0.0/8",
        "172.16.5.5",
    ]


def test_registration_security_settings_admin_emails_json(monkeypatch):
    """
    测试 REGISTRATION_SECURITY_ADMIN_NOTIFICATION_EMAILS JSON 列表解析

    Args:
        monkeypatch: pytest monkeypatch fixture

    Returns:
        None
    """
    from app.core.config.settings import RegistrationSecuritySettings

    monkeypatch.setenv(
        "REGISTRATION_SECURITY_ADMIN_NOTIFICATION_EMAILS",
        '["[email protected]", "[email protected]"]',
    )
    cfg = RegistrationSecuritySettings()
    assert cfg.admin_notification_emails == [
        "[email protected]",
        "[email protected]",
    ]


def test_registration_security_settings_feishu_enabled(monkeypatch):
    """
    测试 REGISTRATION_SECURITY_FEISHU_NOTIFY_ENABLED 布尔字符串解析

    Args:
        monkeypatch: pytest monkeypatch fixture

    Returns:
        None
    """
    from app.core.config.settings import RegistrationSecuritySettings

    monkeypatch.setenv("REGISTRATION_SECURITY_FEISHU_NOTIFY_ENABLED", "1")
    cfg = RegistrationSecuritySettings()
    assert cfg.feishu_notify_enabled is True

    monkeypatch.setenv("REGISTRATION_SECURITY_FEISHU_NOTIFY_ENABLED", "0")
    cfg = RegistrationSecuritySettings()
    assert cfg.feishu_notify_enabled is False


def test_settings_exposes_registration_security():
    """
    测试总配置 Settings 挂载 registration_security 子配置

    Returns:
        None
    """
    from app.core.config.settings import Settings

    s = Settings()
    assert hasattr(s, "registration_security")
    assert s.registration_security.enabled is False
    assert s.registration_security.ip_whitelist == []
    assert s.registration_security.admin_notification_emails == []
    assert s.registration_security.feishu_notify_enabled is False


def test_registration_security_settings_module_importable():
    """P0: 类与实例均可访问（导入即存在性验证）。"""
    from app.core.config.settings import RegistrationSecuritySettings, Settings

    # 类可直接 import
    assert RegistrationSecuritySettings is not None
    # Settings 实例挂载小写属性名 registration_security
    assert hasattr(Settings(), "registration_security")
