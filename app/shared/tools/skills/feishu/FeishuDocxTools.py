#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FeishuDocxTools - 模型可调用的飞书文档工具集

工具清单：
    - create_feishu_document         创建空 docx 文档
    - get_feishu_document_content    读取 docx 纯文本
    - append_feishu_document_blocks  追加 block 子节点（heading/paragraph/table 等）
    - share_feishu_document          构造 docx 分享 URL（仅前端访问）
    - list_feishu_files              列出 drive 文件夹下的文件
    - create_feishu_table_in_document 在 docx 内插入表格
    - replace_feishu_document_block  替换指定 block 内容（占位 / 实验性）

凭证：
    - 复用 ``FeishuEndpointResolver.resolve_current_endpoint`` +
      ``build_lark_client``（与 send_feishu_message 同款路径）
    - **不**走 ``FeishuClient.get_lark_client()`` 旧单例路径
      （2026-09-11 重构后该路径与 DB 多渠道契约不一致）

错误模式：
    - 全部失败以 ToolMessage 返回 ``{"success": False, "error": "..."}``，
      不抛异常，与 send_feishu_message 契约一致

发现机制：
    - 仅使用 ``@tool(description=...)`` 装饰，由 ToolRegistryService 源码扫描发现
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from langchain.tools import tool, ToolRuntime
from langgraph.types import Command

from app.shared.tools.skills.feishu.FeishuDocxClient import FeishuDocxClient
from app.shared.tools.skills.feishu.FeishuDriveClient import FeishuDriveClient
from app.shared.tools.skills.feishu.FeishuEndpointResolver import (
    ERROR_NO_AGENT_NAME,
    build_lark_client,
    resolve_current_endpoint,
)
from app.shared.tools.skills.feishu.FeishuMessageTools import _make_tool_message

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# 内部 helpers（不在 @tool 装饰器下，避免被工具注册中心误识别）
# -----------------------------------------------------------------------------


async def _resolve_client(runtime) -> tuple:
    """解析 endpoint 并构造 docx + drive 两个 client。

    Args:
        runtime: LangChain ToolRuntime

    Returns:
        tuple[Endpoint | None, FeishuDocxClient | None, FeishuDriveClient | None]:
            任一环节失败，docx 与 drive 均为 None
    """
    endpoint = await resolve_current_endpoint(runtime)
    if endpoint is None:
        return None, None, None
    try:
        lark_client = build_lark_client(endpoint)
    except Exception as e:  # noqa: BLE001
        logger.warning("[feishu_docx_tools] build_lark_client 失败: %s", e)
        return endpoint, None, None
    return endpoint, FeishuDocxClient(lark_client), FeishuDriveClient(lark_client)


def _error_cmd(tool_call_id: str, message: str) -> Command:
    """构造统一错误 Command。"""
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


# =============================================================================
# @tool 装饰的工具
# =============================================================================


@tool(description="创建一个飞书 docx 文档，返回 document_id 与 URL。folder_token 可选（空则放根目录）。")
async def create_feishu_document(
    title: str,
    folder_token: Optional[str] = None,
    runtime: ToolRuntime = None,
) -> Command:
    """创建飞书 docx 文档。

    Args:
        title: 文档标题（必填）
        folder_token: 飞书 drive 文件夹 token；空则放根目录
        runtime: LangChain ToolRuntime（自动注入，含 state.agent_name）

    Returns:
        Command: 含 ``messages[0].content`` 的 ``{"success": True/False, ...}``
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    if not title:
        return _error_cmd(tool_call_id, "title 缺失")
    if not runtime or not getattr(runtime, "state", None) or not runtime.state.get("agent_name"):
        return _error_cmd(tool_call_id, ERROR_NO_AGENT_NAME)
    _endpoint, docx_client, _drive = await _resolve_client(runtime)
    if docx_client is None:
        return _error_cmd(
            tool_call_id,
            "智能体飞书渠道缺失，请到「消息设置 → 飞书设置」检查「应用设置」",
        )
    resp = await docx_client.create_document(title=title, folder_token=folder_token)
    return Command(update={"messages": [_make_tool_message(tool_call_id, resp)]})


@tool(description="读取飞书 docx 文档的纯文本内容。参数：document_id（必填，飞书文档 ID）。")
async def get_feishu_document_content(
    document_id: str,
    runtime: ToolRuntime = None,
) -> Command:
    """读取飞书 docx 文档的纯文本。

    Args:
        document_id: 飞书 docx 文档 ID
        runtime: LangChain ToolRuntime
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    if not document_id:
        return _error_cmd(tool_call_id, "document_id 缺失")
    if not runtime or not getattr(runtime, "state", None) or not runtime.state.get("agent_name"):
        return _error_cmd(tool_call_id, ERROR_NO_AGENT_NAME)
    _endpoint, docx_client, _drive = await _resolve_client(runtime)
    if docx_client is None:
        return _error_cmd(tool_call_id, "智能体飞书渠道缺失")
    resp = await docx_client.get_document_raw_content(document_id=document_id)
    return Command(update={"messages": [_make_tool_message(tool_call_id, resp)]})


