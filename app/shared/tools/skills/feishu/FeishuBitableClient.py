#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FeishuBitableClient - 飞书多维表格 v1 服务客户端（只读）

职责：
    - 封装飞书多维表格（Bitable）Open API 三个只读端点
    - 提供 ``list_records`` / ``get_record`` / ``search_records`` 异步方法
    - 失败统一返回 ``{"success": False, "error", "code", "msg", "log_id"}``，不抛异常

注意：
    - 全部走 ``lark.BaseRequest`` 原生 HTTP 路径（与 ``FeishuSheetsClient.write_values``
      / ``read_values`` / ``FeishuWebSocketService._fetch_bot_open_id`` 同款），不依赖
      SDK 1.7.x 中 ``lark_oapi.api.bitable.v1`` 子模块的 ``*Request`` / ``*Response``
      类型签名（历史上多次调整），规避运行时类路径漂移风险
    - 所有端点需 ``tenant_access_token``
    - ``page_size`` 工具内部钳制到 ``[1, 500]``（飞书官方上限 500）
    - 复用 ``FeishuSheetsClient._parse_response``（公开下划线 helper）解析
      ``response.raw.content``，行为与 sheets 端点 100% 对齐
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from lark_oapi.core.enum import AccessTokenType, HttpMethod
from lark_oapi.core.model import BaseRequest, RequestOption

from app.shared.tools.skills.feishu.FeishuSheetsClient import _parse_response

logger = logging.getLogger(__name__)


# 飞书官方约束:每页最多 500 行
_BITABLE_MAX_PAGE_SIZE = 500


def _clamp_page_size(value: Optional[int]) -> Optional[int]:
    """把 ``page_size`` 钳制到 ``[1, 500]`` 范围。

    Args:
        value: 调用方传入的 page_size（可能为 None 或越界值）。

    Returns:
        Optional[int]: 钳制后的值；入参为 None 时返回 None。
    """
    if value is None:
        return None
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None
    if v < 1:
        return 1
    if v > _BITABLE_MAX_PAGE_SIZE:
        return _BITABLE_MAX_PAGE_SIZE
    return v


