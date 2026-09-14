# -*- coding:utf-8 -*-
"""
test_feishu_sheets_tools - FeishuSheetsTools 3 个 @tool 单元测试

2026-09-14 改造:read_feishu_sheet_values / write_feishu_sheet_values 删除
``range_`` 入参,工具内部自动 metainfo 拿 sheet_id 后全表读写。
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


# 标准 metainfo 响应 payload
def _metainfo_payload(token="ss_001", sheet_id="sht1"):
    return {
        "code": 0,
        "msg": "Success",
        "data": {
            "spreadsheetToken": token,
            "sheets": [{"sheetId": sheet_id, "title": "Sheet1", "index": 0}],
        },
    }


def _install_sequential_responses(client, payloads):
    iter_payloads = iter(payloads)
    def _side_effect(*args, **kwargs):
        resp = MagicMock()
        resp.raw = MagicMock()
        resp.raw.content = json.dumps(next(iter_payloads), ensure_ascii=False).encode("utf-8")
        return resp
    client.request.side_effect = _side_effect


# =============================================================================
# create_feishu_spreadsheet(未受 range_ 改造影响,保留旧用例)
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


# =============================================================================
# write_feishu_sheet_values(全表,无 range_)
# =============================================================================


def test_write_sheets_values_happy_path(monkeypatch):
    """工具不传 range_ → 内部先 metainfo 拿 sheet_id,再 PUT 全表。"""
    client = _make_lark_client()
    _install_sequential_responses(
        client,
        [
            _metainfo_payload(),
            {
                "code": 0,
                "msg": "Success",
                "data": {
                    "updatedRange": "sht1!A1:C2",
                    "updatedRows": 2,
                    "updatedColumns": 3,
                    "revision": 1,
                },
            },
        ],
    )
    _patch_endpoint(monkeypatch, client)

    result = asyncio.run(write_feishu_sheet_values(
        spreadsheet_token="ss_001",
        values=[["a", "b", "c"], ["d", "e", "f"]],
        runtime=_make_runtime(),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert payload["sheet_id"] == "sht1"
    assert payload["updated_rows"] == 2


def test_write_sheets_values_empty_token_returns_error():
    result = asyncio.run(write_feishu_sheet_values(
        spreadsheet_token="", values=[["x"]], runtime=_make_runtime()
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "spreadsheet_token" in payload["error"]


def test_write_sheets_values_empty_values_returns_error():
    """反向用例:values=[] → 输入校验拦截。"""
    result = asyncio.run(write_feishu_sheet_values(
        spreadsheet_token="ss_001", values=[], runtime=_make_runtime()
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "values" in payload["error"]


def test_write_sheets_values_no_range_param_in_signature():
    """回归:write_feishu_sheet_values 不再接受 range_ 入参(inspect 签名)。"""
    import inspect
    sig = inspect.signature(write_feishu_sheet_values)
    assert "range_" not in sig.parameters


# =============================================================================
# read_feishu_sheet_values(全表,无 range_)
# =============================================================================


def test_read_sheets_values_happy_path(monkeypatch):
    """工具不传 range_ → 内部先 metainfo 拿 sheet_id,再 GET 全表。"""
    client = _make_lark_client()
    _install_sequential_responses(
        client,
        [
            _metainfo_payload(),
            {
                "code": 0,
                "msg": "Success",
                "data": {
                    "spreadsheetToken": "ss_001",
                    "valueRange": {
                        "range": "sht1!A1:Z1000",
                        "values": [["x", "y"], ["z", "w"]],
                    },
                },
            },
        ],
    )
    _patch_endpoint(monkeypatch, client)

    result = asyncio.run(read_feishu_sheet_values(
        spreadsheet_token="ss_001", runtime=_make_runtime()
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert payload["sheet_id"] == "sht1"
    assert payload["values"] == [["x", "y"], ["z", "w"]]


def test_read_sheets_values_empty_token_returns_error():
    result = asyncio.run(read_feishu_sheet_values(
        spreadsheet_token="", runtime=_make_runtime()
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "spreadsheet_token" in payload["error"]


def test_read_sheets_values_no_range_param_in_signature():
    """回归:read_feishu_sheet_values 不再接受 range_ 入参。"""
    import inspect
    sig = inspect.signature(read_feishu_sheet_values)
    assert "range_" not in sig.parameters


def test_read_sheets_values_description_warns_about_wiki_and_base_url():
    """工具 description 必须显式提示 wiki/base URL 不能作为 spreadsheet_token。"""
    import inspect
    src = inspect.getsource(read_feishu_sheet_values)
    assert "feishu.cn/sheets" in src
    assert "feishu.cn/wiki" in src
    assert "feishu.cn/base" in src
