#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FeishuSheetsClient - 飞书 sheets v3 服务客户端

职责：
    - 封装飞书 sheets v3 Open API（创建 spreadsheet / 读写单元格值）
    - 提供 ``create_spreadsheet`` / ``write_values`` / ``read_values`` 异步方法
    - 失败统一返回 ``{"success": False, "error", "code"}``，不抛异常

注意：
    - 写入 / 读取走 sheets v2 values 接口（项目主流用法与官方文档一致）；
      创建走 sheets v3 spreadsheets 接口（最新 endpoint）
    - 写入 range 形如 ``{sheet_id}!A1:D10``；首次创建后默认有 1 个 sheet，
      由 ``create_spreadsheet`` 返回 ``default_sheet_id`` 供后续写入使用
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class FeishuSheetsClient:
    """飞书 sheets v3 服务客户端。

    Attributes:
        _client: 已构造好的 ``lark.Client`` 实例（由调用方注入）
    """

    def __init__(self, lark_client):
        self._client = lark_client

    async def create_spreadsheet(
        self,
        title: str,
        folder_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """创建飞书 spreadsheet。

        对应 ``POST /open-apis/sheets/v3/spreadsheets``。

        Args:
            title: 表格标题
            folder_token: drive 文件夹 token；空则落根目录

        Returns:
            dict: 成功 ``{"success": True, "spreadsheet_token", "url",
                "default_sheet_id"}``；失败同上
        """
        try:
            from lark_oapi.api.sheets.v3 import (
                CreateSpreadsheetRequest,
                CreateSpreadsheetRequestBody,
            )
            body = CreateSpreadsheetRequestBody.builder().title(title)
            if folder_token:
                body = body.folder_token(folder_token)
            req = (
                CreateSpreadsheetRequest.builder()
                .request_body(body.build())
                .build()
            )
            response = await asyncio.to_thread(
                self._client.sheets.v3.spreadsheet.create, req
            )
            if not response.success():
                return {
                    "success": False,
                    "code": response.code,
                    "msg": response.msg,
                    "log_id": response.get_log_id(),
                }
            data = response.data
            spreadsheet = getattr(data, "spreadsheet", None) if data else None
            token = getattr(spreadsheet, "token", None) if spreadsheet else None
            url = getattr(spreadsheet, "url", None) if spreadsheet else None
            sheets = getattr(spreadsheet, "sheets", []) if spreadsheet else []
            default_sheet_id = None
            if sheets:
                # 飞书 v3 返回 sheets 通常是嵌套 dict/对象，兼容两种结构
                first = sheets[0]
                if isinstance(first, dict):
                    default_sheet_id = (
                        first.get("sheet_id") or first.get("sheetId") or None
                    )
                else:
                    default_sheet_id = getattr(first, "sheet_id", None)
            return {
                "success": True,
                "spreadsheet_token": token,
                "url": url,
                "default_sheet_id": default_sheet_id,
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("[feishu_sheets_client] create_spreadsheet 失败: %s", e)
            return {"success": False, "error": str(e)}

    async def write_values(
        self,
        spreadsheet_token: str,
        range_: str,
        values: List[List[Any]],
    ) -> Dict[str, Any]:
        """写入单元格值。

        对应 ``POST /open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/values``。

        Args:
            spreadsheet_token: 表格 token
            range_: A1 范围字符串，``{sheet_id}!A1:D10``
            values: 二维数组

        Returns:
            dict: 成功 ``{"success": True, "updated_rows", "updated_cols",
                "updated_range"}``；失败同上

        Raises:
            无。所有异常被捕获并以 ``success=False`` 返回。
        """
        if not spreadsheet_token:
            return {"success": False, "error": "spreadsheet_token 缺失"}
        if not range_:
            return {"success": False, "error": "range_ 缺失"}
        if not values or not isinstance(values, list):
            return {"success": False, "error": "values 必须是非空二维数组"}
        try:
            from lark_oapi.api.sheets.v2 import (
                WriteSpreadsheetValuesRequest,
                WriteSpreadsheetValuesRequestBody,
            )
            body = (
                WriteSpreadsheetValuesRequestBody.builder()
                .range_(range_)
                .values(json.dumps(values, ensure_ascii=False))
                .build()
            )
            req = (
                WriteSpreadsheetValuesRequest.builder()
                .spreadsheet_token(spreadsheet_token)
                .request_body(body)
                .build()
            )
            response = await asyncio.to_thread(
                self._client.sheets.v2.spreadsheet_value.write, req
            )
            if not response.success():
                return {
                    "success": False,
                    "code": response.code,
                    "msg": response.msg,
                    "log_id": response.get_log_id(),
                }
            data = response.data
            return {
                "success": True,
                "updated_rows": getattr(data, "updated_rows", None) if data else None,
                "updated_cols": getattr(data, "updated_cols", None) if data else None,
                "updated_range": getattr(data, "updated_range", None) if data else None,
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("[feishu_sheets_client] write_values 失败: %s", e)
            return {"success": False, "error": str(e)}

    async def read_values(
        self,
        spreadsheet_token: str,
        range_: str,
    ) -> Dict[str, Any]:
        """读取单元格值。

        对应 ``GET /open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/values``。

        Args:
            spreadsheet_token: 表格 token
            range_: A1 范围字符串

        Returns:
            dict: 成功 ``{"success": True, "values": list[list]}``；
                失败同上
        """
        if not spreadsheet_token:
            return {"success": False, "error": "spreadsheet_token 缺失"}
        if not range_:
            return {"success": False, "error": "range_ 缺失"}
        try:
            from lark_oapi.api.sheets.v2 import GetSpreadsheetValuesRequest
            req = (
                GetSpreadsheetValuesRequest.builder()
                .spreadsheet_token(spreadsheet_token)
                .range_(range_)
                .build()
            )
            response = await asyncio.to_thread(
                self._client.sheets.v2.spreadsheet_value.get, req
            )
            if not response.success():
                return {
                    "success": False,
                    "code": response.code,
                    "msg": response.msg,
                    "log_id": response.get_log_id(),
                }
            data = response.data
            raw_values = getattr(data, "values", []) if data else []
            return {"success": True, "values": list(raw_values)}
        except Exception as e:  # noqa: BLE001
            logger.warning("[feishu_sheets_client] read_values 失败: %s", e)
            return {"success": False, "error": str(e)}