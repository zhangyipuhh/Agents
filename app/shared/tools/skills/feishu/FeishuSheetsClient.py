#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FeishuSheetsClient - 飞书 sheets 服务客户端

职责：
    - 封装飞书 sheets Open API（创建 spreadsheet / 读写单元格值）
    - 提供 ``create_spreadsheet`` / ``write_values`` / ``read_values`` 异步方法
    - 失败统一返回 ``{"success": False, "error", "code"}``，不抛异常

注意：
    - 写入 / 读取走 ``lark.BaseRequest`` 原生 HTTP 调 sheets v2 values URL
      （lark-oapi 1.7.1 已删除 ``lark_oapi.api.sheets.v2`` 子模块与
      ``spreadsheet_value`` 资源类，只能走 raw HTTP；与本仓库
      ``FeishuWebSocketService._fetch_bot_open_id`` 走同一路径）；
      创建走 sheets v3 spreadsheets 资源类（仍由 SDK v3 提供）
    - 写入 range 形如 ``{sheet_id}!A1:D10``；首次创建后默认有 1 个 sheet，
      由 ``create_spreadsheet`` 返回 ``default_sheet_id`` 供后续写入使用
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from lark_oapi.core.enum import AccessTokenType, HttpMethod
from lark_oapi.core.model import BaseRequest, RequestOption

logger = logging.getLogger(__name__)


def _parse_response(raw_content):
    """把 ``response.raw.content``（bytes/str）解析为 JSON dict。

    Args:
        raw_content: ``lark.Client.request`` 返回的 ``RawResponse.content``。

    Returns:
        dict | None: 解析后的 JSON 字典；解析失败返回 ``None``。
    """
    try:
        if isinstance(raw_content, bytes):
            raw_content = raw_content.decode("utf-8")
        if not raw_content:
            return None
        return json.loads(raw_content)
    except (ValueError, UnicodeDecodeError) as e:  # noqa: BLE001
        logger.warning("[feishu_sheets_client] 响应 JSON 解析失败: %s", e)
        return None


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

        实现说明：lark-oapi 1.7.1 已移除 ``lark_oapi.api.sheets.v2`` 子模块与
        ``spreadsheet_value`` 资源类，本方法走 ``lark.BaseRequest`` 原生 HTTP
        路径（与 ``FeishuWebSocketService._fetch_bot_open_id`` 同款）。

        请求体按官方文档契约构造为 ``{"valueRange": {"range": ..., "values": ...}}``
        形态。

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
            uri = (
                f"/open-apis/sheets/v2/spreadsheets/"
                f"{spreadsheet_token}/values"
            )
            body_json = json.dumps(
                {"valueRange": {"range": range_, "values": values}},
                ensure_ascii=False,
            )
            request = (
                BaseRequest.builder()
                .http_method(HttpMethod.POST)
                .uri(uri)
                .token_types({AccessTokenType.TENANT})
                .body(body_json)
                .build()
            )
            response = await asyncio.to_thread(
                self._client.request,
                request,
                RequestOption.builder().build(),
            )
            raw = getattr(response, "raw", None)
            payload = _parse_response(getattr(raw, "content", None) if raw else None)
            if not payload:
                return {"success": False, "error": "响应体为空或解析失败"}
            code = payload.get("code")
            if code not in (0, None):
                return {
                    "success": False,
                    "code": code,
                    "msg": payload.get("msg"),
                    "log_id": (
                        payload.get("data", {}).get("log_id")
                        if isinstance(payload.get("data"), dict)
                        else None
                    ),
                }
            data = payload.get("data") or {}
            return {
                "success": True,
                "updated_rows": data.get("updatedRows"),
                "updated_cols": data.get("updatedColumns"),
                "updated_range": data.get("updatedRange"),
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

        实现说明：lark-oapi 1.7.1 已移除 ``lark_oapi.api.sheets.v2`` 子模块与
        ``spreadsheet_value`` 资源类，本方法走 ``lark.BaseRequest`` 原生 HTTP
        路径（与 ``FeishuWebSocketService._fetch_bot_open_id`` 同款）。

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
            uri = (
                f"/open-apis/sheets/v2/spreadsheets/"
                f"{spreadsheet_token}/values"
            )
            request = (
                BaseRequest.builder()
                .http_method(HttpMethod.GET)
                .uri(uri)
                .token_types({AccessTokenType.TENANT})
                .queries({"range": range_})
                .build()
            )
            response = await asyncio.to_thread(
                self._client.request,
                request,
                RequestOption.builder().build(),
            )
            raw = getattr(response, "raw", None)
            payload = _parse_response(getattr(raw, "content", None) if raw else None)
            if not payload:
                return {"success": False, "error": "响应体为空或解析失败"}
            code = payload.get("code")
            if code not in (0, None):
                return {
                    "success": False,
                    "code": code,
                    "msg": payload.get("msg"),
                }
            data = payload.get("data") or {}
            raw_values = data.get("values") or []
            return {"success": True, "values": list(raw_values)}
        except Exception as e:  # noqa: BLE001
            logger.warning("[feishu_sheets_client] read_values 失败: %s", e)
            return {"success": False, "error": str(e)}