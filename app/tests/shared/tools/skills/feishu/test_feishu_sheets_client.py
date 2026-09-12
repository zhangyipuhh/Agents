# -*- coding:utf-8 -*-
"""
test_feishu_sheets_client - FeishuSheetsClient 单元测试
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from app.shared.tools.skills.feishu.FeishuSheetsClient import FeishuSheetsClient


def _make_lark_client():
    import lark_oapi as lark
    return lark.Client.builder().app_id("a").app_secret("s").build()


# =============================================================================
# create_spreadsheet
# =============================================================================


def test_sheets_create_spreadsheet_happy_path():
    """正常：API 成功 → 含 token / url / default_sheet_id。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    mock_response = MagicMock()
    mock_response.success.return_value = True
    # 嵌套 spreadsheet.sheets[0] 结构
    sheet = {"sheet_id": "sht1"}
    mock_response.data.spreadsheet.token = "ss_token_001"
    mock_response.data.spreadsheet.url = "https://feishu.cn/sheets/ss_token_001"
    mock_response.data.spreadsheet.sheets = [sheet]
    client.sheets.v3.spreadsheet.create.return_value = mock_response

    resp = asyncio.run(sheets.create_spreadsheet(title="测试表格"))
    assert resp["success"] is True
    assert resp["spreadsheet_token"] == "ss_token_001"
    assert resp["url"].endswith("/ss_token_001")
    assert resp["default_sheet_id"] == "sht1"


def test_sheets_create_spreadsheet_no_sheets_returns_none_default_sheet_id():
    """响应不含 sheets 列表时，default_sheet_id 为 None。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    mock_response = MagicMock()
    mock_response.success.return_value = True
    mock_response.data.spreadsheet.token = "ss_t"
    mock_response.data.spreadsheet.url = "https://feishu.cn/sheets/ss_t"
    mock_response.data.spreadsheet.sheets = []
    client.sheets.v3.spreadsheet.create.return_value = mock_response

    resp = asyncio.run(sheets.create_spreadsheet(title="空"))
    assert resp["success"] is True
    assert resp["default_sheet_id"] is None


def test_sheets_create_spreadsheet_api_failure_returns_error():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    mock_response = MagicMock()
    mock_response.success.return_value = False
    mock_response.code = 400
    mock_response.msg = "bad title"
    client.sheets.v3.spreadsheet.create.return_value = mock_response

    resp = asyncio.run(sheets.create_spreadsheet(title=""))
    assert resp["success"] is False
    assert resp["code"] == 400


def test_sheets_create_spreadsheet_exception_caught():
    """SDK 抛异常 → success=False，不向上抛。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.sheets.v3.spreadsheet.create.side_effect = RuntimeError("net err")

    resp = asyncio.run(sheets.create_spreadsheet(title="x"))
    assert resp["success"] is False
    assert "net err" in resp["error"]


# =============================================================================
# write_values
# =============================================================================


def test_sheets_write_values_happy_path():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    mock_response = MagicMock()
    mock_response.success.return_value = True
    mock_response.data.updated_rows = 3
    mock_response.data.updated_cols = 4
    mock_response.data.updated_range = "sht1!A1:D3"
    client.sheets.v2.spreadsheet_value.write.return_value = mock_response

    resp = asyncio.run(
        sheets.write_values("ss_001", "sht1!A1:D3", [["a", "b"], ["c", "d"]])
    )
    assert resp["success"] is True
    assert resp["updated_rows"] == 3
    assert resp["updated_cols"] == 4
    assert resp["updated_range"] == "sht1!A1:D3"


def test_sheets_write_values_empty_token_returns_error():
    """spreadsheet_token 缺失 → success=False（输入校验）。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)

    resp = asyncio.run(sheets.write_values("", "sht1!A1", [["x"]]))
    assert resp["success"] is False
    assert "spreadsheet_token" in resp["error"]


def test_sheets_write_values_empty_range_returns_error():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)

    resp = asyncio.run(sheets.write_values("ss_001", "", [["x"]]))
    assert resp["success"] is False
    assert "range_" in resp["error"]


def test_sheets_write_values_empty_values_returns_error():
    """values 为空 list → success=False（反向用例：fake 验参数编码）。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)

    resp = asyncio.run(sheets.write_values("ss_001", "sht1!A1", []))
    assert resp["success"] is False
    assert "values" in resp["error"]


def test_sheets_write_values_api_failure_returns_error_payload():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    mock_response = MagicMock()
    mock_response.success.return_value = False
    mock_response.code = 99991663
    mock_response.msg = "permission denied"
    client.sheets.v2.spreadsheet_value.write.return_value = mock_response

    resp = asyncio.run(sheets.write_values("ss_001", "sht1!A1", [["x"]]))
    assert resp["success"] is False
    assert resp["code"] == 99991663


# =============================================================================
# read_values
# =============================================================================


def test_sheets_read_values_happy_path():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    mock_response = MagicMock()
    mock_response.success.return_value = True
    mock_response.data.values = [["a", "b"], ["c", "d"]]
    client.sheets.v2.spreadsheet_value.get.return_value = mock_response

    resp = asyncio.run(sheets.read_values("ss_001", "sht1!A1:B2"))
    assert resp["success"] is True
    assert resp["values"] == [["a", "b"], ["c", "d"]]


def test_sheets_read_values_empty_token_returns_error():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)

    resp = asyncio.run(sheets.read_values("", "sht1!A1"))
    assert resp["success"] is False


def test_sheets_read_values_exception_caught():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.sheets.v2.spreadsheet_value.get.side_effect = RuntimeError("timeout")

    resp = asyncio.run(sheets.read_values("ss_001", "sht1!A1"))
    assert resp["success"] is False
    assert "timeout" in resp["error"]