@tool(description="在飞书 docx 文档下追加 block 列表（heading/paragraph/table/列表/code block）。参数：document_id（必填）、blocks（必填，block JSON 列表，结构参考飞书 docx v1 Open API）。")
async def append_feishu_document_blocks(
    document_id: str,
    blocks: List[Dict[str, Any]],
    runtime: ToolRuntime = None,
) -> Command:
    """追加 block 子节点到飞书 docx。

    Args:
        document_id: 飞书 docx 文档 ID
        blocks: block JSON 列表（来自 create_feishu_table_in_document 或自构造）
        runtime: LangChain ToolRuntime
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    if not document_id:
        return _error_cmd(tool_call_id, "document_id 缺失")
    if not blocks or not isinstance(blocks, list):
        return _error_cmd(tool_call_id, "blocks 必须是非空 list")
    if not runtime or not getattr(runtime, "state", None) or not runtime.state.get("agent_name"):
        return _error_cmd(tool_call_id, ERROR_NO_AGENT_NAME)
    _endpoint, docx_client, _drive = await _resolve_client(runtime)
    if docx_client is None:
        return _error_cmd(tool_call_id, "智能体飞书渠道缺失")
    resp = await docx_client.append_block_children(
        document_id=document_id,
        block_id=document_id,  # 根 block_id 与 document_id 相同
        children=blocks,
    )
    return Command(update={"messages": [_make_tool_message(tool_call_id, resp)]})


@tool(description="构造飞书 docx 文档的分享 URL（仅前端访问，不验证权限）。参数：document_id（必填）。权限授予请到飞书侧操作。")
async def share_feishu_document(
    document_id: str,
    runtime: ToolRuntime = None,
) -> Command:
    """构造 docx 分享 URL。

    Args:
        document_id: 飞书 docx 文档 ID
        runtime: LangChain ToolRuntime（仅用于 tool_call_id 标识）
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    if not document_id:
        return _error_cmd(tool_call_id, "document_id 缺失")
    url = f"https://feishu.cn/docx/{document_id}"
    return Command(
        update={
            "messages": [
                _make_tool_message(
                    tool_call_id,
                    {
                        "success": True,
                        "document_id": document_id,
                        "url": url,
                        "permission_hint": "URL 仅供访问；ACL 设置请到飞书侧「分享」面板完成",
                    },
                )
            ]
        }
    )


