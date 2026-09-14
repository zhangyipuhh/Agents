#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FeishuBitableTools - 模型可调用的飞书多维表格只读工具集（3 件）

工具清单：
    - list_feishu_bitable_records      列出多维表格记录（分页）
    - get_feishu_bitable_record        获取单条记录详情
    - search_feishu_bitable_records    按 filter / sort 复杂检索（分页）

凭证：
    - 复用 ``FeishuEndpointResolver.resolve_current_endpoint`` +
      ``build_lark_client``（与 send_feishu_message / FeishuDocxTools /
      FeishuSheetsTools / FeishuWikiTools 同款）

错误模式：
    - 全部失败以 ToolMessage 返回 ``{"success": False, "error": "..."}``

发现机制：
    - 仅使用 ``@tool(description=...)`` 装饰，由 ToolRegistryService 源码扫描发现

说明（2026-09-14 落地）：
    - 本轮仅落地只读 3 件（list/get/search），不包含写入 / 字段元信息 / 表清单
    - ``search_records`` 的 filter / sort 直接透传飞书官方 schema，工具内
      不做语法翻译；详细语法参考飞书文档
      ``https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/bitable-v1/app-table-record/search``
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from langchain.tools import tool, ToolRuntime
from langgraph.types import Command

from app.shared.tools.skills.feishu.FeishuBitableClient import FeishuBitableClient
from app.shared.tools.skills.feishu.FeishuEndpointResolver import (
    ERROR_NO_AGENT_NAME,
    build_lark_client,
    resolve_current_endpoint,
)
from app.shared.tools.skills.feishu.FeishuMessageTools import _make_tool_message

logger = logging.getLogger(__name__)


async def _resolve_bitable_client(runtime):
    """解析 endpoint 并构造 bitable client。

    Args:
        runtime: LangChain ToolRuntime 实例。

    Returns:
        tuple[Endpoint | None, FeishuBitableClient | None]
    """
    endpoint = await resolve_current_endpoint(runtime)
    if endpoint is None:
        return None, None
    try:
        lark_client = build_lark_client(endpoint)
    except Exception as e:  # noqa: BLE001
        logger.warning("[feishu_bitable_tools] build_lark_client 失败: %s", e)
        return endpoint, None
    return endpoint, FeishuBitableClient(lark_client)


def _error_cmd(tool_call_id: str, message: str) -> Command:
    """统一的失败 ToolMessage Command。"""
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


def _agent_name_guard(runtime) -> Optional[Command]:
    """统一的 agent_name 校验；缺则返回失败 Command，否则返回 None。"""
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    if not runtime or not getattr(runtime, "state", None) or not runtime.state.get("agent_name"):
        return _error_cmd(tool_call_id, ERROR_NO_AGENT_NAME)
    return None


def _missing_client_cmd(runtime, tool_call_id: str) -> Command:
    return _error_cmd(tool_call_id, "智能体飞书渠道缺失")


