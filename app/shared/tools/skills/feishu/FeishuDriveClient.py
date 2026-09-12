#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FeishuDriveClient - 飞书 drive v1 目录服务客户端

职责：
    - 封装飞书 drive v1 Open API（列出文件夹下的文件）
    - 提供 ``list_files`` 异步方法；为 docx / sheets 工具共用
    - 失败统一返回 ``{"success": False, "error", "code"}``，不抛异常

设计：
    - 仅暴露最小公共面（列文件），不实现文件夹创建等高级 API
    - 后续如需 create_folder / move_file 等，按相同模式追加
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class FeishuDriveClient:
    """飞书 drive v1 服务客户端（docx / sheets / wiki 工具共用）。

    Attributes:
        _client: 已构造好的 ``lark.Client`` 实例
    """

    def __init__(self, lark_client):
        self._client = lark_client

    async def list_files(
        self,
        folder_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """列出文件夹下的文件。

        对应 ``GET /open-apis/drive/v1/files?folder_token=xxx``。

        Args:
            folder_token: 文件夹 token；为空则列根目录文件

        Returns:
            dict: 成功 ``{"success": True, "files": list[dict]}``；
                失败 ``{"success": False, "error", "code"}``
        """
        try:
            from lark_oapi.api.drive.v1 import ListFileRequest
            builder = ListFileRequest.builder()
            if folder_token:
                builder = builder.folder_token(folder_token)
            req = builder.build()
            response = await asyncio.to_thread(self._client.drive.v1.file.list, req)
            if not response.success():
                return {
                    "success": False,
                    "code": response.code,
                    "msg": response.msg,
                    "log_id": response.get_log_id(),
                }
            data = response.data
            files = getattr(data, "files", []) if data else []
            return {
                "success": True,
                "files": [_file_to_dict(f) for f in (files or [])],
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("[feishu_drive_client] list_files 失败: %s", e)
            return {"success": False, "error": str(e)}


def _file_to_dict(file_obj) -> Dict[str, Any]:
    """把 drive 文件对象转普通 dict（兼容嵌套对象结构）。"""
    if isinstance(file_obj, dict):
        return file_obj
    out: Dict[str, Any] = {}
    for key in ("token", "name", "type", "url", "parent_token",
                "created_time", "modified_time", "owner_id"):
        if hasattr(file_obj, key):
            out[key] = getattr(file_obj, key)
    return out