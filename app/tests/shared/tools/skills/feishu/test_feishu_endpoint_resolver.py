# -*- coding:utf-8 -*-
"""
FeishuEndpointResolver 单元测试（2026-09-11 新增）。

覆盖契约：
- Endpoint dataclass 字段完整性
- resolve_current_endpoint 从 runtime.state.agent_name 解析
- agent_name 缺失 / DB 返回 None / 同步桥接失败兜底
- build_lark_client 用明文凭证构造 lark.Client

依赖 conftest.py 已 mock lark_oapi SDK（Client.builder / LogLevel 等）。
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from app.shared.tools.skills.feishu.FeishuEndpointResolver import (
    Endpoint,
    ERROR_DB_UNAVAILABLE,
    ERROR_NO_AGENT_NAME,
    ERROR_NO_CHANNEL,
    ERROR_NO_TARGET,
    build_lark_client,
    resolve_current_endpoint,
)


# -----------------------------------------------------------------------------
# helpers
# -----------------------------------------------------------------------------

def _make_runtime(agent_name):
    """构造带 state.agent_name 的假 runtime（LangChain ToolRuntime）。"""
    rt = MagicMock()
    rt.state = {"agent_name": agent_name} if agent_name is not None else {}
    rt.tool_call_id = "call_test"
    return rt


def _make_endpoint_dict(**overrides):
    """构造 resolve_agent_feishu_endpoint 返回的完整 dict。"""
    d = {
        "channel_id": 11, "channel_name": "feishu_proj",
        "app_id": "a", "app_secret": "s", "log_level": "INFO",
        "target_id": 21, "target_name": "项目群",
        "chat_id": "oc_proj", "chat_type": "chat_id",
        "agent_name": "project",
    }
    d.update(overrides)
    return d


# -----------------------------------------------------------------------------
# P0: Endpoint dataclass 契约
# -----------------------------------------------------------------------------


def test_endpoint_dataclass_fields():
    """Endpoint dataclass 必须含全部 9 个字段，frozen 不允许修改。"""
    ep = Endpoint(
        channel_id=1, channel_name="ch", app_id="a", app_secret="s",
        log_level="INFO", target_id=2, target_name="t",
        chat_id="oc_x", chat_type="chat_id", agent_name="project",
    )
    assert ep.channel_id == 1
    assert ep.channel_name == "ch"
    assert ep.app_id == "a"
    assert ep.app_secret == "s"
    assert ep.log_level == "INFO"
    assert ep.target_id == 2
    assert ep.target_name == "t"
    assert ep.chat_id == "oc_x"
    assert ep.chat_type == "chat_id"
    assert ep.agent_name == "project"

    # frozen 字段修改应抛异常
    with pytest.raises(Exception):  # FrozenInstanceError
        ep.channel_id = 999  # noqa


# -----------------------------------------------------------------------------
# P1: resolve_current_endpoint happy path
# -----------------------------------------------------------------------------


def test_resolve_returns_endpoint_on_happy_path(monkeypatch):
    """runtime.state.agent_name 有效 + service 返回完整 dict → Endpoint。"""
    from app.shared.tools.skills.feishu import FeishuEndpointResolver as FER

    fake_svc = MagicMock()

    async def _fake_resolve(_agent_name):
        return _make_endpoint_dict()
    fake_svc.resolve_agent_feishu_endpoint = _fake_resolve

    monkeypatch.setattr(FER, "_get_notification_service", lambda: fake_svc)

    ep = asyncio.run(resolve_current_endpoint(_make_runtime("project")))

    assert ep is not None
    assert isinstance(ep, Endpoint)
    assert ep.chat_id == "oc_proj"
    assert ep.chat_type == "chat_id"
    assert ep.agent_name == "project"
    assert ep.app_id == "a"
    assert ep.app_secret == "s"


# 新增：async 契约断言
def test_resolve_current_endpoint_is_coroutine_function():
    """resolve_current_endpoint 必须是 async（生产由 ToolNode await 调用）。"""
    import inspect
    assert inspect.iscoroutinefunction(resolve_current_endpoint)


# -----------------------------------------------------------------------------
# P1: resolve_current_endpoint 失败路径
# -----------------------------------------------------------------------------


def test_resolve_returns_none_when_agent_name_missing():
    """runtime.state.agent_name 缺失 → 返回 None。"""
    ep = asyncio.run(resolve_current_endpoint(_make_runtime(None)))
    assert ep is None


def test_resolve_returns_none_when_state_empty():
    """runtime.state 不含 agent_name → 返回 None。"""
    ep = asyncio.run(resolve_current_endpoint(_make_runtime("")))
    assert ep is None


def test_resolve_returns_none_when_runtime_none():
    """runtime=None → 返回 None。"""
    ep = asyncio.run(resolve_current_endpoint(None))
    assert ep is None


def test_resolve_returns_none_when_service_unavailable(monkeypatch, caplog):
    """notification_config_service 未初始化 → 返回 None + WARNING 日志。"""
    import logging
    from app.shared.tools.skills.feishu import FeishuEndpointResolver as FER
    monkeypatch.setattr(FER, "_get_notification_service", lambda: None)

    with caplog.at_level(logging.WARNING):
        ep = asyncio.run(resolve_current_endpoint(_make_runtime("project")))

    assert ep is None
    assert "未初始化" in caplog.text


def test_resolve_returns_none_when_db_returns_none(monkeypatch):
    """service 返回 None（channel 或 target 缺失）→ 返回 None。"""
    from app.shared.tools.skills.feishu import FeishuEndpointResolver as FER

    fake_svc = MagicMock()

    async def _fake_resolve(_agent_name):
        return None
    fake_svc.resolve_agent_feishu_endpoint = _fake_resolve

    monkeypatch.setattr(FER, "_get_notification_service", lambda: fake_svc)

    ep = asyncio.run(resolve_current_endpoint(_make_runtime("ghost")))

    assert ep is None


def test_resolve_returns_none_and_logs_when_service_raises(monkeypatch, caplog):
    """service.resolve_agent_feishu_endpoint 抛异常 → 返回 None + WARNING 日志（fail-loud，不向上抛）。"""
    import logging
    from app.shared.tools.skills.feishu import FeishuEndpointResolver as FER

    fake_svc = MagicMock()

    async def _boom(_agent_name):
        raise RuntimeError("db boom")
    fake_svc.resolve_agent_feishu_endpoint = _boom

    monkeypatch.setattr(FER, "_get_notification_service", lambda: fake_svc)

    with caplog.at_level(logging.WARNING):
        ep = asyncio.run(resolve_current_endpoint(_make_runtime("project")))

    assert ep is None
    assert "resolve_agent_feishu_endpoint 失败" in caplog.text


def test_resolve_returns_none_when_service_returns_partial_dict(monkeypatch, caplog):
    """service 返回 dict 但缺关键字段（KeyError）→ 返回 None + WARNING 日志。"""
    import logging
    from app.shared.tools.skills.feishu import FeishuEndpointResolver as FER

    fake_svc = MagicMock()

    async def _fake_resolve(_agent_name):
        return {"channel_id": 1, "channel_name": "x"}  # 缺很多字段
    fake_svc.resolve_agent_feishu_endpoint = _fake_resolve

    monkeypatch.setattr(FER, "_get_notification_service", lambda: fake_svc)

    with caplog.at_level(logging.WARNING):
        ep = asyncio.run(resolve_current_endpoint(_make_runtime("project")))

    assert ep is None
    assert "字段缺失" in caplog.text


# -----------------------------------------------------------------------------
# P1: build_lark_client
# -----------------------------------------------------------------------------


def test_build_lark_client_uses_plain_credentials():
    """build_lark_client 用 Endpoint 明文凭证构造 lark.Client。

    conftest 已 mock lark_oapi.Client.builder() 链式调用，验证构造的 client
    上 _app_id/_app_secret 是否等于端点的明文凭证。
    """
    ep = Endpoint(
        channel_id=1, channel_name="ch", app_id="plain_id_xxx",
        app_secret="plain_secret_yyy", log_level="DEBUG",
        target_id=2, target_name="t", chat_id="oc_x",
        chat_type="chat_id", agent_name="project",
    )
    client = build_lark_client(ep)
    assert client is not None
    assert client._app_id == "plain_id_xxx"
    assert client._app_secret == "plain_secret_yyy"
    assert client._log_level == 10  # DEBUG = 10 (conftest 模拟值)


def test_build_lark_client_defaults_log_level_to_info():
    """Endpoint.log_level 为空 → 默认 INFO（=20）。"""
    ep = Endpoint(
        channel_id=1, channel_name="ch", app_id="a", app_secret="s",
        log_level="",  # 空字符串
        target_id=2, target_name="t", chat_id="oc_x",
        chat_type="chat_id", agent_name="project",
    )
    client = build_lark_client(ep)
    assert client._log_level == 20  # INFO = 20


def test_build_lark_client_uppercase_log_level():
    """Endpoint.log_level 大小写不敏感。"""
    ep = Endpoint(
        channel_id=1, channel_name="ch", app_id="a", app_secret="s",
        log_level="warning",  # 小写
        target_id=2, target_name="t", chat_id="oc_x",
        chat_type="chat_id", agent_name="project",
    )
    client = build_lark_client(ep)
    assert client._log_level == 30  # WARNING = 30


# -----------------------------------------------------------------------------
# P1: 错误文案常量契约
# -----------------------------------------------------------------------------


def test_error_constants_exist():
    """4 个统一错误文案常量存在且含中文路径提示。"""
    assert "智能体" in ERROR_NO_AGENT_NAME or "未识别" in ERROR_NO_AGENT_NAME
    assert "应用设置" in ERROR_NO_CHANNEL
    assert "发送策略" in ERROR_NO_TARGET
    assert "通知配置服务" in ERROR_DB_UNAVAILABLE


def test_error_constants_have_format_placeholders():
    """ERROR_NO_CHANNEL / ERROR_NO_TARGET 含 .format 占位符供调用方填充。"""
    # ERROR_NO_CHANNEL 应含 {agent_name}
    assert "{agent_name" in ERROR_NO_CHANNEL
    # ERROR_NO_TARGET 应含 {channel_name}
    assert "{channel_name" in ERROR_NO_TARGET


def test_error_no_channel_format_renders():
    """ERROR_NO_CHANNEL.format(agent_name="project") 替换占位符成功。"""
    msg = ERROR_NO_CHANNEL.format(agent_name="project")
    assert "'project'" in msg
    assert "应用设置" in msg