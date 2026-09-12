# -*- coding:utf-8 -*-
"""CORSSettings 测试（2026-09-12 渗透整改：CORS 默认拒绝 + 白名单可配）。"""


def test_cors_settings_importable():
    """CORSSettings 可导入且 Settings 含 cors 字段。"""
    from app.core.config.settings import CORSSettings, Settings
    assert CORSSettings is not None
    assert "cors" in Settings.model_fields


def test_default_allowed_origins_empty_denies_all():
    """默认空白名单 = 跨域全拒（同源请求不受 CORS 约束）。"""
    from app.core.config.settings import CORSSettings
    cfg = CORSSettings()
    assert cfg.allowed_origins == []
    assert cfg.allow_credentials is True


def test_allowed_origins_parses_comma_separated():
    """逗号分隔字符串解析为 origin 列表。"""
    from app.core.config.settings import CORSSettings
    cfg = CORSSettings(allowed_origins="https://a.example.com, https://b.example.com")
    assert cfg.allowed_origins == ["https://a.example.com", "https://b.example.com"]


def test_allowed_origins_parses_json_list():
    """JSON list 字符串解析。"""
    from app.core.config.settings import CORSSettings
    cfg = CORSSettings(allowed_origins='["https://a.example.com"]')
    assert cfg.allowed_origins == ["https://a.example.com"]


def test_allowed_origins_blank_string_yields_empty():
    """空白字符串解析为空列表（保持默认拒绝）。"""
    from app.core.config.settings import CORSSettings
    assert CORSSettings(allowed_origins="").allowed_origins == []
    assert CORSSettings(allowed_origins="   ").allowed_origins == []


def test_allow_credentials_parses_string_bool():
    """字符串布尔解析（与项目其他 Settings.parse_bool 风格一致）。"""
    from app.core.config.settings import CORSSettings
    assert CORSSettings(allow_credentials="false").allow_credentials is False
    assert CORSSettings(allow_credentials="true").allow_credentials is True
