#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FeishuSheetsTools - 模型可调用的飞书表格工具集

工具清单：
    - create_feishu_spreadsheet     创建飞书 spreadsheet
    - write_feishu_sheet_values     写入单元格值
    - read_feishu_sheet_values      读取单元格值

凭证：
    - 复用 ``FeishuEndpointResolver.resolve_current_endpoint`` +
      ``build_lark_client``（与 send_feishu_message / FeishuDocxTools 同款）

错误模式：
    - 全部失败以 ToolMessage 返回 ``{"success": False, "error": "..."}``

发现机制：
    - 仅使用 ``@tool(description=...)`` 装饰，由 ToolRegistryService 源码扫描发现
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from langchain.tools import tool, ToolRuntime
from langgraph.types import Command

from app.shared.tools.skills.feishu.FeishuEndpointResolver import (
    ERROR_NO_AGENT_NAME,
    build_lark_client,
    resolve_current_endpoint,
)
from app.shared.tools.skills.feishu.FeishuMessageTools import _make_tool_message
from app.shared.tools.skills.feishu.FeishuSheetsClient import FeishuSheetsClient

logger = logging.getLogger(__name__)


async def _resolve_sheets_client(runtime) -> tuple:
    """解析 endpoint 并构造 sheets client。

    Returns:
        tuple[Endpoint | None, FeishuSheetsClient | None]
    """
    endpoint = await resolve_current_endpoint(runtime)
    if endpoint is None:
        return None, None
    try:
        lark_client = build_lark_client(endpoint)
    except Exception as e:  # noqa: BLE001
        logger.warning("[feishu_sheets_tools] build_lark_client 失败: %s", e)
        return endpoint, None
    return endpoint, FeishuSheetsClient(lark_client)


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


@tool(description="创建一个飞书 spreadsheet（表格），返回 spreadsheet_token、URL 与默认 sheet_id。folder_token 可选（空则放根目录）。")
async def create_feishu_spreadsheet(
    title: str,
    folder_token: Optional[str] = None,
    runtime: ToolRuntime = None,
) -> Command:
    """创建飞书 spreadsheet。

    Args:
        title: 表格标题
        folder_token: drive 文件夹 token；空则放根目录
        runtime: LangChain ToolRuntime
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    if not title:
        return _error_cmd(tool_call_id, "title 缺失")
    if not runtime or not getattr(runtime, "state", None) or not runtime.state.get("agent_name"):
        return _error_cmd(tool_call_id, ERROR_NO_AGENT_NAME)
    _endpoint, sheets_client = await _resolve_sheets_client(runtime)
    if sheets_client is None:
        return _error_cmd(tool_call_id, "智能体飞书渠道缺失")
    resp = await sheets_client.create_spreadsheet(title=title, folder_token=folder_token)
    return Command(update={"messages": [_make_tool_message(tool_call_id, resp)]})


@tool(description="向飞书 spreadsheet 的第一个 sheet 全表写入数据(覆盖式)。参数:spreadsheet_token(必填,从 https://xxx.feishu.cn/sheets/{token} 提取;wiki 节点 URL feishu.cn/wiki/... 与多维表格 URL feishu.cn/base/... 不能直接作为 spreadsheet_token)、values(必填,二维数组,行 x 列)。返回值含 sheet_id / updated_rows / updated_range / revision。")
async def write_feishu_sheet_values(
    spreadsheet_token: str,
    values: List[List[Any]],
    runtime: ToolRuntime = None,
) -> Command:
    """向飞书 spreadsheet 的第一个 sheet 全表写入数据。

    Args:
        spreadsheet_token: 飞书 spreadsheet token。
        values: 二维数组(覆盖目标 sheet 全部区域)。
        runtime: LangChain ToolRuntime。
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    if not spreadsheet_token:
        return _error_cmd(tool_call_id, "spreadsheet_token 缺失")
    if not values or not isinstance(values, list):
        return _error_cmd(tool_call_id, "values 必须是非空二维数组")
    if not runtime or not getattr(runtime, "state", None) or not runtime.state.get("agent_name"):
        return _error_cmd(tool_call_id, ERROR_NO_AGENT_NAME)
    _endpoint, sheets_client = await _resolve_sheets_client(runtime)
    if sheets_client is None:
        return _error_cmd(tool_call_id, "智能体飞书渠道缺失")
    resp = await sheets_client.write_values(
        spreadsheet_token=spreadsheet_token,
        values=values,
    )
    return Command(update={"messages": [_make_tool_message(tool_call_id, resp)]})


@tool(description="读取飞书 spreadsheet 第一个 sheet 的全表数据。参数:spreadsheet_token(必填,从 https://xxx.feishu.cn/sheets/{token} 提取;wiki 节点 URL feishu.cn/wiki/... 与多维表格 URL feishu.cn/base/... 不能直接作为 spreadsheet_token)。返回 {success, sheet_id, values: [[...]], revision}。")
async def read_feishu_sheet_values(
    spreadsheet_token: str,
    runtime: ToolRuntime = None,
) -> Command:
    """读取飞书 spreadsheet 第一个 sheet 的全表数据。

    Args:
        spreadsheet_token: 飞书 spreadsheet token。
        runtime: LangChain ToolRuntime。
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    if not spreadsheet_token:
        return _error_cmd(tool_call_id, "spreadsheet_token 缺失")
    if not runtime or not getattr(runtime, "state", None) or not runtime.state.get("agent_name"):
        return _error_cmd(tool_call_id, ERROR_NO_AGENT_NAME)
    _endpoint, sheets_client = await _resolve_sheets_client(runtime)
    if sheets_client is None:
        return _error_cmd(tool_call_id, "智能体飞书渠道缺失")
    resp = await sheets_client.read_values(spreadsheet_token=spreadsheet_token)
    return Command(update={"messages": [_make_tool_message(tool_call_id, resp)]})