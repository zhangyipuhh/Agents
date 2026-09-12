# -*- coding:utf-8 -*-
"""
test_feishu_wiki_client - FeishuWikiClient 单元测试

覆盖：
    - 6 个基础方法（get/create/list/move/rename/get_node）
    - create_wiki_node_from_markdown 一键入口（含反向用例：docx 失败不留下孤儿 wiki 节点）
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.shared.tools.skills.feishu.FeishuDocxClient import FeishuDocxClient
from app.shared.tools.skills.feishu.FeishuWikiClient import FeishuWikiClient


def _make_lark_client():
    import lark_oapi as lark
    return lark.Client.builder().app_id("a").app_secret("s").build()


def _make_wiki():
    lark_client = _make_lark_client()
    docx_client = FeishuDocxClient(lark_client)
    return FeishuWikiClient(lark_client, docx_client=docx_client)


# =============================================================================
# get_node
# =============================================================================


def test_wiki_get_node_happy_path():
    wiki = _make_wiki()
    mock_resp = MagicMock()
    mock_resp.success.return_value = True
    node = MagicMock()
    node.node_token = "n_001"
    node.obj_token = "d_001"
    node.obj_type = "docx"
    node.title = "标题"
    mock_resp.data.node = node
    wiki._client.wiki.v2.space.get_node.return_value = mock_resp

    resp = asyncio.run(wiki.get_node("d_001"))
    assert resp["success"] is True
    assert resp["node_token"] == "n_001"
    assert resp["obj_token"] == "d_001"
    assert resp["obj_type"] == "docx"
    assert resp["title"] == "标题"


def test_wiki_get_node_empty_token_returns_error():
    wiki = _make_wiki()
    resp = asyncio.run(wiki.get_node(""))
    assert resp["success"] is False
    assert "token" in resp["error"]


def test_wiki_get_node_api_failure_returns_code():
    wiki = _make_wiki()
    mock_resp = MagicMock()
    mock_resp.success.return_value = False
    mock_resp.code = 404
    mock_resp.msg = "not found"
    wiki._client.wiki.v2.space.get_node.return_value = mock_resp

    resp = asyncio.run(wiki.get_node("missing"))
    assert resp["success"] is False
    assert resp["code"] == 404


# =============================================================================
# create_node
# =============================================================================


def test_wiki_create_node_happy_path():
    wiki = _make_wiki()
    mock_resp = MagicMock()
    mock_resp.success.return_value = True
    node = MagicMock()
    node.node_token = "n_new"
    mock_resp.data.node = node
    wiki._client.wiki.v2.space_node.create.return_value = mock_resp

    resp = asyncio.run(
        wiki.create_node(
            space_id="sp_001", title="新节点", obj_token="d_001", parent_node_token="n_parent"
        )
    )
    assert resp["success"] is True
    assert resp["node_token"] == "n_new"
    assert resp["obj_token"] == "d_001"
    assert resp["wiki_url"] == "https://feishu.cn/wiki/sp_001/n_new"


def test_wiki_create_node_missing_space_id():
    wiki = _make_wiki()
    resp = asyncio.run(wiki.create_node(space_id="", title="x", obj_token="d_001"))
    assert resp["success"] is False
    assert "space_id" in resp["error"]


def test_wiki_create_node_missing_obj_token():
    wiki = _make_wiki()
    resp = asyncio.run(wiki.create_node(space_id="sp_1", title="x", obj_token=""))
    assert resp["success"] is False
    assert "obj_token" in resp["error"]


def test_wiki_create_node_permission_denied_returns_error():
    """反向用例：wiki ACL 拒绝 → success=False（不抛异常）。"""
    wiki = _make_wiki()
    mock_resp = MagicMock()
    mock_resp.success.return_value = False
    mock_resp.code = 99991663
    mock_resp.msg = "no permission to space"
    wiki._client.wiki.v2.space_node.create.return_value = mock_resp

    resp = asyncio.run(wiki.create_node(space_id="sp_1", title="x", obj_token="d_1"))
    assert resp["success"] is False
    assert resp["code"] == 99991663


# =============================================================================
# list_nodes
# =============================================================================


def test_wiki_list_nodes_with_parent():
    wiki = _make_wiki()
    mock_resp = MagicMock()
    mock_resp.success.return_value = True
    mock_resp.data.items = [{"node_token": "n_a"}, {"node_token": "n_b"}]
    wiki._client.wiki.v2.space_node.list.return_value = mock_resp

    resp = asyncio.run(wiki.list_nodes("sp_001", parent_node_token="n_root"))
    assert resp["success"] is True
    assert len(resp["nodes"]) == 2


def test_wiki_list_nodes_root_when_parent_none():
    wiki = _make_wiki()
    mock_resp = MagicMock()
    mock_resp.success.return_value = True
    mock_resp.data.items = []
    wiki._client.wiki.v2.space_node.list.return_value = mock_resp

    resp = asyncio.run(wiki.list_nodes("sp_001"))
    assert resp["success"] is True
    assert resp["nodes"] == []


# =============================================================================
# move_node / rename_node
# =============================================================================


def test_wiki_move_node_happy_path():
    wiki = _make_wiki()
    mock_resp = MagicMock()
    mock_resp.success.return_value = True
    wiki._client.wiki.v2.space_node.move.return_value = mock_resp

    resp = asyncio.run(wiki.move_node("sp_001", "n_a", "n_b"))
    assert resp["success"] is True
    assert resp["node_token"] == "n_a"


def test_wiki_move_node_to_root_when_target_none():
    wiki = _make_wiki()
    mock_resp = MagicMock()
    mock_resp.success.return_value = True
    wiki._client.wiki.v2.space_node.move.return_value = mock_resp

    resp = asyncio.run(wiki.move_node("sp_001", "n_a"))
    assert resp["success"] is True


def test_wiki_rename_node_happy_path():
    wiki = _make_wiki()
    mock_resp = MagicMock()
    mock_resp.success.return_value = True
    wiki._client.wiki.v2.space_node.update.return_value = mock_resp

    resp = asyncio.run(wiki.rename_node("sp_001", "n_a", "新标题"))
    assert resp["success"] is True
    assert resp["new_title"] == "新标题"


def test_wiki_rename_node_empty_title_returns_error():
    wiki = _make_wiki()
    resp = asyncio.run(wiki.rename_node("sp_001", "n_a", ""))
    assert resp["success"] is False
    assert "new_title" in resp["error"]


# =============================================================================
# create_wiki_node_from_markdown 一键入口
# =============================================================================


def test_wiki_create_from_markdown_happy_path():
    """组合调用成功：docx.create + blocks.append + wiki.create_node。"""
    wiki = _make_wiki()
    docx = wiki._docx

    # docx.create_document → success
    create_resp = MagicMock()
    create_resp.success.return_value = True
    create_resp.data.document_id = "d_combined"
    docx._client.docx.v1.document.create.return_value = create_resp

    # docx.append_block_children → success
    append_resp = MagicMock()
    append_resp.success.return_value = True
    docx._client.docx.v1.document_block_children.create.return_value = append_resp

    # wiki.create_node → success（mock self._client.wiki.v2.space_node.create）
    wiki_node_resp = MagicMock()
    wiki_node_resp.success.return_value = True
    node_obj = MagicMock()
    node_obj.node_token = "n_combined"
    wiki_node_resp.data.node = node_obj
    wiki._client.wiki.v2.space_node.create.return_value = wiki_node_resp

    md = "# 报告\n\n这是内容。\n\n- 项目 1\n- 项目 2\n"
    resp = asyncio.run(wiki.create_wiki_node_from_markdown(
        space_id="sp_001", title="报告", markdown_content=md
    ))
    assert resp["success"] is True
    assert resp["node_token"] == "n_combined"
    assert resp["wiki_url"] == "https://feishu.cn/wiki/sp_001/n_combined"
    assert resp["document_id"] == "d_combined"
    assert resp["md_blocks_count"] >= 2


def test_wiki_create_from_markdown_when_docx_create_fails_returns_error():
    """反向用例：docx.create 失败 → 整个流程失败，不调用 wiki.create_node。"""
    wiki = _make_wiki()
    docx = wiki._docx

    create_resp = MagicMock()
    create_resp.success.return_value = False
    create_resp.code = 403
    create_resp.msg = "no perm"
    docx._client.docx.v1.document.create.return_value = create_resp

    resp = asyncio.run(wiki.create_wiki_node_from_markdown(
        space_id="sp_001", title="报告", markdown_content="# 测试\n内容"
    ))
    assert resp["success"] is False
    assert resp["stage"] == "create_document"
    # wiki.create_node 不应被调用
    wiki._client.wiki.v2.space_node.create.assert_not_called()


def test_wiki_create_from_markdown_when_append_fails_returns_error():
    """docx.append 失败 → 整个流程失败。"""
    wiki = _make_wiki()
    docx = wiki._docx

    create_resp = MagicMock()
    create_resp.success.return_value = True
    create_resp.data.document_id = "d_x"
    docx._client.docx.v1.document.create.return_value = create_resp

    append_resp = MagicMock()
    append_resp.success.return_value = False
    append_resp.code = 500
    append_resp.msg = "append error"
    docx._client.docx.v1.document_block_children.create.return_value = append_resp

    resp = asyncio.run(wiki.create_wiki_node_from_markdown(
        space_id="sp_001", title="x", markdown_content="# H\n\n内容"
    ))
    assert resp["success"] is False
    assert resp["stage"] == "append_block_children"
    assert resp["document_id"] == "d_x"


def test_wiki_create_from_markdown_when_create_node_fails_returns_error():
    """wiki.create_node 失败 → 整个流程失败（已写入 docx 但未包装为 wiki 节点）。"""
    wiki = _make_wiki()
    docx = wiki._docx

    create_resp = MagicMock()
    create_resp.success.return_value = True
    create_resp.data.document_id = "d_x"
    docx._client.docx.v1.document.create.return_value = create_resp

    append_resp = MagicMock()
    append_resp.success.return_value = True
    docx._client.docx.v1.document_block_children.create.return_value = append_resp

    wiki_node_resp = MagicMock()
    wiki_node_resp.success.return_value = False
    wiki_node_resp.code = 99991663
    wiki_node_resp.msg = "no space perm"
    wiki._client.wiki.v2.space_node.create.return_value = wiki_node_resp

    resp = asyncio.run(wiki.create_wiki_node_from_markdown(
        space_id="sp_001", title="x", markdown_content="# H\n\n内容"
    ))
    assert resp["success"] is False
    assert resp["stage"] == "create_node"
    assert resp["document_id"] == "d_x"


def test_wiki_create_from_markdown_empty_md_returns_error():
    """反向用例：markdown_content 空字符串 → stage=md_to_blocks 失败。"""
    wiki = _make_wiki()
    resp = asyncio.run(wiki.create_wiki_node_from_markdown(
        space_id="sp_001", title="x", markdown_content=""
    ))
    assert resp["success"] is False
    assert "markdown_content" in resp["error"]


def test_wiki_create_from_markdown_whitespace_only_md_returns_error():
    """反向用例：仅有空白行的 markdown → _md_to_blocks 返回空 → stage=md_to_blocks。"""
    wiki = _make_wiki()
    # docx.create 必须成功（走到 md_to_blocks 阶段）
    create_resp = MagicMock()
    create_resp.success.return_value = True
    create_resp.data.document_id = "d_x"
    wiki._docx._client.docx.v1.document.create.return_value = create_resp

    resp = asyncio.run(wiki.create_wiki_node_from_markdown(
        space_id="sp_001", title="x", markdown_content="\n\n   \n"
    ))
    assert resp["success"] is False
    assert resp["stage"] == "md_to_blocks"


def test_wiki_create_from_markdown_requires_space_id_title_md():
    """输入校验：三个必填字段缺失 → 提前返回。"""
    wiki = _make_wiki()
    r1 = asyncio.run(wiki.create_wiki_node_from_markdown(
        space_id="", title="x", markdown_content="hi"
    ))
    assert "space_id" in r1["error"]
    r2 = asyncio.run(wiki.create_wiki_node_from_markdown(
        space_id="sp", title="", markdown_content="hi"
    ))
    assert "title" in r2["error"]