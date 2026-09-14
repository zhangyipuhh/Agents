# -*- coding:utf-8 -*-
"""
test_feishu_bitable_client - FeishuBitableClient 3 个只读方法单元测试

覆盖：
    - list_records（GET /open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records）
    - get_record（GET .../records/{record_id}）
    - search_records（POST .../records/search）
    - 参数校验 / page_size 钳制 / token_type / http_method / 异常吞掉

mock 模式：
    - 用 ``MagicMock`` 替换 ``FeishuBitableClient._client.request``，
      构造 ``response.raw.content`` 为 JSON bytes 模拟飞书 API 响应
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from app.shared.tools.skills.feishu.FeishuBitableClient import (
    _BITABLE_MAX_PAGE_SIZE,
    FeishuBitableClient,
    _clamp_page_size,
)


# =============================================================================
# helpers
# =============================================================================


def _make_client():
    """构造一个 mock lark client（含 MagicMock request）。"""
    client = MagicMock(name="lark.Client")
    return client


def _install_response(client, payload: dict):
    """让 ``client.request(...)`` 返回构造好的 mock response。"""
    response = MagicMock(name="response")
    raw = MagicMock(name="response.raw")
    raw.content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    response.raw = raw
    client.request.return_value = response


def _run(coro):
    return asyncio.run(coro)


def _last_request(client):
    """拿到最后一次 ``client.request`` 调用的 BaseRequest 实例（conftest 记录在 .body/.uri 等）。"""
    return client.request.call_args[0][0]


# =============================================================================
# _clamp_page_size 单元测试
# =============================================================================


@pytest.mark.parametrize(
    "input_value,expected",
    [
        (None, None),
        (0, 1),
        (-5, 1),
        (1, 1),
        (100, 100),
        (500, 500),
        (501, _BITABLE_MAX_PAGE_SIZE),
        (9999, _BITABLE_MAX_PAGE_SIZE),
        ("100", 100),
        ("abc", None),
    ],
)
def test_clamp_page_size(input_value, expected):
    assert _clamp_page_size(input_value) == expected


# =============================================================================
# list_records
# =============================================================================


def test_list_records_happy_path():
    client = _make_client()
    _install_response(
        client,
        {
            "code": 0,
            "msg": "Success",
            "data": {
                "has_more": True,
                "page_token": "pgtok_001",
                "total": 3,
                "items": [
                    {"record_id": "rec1", "fields": {"名称": "A"}},
                    {"record_id": "rec2", "fields": {"名称": "B"}},
                    {"record_id": "rec3", "fields": {"名称": "C"}},
                ],
            },
        },
    )
    bc = FeishuBitableClient(client)
    resp = _run(bc.list_records(
        app_token="appX", table_id="tblY",
        view_id="viewZ", page_size=200, page_token="prev",
    ))
    assert resp["success"] is True
    assert len(resp["items"]) == 3
    assert resp["items"][0]["record_id"] == "rec1"
    assert resp["has_more"] is True
    assert resp["page_token"] == "pgtok_001"
    assert resp["total"] == 3


def test_list_records_empty_items():
    client = _make_client()
    _install_response(client, {"code": 0, "msg": "ok", "data": {"items": []}})
    bc = FeishuBitableClient(client)
    resp = _run(bc.list_records(app_token="a", table_id="t"))
    assert resp["success"] is True
    assert resp["items"] == []


def test_list_records_sends_correct_uri_and_token():
    """验证 GET 请求 URI 与 tenant token 类型。"""
    client = _make_client()
    _install_response(client, {"code": 0, "data": {"items": []}})
    bc = FeishuBitableClient(client)
    _run(bc.list_records(app_token="APP", table_id="TBL"))
    req = _last_request(client)
    assert req.uri == "/open-apis/bitable/v1/apps/APP/tables/TBL/records"
    assert req.token_types == {"tenant"}


def test_list_records_serializes_field_names_as_json():
    client = _make_client()
    _install_response(client, {"code": 0, "data": {"items": []}})
    bc = FeishuBitableClient(client)
    _run(bc.list_records(app_token="a", table_id="t", field_names=["姓名", "状态"]))
    req = _last_request(client)
    assert json.loads(req.queries["field_names"]) == ["姓名", "状态"]


def test_list_records_clamps_page_size_to_500():
    client = _make_client()
    _install_response(client, {"code": 0, "data": {"items": []}})
    bc = FeishuBitableClient(client)
    _run(bc.list_records(app_token="a", table_id="t", page_size=999))
    req = _last_request(client)
    assert req.queries["page_size"] == "500"


def test_list_records_uses_text_field_as_array_query():
    client = _make_client()
    _install_response(client, {"code": 0, "data": {"items": []}})
    bc = FeishuBitableClient(client)
    _run(bc.list_records(app_token="a", table_id="t", text_field_as_array=True, user_id_type="open_id"))
    req = _last_request(client)
    assert req.queries["text_field_as_array"] == "true"
    assert req.queries["user_id_type"] == "open_id"


def test_list_records_api_error_returns_error_dict():
    client = _make_client()
    _install_response(
        client,
        {"code": 1254003, "msg": "WrongBaseToken", "data": {"log_id": "lg1"}},
    )
    bc = FeishuBitableClient(client)
    resp = _run(bc.list_records(app_token="bad", table_id="t"))
    assert resp["success"] is False
    assert resp["code"] == 1254003
    assert resp["msg"] == "WrongBaseToken"
    assert resp["log_id"] == "lg1"


def test_list_records_raw_content_parse_failure_returns_error():
    """反向：response.raw.content 不可解析。"""
    client = _make_client()
    response = MagicMock()
    raw = MagicMock()
    raw.content = b"\x00\x01 not valid json \xff"
    response.raw = raw
    client.request.return_value = response
    bc = FeishuBitableClient(client)
    resp = _run(bc.list_records(app_token="a", table_id="t"))
    assert resp["success"] is False


def test_list_records_exception_in_request_returns_error():
    """反向：client.request 抛任何异常 → 吞掉并返回 error dict。"""
    client = _make_client()
    client.request.side_effect = RuntimeError("net down")
    bc = FeishuBitableClient(client)
    resp = _run(bc.list_records(app_token="a", table_id="t"))
    assert resp["success"] is False
    assert "net down" in resp["error"]


def test_list_records_missing_app_token_returns_error():
    """反向：入参校验 — 缺 app_token 不走 HTTP。"""
    client = _make_client()
    bc = FeishuBitableClient(client)
    resp = _run(bc.list_records(app_token="", table_id="t"))
    assert resp["success"] is False
    assert "app_token" in resp["error"]
    client.request.assert_not_called()


def test_list_records_missing_table_id_returns_error():
    client = _make_client()
    bc = FeishuBitableClient(client)
    resp = _run(bc.list_records(app_token="a", table_id=""))
    assert resp["success"] is False
    assert "table_id" in resp["error"]
    client.request.assert_not_called()


# =============================================================================
# get_record
# =============================================================================


def test_get_record_happy_path():
    client = _make_client()
    _install_response(
        client,
        {
            "code": 0,
            "msg": "ok",
            "data": {"record": {"record_id": "rec1", "fields": {"姓名": "张三"}}},
        },
    )
    bc = FeishuBitableClient(client)
    resp = _run(bc.get_record(app_token="a", table_id="t", record_id="rec1"))
    assert resp["success"] is True
    assert resp["record"]["record_id"] == "rec1"
    assert resp["record"]["fields"]["姓名"] == "张三"


def test_get_record_sends_correct_uri():
    client = _make_client()
    _install_response(client, {"code": 0, "data": {"record": {}}})
    bc = FeishuBitableClient(client)
    _run(bc.get_record(app_token="APP", table_id="TBL", record_id="REC"))
    req = _last_request(client)
    assert req.uri == "/open-apis/bitable/v1/apps/APP/tables/TBL/records/REC"
    assert req.token_types == {"tenant"}


def test_get_record_with_with_shared_url_true():
    client = _make_client()
    _install_response(client, {"code": 0, "data": {"record": {}}})
    bc = FeishuBitableClient(client)
    _run(bc.get_record(
        app_token="a", table_id="t", record_id="r",
        with_shared_url=True, automatic_fields=True,
    ))
    req = _last_request(client)
    assert req.queries["with_shared_url"] == "true"
    assert req.queries["automatic_fields"] == "true"


def test_get_record_api_error_returns_error():
    client = _make_client()
    _install_response(client, {"code": 1254043, "msg": "RecordIdNotFound"})
    bc = FeishuBitableClient(client)
    resp = _run(bc.get_record(app_token="a", table_id="t", record_id="bad"))
    assert resp["success"] is False
    assert resp["code"] == 1254043


def test_get_record_missing_record_id_returns_error():
    client = _make_client()
    bc = FeishuBitableClient(client)
    resp = _run(bc.get_record(app_token="a", table_id="t", record_id=""))
    assert resp["success"] is False
    assert "record_id" in resp["error"]
    client.request.assert_not_called()


# =============================================================================
# search_records
# =============================================================================


def test_search_records_happy_path():
    client = _make_client()
    _install_response(
        client,
        {
            "code": 0,
            "msg": "ok",
            "data": {
                "has_more": False,
                "page_token": None,
                "total": 1,
                "items": [{"record_id": "rec1", "fields": {"状态": "进行中"}}],
            },
        },
    )
    bc = FeishuBitableClient(client)
    resp = _run(bc.search_records(
        app_token="a", table_id="t",
        filter_={"conjunction": "and", "conditions": [
            {"field_name": "状态", "operator": "is", "value": ["进行中"]},
        ]},
        sort=[{"field_name": "创建时间", "direction": "desc"}],
        page_size=50,
    ))
    assert resp["success"] is True
    assert len(resp["items"]) == 1
    assert resp["items"][0]["fields"]["状态"] == "进行中"


def test_search_records_sends_post_and_correct_uri():
    client = _make_client()
    _install_response(client, {"code": 0, "data": {"items": []}})
    bc = FeishuBitableClient(client)
    _run(bc.search_records(app_token="APP", table_id="TBL"))
    req = _last_request(client)
    assert req.http_method == "POST"
    assert req.uri == "/open-apis/bitable/v1/apps/APP/tables/TBL/records/search"
    assert req.token_types == {"tenant"}


def test_search_records_serializes_filter_and_sort_as_json_body():
    """验证 POST body 含 filter / sort / field_names / page_size。"""
    client = _make_client()
    _install_response(client, {"code": 0, "data": {"items": []}})
    bc = FeishuBitableClient(client)
    _run(bc.search_records(
        app_token="a", table_id="t",
        filter_={"conjunction": "and", "conditions": []},
        sort=[{"field_name": "id", "direction": "asc"}],
        field_names=["id", "name"],
        page_size=999,  # 钳制
    ))
    req = _last_request(client)
    body = json.loads(req.body)
    assert body["filter"] == {"conjunction": "and", "conditions": []}
    assert body["sort"] == [{"field_name": "id", "direction": "asc"}]
    assert body["field_names"] == ["id", "name"]
    assert body["page_size"] == 500


def test_search_records_no_filter_sends_empty_body():
    """反向：无 filter 时 body 为 ``{}``,不传任何字段。"""
    client = _make_client()
    _install_response(client, {"code": 0, "data": {"items": []}})
    bc = FeishuBitableClient(client)
    _run(bc.search_records(app_token="a", table_id="t"))
    req = _last_request(client)
    assert req.body == "{}"


def test_search_records_api_error_returns_error():
    client = _make_client()
    _install_response(
        client,
        {"code": 1254018, "msg": "InvalidFilter", "data": {"log_id": "lg_x"}},
    )
    bc = FeishuBitableClient(client)
    resp = _run(bc.search_records(app_token="a", table_id="t"))
    assert resp["success"] is False
    assert resp["code"] == 1254018
    assert resp["log_id"] == "lg_x"


def test_search_records_exception_returns_error():
    client = _make_client()
    client.request.side_effect = ValueError("boom")
    bc = FeishuBitableClient(client)
    resp = _run(bc.search_records(app_token="a", table_id="t"))
    assert resp["success"] is False
    assert "boom" in resp["error"]


def test_search_records_missing_app_token_returns_error():
    client = _make_client()
    bc = FeishuBitableClient(client)
    resp = _run(bc.search_records(app_token="", table_id="t"))
    assert resp["success"] is False
    assert "app_token" in resp["error"]
    client.request.assert_not_called()


# =============================================================================
# 跨方法契约
# =============================================================================


def test_uses_get_method_for_list_and_get():
    """list_records / get_record 必须走 GET。"""
    client = _make_client()
    _install_response(client, {"code": 0, "data": {"items": [], "record": {}}})
    bc = FeishuBitableClient(client)
    _run(bc.list_records(app_token="a", table_id="t"))
    _run(bc.get_record(app_token="a", table_id="t", record_id="r"))
    assert client.request.call_count == 2
    assert client.request.call_args_list[0][0][0].http_method == "GET"
    assert client.request.call_args_list[1][0][0].http_method == "GET"
