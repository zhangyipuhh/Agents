#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FeishuWikiTools - 模型可调用的飞书知识库工具集

工具清单：
    - create_wiki_node                  在知识空间下创建节点（包装已有 docx）
    - get_wiki_node                     解析 token（node_token ↔ obj_token）
    - list_wiki_nodes                   列出父节点下的子节点
    - move_wiki_node                    移动节点到新父节点
    - rename_wiki_node                  修改节点标题
    - create_wiki_node_from_markdown ⭐ 一键入口：md → docx → wiki 节点
      （用户需求「飞书知识库插入 md 文件」的主线入口）

凭证：
    - 复用 ``FeishuEndpointResolver.resolve_current_endpoint`` +
      ``build_lark_client``
    - **不**走 ``FeishuClient.get_lark_client()`` 旧单例路径

错误模式：
    - 全部失败以 ToolMessage 返回 ``{"success": False, "error": "..."}``

发现机制：
    - 仅使用 ``@tool(description=...)`` 装饰，由 ToolRegistryService 源码扫描发现
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from langchain.tools import tool, ToolRuntime
from langgraph.types import Command

from app.shared.tools.skills.feishu.FeishuDocxClient import FeishuDocxClient
from app.shared.tools.skills.feishu.FeishuEndpointResolver import (
    ERROR_NO_AGENT_NAME,
    build_lark_client,
    resolve_current_endpoint,
)
from app.shared.tools.skills.feishu.FeishuMessageTools import _make_tool_message
from app.shared.tools.skills.feishu.FeishuWikiClient import FeishuWikiClient

logger = logging.getLogger(__name__)


async def _resolve_wiki_client(runtime) -> tuple:
    """解析 endpoint 并构造 wiki + docx 两个 client（wiki 依赖 docx）。

    Returns:
        tuple[Endpoint | None, FeishuWikiClient | None]
    """
    endpoint = await resolve_current_endpoint(runtime)
    if endpoint is None:
        return None, None
    try:
        lark_client = build_lark_client(endpoint)
    except Exception as e:  # noqa: BLE001
        logger.warning("[feishu_wiki_tools] build_lark_client 失败: %s", e)
        return endpoint, None
    docx_client = FeishuDocxClient(lark_client)
    wiki_client = FeishuWikiClient(lark_client, docx_client=docx_client)
    return endpoint, wiki_client


def _error_cmd(tool_call_id: str, message: str) -> Command:
    return Command(
        update={
            "messages": [
                _make_tool_message(
                    tool_call_id,
                    {"success": False, "error": message},
                )
            ]
        }
    )


@tool(description="在飞书知识空间下创建节点（包装已有 docx）。参数：space_id（必填）、title（必填）、obj_token（必填，已有的 docx 或 sheet token）、parent_node_token 可选。")
async def create_wiki_node(
    space_id: str,
    title: str,
    obj_token: str,
    parent_node_token: Optional[str] = None,
    obj_type: str = "docx",
    runtime: ToolRuntime = None,
) -> Command:
    """创建 wiki 节点。

    Args:
        space_id: 飞书知识空间 ID
        title: 节点标题
        obj_token: 已有的 docx / sheet token
        parent_node_token: 父节点 token；空则放根目录
        obj_type: 飞书文档类型，默认 docx
        runtime: LangChain ToolRuntime
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    if not space_id:
        return _error_cmd(tool_call_id, "space_id 缺失")
    if not title:
        return _error_cmd(tool_call_id, "title 缺失")
    if not obj_token:
        return _error_cmd(tool_call_id, "obj_token 缺失（必须先调用 create_feishu_document 拿到 document_id）")
    if not runtime or not getattr(runtime, "state", None) or not runtime.state.get("agent_name"):
        return _error_cmd(tool_call_id, ERROR_NO_AGENT_NAME)
    _endpoint, wiki_client = await _resolve_wiki_client(runtime)
    if wiki_client is None:
        return _error_cmd(tool_call_id, "智能体飞书渠道缺失")
    resp = await wiki_client.create_node(
        space_id=space_id,
        title=title,
        obj_token=obj_token,
        parent_node_token=parent_node_token,
        obj_type=obj_type,
    )
    return Command(update={"messages": [_make_tool_message(tool_call_id, resp)]})


@tool(description="解析飞书 wiki token（node_token 或 docx/sheet token）→ 节点信息。参数：token（必填）、obj_type 可选（辅助解析，如 ``docx`` / ``sheet``）。")
async def get_wiki_node(
    token: str,
    obj_type: Optional[str] = None,
    runtime: ToolRuntime = None,
) -> Command:
    """解析 token。

    Args:
        token: 节点 token 或 doc token
        obj_type: 文档类型辅助解析
        runtime: LangChain ToolRuntime
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    if not token:
        return _error_cmd(tool_call_id, "token 缺失")
    if not runtime or not getattr(runtime, "state", None) or not runtime.state.get("agent_name"):
        return _error_cmd(tool_call_id, ERROR_NO_AGENT_NAME)
    _endpoint, wiki_client = await _resolve_wiki_client(runtime)
    if wiki_client is None:
        return _error_cmd(tool_call_id, "智能体飞书渠道缺失")
    resp = await wiki_client.get_node(token=token, obj_type=obj_type)
    return Command(update={"messages": [_make_tool_message(tool_call_id, resp)]})


