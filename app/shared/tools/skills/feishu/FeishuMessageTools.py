#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FeishuMessageTools - 飞书消息发送工具集

职责：
    - 通过 FeishuEndpointResolver 按当前智能体（runtime.state.agent_name）解析
      飞书 endpoint（channel + target + 明文凭证 + chat_id）
    - 用 endpoint 的临时 lark.Client 发送文本 / Markdown 卡片
    - 错误以 ToolMessage 返回，不抛异常（遵循项目工具规范）

工具清单：
    - send_feishu_message  发送文本消息到当前智能体绑定的飞书群

注入与发现：
    - 仅使用 @tool(description=...) 装饰，不调用 register_tool
    - 工具元数据由 ToolRegistryService 通过源码扫描发现

2026-09-11 重构（BREAKING）：
    - 删除 receive_id / receive_id_type 参数（LLM 不显式传参，全部由后台解析）
    - 删除 _resolve_default_receive_via_db 旧逻辑（读 legacy default_receive_id）
    - 改走 FeishuEndpointResolver 按 agent 路由到 channel + target
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from langchain.tools import tool, ToolRuntime
from langgraph.types import Command

try:
    # 生产环境：使用真实 ToolMessage
    from langchain_core.messages import ToolMessage as _RealToolMessage
except Exception:  # noqa: BLE001 - 测试环境被 conftest mock 时降级
    _RealToolMessage = None

from app.shared.tools.skills.feishu.FeishuEndpointResolver import (
    ERROR_NO_AGENT_NAME,
    build_lark_client,
    resolve_current_endpoint,
)
from app.shared.tools.skills.feishu.MarkdownToCardConverter import (
    MarkdownToCardConverter,
)

logger = logging.getLogger(__name__)


def _build_content_payload(content: str) -> tuple:
    """根据 content 是否含 Markdown 特征，决定走交互式卡片还是纯文本。

    当 ``MarkdownToCardConverter.looks_like_markdown(content)`` 命中时，
    返回 ``("interactive", <卡片 JSON 字符串>)``，否则保持现有 ``("text",
    {"text": content} JSON 字符串)`` 行为。这样能保证被自动推送的 Markdown
    内容在飞书侧被正确渲染为卡片（与 ``FeishuCardConsumer._send_card_reply``
    复用同一转换器），同时对纯文本消息不强制加卡片头。

    Args:
        content: 工具调用方传入的原始文本

    Returns:
        tuple[str, str]: ``(msg_type, content_json_str)``
            - ``msg_type``: ``"interactive"`` / ``"text"``
            - ``content_json_str``: 已序列化的 JSON 字符串（ensure_ascii=False）
    """
    if MarkdownToCardConverter.looks_like_markdown(content or ""):
        card = MarkdownToCardConverter.to_card_json(content or "")
        return "interactive", json.dumps(card, ensure_ascii=False)
    return "text", json.dumps({"text": content}, ensure_ascii=False)


def _is_real_tool_message_class(cls) -> bool:
    """判断 ``_RealToolMessage`` 是真实类还是 conftest 注入的 ``Mock``。

    测试环境下 ``conftest.py`` 把 ``langchain_core.messages.ToolMessage = Mock()``
    替换为 Mock，导致 ``from langchain_core.messages import ToolMessage`` 拿到 Mock。

    Args:
        cls: 候选类对象

    Returns:
        bool: ``cls`` 是否为真正的 pydantic 类
    """
    if cls is None:
        return False
    try:
        from unittest.mock import Mock as _Mock  # noqa: WPS433 - 局部 import 避免循环

        if isinstance(cls, _Mock):
            return False
    except Exception:  # noqa: BLE001
        pass
    return True


_REAL_TOOL_MESSAGE_OK: bool = _is_real_tool_message_class(_RealToolMessage)


