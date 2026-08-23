# -*- coding:utf-8 -*-
"""
FeishuMessageTools 单元测试

覆盖目标：
    - send_feishu_message 可正确导入
    - receive_id 缺失时返回错误 ToolMessage（不抛异常）
    - get_lark_client 抛 RuntimeError 时工具返回错误负载
    - API 成功时工具返回 success=True + message_id
    - API 失败（response.success()=False）时工具返回错误负载含 code/msg/log_id
    - Markdown 内容走 msg_type=interactive（飞书交互式卡片），纯文本仍走 msg_type=text

测试策略：
    - conftest 把 @tool mock 成 identity 装饰器，因此直接调用底层函数
    - 通过 monkeypatch 修改 settings.feishu 字段（receive_id 默认值）
    - 通过 monkeypatch 替换 FeishuMessageTools.get_lark_client 为返回 mock client 的 stub
    - 不真实调用飞书 API
    - 新增的 markdown 卡片用例在测试内部 monkeypatch
      ``lark_oapi.api.im.v1.CreateMessageRequestBody`` 为可记录 builder，
      以便捕获 ``msg_type`` 与 ``content`` JSON 进入断言；切测试结束后
      monkeypatch 自行还原，不污染 conftest 的全局 mock。
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


# ---------------------------------------------------------------------------
# Markdown 卡片渲染相关用例（2026-08-23 新增）
# ---------------------------------------------------------------------------


class _RecordingMessageBodyBuilder:
    """测试用可记录的 ``CreateMessageRequestBody.builder()``。

    conftest 中默认的 builder 是「set 即忘」，不利于断言入参；本类保留每个
    setter 的输入并在 ``build()`` 时聚合到一个携带字段的实例上，方便测试
    从 ``mock_client.im.v1.message.create.call_args`` 里反查 ``msg_type``
    与 ``content``。
    """

    def __init__(self) -> None:
        self.received = {
            "receive_id": None,
            "msg_type": None,
            "content": None,
            "uuid": None,
        }

    def receive_id(self, value: str) -> "_RecordingMessageBodyBuilder":
        self.received["receive_id"] = value
        return self

    def msg_type(self, value: str) -> "_RecordingMessageBodyBuilder":
        self.received["msg_type"] = value
        return self

    def content(self, value: str) -> "_RecordingMessageBodyBuilder":
        self.received["content"] = value
        return self

    def uuid(self, value: str) -> "_RecordingMessageBodyBuilder":
        self.received["uuid"] = value
        return self

    def build(self):
        """返回携带聚合字段的 MagicMock，便于测试访问 ``_msg_type/_content``。"""
        m = MagicMock(name="CreateMessageRequestBody")
        for key, value in self.received.items():
            setattr(m, f"_{key}", value)
        return m


def _patch_recording_request_body_builder(monkeypatch) -> _RecordingMessageBodyBuilder:
    """monkeypatch 替换 ``CreateMessageRequestBody`` 为可记录 builder。

    Args:
        monkeypatch: pytest monkeypatch fixture

    Returns:
        _RecordingMessageBodyBuilder: 已注册到 ``lark_oapi.api.im.v1`` 的可记录 builder
    """
    import lark_oapi.api.im.v1 as _lark_im_v1

    recorder = _RecordingMessageBodyBuilder()

    class _RecordingBodyCls:
        @staticmethod
        def builder() -> _RecordingMessageBodyBuilder:
            return recorder

    monkeypatch.setattr(_lark_im_v1, "CreateMessageRequestBody", _RecordingBodyCls)
    return recorder


def test_send_feishu_message_renders_markdown_as_card(monkeypatch):
    """Markdown 内容走交互式卡片（``msg_type='interactive'``），content 是 schema 2.0 卡片 JSON。

    Args:
        monkeypatch: pytest monkeypatch fixture
    """
    monkeypatch.setattr(settings.feishu, "feishu_default_receive_id", "oc_card_chat")

    mock_response = MagicMock()
    mock_response.success.return_value = True
    mock_response.data.message_id = "om_card_msg"

    mock_client = MagicMock()
    mock_client.im.v1.message.create.return_value = mock_response
    monkeypatch.setattr(FeishuMessageTools, "get_lark_client", lambda: mock_client)

    recorder = _patch_recording_request_body_builder(monkeypatch)

    content = (
        "# 标题\n"
        "## 子标题\n"
        "- 列表项 A\n"
        "- 列表项 B\n"
        "**加粗文本**\n"
        "```python\nprint('hi')\n```\n"
    )
    result = send_feishu_message(content=content, runtime=None)
    payload = _parse_message_content(result)
    assert payload["success"] is True

    # mock_client.im.v1.message.create 应被调用一次
    create_mock = mock_client.im.v1.message.create
    assert create_mock.call_count == 1

    # 通过 monkeypatch 注入的可记录 builder 捕获到 msg_type=interactive 与卡片 content
    assert recorder.received["msg_type"] == "interactive"
    assert recorder.received["receive_id"] == "oc_card_chat"
    assert recorder.received["content"]
    assert "标题" in recorder.received["content"]
    # content 是合法 schema 2.0 卡片 JSON
    card = json.loads(recorder.received["content"])
    assert card["schema"] == "2.0"
    assert card["header"]["title"]["content"] == "🤖 AI 智能体回复"
    tags = [el.get("tag") for el in card["body"]["elements"]]
    assert "markdown" in tags
    assert "code_block" in tags


def test_send_feishu_message_pure_text_keeps_text_type(monkeypatch):
    """纯文本内容保持 ``msg_type='text'``、content 为 ``{"text": ...}``。

    Args:
        monkeypatch: pytest monkeypatch fixture
    """
    monkeypatch.setattr(settings.feishu, "feishu_default_receive_id", "oc_text_chat")

    mock_response = MagicMock()
    mock_response.success.return_value = True
    mock_response.data.message_id = "om_text_msg"

    mock_client = MagicMock()
    mock_client.im.v1.message.create.return_value = mock_response
    monkeypatch.setattr(FeishuMessageTools, "get_lark_client", lambda: mock_client)

    recorder = _patch_recording_request_body_builder(monkeypatch)

    result = send_feishu_message(content="你好，这是一条普通文本", runtime=None)
    payload = _parse_message_content(result)
    assert payload["success"] is True

    create_mock = mock_client.im.v1.message.create
    assert create_mock.call_count == 1
    assert recorder.received["msg_type"] == "text"
    text_payload = json.loads(recorder.received["content"])
    assert text_payload == {"text": "你好，这是一条普通文本"}


def test_send_feishu_message_card_json_contains_md_elements(monkeypatch):
    """卡片 JSON 必须包含 markdown / code_block elements，飞书侧才能正确渲染。

    Args:
        monkeypatch: pytest monkeypatch fixture
    """
    monkeypatch.setattr(settings.feishu, "feishu_default_receive_id", "oc_md_chat")

    mock_response = MagicMock()
    mock_response.success.return_value = True
    mock_response.data.message_id = "om_md_msg"

    mock_client = MagicMock()
    mock_client.im.v1.message.create.return_value = mock_response
    monkeypatch.setattr(FeishuMessageTools, "get_lark_client", lambda: mock_client)

    recorder = _patch_recording_request_body_builder(monkeypatch)

    content = (
        "- 任务一\n"
        "- 任务二\n"
        "```bash\necho hello\n```\n"
        "普通段落含 **加粗** 和 `inline code`。"
    )
    result = send_feishu_message(content=content, runtime=None)
    payload = _parse_message_content(result)
    assert payload["success"] is True

    create_mock = mock_client.im.v1.message.create
    assert create_mock.call_count == 1
    assert recorder.received["msg_type"] == "interactive"
    card = json.loads(recorder.received["content"])
    elements = card["body"]["elements"]
    tags = {el.get("tag") for el in elements if isinstance(el, dict)}
    assert "markdown" in tags
    assert "code_block" in tags
    # 显式列表项至少出现两条独立 markdown 元素
    markdown_elements = [el for el in elements if el.get("tag") == "markdown"]
    bullet_count = sum(
        1 for el in markdown_elements
        if el.get("content", "").startswith("- ")
    )
    assert bullet_count >= 2
    # code_block language 字段正确填充
    code_blocks = [el for el in elements if el.get("tag") == "code_block"]
    assert code_blocks and code_blocks[0].get("language") == "bash"
