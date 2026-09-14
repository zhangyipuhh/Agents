# -*- coding:utf-8 -*-
"""
test_feishu_sheets_client - FeishuSheetsClient 单元测试

覆盖范围：
    - create_spreadsheet：v3 资源类调用（未受 v2 import bug 影响）
    - write_values：BaseRequest 原生 HTTP PUT + 内部先 metainfo 拿 sheet_id
    - read_values：BaseRequest 原生 HTTP GET + 内部先 metainfo 拿 sheet_id + 全表
    - _get_default_sheet_id：缓存命中 / API 错误 / 空 sheets 列表

2026-09-14 改造：删除 ``range_`` 入参，工具内部先调 metainfo 拿 sheet_id 缓存,
    read/write 都按全表语义调用 ``/values/{sheet_id}`` 端点(GET/PUT)。

测试 conftest（``app/tests/shared/tools/skills/feishu/conftest.py``）
mock 范围：lark_oapi.api.sheets.v3（仅 CreateSpreadsheetRequest / Body）+
lark_oapi.core.enum.HttpMethod / AccessTokenType + lark_oapi.core.model.BaseRequest /
RequestOption。lark-oapi 1.7.1 已移除 lark_oapi.api.sheets.v2 子模块。
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from app.shared.tools.skills.feishu.FeishuSheetsClient import FeishuSheetsClient


# 标准 metainfo 响应 payload 工厂
def _metainfo_payload(token: str = "ss_001", sheet_id: str = "sht1"):
    return {
        "code": 0,
        "msg": "Success",
        "data": {
            "spreadsheetToken": token,
            "sheets": [
                {"sheetId": sheet_id, "title": "Sheet1", "index": 0, "rowCount": 100, "columnCount": 20},
            ],
        },
    }


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


def _install_sequential_responses(client, payloads):
    """让 client.request 按调用顺序返回 payloads 列表中的内容。"""
    iter_payloads = iter(payloads)
    def _side_effect(*args, **kwargs):
        return _make_response(next(iter_payloads))
    client.request.side_effect = _side_effect


# =============================================================================
# create_spreadsheet
# =============================================================================


def test_sheets_create_spreadsheet_happy_path():
    """正常：API 成功 → 含 token / url / default_sheet_id。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    mock_response = MagicMock()
    mock_response.success.return_value = True
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
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.sheets.v3.spreadsheet.create.side_effect = RuntimeError("net err")

    resp = asyncio.run(sheets.create_spreadsheet(title="x"))
    assert resp["success"] is False
    assert "net err" in resp["error"]


# =============================================================================
# _get_default_sheet_id
# =============================================================================


def test_get_default_sheet_id_happy_path():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.request.return_value = _make_response(_metainfo_payload(sheet_id="shtabc"))

    sid = asyncio.run(sheets._get_default_sheet_id("ss_001"))
    assert sid == "shtabc"


def test_get_default_sheet_id_caches_result():
    """同一 token 第二次调用不再发 metainfo 请求（缓存命中）。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.request.return_value = _make_response(_metainfo_payload(sheet_id="shtxyz"))

    s1 = asyncio.run(sheets._get_default_sheet_id("ss_cache"))
    s2 = asyncio.run(sheets._get_default_sheet_id("ss_cache"))
    assert s1 == s2 == "shtxyz"
    # metainfo 只应被请求 1 次
    metainfo_calls = [
        c for c in client.request.call_args_list
        if "/metainfo" in c[0][0].uri
    ]
    assert len(metainfo_calls) == 1


def test_get_default_sheet_id_api_error_returns_none():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.request.return_value = _make_response({"code": 99991663, "msg": "permission denied"})

    sid = asyncio.run(sheets._get_default_sheet_id("ss_deny"))
    assert sid is None


def test_get_default_sheet_id_empty_sheets_returns_none():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.request.return_value = _make_response(
        {"code": 0, "msg": "ok", "data": {"sheets": []}}
    )

    sid = asyncio.run(sheets._get_default_sheet_id("ss_empty"))
    assert sid is None


def test_get_default_sheet_id_parse_failure_returns_none():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    resp_mock = MagicMock()
    resp_mock.raw = MagicMock()
    resp_mock.raw.content = b"\x00 not json"
    client.request.return_value = resp_mock

    sid = asyncio.run(sheets._get_default_sheet_id("ss_bad"))
    assert sid is None


def test_get_default_sheet_id_exception_returns_none():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.request.side_effect = RuntimeError("net")

    sid = asyncio.run(sheets._get_default_sheet_id("ss_exc"))
    assert sid is None


# =============================================================================
# write_values（BaseRequest 原生 HTTP PUT + 内部 metainfo）
# =============================================================================


def test_sheets_write_values_happy_path():
    """PUT 成功 → updated_rows / updated_cols / updated_range 正确返回 + sheet_id 来自 metainfo。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    # 第一次：metainfo；第二次：write values PUT
    _install_sequential_responses(
        client,
        [
            _metainfo_payload(token="ss_001", sheet_id="sht1"),
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
            },
        ],
    )

    resp = asyncio.run(
        sheets.write_values("ss_001", [["a", "b"], ["c", "d"]])
    )
    assert resp["success"] is True
    assert resp["sheet_id"] == "sht1"
    assert resp["updated_rows"] == 3
    assert resp["updated_cols"] == 4
    assert resp["updated_range"] == "sht1!A1:D3"