@tool(
    description=(
        "列出飞书多维表格(Bitable)某张表的记录(分页)。"
        "参数:app_token(必填,从 URL https://xxx.feishu.cn/base/{app_token}?table={table_id} 取),"
        "table_id(必填),view_id(可选),field_names(可选,字段名数组),"
        "page_size(可选,默认 100 上限 500),page_token(可选,翻页用)。"
        "返回 {success, items, has_more, page_token, total},has_more=true 时用返回的 page_token 再调一次翻页。"
    )
)
async def list_feishu_bitable_records(
    app_token: str,
    table_id: str,
    view_id: Optional[str] = None,
    field_names: Optional[List[str]] = None,
    page_size: Optional[int] = None,
    page_token: Optional[str] = None,
    runtime: ToolRuntime = None,
) -> Command:
    """列出飞书多维表格某张表的记录（分页）。

    Args:
        app_token: 多维表格 App 唯一标识（URL ``base/`` 之后那段）。
        table_id: 数据表唯一标识。
        view_id: 视图 id。
        field_names: 限定返回的字段名数组。
        page_size: 单页记录数。
        page_token: 翻页 token。
        runtime: LangChain ToolRuntime。
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    if not app_token:
        return _error_cmd(tool_call_id, "app_token 缺失")
    if not table_id:
        return _error_cmd(tool_call_id, "table_id 缺失")
    guard = _agent_name_guard(runtime)
    if guard is not None:
        return guard
    _endpoint, bitable_client = await _resolve_bitable_client(runtime)
    if bitable_client is None:
        return _missing_client_cmd(runtime, tool_call_id)
    resp = await bitable_client.list_records(
        app_token=app_token,
        table_id=table_id,
        view_id=view_id,
        field_names=field_names,
        page_size=page_size,
        page_token=page_token,
    )
    return Command(update={"messages": [_make_tool_message(tool_call_id, resp)]})


@tool(
    description=(
        "获取飞书多维表格(Bitable)单条记录详情。"
        "参数:app_token(必填),table_id(必填),record_id(必填),with_shared_url(可选,默认 false)。"
        "返回 {success, record}。"
    )
)
async def get_feishu_bitable_record(
    app_token: str,
    table_id: str,
    record_id: str,
    with_shared_url: Optional[bool] = None,
    runtime: ToolRuntime = None,
) -> Command:
    """获取飞书多维表格单条记录详情。

    Args:
        app_token: 多维表格 App 唯一标识。
        table_id: 数据表唯一标识。
        record_id: 记录 id。
        with_shared_url: 是否返回记录的分享链接。
        runtime: LangChain ToolRuntime。
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    if not app_token:
        return _error_cmd(tool_call_id, "app_token 缺失")
    if not table_id:
        return _error_cmd(tool_call_id, "table_id 缺失")
    if not record_id:
        return _error_cmd(tool_call_id, "record_id 缺失")
    guard = _agent_name_guard(runtime)
    if guard is not None:
        return guard
    _endpoint, bitable_client = await _resolve_bitable_client(runtime)
    if bitable_client is None:
        return _missing_client_cmd(runtime, tool_call_id)
    resp = await bitable_client.get_record(
        app_token=app_token,
        table_id=table_id,
        record_id=record_id,
        with_shared_url=with_shared_url,
    )
    return Command(update={"messages": [_make_tool_message(tool_call_id, resp)]})


@tool(
    description=(
        "按复杂条件检索飞书多维表格(Bitable)记录(分页)。"
        "参数:app_token(必填),table_id(必填),"
        "filter(可选,形如 {conjunction:'and',conditions:[{field_name,operator,value},...]}),"
        "sort(可选,形如 [{field_name,direction:asc|desc}] 数组),"
        "field_names(可选,字段名数组),"
        "page_size(可选,默认 100 上限 500),page_token(可选,翻页用)。"
        "返回 {success, items, has_more, page_token, total}。"
        "operator 取值见飞书文档(is/is_not/contains/does_not_contain/is_empty/is_not_empty/"
        "is greater than/is less than 等);filter 或 sort 非空时 view_id 被忽略。"
    )
)
async def search_feishu_bitable_records(
    app_token: str,
    table_id: str,
    filter_: Optional[Dict[str, Any]] = None,
    sort: Optional[List[Dict[str, Any]]] = None,
    field_names: Optional[List[str]] = None,
    page_size: Optional[int] = None,
    page_token: Optional[str] = None,
    runtime: ToolRuntime = None,
) -> Command:
    """按复杂条件检索飞书多维表格记录（支持 filter / sort / 分页）。

    Args:
        app_token: 多维表格 App 唯一标识。
        table_id: 数据表唯一标识。
        filter_: 飞书官方 filter 结构（dict）。
        sort: 排序规则列表。
        field_names: 限定返回的字段名数组。
        page_size: 单页记录数。
        page_token: 翻页 token。
        runtime: LangChain ToolRuntime。
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    if not app_token:
        return _error_cmd(tool_call_id, "app_token 缺失")
    if not table_id:
        return _error_cmd(tool_call_id, "table_id 缺失")
    guard = _agent_name_guard(runtime)
    if guard is not None:
        return guard
    _endpoint, bitable_client = await _resolve_bitable_client(runtime)
    if bitable_client is None:
        return _missing_client_cmd(runtime, tool_call_id)
    resp = await bitable_client.search_records(
        app_token=app_token,
        table_id=table_id,
        filter_=filter_,
        sort=sort,
        field_names=field_names,
        page_size=page_size,
        page_token=page_token,
    )
    return Command(update={"messages": [_make_tool_message(tool_call_id, resp)]})
