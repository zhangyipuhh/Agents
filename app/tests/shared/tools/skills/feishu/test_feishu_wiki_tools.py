# -*- coding:utf-8 -*-
"""
test_feishu_wiki_tools - FeishuWikiTools 6 个 @tool 单元测试

重点：``create_wiki_node_from_markdown`` 是用户需求「飞书知识库插入 md 文件」
的主线入口，必须有完整 happy + 反向用例覆盖。
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from app.shared.tools.skills.feishu import FeishuWikiTools
from app.shared.tools.skills.feishu.FeishuWikiTools import (
    create_wiki_node,
    create_wiki_node_from_markdown,
    get_wiki_node,
    list_wiki_nodes,
    move_wiki_node,
    rename_wiki_node,
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

    monkeypatch.setattr(FeishuWikiTools, "resolve_current_endpoint", _fake_resolve)
    monkeypatch.setattr(
        FeishuWikiTools,
        "build_lark_client",
        lambda ep: lark_client or _make_lark_client(),
    )


# =============================================================================
# 通用反向用例
# =============================================================================


def test_create_wiki_tool_no_agent_name_returns_error():
    result = asyncio.run(create_wiki_node(
        space_id="sp_1", title="x", obj_token="d_1", runtime=_make_runtime(agent_name=None)
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False


def test_create_wiki_tool_missing_obj_token_returns_error():
    """反向用例：obj_token 缺失 → 引导先创建 docx。"""
    result = asyncio.run(create_wiki_node(
        space_id="sp_1", title="x", obj_token="", runtime=_make_runtime()
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "obj_token" in payload["error"]


# =============================================================================
# create_wiki_node
# =============================================================================


def test_create_wiki_tool_happy_path(monkeypatch):
    client = _make_lark_client()
    mock_resp = MagicMock()
    mock_resp.success.return_value = True
    node = MagicMock()
    node.node_token = "n_001"
    mock_resp.data.node = node
    client.wiki.v2.space_node.create.return_value = mock_resp
    _patch_endpoint(monkeypatch, client)

    result = asyncio.run(create_wiki_node(
        space_id="sp_1", title="x", obj_token="d_001", runtime=_make_runtime()
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert payload["node_token"] == "n_001"
    assert "feishu.cn/wiki" in payload["wiki_url"]


def test_create_wiki_tool_permission_denied_returns_error(monkeypatch):
    """反向用例：wiki ACL 拒绝 → success=False（不抛异常）。"""
    client = _make_lark_client()
    mock_resp = MagicMock()
    mock_resp.success.return_value = False
    mock_resp.code = 99991663
    mock_resp.msg = "no perm"
    mock_resp.get_log_id.return_value = "log_wiki"
    client.wiki.v2.space_node.create.return_value = mock_resp
    _patch_endpoint(monkeypatch, client)

    result = asyncio.run(create_wiki_node(
        space_id="sp_1", title="x", obj_token="d_001", runtime=_make_runtime()
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert payload["code"] == 99991663


# =============================================================================
# get_wiki_node / list_wiki_nodes / move_wiki_node / rename_wiki_node
# =============================================================================


def test_get_wiki_node_happy_path(monkeypatch):
    client = _make_lark_client()
    mock_resp = MagicMock()
    mock_resp.success.return_value = True
    node = MagicMock()
    node.node_token = "n_001"
    node.obj_token = "d_001"
    node.obj_type = "docx"
    node.title = "标题"
    mock_resp.data.node = node
    client.wiki.v2.space.get_node.return_value = mock_resp
    _patch_endpoint(monkeypatch, client)

    result = asyncio.run(get_wiki_node("d_001", runtime=_make_runtime()))
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert payload["node_token"] == "n_001"


def test_get_wiki_node_empty_token_returns_error():
    result = asyncio.run(get_wiki_node("", runtime=_make_runtime()))
    payload = _parse_message_content(result)
    assert payload["success"] is False


def test_list_wiki_nodes_happy_path(monkeypatch):
    client = _make_lark_client()
    mock_resp = MagicMock()
    mock_resp.success.return_value = True
    mock_resp.data.items = [{"node_token": "n_a"}]
    client.wiki.v2.space_node.list.return_value = mock_resp
    _patch_endpoint(monkeypatch, client)

    result = asyncio.run(list_wiki_nodes("sp_1", parent_node_token="n_root", runtime=_make_runtime()))
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert len(payload["nodes"]) == 1


def test_move_wiki_node_happy_path(monkeypatch):
    client = _make_lark_client()
    mock_resp = MagicMock()
    mock_resp.success.return_value = True
    client.wiki.v2.space_node.move.return_value = mock_resp
    _patch_endpoint(monkeypatch, client)

    result = asyncio.run(move_wiki_node(
        space_id="sp_1", node_token="n_a", target_parent_token="n_b", runtime=_make_runtime()
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is True


def test_rename_wiki_node_happy_path(monkeypatch):
    client = _make_lark_client()
    mock_resp = MagicMock()
    mock_resp.success.return_value = True
    client.wiki.v2.space_node.update.return_value = mock_resp
    _patch_endpoint(monkeypatch, client)

    result = asyncio.run(rename_wiki_node(
        space_id="sp_1", node_token="n_a", new_title="新标题", runtime=_make_runtime()
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert payload["new_title"] == "新标题"


def test_rename_wiki_node_empty_title_returns_error():
    result = asyncio.run(rename_wiki_node(
        space_id="sp_1", node_token="n_a", new_title="", runtime=_make_runtime()
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False


# =============================================================================
# create_wiki_node_from_markdown 一键入口
# =============================================================================


def test_create_wiki_node_from_markdown_happy_path(monkeypatch):
    """一键入口：md → docx → wiki 节点成功。"""
    client = _make_lark_client()
    # docx.create_document 成功
    create_docx_resp = MagicMock()
    create_docx_resp.success.return_value = True
    create_docx_resp.data.document_id = "d_combined"
    client.docx.v1.document.create.return_value = create_docx_resp
    # docx.append_block_children 成功
    append_resp = MagicMock()
    append_resp.success.return_value = True
    client.docx.v1.document_block_children.create.return_value = append_resp
    # wiki.create_node 成功
    wiki_resp = MagicMock()
    wiki_resp.success.return_value = True
    node = MagicMock()
    node.node_token = "n_combined"
    wiki_resp.data.node = node
    client.wiki.v2.space_node.create.return_value = wiki_resp
    _patch_endpoint(monkeypatch, client)

    md = "# 报告\n\n## 章节\n- 项目 1\n- 项目 2\n"
    result = asyncio.run(create_wiki_node_from_markdown(
        space_id="sp_001", title="报告", markdown_content=md, runtime=_make_runtime()
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is True
    assert payload["node_token"] == "n_combined"
    assert payload["document_id"] == "d_combined"
    assert payload["md_blocks_count"] >= 3
    assert payload["wiki_url"] == "https://feishu.cn/wiki/sp_001/n_combined"


def test_create_wiki_node_from_markdown_docx_failure_no_orphan(monkeypatch):
    """反向用例：docx.create 失败 → wiki.create_node 不被调用（无孤儿 wiki 节点）。"""
    client = _make_lark_client()
    create_docx_resp = MagicMock()
    create_docx_resp.success.return_value = False
    create_docx_resp.code = 403
    create_docx_resp.msg = "no perm"
    create_docx_resp.get_log_id.return_value = "log_x"
    client.docx.v1.document.create.return_value = create_docx_resp
    _patch_endpoint(monkeypatch, client)

    result = asyncio.run(create_wiki_node_from_markdown(
        space_id="sp_001", title="报告", markdown_content="# 测试\n内容",
        runtime=_make_runtime(),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert payload["stage"] == "create_document"
    client.wiki.v2.space_node.create.assert_not_called()


def test_create_wiki_node_from_markdown_append_failure_returns_error(monkeypatch):
    client = _make_lark_client()
    create_docx_resp = MagicMock()
    create_docx_resp.success.return_value = True
    create_docx_resp.data.document_id = "d_x"
    client.docx.v1.document.create.return_value = create_docx_resp
    append_resp = MagicMock()
    append_resp.success.return_value = False
    append_resp.code = 500
    append_resp.msg = "boom"
    append_resp.get_log_id.return_value = "log_y"
    client.docx.v1.document_block_children.create.return_value = append_resp
    _patch_endpoint(monkeypatch, client)

    result = asyncio.run(create_wiki_node_from_markdown(
        space_id="sp_001", title="x", markdown_content="# H\n\n内容",
        runtime=_make_runtime(),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert payload["stage"] == "append_block_children"


def test_create_wiki_node_from_markdown_wiki_create_failure(monkeypatch):
    """反向用例：wiki.create_node 失败 → 整体失败（docx 已写入但未包装为 wiki 节点）。"""
    client = _make_lark_client()
    create_docx_resp = MagicMock()
    create_docx_resp.success.return_value = True
    create_docx_resp.data.document_id = "d_x"
    client.docx.v1.document.create.return_value = create_docx_resp
    append_resp = MagicMock()
    append_resp.success.return_value = True
    client.docx.v1.document_block_children.create.return_value = append_resp
    wiki_resp = MagicMock()
    wiki_resp.success.return_value = False
    wiki_resp.code = 99991663
    wiki_resp.msg = "no space perm"
    wiki_resp.get_log_id.return_value = "log_z"
    client.wiki.v2.space_node.create.return_value = wiki_resp
    _patch_endpoint(monkeypatch, client)

    result = asyncio.run(create_wiki_node_from_markdown(
        space_id="sp_001", title="x", markdown_content="# H\n\n内容",
        runtime=_make_runtime(),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert payload["stage"] == "create_node"


def test_create_wiki_node_from_markdown_empty_content_returns_error():
    """反向用例：markdown_content 空 → 提前拦截。"""
    result = asyncio.run(create_wiki_node_from_markdown(
        space_id="sp_001", title="x", markdown_content="", runtime=_make_runtime()
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "markdown_content" in payload["error"]


def test_create_wiki_node_from_markdown_whitespace_only_md_returns_error(monkeypatch):
    """反向用例：仅有空白行的 md → stage=md_to_blocks 拦截。"""
    client = _make_lark_client()
    create_docx_resp = MagicMock()
    create_docx_resp.success.return_value = True
    create_docx_resp.data.document_id = "d_x"
    client.docx.v1.document.create.return_value = create_docx_resp
    _patch_endpoint(monkeypatch, client)

    result = asyncio.run(create_wiki_node_from_markdown(
        space_id="sp_001", title="x", markdown_content="\n\n   \n",
        runtime=_make_runtime(),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert payload["stage"] == "md_to_blocks"


def test_create_wiki_node_from_markdown_requires_space_id():
    result = asyncio.run(create_wiki_node_from_markdown(
        space_id="", title="x", markdown_content="hi", runtime=_make_runtime()
    ))
    payload = _parse_message_content(result)
    assert "space_id" in payload["error"]


def test_create_wiki_node_from_markdown_requires_title():
    result = asyncio.run(create_wiki_node_from_markdown(
        space_id="sp", title="", markdown_content="hi", runtime=_make_runtime()
    ))
    payload = _parse_message_content(result)
    assert "title" in payload["error"]


def test_create_wiki_node_from_markdown_no_agent_name_returns_error():
    """agent_name 缺失 → ERROR_NO_AGENT_NAME（不进入 client 路径）。"""
    result = asyncio.run(create_wiki_node_from_markdown(
        space_id="sp_1", title="x", markdown_content="hi",
        runtime=_make_runtime(agent_name=None),
    ))
    payload = _parse_message_content(result)
    assert payload["success"] is False
    assert "智能体" in payload["error"]