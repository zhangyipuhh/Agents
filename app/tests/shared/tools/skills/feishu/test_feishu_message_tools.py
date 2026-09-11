# -*- coding:utf-8 -*-
"""
FeishuMessageTools 单元测试（2026-09-11 重构：按 agent 路由）。

新行为：
- send_feishu_message 签名删除 receive_id / receive_id_type 参数
- 仅保留 content + runtime 两个参数
- 内部走 FeishuEndpointResolver 按 runtime.state.agent_name 解析 endpoint
- 各失败路径返回带「应用设置 / 发送策略」指引的 ToolMessage
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from app.shared.tools.skills.feishu import FeishuMessageTools
from app.shared.tools.skills.feishu.FeishuEndpointResolver import Endpoint
from app.shared.tools.skills.feishu.FeishuMessageTools import send_feishu_message


def _parse_message_content(result) -> dict:
    """从 Command 结果中提取第一条消息的 JSON 内容。"""
    messages = result.update["messages"]
    assert len(messages) == 1
    return json.loads(messages[0].content)


def _make_runtime(agent_name=None, tool_call_id="call_x"):
    """构造带 state.agent_name 的假 runtime。"""
    rt = MagicMock()
    rt.tool_call_id = tool_call_id
    rt.state = {"agent_name": agent_name} if agent_name else {}
    return rt


def _make_endpoint(chat_id="oc_proj", chat_type="chat_id", channel_name="feishu_proj"):
    return Endpoint(
        channel_id=11, channel_name=channel_name,
        app_id="a", app_secret="s", log_level="INFO",
        target_id=21, target_name="项目群",
        chat_id=chat_id, chat_type=chat_type,
        agent_name="project",
    )


def test_send_feishu_message_importable():
    """send_feishu_message 可被导入且为可调用对象。"""
    assert callable(send_feishu_message)


def test_send_feishu_message_signature_no_receive_id():
    """工具签名不再含 receive_id / receive_id_type 参数。

    注意：项目顶层 conftest 把 ``@tool`` 装饰器替换为 identity decorator，
    所以测试环境下 ``send_feishu_message`` 是普通 function；
    生产环境下是 StructuredTool，其原函数通过 .func 访问。
    用 ``inspect.signature`` 兼容两种环境。
    """
    import inspect
    target = getattr(send_feishu_message, "func", send_feishu_message)
    sig = inspect.signature(target)
    params = list(sig.parameters.keys())
    assert "receive_id" not in params
    assert "receive_id_type" not in params
    assert "content" in params
    assert "runtime" in params


def test_send_feishu_message_runtime_none_returns_error():
    """runtime=None → 返回「未识别当前智能体」错误。"""
    result = asyncio.run(send_feishu_message(content="hi", runtime=None))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "未识别当前智能体" in payload["error"]


def test_send_feishu_message_missing_agent_name_returns_error():
    """runtime.state.agent_name 缺失 → 返回「未识别当前智能体」错误。"""
    result = asyncio.run(send_feishu_message(content="hello", runtime=_make_runtime(None)))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "未识别当前智能体" in payload["error"]


def test_send_feishu_message_no_endpoint_returns_config_hint(monkeypatch):
    """Resolver 返回 None → 返回「飞书设置」指引错误。"""
    async def _fake_resolve_none(rt):
        return None
    monkeypatch.setattr(
        FeishuMessageTools, "resolve_current_endpoint", _fake_resolve_none
    )
    result = asyncio.run(send_feishu_message(content="hello", runtime=_make_runtime("ghost")))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "飞书设置" in payload["error"]
    assert "应用设置" in payload["error"]
    assert "发送策略" in payload["error"]


def test_send_feishu_message_happy_path_text(monkeypatch):
    """endpoint 解析成功 + 纯文本 → 走 msg_type=text 发送成功。"""
    mock_response = MagicMock()
    mock_response.success.return_value = True
    mock_response.data.message_id = "om_msg_001"
    mock_client = MagicMock()
    mock_client.im.v1.message.create.return_value = mock_response

    async def _fake_resolve(rt):
        return _make_endpoint("oc_proj")
    monkeypatch.setattr(
        FeishuMessageTools, "resolve_current_endpoint",
        _fake_resolve,
    )
    monkeypatch.setattr(
        FeishuMessageTools, "build_lark_client", lambda ep: mock_client
    )

    result = asyncio.run(send_feishu_message(content="hello", runtime=_make_runtime("project")))
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert payload["message_id"] == "om_msg_001"
    assert payload["chat_id"] == "oc_proj"
    assert payload["agent_name"] == "project"


def test_send_feishu_message_happy_path_markdown_card(monkeypatch):
    """Markdown 内容 → msg_type=interactive + schema 2.0 卡片发送成功。"""
    mock_response = MagicMock()
    mock_response.success.return_value = True
    mock_response.data.message_id = "om_msg_md"
    mock_client = MagicMock()
    mock_client.im.v1.message.create.return_value = mock_response

    async def _fake_resolve(rt):
        return _make_endpoint()
    monkeypatch.setattr(
        FeishuMessageTools, "resolve_current_endpoint",
        _fake_resolve,
    )
    monkeypatch.setattr(
        FeishuMessageTools, "build_lark_client", lambda ep: mock_client
    )

    result = asyncio.run(send_feishu_message(
        content="# 标题\n**粗体内容**", runtime=_make_runtime("project")
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is True


def test_send_feishu_message_api_failure_returns_error_payload(monkeypatch):
    """API response.success()=False → 返回含 code/msg/log_id 的错误负载。"""
    mock_response = MagicMock()
    mock_response.success.return_value = False
    mock_response.code = 230020
    mock_response.msg = "invalid chat_id"
    mock_response.get_log_id.return_value = "log_xxx"
    mock_client = MagicMock()
    mock_client.im.v1.message.create.return_value = mock_response

    async def _fake_resolve(rt):
        return _make_endpoint()
    monkeypatch.setattr(
        FeishuMessageTools, "resolve_current_endpoint",
        _fake_resolve,
    )
    monkeypatch.setattr(
        FeishuMessageTools, "build_lark_client", lambda ep: mock_client
    )

    result = asyncio.run(send_feishu_message(content="hi", runtime=_make_runtime("project")))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert payload["code"] == 230020
    assert "invalid chat_id" in payload["msg"]
    assert payload["log_id"] == "log_xxx"


def test_send_feishu_message_api_exception_returns_error(monkeypatch):
    """client.im.v1.message.create 抛异常 → 返回通用错误，不向上抛。"""
    mock_client = MagicMock()
    mock_client.im.v1.message.create.side_effect = Exception("network down")

    async def _fake_resolve(rt):
        return _make_endpoint()
    monkeypatch.setattr(
        FeishuMessageTools, "resolve_current_endpoint",
        _fake_resolve,
    )
    monkeypatch.setattr(
        FeishuMessageTools, "build_lark_client", lambda ep: mock_client
    )

    result = asyncio.run(send_feishu_message(content="hi", runtime=_make_runtime("project")))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "飞书消息发送失败" in payload["error"]
    assert "network down" in payload["error"]


def test_send_feishu_message_build_client_failure_returns_error(monkeypatch):
    """build_lark_client 抛异常 → 返回「客户端初始化失败」错误，不向上抛。"""
    def boom(ep):
        raise RuntimeError("lark sdk missing")
    async def _fake_resolve(rt):
        return _make_endpoint()
    monkeypatch.setattr(
        FeishuMessageTools, "resolve_current_endpoint",
        _fake_resolve,
    )
    monkeypatch.setattr(
        FeishuMessageTools, "build_lark_client", boom
    )

    result = asyncio.run(send_feishu_message(content="hi", runtime=_make_runtime("project")))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "飞书客户端初始化失败" in payload["error"]
    assert "lark sdk missing" in payload["error"]


def test_send_feishu_message_passes_tool_call_id(monkeypatch):
    """runtime.tool_call_id 被透传到 ToolMessage。"""
    mock_response = MagicMock()
    mock_response.success.return_value = True
    mock_response.data.message_id = "om_msg_x"
    mock_client = MagicMock()
    mock_client.im.v1.message.create.return_value = mock_response

    async def _fake_resolve(rt):
        return _make_endpoint()
    monkeypatch.setattr(
        FeishuMessageTools, "resolve_current_endpoint",
        _fake_resolve,
    )
    monkeypatch.setattr(
        FeishuMessageTools, "build_lark_client", lambda ep: mock_client
    )

    result = asyncio.run(send_feishu_message(
        content="hi",
        runtime=_make_runtime("project", tool_call_id="call_xyz_789"),
    ))
    assert result.update["messages"][0].tool_call_id == "call_xyz_789"


def test_send_feishu_message_returns_none_data_message_id_gracefully(monkeypatch):
    """response.data=None → message_id 也安全返回 None（不抛 AttributeError）。"""
    mock_response = MagicMock()
    mock_response.success.return_value = True
    mock_response.data = None  # 边界：data 为空
    mock_client = MagicMock()
    mock_client.im.v1.message.create.return_value = mock_response

    async def _fake_resolve(rt):
        return _make_endpoint()
    monkeypatch.setattr(
        FeishuMessageTools, "resolve_current_endpoint",
        _fake_resolve,
    )
    monkeypatch.setattr(
        FeishuMessageTools, "build_lark_client", lambda ep: mock_client
    )

    result = asyncio.run(send_feishu_message(content="hi", runtime=_make_runtime("project")))
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert payload["message_id"] is None


def test_send_feishu_message_is_coroutine_function():
    """send_feishu_message 必须是 async 工具（ToolNode await 调用，杜绝同步桥接回归）。"""
    import inspect
    target = getattr(send_feishu_message, "func", send_feishu_message)
    if inspect.isfunction(target):
        assert inspect.iscoroutinefunction(target)
    else:
        assert getattr(send_feishu_message, "coroutine", None) is not None


def test_send_feishu_message_offloads_sdk_create_to_thread(monkeypatch):
    """阻塞型 lark SDK 调用必须经 asyncio.to_thread 卸载，不占住主事件 loop。"""
    calls = {"to_thread": 0}
    real_to_thread = asyncio.to_thread

    async def _spy_to_thread(func, *args, **kwargs):
        calls["to_thread"] += 1
        return await real_to_thread(func, *args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", _spy_to_thread)

    mock_response = MagicMock()
    mock_response.success.return_value = True
    mock_response.data.message_id = "om_msg_thread"
    mock_client = MagicMock()
    mock_client.im.v1.message.create.return_value = mock_response

    async def _fake_resolve(rt):
        return _make_endpoint("oc_proj")
    monkeypatch.setattr(FeishuMessageTools, "resolve_current_endpoint", _fake_resolve)
    monkeypatch.setattr(
        FeishuMessageTools, "build_lark_client", lambda ep: mock_client
    )

    result = asyncio.run(send_feishu_message(content="hi", runtime=_make_runtime("project")))

    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert calls["to_thread"] == 1