def test_sheets_write_values_body_uses_value_range_envelope_without_range():
    """写入请求体严格按官方契约使用 ``valueRange`` 信封且不含 range 字段（2026-09-14 全表契约）。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    _install_sequential_responses(
        client,
        [
            _metainfo_payload(),
            {"code": 0, "msg": "Success", "data": {"updatedRange": "sht1!A1:D3"}},
        ],
    )

    asyncio.run(sheets.write_values("ss_001", [["a", "b"], ["c", "d"]]))
    # 第 2 次 request（PUT values）才是写操作
    write_req = client.request.call_args_list[1][0][0]
    body = json.loads(write_req.body)
    assert "valueRange" in body
    assert "range" not in body["valueRange"]  # 全表模式不传 range
    assert body["valueRange"]["values"] == [["a", "b"], ["c", "d"]]


def test_sheets_write_values_uses_tenant_token_type():
    from lark_oapi.core.enum import AccessTokenType
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    _install_sequential_responses(
        client,
        [
            _metainfo_payload(),
            {"code": 0, "msg": "Success", "data": {}},
        ],
    )

    asyncio.run(sheets.write_values("ss_001", [["x"]]))
    write_req = client.request.call_args_list[1][0][0]
    assert AccessTokenType.TENANT in write_req.token_types


def test_sheets_write_values_uses_put_http_method():
    """BaseRequest.http_method == PUT（不再是 POST）。"""
    from lark_oapi.core.enum import HttpMethod
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    _install_sequential_responses(
        client,
        [
            _metainfo_payload(),
            {"code": 0, "msg": "Success", "data": {}},
        ],
    )

    asyncio.run(sheets.write_values("ss_001", [["x"]]))
    write_req = client.request.call_args_list[1][0][0]
    assert write_req.http_method == HttpMethod.PUT


def test_sheets_write_values_uri_includes_sheet_id():
    """PUT URI 必须是 /values/{sheet_id} 形态（不是 /values）。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    _install_sequential_responses(
        client,
        [
            _metainfo_payload(sheet_id="shtXYZ"),
            {"code": 0, "msg": "Success", "data": {}},
        ],
    )

    asyncio.run(sheets.write_values("ss_xyz", [["x"]]))
    write_req = client.request.call_args_list[1][0][0]
    assert write_req.uri == "/open-apis/sheets/v2/spreadsheets/ss_xyz/values/shtXYZ"


def test_sheets_write_values_first_calls_metainfo():
    """验证 write 链路确实先调 metainfo 拿 sheet_id。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    _install_sequential_responses(
        client,
        [
            _metainfo_payload(),
            {"code": 0, "msg": "Success", "data": {}},
        ],
    )

    asyncio.run(sheets.write_values("ss_001", [["x"]]))
    first_req = client.request.call_args_list[0][0][0]
    assert first_req.uri.endswith("/metainfo")


def test_sheets_write_values_metainfo_failure_returns_error():
    """metainfo 拿不到 sheet_id → 整体失败,不发 PUT。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.request.return_value = _make_response({"code": 99991663, "msg": "denied"})

    resp = asyncio.run(sheets.write_values("ss_001", [["x"]]))
    assert resp["success"] is False
    assert "sheet_id" in resp["error"]
    # 只能调一次（metainfo）,不会继续 PUT
    assert client.request.call_count == 1


