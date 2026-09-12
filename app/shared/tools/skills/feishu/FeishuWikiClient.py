#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FeishuWikiClient - 飞书 wiki v2 服务客户端

职责：
    - 封装飞书 wiki v2 Open API（节点管理 + 把已有 docx 包装为 wiki 节点）
    - 提供 ``get_node`` / ``create_node`` / ``list_nodes`` / ``move_node`` /
      ``rename_node`` 异步方法
    - 提供 ``create_wiki_node_from_markdown`` 一键入口（docx.create +
      blocks.append + wiki.create_node 组合）
    - 失败统一返回 ``{"success": False, "error", "code"}``，不抛异常

复用：
    - ``FeishuDocxClient`` 实例注入到 ``__init__``，避免 wiki 内重复
      实现 docx 调用（DRY 原则；测试时可独立 mock docx）
    - ``_md_to_blocks`` helper 通过 docx client 间接使用

约束：
    - wiki 节点的 ``obj_token`` 必须引用已有 docx / sheet（飞书 v2 不提供
      直接上传 .md → docx 的 API）；本 client 不内置 docx 转换逻辑
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from app.shared.tools.skills.feishu.FeishuDocxClient import FeishuDocxClient, _md_to_blocks

logger = logging.getLogger(__name__)


class FeishuWikiClient:
    """飞书 wiki v2 服务客户端。

    Attributes:
        _client: 已构造好的 ``lark.Client`` 实例
        _docx: ``FeishuDocxClient`` 实例（提供 create_document 与 append_block_children）
    """

    def __init__(self, lark_client, docx_client: FeishuDocxClient):
        """初始化。

        Args:
            lark_client: ``lark.Client`` 实例
            docx_client: ``FeishuDocxClient`` 实例；``create_wiki_node_from_markdown``
                一键入口必须依赖 docx 能力
        """
        self._client = lark_client
        self._docx = docx_client

    async def get_node(
        self,
        token: str,
        obj_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """解析 token（node_token 或 doc token）→ 节点信息。

        对应 ``GET /open-apis/wiki/v2/spaces/get_node?token=xxx``。

        Args:
            token: 节点 token 或 doc token
            obj_type: 可选，飞书文档类型（docx / sheet 等）辅助解析

        Returns:
            dict: 成功 ``{"success": True, "node_token", "obj_token",
                "obj_type", "title"}``；失败同上
        """
        if not token:
            return {"success": False, "error": "token 缺失"}
        try:
            from lark_oapi.api.wiki.v2 import GetNodeSpaceRequest
            builder = GetNodeSpaceRequest.builder().token(token)
            if obj_type:
                builder = builder.obj_type(obj_type)
            req = builder.build()
            response = await asyncio.to_thread(self._client.wiki.v2.space.get_node, req)
            if not response.success():
                return {
                    "success": False,
                    "code": response.code,
                    "msg": response.msg,
                    "log_id": response.get_log_id(),
                }
            node = response.data.node if response.data and response.data.node else None
            return {
                "success": True,
                "node_token": getattr(node, "node_token", None) if node else None,
                "obj_token": getattr(node, "obj_token", None) if node else None,
                "obj_type": getattr(node, "obj_type", None) if node else None,
                "title": getattr(node, "title", None) if node else None,
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("[feishu_wiki_client] get_node 失败: %s", e)
            return {"success": False, "error": str(e)}

    async def create_node(
        self,
        space_id: str,
        title: str,
        obj_token: str,
        parent_node_token: Optional[str] = None,
        obj_type: str = "docx",
    ) -> Dict[str, Any]:
        """在指定知识空间下创建节点（包装已有 docx）。

        对应 ``POST /open-apis/wiki/v2/spaces/{space_id}/nodes``。

        Args:
            space_id: 飞书知识空间 ID
            title: 节点标题
            obj_token: 已有的 docx / sheet 的 token（飞书 wiki 节点必须引用）
            parent_node_token: 父节点 token；空则放空间根目录
            obj_type: 飞书文档类型，默认 ``"docx"``

        Returns:
            dict: 成功 ``{"success": True, "node_token", "obj_token",
                "wiki_url"}``；失败同上
        """
        if not space_id:
            return {"success": False, "error": "space_id 缺失"}
        if not title:
            return {"success": False, "error": "title 缺失"}
        if not obj_token:
            return {"success": False, "error": "obj_token 缺失（必须先创建 docx）"}
        try:
            from lark_oapi.api.wiki.v2 import (
                CreateSpaceNodeRequest,
                CreateSpaceNodeRequestBody,
            )
            body = (
                CreateSpaceNodeRequestBody.builder()
                .obj_type(obj_type)
                .obj_token(obj_token)
                .node_type("origin")
                .title(title)
            )
            if parent_node_token:
                body = body.parent_node_token(parent_node_token)
            req = (
                CreateSpaceNodeRequest.builder()
                .space_id(space_id)
                .request_body(body.build())
                .build()
            )
            response = await asyncio.to_thread(self._client.wiki.v2.space_node.create, req)
            if not response.success():
                return {
                    "success": False,
                    "code": response.code,
                    "msg": response.msg,
                    "log_id": response.get_log_id(),
                }
            data = response.data
            node = getattr(data, "node", None) if data else None
            node_token = getattr(node, "node_token", None) if node else None
            return {
                "success": True,
                "node_token": node_token,
                "obj_token": obj_token,
                "wiki_url": _build_wiki_url(space_id, node_token),
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("[feishu_wiki_client] create_node 失败: %s", e)
            return {"success": False, "error": str(e)}

    async def list_nodes(
        self,
        space_id: str,
        parent_node_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """列出父节点下的子节点。

        对应 ``GET /open-apis/wiki/v2/spaces/{space_id}/nodes?parent_node_token=xxx``。

        Args:
            space_id: 知识空间 ID
            parent_node_token: 父节点 token；空则列根

        Returns:
            dict: 成功 ``{"success": True, "nodes": list[dict]}``；
                失败同上
        """
        if not space_id:
            return {"success": False, "error": "space_id 缺失"}
        try:
            from lark_oapi.api.wiki.v2 import ListSpaceNodeRequest
            builder = ListSpaceNodeRequest.builder().space_id(space_id)
            if parent_node_token:
                builder = builder.parent_node_token(parent_node_token)
            req = builder.build()
            response = await asyncio.to_thread(self._client.wiki.v2.space_node.list, req)
            if not response.success():
                return {
                    "success": False,
                    "code": response.code,
                    "msg": response.msg,
                    "log_id": response.get_log_id(),
                }
            data = response.data
            items = getattr(data, "items", []) if data else []
            return {"success": True, "nodes": list(items)}
        except Exception as e:  # noqa: BLE001
            logger.warning("[feishu_wiki_client] list_nodes 失败: %s", e)
            return {"success": False, "error": str(e)}

    async def move_node(
        self,
        space_id: str,
        node_token: str,
        target_parent_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """移动节点到新父节点下。

        对应 ``POST /open-apis/wiki/v2/spaces/{space_id}/nodes/{node_token}/move``。

        Args:
            space_id: 知识空间 ID
            node_token: 节点 token
            target_parent_token: 目标父节点 token；空则移到空间根目录

        Returns:
            dict: 成功 ``{"success": True, "node_token"}``；失败同上
        """
        if not space_id:
            return {"success": False, "error": "space_id 缺失"}
        if not node_token:
            return {"success": False, "error": "node_token 缺失"}
        try:
            from lark_oapi.api.wiki.v2 import (
                MoveSpaceNodeRequest,
                MoveSpaceNodeRequestBody,
            )
            body = MoveSpaceNodeRequestBody.builder()
            if target_parent_token:
                body = body.target_parent_token(target_parent_token)
            req = (
                MoveSpaceNodeRequest.builder()
                .space_id(space_id)
                .node_token(node_token)
                .request_body(body.build())
                .build()
            )
            response = await asyncio.to_thread(self._client.wiki.v2.space_node.move, req)
            if not response.success():
                return {
                    "success": False,
                    "code": response.code,
                    "msg": response.msg,
                    "log_id": response.get_log_id(),
                }
            return {"success": True, "node_token": node_token}
        except Exception as e:  # noqa: BLE001
            logger.warning("[feishu_wiki_client] move_node 失败: %s", e)
            return {"success": False, "error": str(e)}

    async def rename_node(
        self,
        space_id: str,
        node_token: str,
        new_title: str,
    ) -> Dict[str, Any]:
        """修改节点标题。

        对应 ``PATCH /open-apis/wiki/v2/spaces/{space_id}/nodes/{node_token}``。

        Args:
            space_id: 知识空间 ID
            node_token: 节点 token
            new_title: 新标题

        Returns:
            dict: 成功 ``{"success": True, "node_token", "new_title"}``；
                失败同上
        """
        if not space_id:
            return {"success": False, "error": "space_id 缺失"}
        if not node_token:
            return {"success": False, "error": "node_token 缺失"}
        if not new_title:
            return {"success": False, "error": "new_title 缺失"}
        try:
            from lark_oapi.api.wiki.v2 import (
                UpdateSpaceNodeRequest,
                UpdateSpaceNodeRequestBody,
            )
            body = (
                UpdateSpaceNodeRequestBody.builder()
                .title(new_title)
                .build()
            )
            req = (
                UpdateSpaceNodeRequest.builder()
                .space_id(space_id)
                .node_token(node_token)
                .request_body(body)
                .build()
            )
            response = await asyncio.to_thread(self._client.wiki.v2.space_node.update, req)
            if not response.success():
                return {
                    "success": False,
                    "code": response.code,
                    "msg": response.msg,
                    "log_id": response.get_log_id(),
                }
            return {"success": True, "node_token": node_token, "new_title": new_title}
        except Exception as e:  # noqa: BLE001
            logger.warning("[feishu_wiki_client] rename_node 失败: %s", e)
            return {"success": False, "error": str(e)}

    async def create_wiki_node_from_markdown(
        self,
        space_id: str,
        title: str,
        markdown_content: str,
        parent_node_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """一键组合：md → docx → wiki 节点。

        流程：
            1. ``self._docx.create_document(title)`` 拿到 document_id
            2. ``_md_to_blocks(markdown_content)`` 解析 markdown
            3. ``self._docx.append_block_children(document_id, root, blocks)``
               写入内容
            4. ``self.create_node(space_id, title, document_id)`` 包装为 wiki 节点

        任一中间步骤失败 → 整体失败（docx 创建失败时不会留下孤儿 wiki 节点，
        因为后续步骤不会执行）。

        Args:
            space_id: 飞书知识空间 ID
            title: 节点标题（同时也是 docx 标题）
            markdown_content: markdown 文本
            parent_node_token: 父节点 token；空则放空间根目录

        Returns:
            dict: 成功 ``{"success": True, "node_token", "wiki_url",
                "document_id", "md_blocks_count"}``；失败同上
        """
        if not space_id:
            return {"success": False, "error": "space_id 缺失"}
        if not title:
            return {"success": False, "error": "title 缺失"}
        if not markdown_content:
            return {"success": False, "error": "markdown_content 缺失"}

        # Step 1: 创建空 docx
        create_resp = await self._docx.create_document(title)
        if not create_resp.get("success"):
            return {
                "success": False,
                "error": f"创建 docx 失败: {create_resp.get('error') or create_resp.get('msg')}",
                "stage": "create_document",
                "upstream": create_resp,
            }
        document_id = create_resp.get("document_id")
        if not document_id:
            return {
                "success": False,
                "error": "create_document 未返回 document_id",
                "stage": "create_document",
                "upstream": create_resp,
            }

        # Step 2: md → blocks
        try:
            blocks = _md_to_blocks(markdown_content)
        except Exception as e:  # noqa: BLE001
            logger.warning("[feishu_wiki_client] _md_to_blocks 失败: %s", e)
            return {
                "success": False,
                "error": f"markdown 解析失败: {e}",
                "stage": "md_to_blocks",
                "document_id": document_id,
            }

        if not blocks:
            return {
                "success": False,
                "error": "markdown 解析后为空（无任何 block）",
                "stage": "md_to_blocks",
                "document_id": document_id,
            }

        # Step 3: 写入 blocks（飞书 docx 的 root block_id 通常为 document_id 本身）
        append_resp = await self._docx.append_block_children(
            document_id=document_id,
            block_id=document_id,
            children=blocks,
        )
        if not append_resp.get("success"):
            return {
                "success": False,
                "error": (
                    f"写入 docx blocks 失败: "
                    f"{append_resp.get('error') or append_resp.get('msg')}"
                ),
                "stage": "append_block_children",
                "document_id": document_id,
                "md_blocks_count": len(blocks),
                "upstream": append_resp,
            }

        # Step 4: 包装为 wiki 节点
        wiki_resp = await self.create_node(
            space_id=space_id,
            title=title,
            obj_token=document_id,
            parent_node_token=parent_node_token,
        )
        if not wiki_resp.get("success"):
            return {
                "success": False,
                "error": (
                    f"创建 wiki 节点失败: "
                    f"{wiki_resp.get('error') or wiki_resp.get('msg')}"
                ),
                "stage": "create_node",
                "document_id": document_id,
                "md_blocks_count": len(blocks),
                "upstream": wiki_resp,
            }

        return {
            "success": True,
            "node_token": wiki_resp.get("node_token"),
            "wiki_url": wiki_resp.get("wiki_url"),
            "document_id": document_id,
            "md_blocks_count": len(blocks),
        }


def _build_wiki_url(space_id: Optional[str], node_token: Optional[str]) -> Optional[str]:
    """构造飞书 wiki URL（仅供前端访问）。"""
    if not space_id or not node_token:
        return None
    return f"https://feishu.cn/wiki/{space_id}/{node_token}"