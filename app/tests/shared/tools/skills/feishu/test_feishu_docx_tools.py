# -*- coding:utf-8 -*-
"""
test_feishu_docx_tools - FeishuDocxTools 7 个 @tool 工具的单元测试

覆盖：
    - create_feishu_document / get_feishu_document_content /
      append_feishu_document_blocks / share_feishu_document /
      list_feishu_files / create_feishu_table_in_document /
      replace_feishu_document_block
    - 反向用例：agent_name 缺失 / 必填参数缺失 / endpoint 解析失败
"""
from __future__ import annotations

import asyncio
import inspect
import json
from unittest.mock import MagicMock

import pytest

from app.shared.tools.skills.feishu import FeishuDocxTools
from app.shared.tools.skills.feishu.FeishuDocxTools import (
    append_feishu_document_blocks,
    create_feishu_document,
    create_feishu_table_in_document,
    get_feishu_document_content,
    list_feishu_files,
    replace_feishu_document_block,
    share_feishu_document,
)


def _parse_message_content(result) -> dict:
    """从 Command 结果提取首条 ToolMessage 的 JSON 内容。"""
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
    """统一 monkeypatch：resolve_current_endpoint 返回 dummy endpoint，build_lark_client 返回 lark_client。"""
    from app.shared.tools.skills.feishu import FeishuEndpointResolver
    from app.shared.tools.skills.feishu.FeishuEndpointResolver import Endpoint

    endpoint = Endpoint(
        channel_id=11,
        channel_name="feishu_default",
        app_id="a",
        app_secret="s",
        log_level="INFO",
        target_id=21,
        target_name="项目群",
        chat_id="oc_proj",
        chat_type="chat_id",
        agent_name="project",
    )

    async def _fake_resolve(rt):
        return endpoint

    monkeypatch.setattr(FeishuDocxTools, "resolve_current_endpoint", _fake_resolve)
    monkeypatch.setattr(
        FeishuDocxTools,
        "build_lark_client",
        lambda ep: lark_client or _make_lark_client(),
    )
    return endpoint


# =============================================================================
# 工具签名 / 可导入性
# =============================================================================


@pytest.mark.parametrize("tool_fn", [
    create_feishu_document, get_feishu_document_content,
    append_feishu_document_blocks, share_feishu_document,
    list_feishu_files, create_feishu_table_in_document,
    replace_feishu_document_block,
])
def test_docx_tools_importable(tool_fn):
    """7 个 @tool 工具均可导入。"""
    assert callable(tool_fn)


# =============================================================================
# 通用反向用例：agent_name 缺失 / endpoint 解析失败
# =============================================================================


def test_create_docx_tool_no_agent_name_returns_error():
    """runtime.state.agent_name 缺失 → 返回 ERROR_NO_AGENT_NAME 错误。"""
    runtime = _make_runtime(agent_name=None)
    result = asyncio.run(create_feishu_document(title="x", runtime=runtime))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "智能体" in payload["error"]


def test_create_docx_tool_endpoint_resolve_fails_returns_hint(monkeypatch):
    """endpoint 解析失败 → 返回「飞书渠道缺失」指引。"""
    async def _fake_resolve(rt):
        return None
    monkeypatch.setattr(FeishuDocxTools, "resolve_current_endpoint", _fake_resolve)
    result = asyncio.run(create_feishu_document(title="x", runtime=_make_runtime()))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "智能体" in payload["error"] or "飞书渠道" in payload["error"]


def test_create_docx_tool_empty_title_returns_error():
    """title 缺失 → 错误提示。"""
    result = asyncio.run(create_feishu_document(title="", runtime=_make_runtime()))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "title" in payload["error"]


# =============================================================================
# create_feishu_document
# =============================================================================


def test_create_docx_tool_happy_path(monkeypatch):
    client = _make_lark_client()
    mock_resp = MagicMock()
    mock_resp.success.return_value = True
    mock_resp.data.document_id = "d_001"
    client.docx.v1.document.create.return_value = mock_resp
    _patch_endpoint(monkeypatch, client)

    result = asyncio.run(create_feishu_document(title="x", runtime=_make_runtime()))
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert payload["document_id"] == "d_001"
    assert payload["url"] == "https://feishu.cn/docx/d_001"


def test_create_docx_tool_api_failure_returns_error_payload(monkeypatch):
    client = _make_lark_client()
    mock_resp = MagicMock()
    mock_resp.success.return_value = False
    mock_resp.code = 403
    mock_resp.msg = "no permission"
    mock_resp.get_log_id.return_value = "log_x"  # 显式 string，避免 MagicMock
    client.docx.v1.document.create.return_value = mock_resp
    _patch_endpoint(monkeypatch, client)

    result = asyncio.run(create_feishu_document(title="x", runtime=_make_runtime()))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert payload["code"] == 403


# =============================================================================
# get_feishu_document_content
# =============================================================================


