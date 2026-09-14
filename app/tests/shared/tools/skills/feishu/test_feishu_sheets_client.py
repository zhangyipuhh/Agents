# -*- coding:utf-8 -*-
"""
test_feishu_sheets_client - FeishuSheetsClient 单元测试

覆盖范围：
    - create_spreadsheet：v3 资源类调用（未受 v2 import bug 影响）
    - write_values：BaseRequest 原生 HTTP POST + valueRange 信封
    - read_values：BaseRequest 原生 HTTP GET + queries range 参数

测试 conftest（``app/tests/shared/tools/skills/feishu/conftest.py``）
mock 范围：lark_oapi.api.sheets.v3（仅 CreateSpreadsheetRequest / Body）+
lark_oapi.core.enum.HttpMethod / AccessTokenType + lark_oapi.core.model.BaseRequest /
RequestOption。lark-oapi 1.7.1 已移除 lark_oapi.api.sheets.v2 子模块，write_values /
read_values 改走 BaseRequest 原生 HTTP 路径（与
``FeishuWebSocketService._fetch_bot_open_id`` 同款）。
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from app.shared.tools.skills.feishu.FeishuSheetsClient import FeishuSheetsClient
from app.tests.shared.tools.skills.feishu.conftest import (
    _BaseRequest,
)


def _make_lark_client():
    """构造一个 mock lark.Client（带 client.request MagicMock 默认值）。"""
    import lark_oapi as lark
    return lark.Client.builder().app_id("a").app_secret("s").build()


def _make_response(payload: dict):
    """构造 ``client.request`` 返回的 mock 响应（含 raw.content bytes）。"""
    resp = MagicMock(name="response")
    resp.raw = MagicMock(name="response.raw")
    resp.raw.content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return resp


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
# write_values（BaseRequest 原生 HTTP）
# =============================================================================


def test_sheets_write_values_happy_path():
    """POST 成功 → updated_rows / updated_cols / updated_range 正确返回。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.request.return_value = _make_response(
        {
            "code": 0,
            "msg": "Success",
            "data": {
                "spreadsheetToken": "ss_001",
                "updatedRange": "sht1!A1:D3",
                "updatedRows": 3,
                "updatedColumns": 4,
                "revision": 1,
            },
        }
    )

    resp = asyncio.run(
        sheets.write_values("ss_001", "sht1!A1:D3", [["a", "b"], ["c", "d"]])
    )
    assert resp["success"] is True
    assert resp["updated_rows"] == 3
    assert resp["updated_cols"] == 4
    assert resp["updated_range"] == "sht1!A1:D3"


def test_sheets_write_values_body_uses_value_range_envelope():
    """写入请求体严格按官方契约使用 ``valueRange`` 信封（防裸字段退化）。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.request.return_value = _make_response(
        {
            "code": 0,
            "msg": "Success",
            "data": {
                "updatedRange": "sht1!A1:D3",
                "updatedRows": 3,
                "updatedColumns": 4,
            },
        }
    )

    asyncio.run(
        sheets.write_values(
            "ss_001", "sht1!A1:D3", [["a", "b"], ["c", "d"]]
        )
    )
    # 拿到 BaseRequest 实例
    req = client.request.call_args[0][0]
    body = json.loads(req.body)
    assert "valueRange" in body
    assert body["valueRange"]["range"] == "sht1!A1:D3"
    assert body["valueRange"]["values"] == [["a", "b"], ["c", "d"]]


def test_sheets_write_values_uses_tenant_token_type():
    """BaseRequest.token_types 必须包含 AccessTokenType.TENANT（官方契约）。"""
    from lark_oapi.core.enum import AccessTokenType
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.request.return_value = _make_response(
        {"code": 0, "msg": "Success", "data": {}}
    )

    asyncio.run(sheets.write_values("ss_001", "sht1!A1", [["x"]]))
    req = client.request.call_args[0][0]
    assert AccessTokenType.TENANT in req.token_types


def test_sheets_write_values_uses_post_http_method():
    """BaseRequest.http_method == POST。"""
    from lark_oapi.core.enum import HttpMethod
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.request.return_value = _make_response(
        {"code": 0, "msg": "Success", "data": {}}
    )

    asyncio.run(sheets.write_values("ss_001", "sht1!A1", [["x"]]))
    req = client.request.call_args[0][0]
    assert req.http_method == HttpMethod.POST


def test_sheets_write_values_uri_includes_spreadsheet_token():
    """URI 必须包含 spreadsheet_token 路径参数。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.request.return_value = _make_response(
        {"code": 0, "msg": "Success", "data": {}}
    )

    asyncio.run(sheets.write_values("ss_xyz", "sht1!A1", [["x"]]))
    req = client.request.call_args[0][0]
    assert "ss_xyz" in req.uri
    assert req.uri.startswith("/open-apis/sheets/v2/spreadsheets/")


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
    """非零 code → success=False + 透传 code / msg。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.request.return_value = _make_response(
        {"code": 99991663, "msg": "permission denied", "data": None}
    )

    resp = asyncio.run(sheets.write_values("ss_001", "sht1!A1", [["x"]]))
    assert resp["success"] is False
    assert resp["code"] == 99991663
    assert resp["msg"] == "permission denied"


def test_sheets_write_values_non_zero_code_230020_returns_failure():
    """非零 code 230020（飞书官方典型：spreadsheet not found）→ success=False。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.request.return_value = _make_response(
        {"code": 230020, "msg": "spreadsheet not found", "data": None}
    )

    resp = asyncio.run(sheets.write_values("missing", "sht1!A1", [["x"]]))
    assert resp["success"] is False
    assert resp["code"] == 230020


