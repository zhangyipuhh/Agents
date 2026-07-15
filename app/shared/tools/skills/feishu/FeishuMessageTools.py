#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FeishuMessageTools - 飞书消息发送工具集

职责：
    - 通过 get_lark_client() 获取公共飞书客户端
    - 调用 client.im.v1.message.create 发送文本消息
    - 错误以 ToolMessage 返回，不抛异常（遵循项目工具规范）

工具清单：
    - send_feishu_message  发送文本消息到指定群/用户

注入与发现：
    - 仅使用 @tool(description=...) 装饰，不调用 register_tool
    - 工具元数据由 ToolRegistryService 通过源码扫描发现
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

from langchain.tools import tool, ToolRuntime
from langgraph.types import Command

try:
    # 生产环境：使用真实 ToolMessage
    from langchain_core.messages import ToolMessage as _RealToolMessage
except Exception:  # noqa: BLE001 - 测试环境被 conftest mock 时降级
    _RealToolMessage = None

from app.core.config.settings import settings
from app.shared.tools.skills.feishu.FeishuClient import get_lark_client

logger = logging.getLogger(__name__)


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
            return f"<_DuckMessage tool_call_id={self.tool_call_id!r} content={self.content[:80]!r}>"

    return _DuckMessage(text, tool_call_id)


@tool(description="向飞书群或用户发送文本消息。需在 .env 中配置 feishu_app_id / feishu_app_secret。")
def send_feishu_message(
    content: str,
    receive_id: Optional[str] = None,
    receive_id_type: str = "",
    runtime: ToolRuntime = None,
) -> Command:
    """发送飞书文本消息。

    步骤：
      1) 通过 get_lark_client() 取公共 client（凭证来自 settings.feishu）
      2) 解析 receive_id / receive_id_type（缺省时回退到 settings.feishu 默认值）
      3) 构造 CreateMessageRequest 并调用 client.im.v1.message.create
      4) 把发送结果封装为 ToolMessage 返回 Command

    Args:
        content: 文本消息内容
        receive_id: 接收方 ID（群 chat_id / 用户 open_id 等）；
            空则用 settings.feishu.feishu_default_receive_id
        receive_id_type: 接收方类型（chat_id / open_id / user_id / email）；
            空则用 settings.feishu.feishu_default_receive_id_type
        runtime: LangChain ToolRuntime（自动注入）

    Returns:
        Command: 含 messages 的 LangChain 命令对象
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"

    # 解析接收方（参数优先，缺省回退到全局配置）
    target_receive_id = receive_id or settings.feishu.feishu_default_receive_id
    target_receive_id_type = (
        receive_id_type or settings.feishu.feishu_default_receive_id_type
    )
    if not target_receive_id:
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {
                            "success": False,
                            "error": "receive_id 缺失：请传入参数或在 .env 配置 feishu_default_receive_id",
                        },
                    )
                ]
            }
        )

    # 取 client
    try:
        client = get_lark_client()
    except RuntimeError as e:
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

    # 构造请求（参考 exmple.py）
    from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

    request = (
        CreateMessageRequest.builder()
        .receive_id_type(target_receive_id_type)
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(target_receive_id)
            .msg_type("text")
            .content(json.dumps({"text": content}, ensure_ascii=False))
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

        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {
                            "success": True,
                            "message_id": getattr(response.data, "message_id", None)
                            if response.data
                            else None,
                            "receive_id": target_receive_id,
                            "receive_id_type": target_receive_id_type,
                            "content": content,
                        },
                    )
                ]
            }
        )
    except Exception as e:  # noqa: BLE001 - 捕获所有并以通用错误返回
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