def test_sheets_write_values_empty_token_returns_error():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    resp = asyncio.run(sheets.write_values("", [["x"]]))
    assert resp["success"] is False
    assert "spreadsheet_token" in resp["error"]


def test_sheets_write_values_empty_values_returns_error():
    """values 为空 list → success=False。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    resp = asyncio.run(sheets.write_values("ss_001", []))
    assert resp["success"] is False
    assert "values" in resp["error"]


def test_sheets_write_values_api_failure_returns_error_payload():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    _install_sequential_responses(
        client,
        [
            _metainfo_payload(),
            {"code": 99991663, "msg": "permission denied", "data": None},
        ],
    )

    resp = asyncio.run(sheets.write_values("ss_001", [["x"]]))
    assert resp["success"] is False
    assert resp["code"] == 99991663
    assert resp["msg"] == "permission denied"


def test_sheets_write_values_non_zero_code_230020_returns_failure():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    _install_sequential_responses(
        client,
        [
            _metainfo_payload(),
            {"code": 230020, "msg": "spreadsheet not found", "data": None},
        ],
    )

    resp = asyncio.run(sheets.write_values("missing", [["x"]]))
    assert resp["success"] is False
    assert resp["code"] == 230020


def test_sheets_write_values_exception_caught():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    # 第一次 metainfo 正常,第二次 write 时网络炸 → 写操作 catch
    def _side_effect(*args, **kwargs):
        if "/metainfo" in args[0].uri:
            return _make_response(_metainfo_payload())
        raise RuntimeError("net err")
    client.request.side_effect = _side_effect

    resp = asyncio.run(sheets.write_values("ss_001", [["x"]]))
    assert resp["success"] is False
    assert "net err" in resp["error"]


def test_sheets_write_values_empty_response_content_returns_error():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    # 第一次：metainfo 正常；第二次：write 响应 body 为空
    def _side_effect(*args, **kwargs):
        if "/metainfo" in args[0].uri:
            return _make_response(_metainfo_payload())
        resp_mock = MagicMock()
        resp_mock.raw = MagicMock()
        resp_mock.raw.content = b""
        return resp_mock
    client.request.side_effect = _side_effect

    resp = asyncio.run(sheets.write_values("ss_001", [["x"]]))
    assert resp["success"] is False


# =============================================================================
# read_values（BaseRequest 原生 HTTP GET + 全表）
# =============================================================================


def test_sheets_read_values_happy_path_returns_full_table():
    """正常：返回首个 sheet 全表数据 + sheet_id 透出。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    _install_sequential_responses(
        client,
        [
            _metainfo_payload(token="ss_001", sheet_id="sht_main"),
            {
                "code": 0,
                "msg": "Success",
                "data": {
                    "revision": 1,
                    "spreadsheetToken": "ss_001",
                    "valueRange": {
                        "range": "sht_main!A1:Z1000",
                        "values": [["a", "b"], ["c", "d"]],
                    },
                },
            },
        ],
    )

    resp = asyncio.run(sheets.read_values("ss_001"))
    assert resp["success"] is True
    assert resp["sheet_id"] == "sht_main"
    assert resp["values"] == [["a", "b"], ["c", "d"]]
    assert resp["revision"] == 1


def test_sheets_read_values_falls_back_to_data_values_when_no_value_range_envelope():
    """兼容旧契约：data 直接是 values 数组（无 valueRange 信封）也能取到。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    _install_sequential_responses(
        client,
        [
            _metainfo_payload(),
            {
                "code": 0,
                "msg": "Success",
                "data": {
                    "spreadsheetToken": "ss_001",
                    "values": [["a", "b"], ["c", "d"]],
                },
            },
        ],
    )

    resp = asyncio.run(sheets.read_values("ss_001"))
    assert resp["success"] is True
    assert resp["values"] == [["a", "b"], ["c", "d"]]


def test_sheets_read_values_uses_get_http_method():
    from lark_oapi.core.enum import HttpMethod
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    _install_sequential_responses(
        client,
        [
            _metainfo_payload(),
            {"code": 0, "msg": "Success", "data": {"values": []}},
        ],
    )

    asyncio.run(sheets.read_values("ss_001"))
    read_req = client.request.call_args_list[1][0][0]
    assert read_req.http_method == HttpMethod.GET


def test_sheets_read_values_uri_includes_sheet_id():
    """GET URI 必须是 /values/{sheet_id} 形态(无 queries range)。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    _install_sequential_responses(
        client,
        [
            _metainfo_payload(sheet_id="shtMain"),
            {"code": 0, "msg": "Success", "data": {"values": []}},
        ],
    )

    asyncio.run(sheets.read_values("ss_xyz"))
    read_req = client.request.call_args_list[1][0][0]
    assert read_req.uri == "/open-apis/sheets/v2/spreadsheets/ss_xyz/values/shtMain"
    assert read_req.queries is None  # 全表读取不传任何 queries