def test_sheets_write_values_exception_caught():
    """SDK / 网络抛异常 → success=False，不向上抛。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.request.side_effect = RuntimeError("net err")

    resp = asyncio.run(sheets.write_values("ss_001", "sht1!A1", [["x"]]))
    assert resp["success"] is False
    assert "net err" in resp["error"]


def test_sheets_write_values_empty_response_content_returns_error():
    """响应体为空 → success=False（防 raw.content=None/'' 崩溃）。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    resp_mock = MagicMock()
    resp_mock.raw = MagicMock()
    resp_mock.raw.content = b""
    client.request.return_value = resp_mock

    resp = asyncio.run(sheets.write_values("ss_001", "sht1!A1", [["x"]]))
    assert resp["success"] is False


# =============================================================================
# read_values（BaseRequest 原生 HTTP）
# =============================================================================


def test_sheets_read_values_happy_path():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.request.return_value = _make_response(
        {
            "code": 0,
            "msg": "Success",
            "data": {
                "revision": 1,
                "spreadsheetToken": "ss_001",
                "valueRanges": [
                    {
                        "majorDimension": "ROWS",
                        "range": "sht1!A1:B2",
                        "values": [["a", "b"], ["c", "d"]],
                    }
                ],
            },
        }
    )
    # 真实飞书 GET 响应 data.values 直接是 [[...]]
    client.request.return_value = _make_response(
        {
            "code": 0,
            "msg": "Success",
            "data": {
                "revision": 1,
                "spreadsheetToken": "ss_001",
                "values": [["a", "b"], ["c", "d"]],
            },
        }
    )

    resp = asyncio.run(sheets.read_values("ss_001", "sht1!A1:B2"))
    assert resp["success"] is True
    assert resp["values"] == [["a", "b"], ["c", "d"]]


def test_sheets_read_values_uses_get_http_method():
    """BaseRequest.http_method == GET。"""
    from lark_oapi.core.enum import HttpMethod
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.request.return_value = _make_response(
        {"code": 0, "msg": "Success", "data": {"values": []}}
    )

    asyncio.run(sheets.read_values("ss_001", "sht1!A1:B2"))
    req = client.request.call_args[0][0]
    assert req.http_method == HttpMethod.GET


def test_sheets_read_values_uses_tenant_token_type():
    """GET 也必须用 tenant_access_token。"""
    from lark_oapi.core.enum import AccessTokenType
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.request.return_value = _make_response(
        {"code": 0, "msg": "Success", "data": {"values": []}}
    )

    asyncio.run(sheets.read_values("ss_001", "sht1!A1:B2"))
    req = client.request.call_args[0][0]
    assert AccessTokenType.TENANT in req.token_types


def test_sheets_read_values_includes_range_query_param():
    """GET 请求的 queries 必须含 range 字段（值就是用户传入的 range_）。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.request.return_value = _make_response(
        {"code": 0, "msg": "Success", "data": {"values": []}}
    )

    asyncio.run(sheets.read_values("ss_001", "sht1!A1:B2"))
    req = client.request.call_args[0][0]
    assert req.queries is not None
    assert req.queries.get("range") == "sht1!A1:B2"


def test_sheets_read_values_uri_includes_spreadsheet_token():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.request.return_value = _make_response(
        {"code": 0, "msg": "Success", "data": {"values": []}}
    )

    asyncio.run(sheets.read_values("ss_xyz", "sht1!A1:B2"))
    req = client.request.call_args[0][0]
    assert "ss_xyz" in req.uri
    assert req.uri.startswith("/open-apis/sheets/v2/spreadsheets/")


def test_sheets_read_values_empty_token_returns_error():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)

    resp = asyncio.run(sheets.read_values("", "sht1!A1"))
    assert resp["success"] is False
    assert "spreadsheet_token" in resp["error"]


def test_sheets_read_values_empty_range_returns_error():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)

    resp = asyncio.run(sheets.read_values("ss_001", ""))
    assert resp["success"] is False
    assert "range_" in resp["error"]


def test_sheets_read_values_exception_caught():
    """SDK / 网络抛异常 → success=False。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.request.side_effect = RuntimeError("timeout")

    resp = asyncio.run(sheets.read_values("ss_001", "sht1!A1"))
    assert resp["success"] is False
    assert "timeout" in resp["error"]


def test_sheets_read_values_api_failure_returns_error_payload():
    """非零 code → success=False + 透传 code / msg。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.request.return_value = _make_response(
        {"code": 230002, "msg": "sheet not found", "data": None}
    )

    resp = asyncio.run(sheets.read_values("missing", "sht1!A1"))
    assert resp["success"] is False
    assert resp["code"] == 230002
    assert resp["msg"] == "sheet not found"


def test_sheets_read_values_empty_response_content_returns_error():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    resp_mock = MagicMock()
    resp_mock.raw = MagicMock()
    resp_mock.raw.content = b""
    client.request.return_value = resp_mock

    resp = asyncio.run(sheets.read_values("ss_001", "sht1!A1"))
    assert resp["success"] is False


def test_sheets_read_values_data_without_values_key_returns_empty_list():
    """成功响应 data 中无 values 键 → 返回空 list（防御性）。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.request.return_value = _make_response(
        {"code": 0, "msg": "Success", "data": {"spreadsheetToken": "ss_001"}}
    )

    resp = asyncio.run(sheets.read_values("ss_001", "sht1!A1:B2"))
    assert resp["success"] is True
    assert resp["values"] == []
