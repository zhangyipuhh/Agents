# -*- coding:utf-8 -*-
"""
FeishuMessageTools 单元测试

覆盖目标：
    - send_feishu_message 可正确导入
    - receive_id 缺失时返回错误 ToolMessage（不抛异常）
    - get_lark_client 抛 RuntimeError 时工具返回错误负载
    - API 成功时工具返回 success=True + message_id
    - API 失败（response.success()=False）时工具返回错误负载含 code/msg/log_id

测试策略：
    - conftest 把 @tool mock 成 identity 装饰器，因此直接调用底层函数
    - 通过 monkeypatch 修改 settings.feishu 字段（receive_id 默认值）
    - 通过 monkeypatch 替换 FeishuMessageTools.get_lark_client 为返回 mock client 的 stub
    - 不真实调用飞书 API
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.core.config.settings import settings
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


def test_send_feishu_message_missing_receive_id(monkeypatch):
    """receive_id 缺失（参数与默认值都为空）时返回错误 ToolMessage。

    Args:
        monkeypatch: pytest monkeypatch fixture
    """
    monkeypatch.setattr(settings.feishu, "feishu_default_receive_id", "")

    result = send_feishu_message(content="你好", runtime=None)
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "receive_id 缺失" in payload["error"]


def test_send_feishu_message_client_init_failure(monkeypatch):
    """get_lark_client 抛 RuntimeError 时工具返回错误，不抛异常。

    Args:
        monkeypatch: pytest monkeypatch fixture
    """
    monkeypatch.setattr(settings.feishu, "feishu_default_receive_id", "oc_test_chat")

    def _raise_runtime_error():
        raise RuntimeError("飞书应用凭证未配置")

    monkeypatch.setattr(FeishuMessageTools, "get_lark_client", _raise_runtime_error)

    result = send_feishu_message(content="你好", runtime=None)
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "飞书客户端初始化失败" in payload["error"]


def test_send_feishu_message_success(monkeypatch):
    """API 成功时返回 success=True + message_id。

    Args:
        monkeypatch: pytest monkeypatch fixture
    """
    monkeypatch.setattr(settings.feishu, "feishu_default_receive_id", "oc_test_chat")

    # 构造 mock response
    mock_response = MagicMock()
    mock_response.success.return_value = True
    mock_response.data.message_id = "om_test_message_id"

    # 构造 mock client
    mock_client = MagicMock()
    mock_client.im.v1.message.create.return_value = mock_response

    monkeypatch.setattr(FeishuMessageTools, "get_lark_client", lambda: mock_client)

    result = send_feishu_message(content="你好飞书", runtime=None)
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert payload["message_id"] == "om_test_message_id"
    assert payload["receive_id"] == "oc_test_chat"
    assert payload["receive_id_type"] == "chat_id"
    assert payload["content"] == "你好飞书"


def test_send_feishu_message_api_failure(monkeypatch):
    """response.success()=False 时返回错误负载含 code/msg/log_id。

    Args:
        monkeypatch: pytest monkeypatch fixture
    """
    monkeypatch.setattr(settings.feishu, "feishu_default_receive_id", "oc_test_chat")

    mock_response = MagicMock()
    mock_response.success.return_value = False
    mock_response.code = 230002
    mock_response.msg = "invalid receive_id"
    mock_response.get_log_id.return_value = "log_test_123"

    mock_client = MagicMock()
    mock_client.im.v1.message.create.return_value = mock_response

    monkeypatch.setattr(FeishuMessageTools, "get_lark_client", lambda: mock_client)

    result = send_feishu_message(content="测试", runtime=None)
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert payload["code"] == 230002
    assert payload["msg"] == "invalid receive_id"
    assert payload["log_id"] == "log_test_123"


def test_send_feishu_message_create_exception(monkeypatch):
    """client.im.v1.message.create 抛异常时工具返回通用错误，不抛异常。

    Args:
        monkeypatch: pytest monkeypatch fixture
    """
    monkeypatch.setattr(settings.feishu, "feishu_default_receive_id", "oc_test_chat")

    mock_client = MagicMock()
    mock_client.im.v1.message.create.side_effect = ConnectionError("network down")

    monkeypatch.setattr(FeishuMessageTools, "get_lark_client", lambda: mock_client)

    result = send_feishu_message(content="测试", runtime=None)
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "飞书消息发送失败" in payload["error"]


def test_send_feishu_message_explicit_receive_id_overrides_default(monkeypatch):
    """显式传入 receive_id 优先于默认配置。

    Args:
        monkeypatch: pytest monkeypatch fixture
    """
    monkeypatch.setattr(settings.feishu, "feishu_default_receive_id", "oc_default_chat")

    mock_response = MagicMock()
    mock_response.success.return_value = True
    mock_response.data.message_id = "om_explicit"

    mock_client = MagicMock()
    mock_client.im.v1.message.create.return_value = mock_response

    monkeypatch.setattr(FeishuMessageTools, "get_lark_client", lambda: mock_client)

    result = send_feishu_message(
        content="测试",
        receive_id="oc_explicit_chat",
        receive_id_type="open_id",
        runtime=None,
    )
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert payload["receive_id"] == "oc_explicit_chat"
    assert payload["receive_id_type"] == "open_id"
