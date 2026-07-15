# -*- coding:utf-8 -*-
"""
FeishuClient 单元测试

覆盖目标：
    - get_lark_client / reset_lark_client / _resolve_log_level 可正确导入
    - 凭证缺失时 get_lark_client 抛 RuntimeError
    - 二次调用返回同一缓存实例（单例语义）
    - reset_lark_client 清空缓存后重新构造
    - _resolve_log_level 字符串到 lark.LogLevel 的映射

测试策略：
    - 通过 monkeypatch 直接修改 settings.feishu 字段（生产中 settings 是真实单例）
    - 每个用例前后调用 reset_lark_client() 确保缓存干净
    - 不 mock lark_oapi 本身，让 lark.Client.builder() 真实执行（仅构造对象，不发网络请求）
"""
from __future__ import annotations

import pytest

from app.core.config.settings import settings
from app.shared.tools.skills.feishu.FeishuClient import (
    _resolve_log_level,
    get_lark_client,
    reset_lark_client,
)
import lark_oapi as lark


@pytest.fixture(autouse=True)
def _reset_client():
    """每个用例前后清空 client 缓存，避免用例间互相污染。

    生产中 client 单例由模块级 ``_client_instance`` 维护，
    此处对应 ``reset_lark_client`` 公共函数。
    """
    reset_lark_client()
    yield
    reset_lark_client()


def test_get_lark_client_importable():
    """get_lark_client / reset_lark_client 可被导入。"""
    assert callable(get_lark_client)
    assert callable(reset_lark_client)


def test_get_lark_client_raises_when_no_credentials(monkeypatch):
    """凭证缺失时抛 RuntimeError。

    Args:
        monkeypatch: pytest monkeypatch fixture
    """
    monkeypatch.setattr(settings.feishu, "feishu_app_id", "")
    monkeypatch.setattr(settings.feishu, "feishu_app_secret", "")
    with pytest.raises(RuntimeError, match="飞书应用凭证未配置"):
        get_lark_client()


def test_get_lark_client_raises_when_only_app_id(monkeypatch):
    """仅 app_id 配置、app_secret 缺失时抛 RuntimeError。

    Args:
        monkeypatch: pytest monkeypatch fixture
    """
    monkeypatch.setattr(settings.feishu, "feishu_app_id", "cli_test")
    monkeypatch.setattr(settings.feishu, "feishu_app_secret", "")
    with pytest.raises(RuntimeError, match="飞书应用凭证未配置"):
        get_lark_client()


def test_get_lark_client_returns_cached_instance(monkeypatch):
    """二次调用返回同一实例（单例语义）。

    Args:
        monkeypatch: pytest monkeypatch fixture
    """
    monkeypatch.setattr(settings.feishu, "feishu_app_id", "cli_test")
    monkeypatch.setattr(settings.feishu, "feishu_app_secret", "secret_test")
    monkeypatch.setattr(settings.feishu, "feishu_log_level", "DEBUG")

    first = get_lark_client()
    second = get_lark_client()
    assert first is second


def test_reset_lark_client_clears_cache(monkeypatch):
    """reset 后再次调用构造新实例。

    Args:
        monkeypatch: pytest monkeypatch fixture
    """
    monkeypatch.setattr(settings.feishu, "feishu_app_id", "cli_test")
    monkeypatch.setattr(settings.feishu, "feishu_app_secret", "secret_test")

    first = get_lark_client()
    reset_lark_client()
    second = get_lark_client()
    assert first is not second


def test_resolve_log_level_debug():
    """DEBUG 映射到 lark.LogLevel.DEBUG。"""
    assert _resolve_log_level("DEBUG") == lark.LogLevel.DEBUG


def test_resolve_log_level_info_default():
    """INFO 与未识别值都映射到 lark.LogLevel.INFO。"""
    assert _resolve_log_level("INFO") == lark.LogLevel.INFO
    assert _resolve_log_level("UNKNOWN") == lark.LogLevel.INFO
    assert _resolve_log_level("") == lark.LogLevel.INFO
    assert _resolve_log_level(None) == lark.LogLevel.INFO  # type: ignore[arg-type]


def test_resolve_log_level_warning_error():
    """WARNING / ERROR 正确映射。"""
    assert _resolve_log_level("WARNING") == lark.LogLevel.WARNING
    assert _resolve_log_level("ERROR") == lark.LogLevel.ERROR


def test_resolve_log_level_case_insensitive():
    """日志级别字符串大小写不敏感。"""
    assert _resolve_log_level("debug") == lark.LogLevel.DEBUG
    assert _resolve_log_level("Info") == lark.LogLevel.INFO