@tool(description="列出飞书 drive 文件夹下的文件。folder_token 可选（空则列根目录）。")
async def list_feishu_files(
    folder_token: Optional[str] = None,
    runtime: ToolRuntime = None,
) -> Command:
    """列出飞书 drive 文件夹下的文件。

    Args:
        folder_token: 文件夹 token；空则列根目录
        runtime: LangChain ToolRuntime
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    if not runtime or not getattr(runtime, "state", None) or not runtime.state.get("agent_name"):
        return _error_cmd(tool_call_id, ERROR_NO_AGENT_NAME)
    _endpoint, _docx, drive = await _resolve_client(runtime)
    if drive is None:
        return _error_cmd(tool_call_id, "智能体飞书渠道缺失")
    resp = await drive.list_files(folder_token=folder_token)
    return Command(update={"messages": [_make_tool_message(tool_call_id, resp)]})


@tool(description="在飞书 docx 文档内插入表格（首行视为表头，加粗）。参数：document_id（必填）、rows（必填，二维字符串数组，每一行等长字符串列表）。")
async def create_feishu_table_in_document(
    document_id: str,
    rows: List[List[str]],
    runtime: ToolRuntime = None,
) -> Command:
    """在 docx 内插入表格。

    Args:
        document_id: 飞书 docx 文档 ID
        rows: 二维字符串数组（首行为表头，列数必须一致）
        runtime: LangChain ToolRuntime
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    if not document_id:
        return _error_cmd(tool_call_id, "document_id 缺失")
    if not rows or not isinstance(rows, list) or not all(isinstance(r, list) for r in rows):
        return _error_cmd(tool_call_id, "rows 必须是非空二维数组")
    if not runtime or not getattr(runtime, "state", None) or not runtime.state.get("agent_name"):
        return _error_cmd(tool_call_id, ERROR_NO_AGENT_NAME)
    _endpoint, docx_client, _drive = await _resolve_client(runtime)
    if docx_client is None:
        return _error_cmd(tool_call_id, "智能体飞书渠道缺失")

    # 校验列数一致
    n_cols = max(len(r) for r in rows)
    normalized = [(r + [""] * (n_cols - len(r)))[:n_cols] for r in rows]

    # 构造 table block（内部 helper 在 FeishuDocxClient 内）
    from app.shared.tools.skills.feishu.FeishuDocxClient import _table_block

    table_block = _table_block(normalized)
    resp = await docx_client.append_block_children(
        document_id=document_id,
        block_id=document_id,
        children=[table_block],
    )
    if resp.get("success"):
        resp = {
            "success": True,
            "row_count": len(normalized),
            "col_count": n_cols,
            "document_id": document_id,
        }
    return Command(update={"messages": [_make_tool_message(tool_call_id, resp)]})


@tool(description="替换飞书 docx 文档指定 block 的内容（实验性：当前仅支持删除 + 追加替代 block，原 block 保留为墓碑）。参数：document_id（必填）、block_id（必填）、new_blocks（必填，新 block JSON 列表）。")
async def replace_feishu_document_block(
    document_id: str,
    block_id: str,
    new_blocks: List[Dict[str, Any]],
    runtime: ToolRuntime = None,
) -> Command:
    """替换 docx block（实验性）。

    飞书 docx v1 API 不提供"原地替换 block"端点；本工具走"在父级追加新 block +
    由调用方后续手动清理原 block"的折中流程（若调用方需要，可再调 list_blocks
    拿到 block id 后通过飞书后台 UI 删除）。

    Args:
        document_id: 飞书 docx 文档 ID
        block_id: 目标 block_id（仅用于返回体透传，实际替换需飞书 UI）
        new_blocks: 新 block JSON 列表
        runtime: LangChain ToolRuntime
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    if not document_id:
        return _error_cmd(tool_call_id, "document_id 缺失")
    if not block_id:
        return _error_cmd(tool_call_id, "block_id 缺失")
    if not new_blocks or not isinstance(new_blocks, list):
        return _error_cmd(tool_call_id, "new_blocks 必须是非空 list")
    if not runtime or not getattr(runtime, "state", None) or not runtime.state.get("agent_name"):
        return _error_cmd(tool_call_id, ERROR_NO_AGENT_NAME)
    _endpoint, docx_client, _drive = await _resolve_client(runtime)
    if docx_client is None:
        return _error_cmd(tool_call_id, "智能体飞书渠道缺失")
    resp = await docx_client.append_block_children(
        document_id=document_id,
        block_id=document_id,
        children=new_blocks,
    )
    if resp.get("success"):
        resp = {
            "success": True,
            "document_id": document_id,
            "target_block_id": block_id,
            "new_blocks_appended": len(new_blocks),
            "note": "飞书 docx 不支持原地替换；新 block 已追加到文档根。请到飞书侧 UI 手动删除旧 block。",
        }
    return Command(update={"messages": [_make_tool_message(tool_call_id, resp)]})