def _make_tool_message(tool_call_id: str, content: Any):
    """构造一个消息对象（生产环境用真实的 ``ToolMessage``，测试环境用 duck-typed）。

    Args:
        tool_call_id: 工具调用 ID
        content: ``dict`` 或 ``str`` 内容

    Returns:
        一个带 ``.content`` 与 ``.tool_call_id`` 属性的对象
    """
    if isinstance(content, dict):
        text = json.dumps(content, ensure_ascii=False)
    else:
        text = str(content)
    if _REAL_TOOL_MESSAGE_OK:
        return _RealToolMessage(content=text, tool_call_id=tool_call_id)  # type: ignore[misc]

    # 降级：测试环境 conftest 把 ToolMessage mock 为 MagicMock
    class _DuckMessage:
        """简易消息载体，提供 ``content`` 与 ``tool_call_id`` 属性。"""

        def __init__(self, content: str, tool_call_id: str) -> None:
            self.content = content
            self.tool_call_id = tool_call_id

        def __repr__(self) -> str:
            return f"<_DuckMessage tool_call_id={tool_call_id!r} content={content[:80]!r}>"

    return _DuckMessage(text, tool_call_id)


@tool(description="向当前智能体绑定的飞书群发送文本消息（Markdown 自动转交互式卡片）。无需指定接收方，后台按智能体自动路由。")
def send_feishu_message(
    content: str,
    runtime: ToolRuntime = None,
) -> Command:
    """发送飞书文本消息到当前智能体绑定的群。

    步骤：
      1) 从 runtime.state.agent_name 拿当前智能体名（缺失返回错误）
      2) 调 FeishuEndpointResolver.resolve_current_endpoint 解析 endpoint
      3) 用 build_lark_client 构造临时 lark.Client（按 channel 明文凭证）
      4) 构造 CreateMessageRequest 发送到 endpoint.chat_id
      5) 把发送结果封装为 ToolMessage 返回 Command

    Args:
        content: 文本消息内容（Markdown 自动转交互式卡片）
        runtime: LangChain ToolRuntime（自动注入，含 state.agent_name）

    Returns:
        Command: 含 messages 的 LangChain 命令对象；失败时 messages[0].content
        为 ``{"success": False, "error": "..."}`` JSON。
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"

    # 1) agent_name 缺失
    agent_name = None
    try:
        state = getattr(runtime, "state", None) if runtime else None
        agent_name = state.get("agent_name") if state else None
    except Exception:  # noqa: BLE001
        agent_name = None
    if not agent_name:
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": ERROR_NO_AGENT_NAME},
                    )
                ]
            }
        )

    # 2) 解析 endpoint（Resolver 内部已处理 service 未初始化 / channel 缺失 / target 缺失）
    endpoint = resolve_current_endpoint(runtime)
    if endpoint is None:
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {
                            "success": False,
                            "error": (
                                f"智能体 {agent_name!r} 飞书发送配置缺失，"
                                "请到「消息设置 → 飞书设置」检查「应用设置」与「发送策略」"
                            ),
                        },
                    )
                ]
            }
        )

    # 3) 构造 client
    try:
        client = build_lark_client(endpoint)
    except Exception as e:  # noqa: BLE001
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": f"飞书客户端初始化失败: {e}"},
                    )
                ]
            }
        )

    # 4) 构造请求并发送
    from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

    msg_type, content_str = _build_content_payload(content)

    request = (
        CreateMessageRequest.builder()
        .receive_id_type(endpoint.chat_type)
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(endpoint.chat_id)
            .msg_type(msg_type)
            .content(content_str)
            .uuid(str(uuid.uuid4()))
            .build()
        )
        .build()
    )

    try:
        response = client.im.v1.message.create(request)
        if not response.success():
            err_payload = {
                "success": False,
                "code": response.code,
                "msg": response.msg,
                "log_id": response.get_log_id(),
            }
            return Command(
                update={"messages": [_make_tool_message(tool_call_id, err_payload)]}
            )
        # 安全取 message_id（response.data 可能为 None）
        msg_id = None
        if response.data is not None:
            msg_id = getattr(response.data, "message_id", None)
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {
                            "success": True,
                            "message_id": msg_id,
                            "chat_id": endpoint.chat_id,
                            "chat_type": endpoint.chat_type,
                            "agent_name": endpoint.agent_name,
                            "content": content,
                        },
                    )
                ]
            }
        )
    except Exception as e:  # noqa: BLE001
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": f"飞书消息发送失败: {e}"},
                    )
                ]
            }
        )