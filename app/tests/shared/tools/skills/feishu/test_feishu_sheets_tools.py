# -*- coding:utf-8 -*-
"""
test_feishu_sheets_tools - FeishuSheetsTools 3 个 @tool 单元测试
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from app.shared.tools.skills.feishu import FeishuSheetsTools
from app.shared.tools.skills.feishu.FeishuSheetsTools import (
    create_feishu_spreadsheet,
    read_feishu_sheet_values,
    write_feishu_sheet_values,
)


def _parse_message_content(result) -> dict:
    messages = result.update["messages"]
    assert len(messages) == 1
    return json.loads(messages[0].content)


def _make_runtime(agent_name="project", tool_call_id="call_x"):
    rt = MagicMock()
    rt.tool_call_id = tool_call_id
    rt.state = {"agent_name": agent_name} if agent_name else {}
    return rt


def _make_lark_client():
    import lark_oapi as lark
    return lark.Client.builder().app_id("a").app_secret("s").build()


def _patch_endpoint(monkeypatch, lark_client=None):
    from app.shared.tools.skills.feishu import FeishuEndpointResolver
    from app.shared.tools.skills.feishu.FeishuEndpointResolver import Endpoint

    endpoint = Endpoint(
        channel_id=11, channel_name="feishu_default",
        app_id="a", app_secret="s", log_level="INFO",
        target_id=21, target_name="项目群",
        chat_id="oc_proj", chat_type="chat_id", agent_name="project",
    )

    async def _fake_resolve(rt):
        return endpoint

    monkeypatch.setattr(FeishuSheetsTools, "resolve_current_endpoint", _fake_resolve)
    monkeypatch.setattr(
        FeishuSheetsTools,
        "build_lark_client",
        lambda ep: lark_client or _make_lark_client(),
    )


# =============================================================================
# 通用反向用例
# =============================================================================


def test_create_sheets_tool_no_agent_name_returns_error():
    result = asyncio.run(create_feishu_spreadsheet(title="x", runtime=_make_runtime(agent_name=None)))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "智能体" in payload["error"]


def test_create_sheets_tool_empty_title_returns_error():
    result = asyncio.run(create_feishu_spreadsheet(title="", runtime=_make_runtime()))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "title" in payload["error"]


# =============================================================================
# create_feishu_spreadsheet
# =============================================================================


def test_create_sheets_tool_happy_path(monkeypatch):
    client = _make_lark_client()
    mock_resp = MagicMock()
    mock_resp.success.return_value = True
    sheet = {"sheet_id": "sht1"}
    mock_resp.data.spreadsheet.token = "ss_001"
    mock_resp.data.spreadsheet.url = "https://feishu.cn/sheets/ss_001"
    mock_resp.data.spreadsheet.sheets = [sheet]
    client.sheets.v3.spreadsheet.create.return_value = mock_resp
    _patch_endpoint(monkeypatch, client)

    result = asyncio.run(create_feishu_spreadsheet(title="x", runtime=_make_runtime()))
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert payload["spreadsheet_token"] == "ss_001"
    assert payload["default_sheet_id"] == "sht1"


def test_create_sheets_tool_endpoint_resolve_fails(monkeypatch):
    async def _fake_resolve(rt):
        return None
    monkeypatch.setattr(FeishuSheetsTools, "resolve_current_endpoint", _fake_resolve)
    result = asyncio.run(create_feishu_spreadsheet(title="x", runtime=_make_runtime()))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    # 中文文案透传：「智能体飞书渠道缺失」
    assert "智能体" in payload["error"] or "飞书渠道" in payload["error"]


# =============================================================================
# write_feishu_sheet_values
# =============================================================================


def test_write_sheets_values_happy_path(monkeypatch):
    client = _make_lark_client()
    mock_resp = MagicMock()
    mock_resp.success.return_value = True
    mock_resp.data.updated_rows = 2
    mock_resp.data.updated_cols = 3
    mock_resp.data.updated_range = "sht1!A1:C2"
    client.sheets.v2.spreadsheet_value.write.return_value = mock_resp
    _patch_endpoint(monkeypatch, client)

    result = asyncio.run(write_feishu_sheet_values(
        spreadsheet_token="ss_001",
        range_="sht1!A1:C2",
        values=[["a", "b", "c"], ["d", "e", "f"]],
        runtime=_make_runtime(),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert payload["updated_rows"] == 2


def test_write_sheets_values_empty_token_returns_error():
    result = asyncio.run(write_feishu_sheet_values(
        spreadsheet_token="", range_="sht1!A1", values=[["x"]], runtime=_make_runtime()
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False


def test_write_sheets_values_empty_values_returns_error():
    """反向用例：values=[] → 输入校验拦截。"""
    result = asyncio.run(write_feishu_sheet_values(
        spreadsheet_token="ss_001", range_="sht1!A1", values=[], runtime=_make_runtime()
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "values" in payload["error"]


# =============================================================================
# read_feishu_sheet_values
# =============================================================================


def test_read_sheets_values_happy_path(monkeypatch):
    client = _make_lark_client()
    mock_resp = MagicMock()
    mock_resp.success.return_value = True
    mock_resp.data.values = [["x", "y"], ["z", "w"]]
    client.sheets.v2.spreadsheet_value.get.return_value = mock_resp
    _patch_endpoint(monkeypatch, client)

    result = asyncio.run(read_feishu_sheet_values(
        spreadsheet_token="ss_001", range_="sht1!A1:B2", runtime=_make_runtime()
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert payload["values"] == [["x", "y"], ["z", "w"]]


def test_read_sheets_values_empty_range_returns_error():
    result = asyncio.run(read_feishu_sheet_values(
        spreadsheet_token="ss_001", range_="", runtime=_make_runtime()
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False