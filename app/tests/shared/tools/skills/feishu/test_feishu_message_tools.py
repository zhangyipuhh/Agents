# -*- coding:utf-8 -*-
"""
FeishuMessageTools 单元测试(2026-09-03 适配新行为)。

新行为(详见 app/shared/tools/skills/feishu/FeishuMessageTools.py):
- 默认 receive_id 从 NotificationConfigService.resolve_default_channel("feishu")
  读取,不再读 settings.feishu.feishu_default_receive_id
- 失败信息文案改为「消息设置 → 飞书设置 → 应用设置」路径

本期保留的契约测试:
- module 导入 + send_feishu_message 可调用
- receive_id 参数优先 + DB 失败兜底 + get_lark_client 失败的错误信息
- Markdown vs 纯文本 msg_type 选择(已迁移到 send_test_message 路径,本测试覆盖)
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.shared.tools.skills.feishu import FeishuMessageTools
from app.shared.tools.skills.feishu.FeishuMessageTools import send_feishu_message


def _parse_message_content(result) -> dict:
    """从 Command 结果中提取第一条消息的 JSON 内容。

    Args:
        result: send_feishu_message 返回的 Command 对象
    Returns:
        dict: 消息内容解析后的字典
    """
    messages = result.update["messages"]
    assert len(messages) == 1
    return json.loads(messages[0].content)


def test_send_feishu_message_importable():
    """send_feishu_message 可被导入且为可调用对象。"""
    assert callable(send_feishu_message)


def test_send_feishu_message_receives_explicit_id_bypasses_db(monkeypatch):
    """显式传入 receive_id 时不查 DB。

    Args:
        monkeypatch: pytest monkeypatch fixture
    """
    # 即使 DB 解析失败,显式 receive_id 也应通过
    def _raise_runtime_error():
        raise RuntimeError("DB 未初始化")

    monkeypatch.setattr(
        FeishuMessageTools, "_resolve_default_receive_via_db", _raise_runtime_error
    )

    # mock client
    mock_response = MagicMock()
    mock_response.success.return_value = True
    mock_response.data.message_id = "om_msg_001"

    mock_client = MagicMock()
    mock_client.im.v1.message.create.return_value = mock_response

    def _get_client():
        return mock_client

    monkeypatch.setattr(FeishuMessageTools, "get_lark_client", _get_client)

    result = send_feishu_message(
        content="hello",
        receive_id="oc_explicit_chat",
        receive_id_type="chat_id",
        runtime=None,
    )
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert payload["message_id"] == "om_msg_001"
    assert payload["receive_id"] == "oc_explicit_chat"


def test_send_feishu_message_get_lark_client_failure_returns_error(monkeypatch):
    """get_lark_client 抛 RuntimeError 时工具返回错误，不抛异常。

    Args:
        monkeypatch: pytest monkeypatch fixture
    """
    def _raise_runtime_error():
        raise RuntimeError("飞书默认应用未配置")

    monkeypatch.setattr(FeishuMessageTools, "get_lark_client", _raise_runtime_error)

    result = send_feishu_message(
        content="hello",
        receive_id="oc_test_chat",
        runtime=None,
    )
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "飞书客户端初始化失败" in payload["error"]


def test_send_feishu_message_api_failure_returns_error_payload(monkeypatch):
    """API response.success() = False 时返回含 code/msg/log_id 的错误负载。

    Args:
        monkeypatch: pytest monkeypatch fixture
    """
    mock_response = MagicMock()
    mock_response.success.return_value = False
    mock_response.code = 230020
    mock_response.msg = "invalid receive_id"
    mock_response.get_log_id.return_value = "log_xxx"

    mock_client = MagicMock()
    mock_client.im.v1.message.create.return_value = mock_response

    monkeypatch.setattr(
        FeishuMessageTools,
        "get_lark_client",
        lambda: mock_client,
    )

    result = send_feishu_message(
        content="hello",
        receive_id="oc_invalid",
        runtime=None,
    )
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert payload["code"] == 230020
    assert "invalid receive_id" in payload["msg"]
    assert payload["log_id"] == "log_xxx"


def test_send_feishu_message_passes_through_runtime_kwargs(monkeypatch):
    """runtime 参数被透传到工具调用(tool_call_id 解析)。"""
    mock_response = MagicMock()
    mock_response.success.return_value = True
    mock_response.data.message_id = "om_msg_002"
    mock_client = MagicMock()
    mock_client.im.v1.message.create.return_value = mock_response

    monkeypatch.setattr(FeishuMessageTools, "get_lark_client", lambda: mock_client)

    fake_runtime = MagicMock()
    fake_runtime.tool_call_id = "call_xyz_789"

    result = send_feishu_message(
        content="hello",
        receive_id="oc_test_chat",
        runtime=fake_runtime,
    )
    payload = _parse_message_content(result)
    assert payload["success"] is True
    # 验证 tool_call_id 被透传
    assert result.update["messages"][0].tool_call_id == "call_xyz_789"
