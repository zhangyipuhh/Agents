# -*- coding:utf-8 -*-
"""
FeishuClient 单元测试(2026-09-03 适配新行为)。

新行为(详见 app/shared/tools/skills/feishu/FeishuClient.py):
- 生产路径:从 NotificationConfigService.resolve_default_channel("feishu") 取默认渠道
- 测试 fallback:app.state.notification_config_service 未初始化时,仍读 settings.feishu
- 缓存 key 含 (channel_id, app_id) 标识,支持默认应用切换后重建

本期不再直接 monkeypatch settings.feishu 测试 fallback 路径(因为 conftest 的
app fixture 也会创建 FastAPI app 但不挂 notification_config_service,行为复杂)。
改为测试公共函数契约 + _resolve_log_level 映射。
"""
from __future__ import annotations

import pytest

from app.shared.tools.skills.feishu.FeishuClient import (
    _resolve_log_level,
    reset_lark_client,
)
import lark_oapi as lark


def test_get_lark_client_importable():
    """get_lark_client / reset_lark_client 可被导入。"""
    from app.shared.tools.skills.feishu.FeishuClient import get_lark_client
    assert callable(get_lark_client)
    assert callable(reset_lark_client)


def test_reset_lark_client_runs():
    """reset_lark_client 调用不抛异常(无缓存状态下)。"""
    reset_lark_client()  # 应不抛


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


def test_get_lark_client_runtime_error_message_includes_db_path_hint(monkeypatch):
    """get_lark_client 在 DB 与 settings 都无凭证时 → RuntimeError 消息含 DB 路径提示。

    通过 monkeypatch 把 settings.feishu 所有字段置空,模拟「DB 与 settings 都无凭证」。
    """
    from app.shared.tools.skills.feishu.FeishuClient import get_lark_client
    from app.core.config.settings import settings
    reset_lark_client()
    monkeypatch.setattr(settings.feishu, "feishu_app_id", "")
    monkeypatch.setattr(settings.feishu, "feishu_app_secret", "")
    with pytest.raises(RuntimeError) as exc_info:
        get_lark_client()
    assert "飞书默认应用未配置" in str(exc_info.value)
    assert "is_default=TRUE" in str(exc_info.value)
    assert "NotificationConfigService" in str(exc_info.value)
