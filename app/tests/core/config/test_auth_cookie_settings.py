# -*- coding:utf-8 -*-
"""
AuthCookieSettings 配置测试模块

验证认证 Cookie 配置项的默认值、环境变量解析与总配置挂载。
"""
from app.core.config.settings import AuthCookieSettings, Settings


def test_auth_cookie_settings_defaults():
    """
    测试默认配置值

    Returns:
        None
    """
    cfg = AuthCookieSettings()
    assert cfg.secure is False
    assert cfg.samesite == "strict"
    assert cfg.access_token_name == "access_token"
    assert cfg.access_token_path == "/api"
    assert cfg.access_token_max_age_seconds == 1800


def test_auth_cookie_settings_parse_secure_from_string(monkeypatch):
    """
    测试 AUTH_COOKIE_SECURE 字符串环境变量解析为布尔值

    Args:
        monkeypatch: pytest monkeypatch fixture

    Returns:
        None
    """
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")
    cfg = AuthCookieSettings()
    assert cfg.secure is True


def test_settings_exposes_auth_cookie():
    """
    测试总配置 Settings 挂载 auth_cookie 子配置

    Returns:
        None
    """
    s = Settings()
    assert hasattr(s, "auth_cookie")
    assert s.auth_cookie.access_token_name == "access_token"
