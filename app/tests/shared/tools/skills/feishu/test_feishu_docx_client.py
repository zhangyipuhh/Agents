# -*- coding:utf-8 -*-
"""
test_feishu_docx_client - FeishuDocxClient 单元测试

覆盖：
    - create_document 正常 / 失败 / 异常
    - get_document_raw_content 正常 / 失败 / 异常
    - list_blocks 正常
    - append_block_children 正常 / 异常
    - _build_docx_url 边界

注意：
    - 项目顶层 conftest 已为 lark_oapi.api.docx.v1 提供 builder mock；
      测试通过 ``client.docx.v1.document.create.return_value`` 注入响应
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from app.shared.tools.skills.feishu.FeishuDocxClient import FeishuDocxClient


def _make_lark_client():
    """构造一个 mock lark.Client（已带 docx 命名空间）。"""
    import lark_oapi as lark

    return lark.Client.builder().app_id("a").app_secret("s").build()


# =============================================================================
# create_document
# =============================================================================


def test_docx_create_document_happy_path():
    """正常：API 返回 success → dict 含 document_id 与 url。"""
    client = _make_lark_client()
    docx = FeishuDocxClient(client)
    mock_response = MagicMock()
    mock_response.success.return_value = True
    mock_response.data.document_id = "d_abc123"
    client.docx.v1.document.create.return_value = mock_response

    resp = asyncio.run(docx.create_document(title="测试标题"))
    assert resp["success"] is True
    assert resp["document_id"] == "d_abc123"
    assert resp["url"] == "https://feishu.cn/docx/d_abc123"


def test_docx_create_document_with_folder_token_passes_to_sdk():
    """folder_token 显式传入时，SDK 应收到对应值（通过 _title / _folder_token 字段验证）。"""
    client = _make_lark_client()
    docx = FeishuDocxClient(client)
    mock_response = MagicMock()
    mock_response.success.return_value = True
    mock_response.data.document_id = "d_xyz"
    client.docx.v1.document.create.return_value = mock_response

    asyncio.run(docx.create_document(title="x", folder_token="fld_42"))
    # SDK builder 已被调用；body 字段记录在 _request_body 内
    req = client.docx.v1.document.create.call_args[0][0]
    assert req._request_body._title == "x"
    assert req._request_body._folder_token == "fld_42"


def test_docx_create_document_api_failure_returns_error_payload():
    """API 返回 success=False → 返回 code/msg/log_id 错误负载。"""
    client = _make_lark_client()
    docx = FeishuDocxClient(client)
    mock_response = MagicMock()
    mock_response.success.return_value = False
    mock_response.code = 230002
    mock_response.msg = "no permission"
    mock_response.get_log_id.return_value = "log_001"
    client.docx.v1.document.create.return_value = mock_response

    resp = asyncio.run(docx.create_document(title="x"))
    assert resp["success"] is False
    assert resp["code"] == 230002
    assert "no permission" in resp["msg"]


def test_docx_create_document_exception_returns_error():
    """SDK 抛出任意异常 → 返回 ``success=False``，不抛给调用方。"""
    client = _make_lark_client()
    docx = FeishuDocxClient(client)
    client.docx.v1.document.create.side_effect = RuntimeError("network down")

    resp = asyncio.run(docx.create_document(title="x"))
    assert resp["success"] is False
    assert "network down" in resp["error"]


# =============================================================================
# get_document_raw_content
# =============================================================================


def test_docx_get_raw_content_happy_path():
    """正常：返回 content 字符串。"""
    client = _make_lark_client()
    docx = FeishuDocxClient(client)
    mock_response = MagicMock()
    mock_response.success.return_value = True
    mock_response.data.content = "这是文档内容"
    client.docx.v1.document_raw_content.get.return_value = mock_response

    resp = asyncio.run(docx.get_document_raw_content("d_001"))
    assert resp["success"] is True
    assert resp["content"] == "这是文档内容"


def test_docx_get_raw_content_empty_data_returns_empty_string():
    """API 返回 data=None → content 为空字符串（不抛错）。"""
    client = _make_lark_client()
    docx = FeishuDocxClient(client)
    mock_response = MagicMock()
    mock_response.success.return_value = True
    mock_response.data = None
    client.docx.v1.document_raw_content.get.return_value = mock_response

    resp = asyncio.run(docx.get_document_raw_content("d_001"))
    assert resp["success"] is True
    assert resp["content"] == ""


def test_docx_get_raw_content_exception_returns_error():
    """SDK 抛错 → success=False。"""
    client = _make_lark_client()
    docx = FeishuDocxClient(client)
    client.docx.v1.document_raw_content.get.side_effect = ConnectionError("timeout")

    resp = asyncio.run(docx.get_document_raw_content("d_001"))
    assert resp["success"] is False
    assert "timeout" in resp["error"]


# =============================================================================
# list_blocks
# =============================================================================


def test_docx_list_blocks_returns_items():
    """列出文档 block 树。"""
    client = _make_lark_client()
    docx = FeishuDocxClient(client)
    mock_response = MagicMock()
    mock_response.success.return_value = True
    mock_items = [{"block_id": "b1"}, {"block_id": "b2"}]
    mock_response.data.items = mock_items
    client.docx.v1.document_block.list.return_value = mock_response

    resp = asyncio.run(docx.list_blocks("d_001"))
    assert resp["success"] is True
    assert resp["blocks"] == mock_items


def test_docx_list_blocks_failure_returns_code():
    """list_blocks 失败返回 code/msg。"""
    client = _make_lark_client()
    docx = FeishuDocxClient(client)
    mock_response = MagicMock()
    mock_response.success.return_value = False
    mock_response.code = 404
    mock_response.msg = "doc not found"
    client.docx.v1.document_block.list.return_value = mock_response

    resp = asyncio.run(docx.list_blocks("missing"))
    assert resp["success"] is False
    assert resp["code"] == 404


# =============================================================================
# append_block_children
# =============================================================================


def test_docx_append_blocks_happy_path():
    """正常追加 blocks：成功 + child_count 等于 children 长度。"""
    client = _make_lark_client()
    docx = FeishuDocxClient(client)
    mock_response = MagicMock()
    mock_response.success.return_value = True
    client.docx.v1.document_block_children.create.return_value = mock_response

    children = [
        {"block_type": 2, "text": {"rich_text": [{"text_run": {"content": "hi"}}]}},
    ]
    resp = asyncio.run(docx.append_block_children("d_001", "b_root", children))
    assert resp["success"] is True
    assert resp["child_count"] == 1


def test_docx_append_blocks_passes_block_id():
    """block_id 透传给 SDK request。"""
    client = _make_lark_client()
    docx = FeishuDocxClient(client)
    mock_response = MagicMock()
    mock_response.success.return_value = True
    client.docx.v1.document_block_children.create.return_value = mock_response

    asyncio.run(docx.append_block_children("d_001", "b_root_xyz", []))
    req = client.docx.v1.document_block_children.create.call_args[0][0]
    assert req._block_id == "b_root_xyz"
    assert req._document_id == "d_001"


def test_docx_append_blocks_exception_returns_error():
    """SDK 抛错 → success=False。"""
    client = _make_lark_client()
    docx = FeishuDocxClient(client)
    client.docx.v1.document_block_children.create.side_effect = RuntimeError("boom")

    resp = asyncio.run(docx.append_block_children("d_001", "b_root", [{"x": 1}]))
    assert resp["success"] is False
    assert "boom" in resp["error"]


# =============================================================================
# 内部 helper：_build_docx_url
# =============================================================================


def test_build_docx_url_with_id():
    from app.shared.tools.skills.feishu.FeishuDocxClient import _build_docx_url

    assert _build_docx_url("d_001") == "https://feishu.cn/docx/d_001"


def test_build_docx_url_with_none_returns_none():
    from app.shared.tools.skills.feishu.FeishuDocxClient import _build_docx_url

    assert _build_docx_url(None) is None