@tool(description="列出飞书知识空间下父节点的子节点。参数：space_id（必填）、parent_node_token 可选（空则列根目录）。")
async def list_wiki_nodes(
    space_id: str,
    parent_node_token: Optional[str] = None,
    runtime: ToolRuntime = None,
) -> Command:
    """列出父节点下的子节点。

    Args:
        space_id: 知识空间 ID
        parent_node_token: 父节点 token；空则列根
        runtime: LangChain ToolRuntime
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    if not space_id:
        return _error_cmd(tool_call_id, "space_id 缺失")
    if not runtime or not getattr(runtime, "state", None) or not runtime.state.get("agent_name"):
        return _error_cmd(tool_call_id, ERROR_NO_AGENT_NAME)
    _endpoint, wiki_client = await _resolve_wiki_client(runtime)
    if wiki_client is None:
        return _error_cmd(tool_call_id, "智能体飞书渠道缺失")
    resp = await wiki_client.list_nodes(
        space_id=space_id,
        parent_node_token=parent_node_token,
    )
    return Command(update={"messages": [_make_tool_message(tool_call_id, resp)]})


@tool(description="移动飞书 wiki 节点到新父节点下。参数：space_id（必填）、node_token（必填）、target_parent_token 可选（空则移到空间根目录）。")
async def move_wiki_node(
    space_id: str,
    node_token: str,
    target_parent_token: Optional[str] = None,
    runtime: ToolRuntime = None,
) -> Command:
    """移动节点。

    Args:
        space_id: 知识空间 ID
        node_token: 节点 token
        target_parent_token: 目标父节点 token
        runtime: LangChain ToolRuntime
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    if not space_id:
        return _error_cmd(tool_call_id, "space_id 缺失")
    if not node_token:
        return _error_cmd(tool_call_id, "node_token 缺失")
    if not runtime or not getattr(runtime, "state", None) or not runtime.state.get("agent_name"):
        return _error_cmd(tool_call_id, ERROR_NO_AGENT_NAME)
    _endpoint, wiki_client = await _resolve_wiki_client(runtime)
    if wiki_client is None:
        return _error_cmd(tool_call_id, "智能体飞书渠道缺失")
    resp = await wiki_client.move_node(
        space_id=space_id,
        node_token=node_token,
        target_parent_token=target_parent_token,
    )
    return Command(update={"messages": [_make_tool_message(tool_call_id, resp)]})


@tool(description="修改飞书 wiki 节点标题。参数：space_id（必填）、node_token（必填）、new_title（必填）。")
async def rename_wiki_node(
    space_id: str,
    node_token: str,
    new_title: str,
    runtime: ToolRuntime = None,
) -> Command:
    """修改节点标题。

    Args:
        space_id: 知识空间 ID
        node_token: 节点 token
        new_title: 新标题
        runtime: LangChain ToolRuntime
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    if not space_id:
        return _error_cmd(tool_call_id, "space_id 缺失")
    if not node_token:
        return _error_cmd(tool_call_id, "node_token 缺失")
    if not new_title:
        return _error_cmd(tool_call_id, "new_title 缺失")
    if not runtime or not getattr(runtime, "state", None) or not runtime.state.get("agent_name"):
        return _error_cmd(tool_call_id, ERROR_NO_AGENT_NAME)
    _endpoint, wiki_client = await _resolve_wiki_client(runtime)
    if wiki_client is None:
        return _error_cmd(tool_call_id, "智能体飞书渠道缺失")
    resp = await wiki_client.rename_node(
        space_id=space_id,
        node_token=node_token,
        new_title=new_title,
    )
    return Command(update={"messages": [_make_tool_message(tool_call_id, resp)]})


@tool(description="一键把 Markdown 内容写入飞书知识库节点（自动创建 docx + 解析 md 为 blocks + 写入 + 包装为 wiki 节点）。参数：space_id（必填）、title（必填，同时作为 docx 标题）、markdown_content（必填，markdown 文本）、parent_node_token 可选。返回 node_token / wiki_url / document_id / md_blocks_count。")
async def create_wiki_node_from_markdown(
    space_id: str,
    title: str,
    markdown_content: str,
    parent_node_token: Optional[str] = None,
    runtime: ToolRuntime = None,
) -> Command:
    """一键：md → 飞书 wiki 节点。

    内部流程（不暴露给 LLM）：
        1. FeishuDocxClient.create_document(title) 拿 document_id
        2. _md_to_blocks(markdown_content) 解析 markdown
        3. FeishuDocxClient.append_block_children(document_id, root, blocks)
        4. FeishuWikiClient.create_node(space_id, title, document_id)

    Args:
        space_id: 飞书知识空间 ID
        title: 节点标题（同时也是 docx 标题）
        markdown_content: markdown 文本
        parent_node_token: 父节点 token；空则放根目录
        runtime: LangChain ToolRuntime
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    if not space_id:
        return _error_cmd(tool_call_id, "space_id 缺失")
    if not title:
        return _error_cmd(tool_call_id, "title 缺失")
    if not markdown_content:
        return _error_cmd(tool_call_id, "markdown_content 缺失")
    if not runtime or not getattr(runtime, "state", None) or not runtime.state.get("agent_name"):
        return _error_cmd(tool_call_id, ERROR_NO_AGENT_NAME)
    _endpoint, wiki_client = await _resolve_wiki_client(runtime)
    if wiki_client is None:
        return _error_cmd(tool_call_id, "智能体飞书渠道缺失")
    resp = await wiki_client.create_wiki_node_from_markdown(
        space_id=space_id,
        title=title,
        markdown_content=markdown_content,
        parent_node_token=parent_node_token,
    )
    return Command(update={"messages": [_make_tool_message(tool_call_id, resp)]})