def test_get_docx_content_happy_path(monkeypatch):
    client = _make_lark_client()
    mock_resp = MagicMock()
    mock_resp.success.return_value = True
    mock_resp.data.content = "全文内容"
    client.docx.v1.document_raw_content.get.return_value = mock_resp
    _patch_endpoint(monkeypatch, client)

    result = asyncio.run(get_feishu_document_content("d_001", runtime=_make_runtime()))
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert payload["content"] == "全文内容"


def test_get_docx_content_missing_doc_id_returns_error():
    result = asyncio.run(get_feishu_document_content("", runtime=_make_runtime()))
    payload = _parse_message_content(result)
    assert payload["success"] is False


# =============================================================================
# append_feishu_document_blocks
# =============================================================================


def test_append_docx_blocks_happy_path(monkeypatch):
    client = _make_lark_client()
    mock_resp = MagicMock()
    mock_resp.success.return_value = True
    # client 不读 data 字段；保证 data=None 不抛错
    mock_resp.data = None
    client.docx.v1.document_block_children.create.return_value = mock_resp
    _patch_endpoint(monkeypatch, client)

    blocks = [{"block_type": 2, "text": {"rich_text": [{"text_run": {"content": "x"}}]}}]
    result = asyncio.run(append_feishu_document_blocks("d_001", blocks, runtime=_make_runtime()))
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert payload["child_count"] == 1


def test_append_docx_blocks_empty_blocks_returns_error():
    result = asyncio.run(append_feishu_document_blocks("d_001", [], runtime=_make_runtime()))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "blocks" in payload["error"]


# =============================================================================
# share_feishu_document
# =============================================================================


def test_share_docx_happy_path():
    result = asyncio.run(share_feishu_document("d_001", runtime=_make_runtime()))
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert payload["url"] == "https://feishu.cn/docx/d_001"
    # 中文文案透传校验
    assert "ACL" in payload["permission_hint"] or "分享" in payload["permission_hint"]


def test_share_docx_missing_id_returns_error():
    result = asyncio.run(share_feishu_document("", runtime=_make_runtime()))
    payload = _parse_message_content(result)
    assert payload["success"] is False


# =============================================================================
# list_feishu_files
# =============================================================================


def test_list_feishu_files_happy_path(monkeypatch):
    client = _make_lark_client()
    mock_resp = MagicMock()
    mock_resp.success.return_value = True
    mock_resp.data.files = [{"token": "f1", "name": "a.docx"}]
    client.drive.v1.file.list.return_value = mock_resp
    _patch_endpoint(monkeypatch, client)

    result = asyncio.run(list_feishu_files(folder_token="fld", runtime=_make_runtime()))
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert len(payload["files"]) == 1


# =============================================================================
# create_feishu_table_in_document
# =============================================================================


def test_create_table_in_docx_happy_path(monkeypatch):
    client = _make_lark_client()
    mock_resp = MagicMock()
    mock_resp.success.return_value = True
    client.docx.v1.document_block_children.create.return_value = mock_resp
    _patch_endpoint(monkeypatch, client)

    rows = [["列 A", "列 B"], ["a1", "b1"], ["a2", "b2"]]
    result = asyncio.run(create_feishu_table_in_document("d_001", rows, runtime=_make_runtime()))
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert payload["row_count"] == 3
    assert payload["col_count"] == 2


def test_create_table_in_docx_normalizes_columns_to_max_width(monkeypatch):
    """列数不一致时自动补空字符串到 max 列宽。"""
    client = _make_lark_client()
    mock_resp = MagicMock()
    mock_resp.success.return_value = True
    client.docx.v1.document_block_children.create.return_value = mock_resp
    _patch_endpoint(monkeypatch, client)

    rows = [["a", "b", "c"], ["1", "2"]]  # 第二行缺一列
    result = asyncio.run(create_feishu_table_in_document("d_001", rows, runtime=_make_runtime()))
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert payload["col_count"] == 3


def test_create_table_in_docx_empty_rows_returns_error():
    result = asyncio.run(create_feishu_table_in_document("d_001", [], runtime=_make_runtime()))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "rows" in payload["error"]


# =============================================================================
# replace_feishu_document_block
# =============================================================================


def test_replace_docx_block_appends_new_blocks(monkeypatch):
    """飞书 docx 不支持原地替换 → 工具退化为追加 + 在结果中标注 note。"""
    client = _make_lark_client()
    mock_resp = MagicMock()
    mock_resp.success.return_value = True
    client.docx.v1.document_block_children.create.return_value = mock_resp
    _patch_endpoint(monkeypatch, client)

    new_blocks = [{"block_type": 2, "text": {"rich_text": []}}]
    result = asyncio.run(replace_feishu_document_block(
        document_id="d_001", block_id="b_old", new_blocks=new_blocks, runtime=_make_runtime()
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert payload["new_blocks_appended"] == 1
    assert payload["target_block_id"] == "b_old"
    assert "note" in payload