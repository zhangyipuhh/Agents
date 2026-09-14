# -*- coding:utf-8 -*-
"""
test_feishu_bitable_tools - FeishuBitableTools 3 个 @tool 单元测试

镜像 test_feishu_sheets_tools.py 风格：
    - P0 导入/存在性
    - P1 成功路径（happy）
    - P1 失败路径（endpoint 缺失 / agent_name 缺失 / build_lark_client 异常 / 入参缺失）
    - P2 边界（page_size 钳制 / filter_=None 时 body=空）
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

from app.shared.tools.skills.feishu import FeishuBitableTools
from app.shared.tools.skills.feishu.FeishuBitableTools import (
    get_feishu_bitable_record,
    list_feishu_bitable_records,
    search_feishu_bitable_records,
)


# =============================================================================
# helpers
# =============================================================================


def _make_runtime(agent_name="project", tool_call_id="call_b1"):
    rt = MagicMock()
    rt.tool_call_id = tool_call_id
    rt.state = {"agent_name": agent_name} if agent_name else {}
    return rt


def _make_lark_client():
    import lark_oapi as lark
    return lark.Client.builder().app_id("a").app_secret("s").build()


def _parse_message_content(result) -> dict:
    messages = result.update["messages"]
    assert len(messages) == 1
    return json.loads(messages[0].content)


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

    monkeypatch.setattr(FeishuBitableTools, "resolve_current_endpoint", _fake_resolve)
    monkeypatch.setattr(
        FeishuBitableTools,
        "build_lark_client",
        lambda ep: lark_client or _make_lark_client(),
    )


# =============================================================================
# P0 — 导入 / 存在性
# =============================================================================


def test_list_tool_importable():
    assert callable(list_feishu_bitable_records)


def test_get_tool_importable():
    assert callable(get_feishu_bitable_record)


def test_search_tool_importable():
    assert callable(search_feishu_bitable_records)


# =============================================================================
# list_feishu_bitable_records
# =============================================================================


def test_list_records_happy_path(monkeypatch):
    client = _make_lark_client()
    response = MagicMock()
    response.raw = MagicMock()
    response.raw.content = json.dumps(
        {"code": 0, "data": {"items": [{"record_id": "r1"}], "has_more": False, "total": 1}},
        ensure_ascii=False,
    ).encode("utf-8")
    client.request.return_value = response
    _patch_endpoint(monkeypatch, client)

    result = asyncio.run(list_feishu_bitable_records(
        app_token="APP", table_id="TBL", runtime=_make_runtime(),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert payload["items"] == [{"record_id": "r1"}]


def test_list_records_no_agent_name_returns_error():
    result = asyncio.run(list_feishu_bitable_records(
        app_token="APP", table_id="TBL", runtime=_make_runtime(agent_name=None),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "智能体" in payload["error"]


def test_list_records_empty_app_token_returns_error():
    result = asyncio.run(list_feishu_bitable_records(
        app_token="", table_id="TBL", runtime=_make_runtime(),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "app_token" in payload["error"]


def test_list_records_empty_table_id_returns_error():
    result = asyncio.run(list_feishu_bitable_records(
        app_token="APP", table_id="", runtime=_make_runtime(),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "table_id" in payload["error"]


def test_list_records_endpoint_resolve_fails(monkeypatch):
    async def _fake_resolve(rt):
        return None
    monkeypatch.setattr(FeishuBitableTools, "resolve_current_endpoint", _fake_resolve)
    result = asyncio.run(list_feishu_bitable_records(
        app_token="A", table_id="T", runtime=_make_runtime(),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "智能体" in payload["error"] or "飞书渠道" in payload["error"]


def test_list_records_build_lark_client_raises(monkeypatch):
    """反向：build_lark_client 抛异常被吞,返回「智能体飞书渠道缺失」。"""
    from app.shared.tools.skills.feishu import FeishuEndpointResolver
    from app.shared.tools.skills.feishu.FeishuEndpointResolver import Endpoint

    endpoint = Endpoint(
        channel_id=1, channel_name="c", app_id="a", app_secret="s",
        log_level="INFO", target_id=2, target_name="t",
        chat_id="oc", chat_type="chat_id", agent_name="project",
    )

    async def _fake_resolve(rt):
        return endpoint

    def _boom(ep):
        raise RuntimeError("client builder exploded")

    monkeypatch.setattr(FeishuBitableTools, "resolve_current_endpoint", _fake_resolve)
    monkeypatch.setattr(FeishuBitableTools, "build_lark_client", _boom)
    result = asyncio.run(list_feishu_bitable_records(
        app_token="A", table_id="T", runtime=_make_runtime(),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "智能体" in payload["error"] or "飞书渠道" in payload["error"]


# =============================================================================
# get_feishu_bitable_record
# =============================================================================


def test_get_record_happy_path(monkeypatch):
    client = _make_lark_client()
    response = MagicMock()
    response.raw = MagicMock()
    response.raw.content = json.dumps(
        {"code": 0, "data": {"record": {"record_id": "r42", "fields": {"名称": "hi"}}}},
        ensure_ascii=False,
    ).encode("utf-8")
    client.request.return_value = response
    _patch_endpoint(monkeypatch, client)

    result = asyncio.run(get_feishu_bitable_record(
        app_token="A", table_id="T", record_id="r42", runtime=_make_runtime(),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert payload["record"]["record_id"] == "r42"


def test_get_record_no_agent_name_returns_error():
    result = asyncio.run(get_feishu_bitable_record(
        app_token="A", table_id="T", record_id="r", runtime=_make_runtime(agent_name=None),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "智能体" in payload["error"]


def test_get_record_empty_record_id_returns_error():
    result = asyncio.run(get_feishu_bitable_record(
        app_token="A", table_id="T", record_id="", runtime=_make_runtime(),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "record_id" in payload["error"]


def test_get_record_empty_app_token_returns_error():
    result = asyncio.run(get_feishu_bitable_record(
        app_token="", table_id="T", record_id="r", runtime=_make_runtime(),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "app_token" in payload["error"]


def test_get_record_empty_table_id_returns_error():
    result = asyncio.run(get_feishu_bitable_record(
        app_token="A", table_id="", record_id="r", runtime=_make_runtime(),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "table_id" in payload["error"]


def test_get_record_endpoint_resolve_fails(monkeypatch):
    async def _fake_resolve(rt):
        return None
    monkeypatch.setattr(FeishuBitableTools, "resolve_current_endpoint", _fake_resolve)
    result = asyncio.run(get_feishu_bitable_record(
        app_token="A", table_id="T", record_id="r", runtime=_make_runtime(),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False


# =============================================================================
# search_feishu_bitable_records
# =============================================================================


def test_search_records_happy_path_with_filter(monkeypatch):
    client = _make_lark_client()
    response = MagicMock()
    response.raw = MagicMock()
    response.raw.content = json.dumps(
        {"code": 0, "data": {"items": [{"record_id": "r1"}], "has_more": True, "page_token": "tok2", "total": 5}},
        ensure_ascii=False,
    ).encode("utf-8")
    client.request.return_value = response
    _patch_endpoint(monkeypatch, client)

    result = asyncio.run(search_feishu_bitable_records(
        app_token="A", table_id="T",
        filter_={"conjunction": "and", "conditions": [
            {"field_name": "状态", "operator": "is", "value": ["进行中"]},
        ]},
        runtime=_make_runtime(),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert payload["has_more"] is True
    assert payload["page_token"] == "tok2"


def test_search_records_no_agent_name_returns_error():
    result = asyncio.run(search_feishu_bitable_records(
        app_token="A", table_id="T", runtime=_make_runtime(agent_name=None),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "智能体" in payload["error"]


def test_search_records_empty_app_token_returns_error():
    result = asyncio.run(search_feishu_bitable_records(
        app_token="", table_id="T", runtime=_make_runtime(),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "app_token" in payload["error"]


def test_search_records_empty_table_id_returns_error():
    result = asyncio.run(search_feishu_bitable_records(
        app_token="A", table_id="", runtime=_make_runtime(),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "table_id" in payload["error"]


def test_search_records_endpoint_resolve_fails(monkeypatch):
    async def _fake_resolve(rt):
        return None
    monkeypatch.setattr(FeishuBitableTools, "resolve_current_endpoint", _fake_resolve)
    result = asyncio.run(search_feishu_bitable_records(
        app_token="A", table_id="T", runtime=_make_runtime(),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False


def test_search_records_filter_none_succeeds(monkeypatch):
    """边界:filter_=None 时也能正常调用,后端 client body 序列化为空 dict。"""
    client = _make_lark_client()
    response = MagicMock()
    response.raw = MagicMock()
    response.raw.content = json.dumps(
        {"code": 0, "data": {"items": []}},
        ensure_ascii=False,
    ).encode("utf-8")
    client.request.return_value = response
    _patch_endpoint(monkeypatch, client)

    result = asyncio.run(search_feishu_bitable_records(
        app_token="A", table_id="T", runtime=_make_runtime(),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is True


def test_search_records_api_error_passes_through(monkeypatch):
    """反向:飞书 API 错误响应(1254018 InvalidFilter)被透传到 ToolMessage。"""
    client = _make_lark_client()
    response = MagicMock()
    response.raw = MagicMock()
    response.raw.content = json.dumps(
        {"code": 1254018, "msg": "InvalidFilter", "data": {"log_id": "lgZ"}},
        ensure_ascii=False,
    ).encode("utf-8")
    client.request.return_value = response
    _patch_endpoint(monkeypatch, client)

    result = asyncio.run(search_feishu_bitable_records(
        app_token="A", table_id="T", filter_={"bad": True}, runtime=_make_runtime(),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert payload["code"] == 1254018