class FeishuBitableClient:
    """飞书 Bitable v1 服务客户端（只读）。

    Attributes:
        _client: 已构造好的 ``lark.Client`` 实例（由调用方注入）。
    """

    def __init__(self, lark_client):
        self._client = lark_client

    # ------------------------------------------------------------------
    # 列出记录
    # ------------------------------------------------------------------
    async def list_records(
        self,
        app_token: str,
        table_id: str,
        view_id: Optional[str] = None,
        field_names: Optional[List[str]] = None,
        text_field_as_array: Optional[bool] = None,
        user_id_type: Optional[str] = None,
        page_token: Optional[str] = None,
        page_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """列出飞书多维表格某张表的记录（分页，单页最多 500）。

        对应 ``GET /open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records``。

        Args:
            app_token: 多维表格 App 唯一标识（URL ``base/`` 之后那段）。
            table_id: 数据表唯一标识。
            view_id: 视图 id；空则按默认视图拉取。
            field_names: 限定返回的字段名数组；空则返回所有字段。
            text_field_as_array: 多行文本字段是否以数组形式返回。
            user_id_type: 用户字段的 ID 类型，可选 ``user_id`` / ``union_id`` / ``open_id``。
            page_token: 翻页 token；首次为空。
            page_size: 单页记录数；内部钳制到 ``[1, 500]``。

        Returns:
            dict: 成功 ``{"success": True, "items": [...], "has_more": bool,
                "page_token": str|None, "total": int}``；失败同上形态。

        Raises:
            无。所有异常被捕获并以 ``success=False`` 返回。
        """
        if not app_token:
            return {"success": False, "error": "app_token 缺失"}
        if not table_id:
            return {"success": False, "error": "table_id 缺失"}
        try:
            queries: Dict[str, str] = {}
            if view_id:
                queries["view_id"] = view_id
            if field_names:
                # 飞书要求以 JSON 字符串传递 list 参数
                queries["field_names"] = json.dumps(list(field_names), ensure_ascii=False)
            if text_field_as_array is not None:
                queries["text_field_as_array"] = "true" if text_field_as_array else "false"
            if user_id_type:
                queries["user_id_type"] = user_id_type
            if page_token:
                queries["page_token"] = page_token
            clamped_size = _clamp_page_size(page_size)
            if clamped_size is not None:
                queries["page_size"] = str(clamped_size)

            uri = (
                f"/open-apis/bitable/v1/apps/{app_token}"
                f"/tables/{table_id}/records"
            )
            builder = (
                BaseRequest.builder()
                .http_method(HttpMethod.GET)
                .uri(uri)
                .token_types({AccessTokenType.TENANT})
            )
            if queries:
                builder = builder.queries(queries)
            request = builder.build()

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
                "items": list(data.get("items") or []),
                "has_more": bool(data.get("has_more", False)),
                "page_token": data.get("page_token"),
                "total": data.get("total"),
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("[feishu_bitable_client] list_records 失败: %s", e)
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # 获取单条记录
    # ------------------------------------------------------------------
    async def get_record(
        self,
        app_token: str,
        table_id: str,
        record_id: str,
        user_id_type: Optional[str] = None,
        with_shared_url: Optional[bool] = None,
        automatic_fields: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """获取飞书多维表格单条记录详情。

        对应 ``GET /open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}``。

        Args:
            app_token: 多维表格 App 唯一标识。
            table_id: 数据表唯一标识。
            record_id: 记录 id。
            user_id_type: 用户字段的 ID 类型，可选 ``user_id`` / ``union_id`` / ``open_id``。
            with_shared_url: 是否返回记录的分享链接；默认 ``False``。
            automatic_fields: 是否返回自动计算的字段；默认 ``False``。

        Returns:
            dict: 成功 ``{"success": True, "record": {...}}``；失败同上形态。

        Raises:
            无。所有异常被捕获并以 ``success=False`` 返回。
        """
        if not app_token:
            return {"success": False, "error": "app_token 缺失"}
        if not table_id:
            return {"success": False, "error": "table_id 缺失"}
        if not record_id:
            return {"success": False, "error": "record_id 缺失"}
        try:
            queries: Dict[str, str] = {}
            if user_id_type:
                queries["user_id_type"] = user_id_type
            if with_shared_url is not None:
                queries["with_shared_url"] = "true" if with_shared_url else "false"
            if automatic_fields is not None:
                queries["automatic_fields"] = "true" if automatic_fields else "false"

            uri = (
                f"/open-apis/bitable/v1/apps/{app_token}"
                f"/tables/{table_id}/records/{record_id}"
            )
            builder = (
                BaseRequest.builder()
                .http_method(HttpMethod.GET)
                .uri(uri)
                .token_types({AccessTokenType.TENANT})
            )
            if queries:
                builder = builder.queries(queries)
            request = builder.build()

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
            record = data.get("record")
            return {"success": True, "record": record}
        except Exception as e:  # noqa: BLE001
            logger.warning("[feishu_bitable_client] get_record 失败: %s", e)
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # 复杂筛选检索
    # ------------------------------------------------------------------
    async def search_records(
        self,
        app_token: str,
        table_id: str,
        view_id: Optional[str] = None,
        filter_: Optional[Dict[str, Any]] = None,
        sort: Optional[List[Dict[str, Any]]] = None,
        field_names: Optional[List[str]] = None,
        text_field_as_array: Optional[bool] = None,
        automatic_fields: Optional[bool] = None,
        page_token: Optional[str] = None,
        page_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """按复杂条件检索飞书多维表格记录（支持 filter / sort / 分页）。

        对应 ``POST /open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/search``。

        ``filter_`` 形如 ``{"conjunction": "and", "conditions": [
            {"field_name": "状态", "operator": "is", "value": ["进行中"]}
        ]}``；``sort`` 形如 ``[{"field_name": "创建时间", "direction": "desc"}]``。

        Args:
            app_token: 多维表格 App 唯一标识。
            table_id: 数据表唯一标识。
            view_id: 视图 id；filter 或 sort 非空时被忽略。
            filter_: 飞书官方 filter 结构（dict）。
            sort: 排序规则列表。
            field_names: 限定返回的字段名数组。
            text_field_as_array: 多行文本字段是否以数组形式返回。
            automatic_fields: 是否返回自动计算的字段。
            page_token: 翻页 token。
            page_size: 单页记录数；内部钳制到 ``[1, 500]``。

        Returns:
            dict: 成功 ``{"success": True, "items": [...], "has_more": bool,
                "page_token": str|None, "total": int}``；失败同上形态。

        Raises:
            无。所有异常被捕获并以 ``success=False`` 返回。
        """
        if not app_token:
            return {"success": False, "error": "app_token 缺失"}
        if not table_id:
            return {"success": False, "error": "table_id 缺失"}
        try:
            body: Dict[str, Any] = {}
            if view_id:
                body["view_id"] = view_id
            if filter_ is not None:
                body["filter"] = filter_
            if sort is not None:
                body["sort"] = list(sort)
            if field_names is not None:
                body["field_names"] = list(field_names)
            if text_field_as_array is not None:
                body["text_field_as_array"] = bool(text_field_as_array)
            if automatic_fields is not None:
                body["automatic_fields"] = bool(automatic_fields)
            if page_token:
                body["page_token"] = page_token
            clamped_size = _clamp_page_size(page_size)
            if clamped_size is not None:
                body["page_size"] = clamped_size

            uri = (
                f"/open-apis/bitable/v1/apps/{app_token}"
                f"/tables/{table_id}/records/search"
            )
            request = (
                BaseRequest.builder()
                .http_method(HttpMethod.POST)
                .uri(uri)
                .token_types({AccessTokenType.TENANT})
                .body(json.dumps(body, ensure_ascii=False))
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
                "items": list(data.get("items") or []),
                "has_more": bool(data.get("has_more", False)),
                "page_token": data.get("page_token"),
                "total": data.get("total"),
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("[feishu_bitable_client] search_records 失败: %s", e)
            return {"success": False, "error": str(e)}