def test_sheets_read_values_first_calls_metainfo():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    _install_sequential_responses(
        client,
        [
            _metainfo_payload(),
            {"code": 0, "msg": "Success", "data": {"values": []}},
        ],
    )

    asyncio.run(sheets.read_values("ss_001"))
    first_req = client.request.call_args_list[0][0][0]
    assert first_req.uri.endswith("/metainfo")


def test_sheets_read_values_metainfo_failure_returns_error():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    client.request.return_value = _make_response({"code": 99991663, "msg": "denied"})

    resp = asyncio.run(sheets.read_values("ss_001"))
    assert resp["success"] is False
    assert "sheet_id" in resp["error"]
    assert client.request.call_count == 1


def test_sheets_read_values_reuses_cached_sheet_id():
    """同一 token 多次 read 只调一次 metainfo,后续读走缓存。"""
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    _install_sequential_responses(
        client,
        [
            _metainfo_payload(),
            {"code": 0, "msg": "Success", "data": {"values": [["a"]]}},
            {"code": 0, "msg": "Success", "data": {"values": [["b"]]}},
        ],
    )

    r1 = asyncio.run(sheets.read_values("ss_001"))
    r2 = asyncio.run(sheets.read_values("ss_001"))
    assert r1["values"] == [["a"]]
    assert r2["values"] == [["b"]]
    # 1 metainfo + 2 reads = 3 calls
    assert client.request.call_count == 3
    metainfo_calls = [c for c in client.request.call_args_list if "/metainfo" in c[0][0].uri]
    assert len(metainfo_calls) == 1


def test_sheets_read_values_empty_token_returns_error():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    resp = asyncio.run(sheets.read_values(""))
    assert resp["success"] is False
    assert "spreadsheet_token" in resp["error"]


def test_sheets_read_values_exception_caught():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    # 第一次 metainfo 正常,第二次 read 时网络炸 → 读操作 catch
    def _side_effect(*args, **kwargs):
        if "/metainfo" in args[0].uri:
            return _make_response(_metainfo_payload())
        raise RuntimeError("timeout")
    client.request.side_effect = _side_effect

    resp = asyncio.run(sheets.read_values("ss_001"))
    assert resp["success"] is False
    assert "timeout" in resp["error"]


def test_sheets_read_values_api_failure_returns_error_payload():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    _install_sequential_responses(
        client,
        [
            _metainfo_payload(),
            {"code": 230002, "msg": "sheet not found", "data": None},
        ],
    )

    resp = asyncio.run(sheets.read_values("missing"))
    assert resp["success"] is False
    assert resp["code"] == 230002
    assert resp["msg"] == "sheet not found"


def test_sheets_read_values_empty_response_content_returns_error():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)

    def _side_effect(*args, **kwargs):
        if "/metainfo" in args[0].uri:
            return _make_response(_metainfo_payload())
        resp_mock = MagicMock()
        resp_mock.raw = MagicMock()
        resp_mock.raw.content = b""
        return resp_mock

    client.request.side_effect = _side_effect
    resp = asyncio.run(sheets.read_values("ss_001"))
    assert resp["success"] is False


def test_sheets_read_values_data_without_values_key_returns_empty_list():
    client = _make_lark_client()
    sheets = FeishuSheetsClient(client)
    _install_sequential_responses(
        client,
        [
            _metainfo_payload(),
            {"code": 0, "msg": "Success", "data": {"spreadsheetToken": "ss_001"}},
        ],
    )

    resp = asyncio.run(sheets.read_values("ss_001"))
    assert resp["success"] is True
    assert resp["values"] == []


def test_sheets_read_values_description_emphasizes_full_table():
    """回归：description 文本必须强调「全表」+ 不再有 range_ 关键字（仅源码静态断言）。"""
    import inspect
    from app.shared.tools.skills.feishu import FeishuSheetsTools

    src = inspect.getsource(FeishuSheetsTools.read_feishu_sheet_values)
    assert "range_" not in src
    assert "全表" in src
