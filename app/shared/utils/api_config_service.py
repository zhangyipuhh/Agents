#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
API 接口配置服务模块。

该模块负责管理「API 接口配置」的树形节点（folder / api）、每个 api 节点
对应的请求配置（method / url / params / headers / body / form_fields /
expectations），以及通过 httpx 代理发送请求并按预期结果规则校验、落库
调用历史（api_check_runs）。

设计约定：
- 数据库是真相源；启动时 ``preload_all`` 把节点与配置载入内存缓存，
  之后所有写操作同步内存与 DB。
- ``db=None``（内存降级模式）时 ``preload_all`` no-op，读操作返回空，
  写操作抛 ``RuntimeError("数据库未启用")``。
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from app.shared.utils.auth.ownership_scope import OwnershipScope


logger = logging.getLogger(__name__)


# 节点类型枚举
NODE_TYPES = ("folder", "api")
# HTTP 方法枚举
METHODS = ("POST", "PUT")
# 请求体类型枚举
BODY_TYPES = ("none", "json", "xml", "text", "form-data", "x-www-form-urlencoded")
# 预期结果断言类型枚举
EXPECTATION_TYPES = ("status_code", "body_contains", "json_field")
# 响应体截断长度
RESPONSE_EXCERPT_MAX_LEN = 4000


class ApiConfigNotFoundError(LookupError):
    """节点不存在时抛出（路由层映射为 404）。"""


class ApiConfigService:
    """API 接口配置服务。

    参数:
        db: 数据库连接池，需支持 fetch / fetchrow / execute 异步方法；
            None 表示内存降级模式。
    """

    def __init__(self, db: Any) -> None:
        """初始化 API 接口配置服务。

        参数:
            db: 数据库连接池；None 时进入降级模式。
        """
        self._db = db
        # 内存缓存：node_id -> 节点 dict；node_id -> 配置 dict
        self._nodes: Dict[int, Dict[str, Any]] = {}
        self._configs: Dict[int, Dict[str, Any]] = {}

    def _require_db(self) -> None:
        """确认数据库可用。

        返回:
            None。

        异常:
            RuntimeError: db 为 None（数据库未启用）时抛出。
        """
        if self._db is None:
            raise RuntimeError("数据库未启用")

    @staticmethod
    def _assert_node_access(node: Optional[Dict[str, Any]], scope: OwnershipScope) -> Dict[str, Any]:
        """校验调用方对节点的可见性，越权或缺失一律抛 ``ApiConfigNotFoundError``。

        缺失与越权不区分是为了防止通过状态码差异探测节点是否存在（与
        ``OwnershipScope`` 文档约定一致：service 层越权返回 None / NotFound，
        路由层映射 HTTP 404）。

        参数:
            node: 节点 dict（来自内存缓存）；``None`` 表示节点不存在。
            scope: 调用方归属上下文。

        返回:
            Dict[str, Any]: 节点 dict（便于链式调用）。

        异常:
            ApiConfigNotFoundError: 节点不存在或当前 scope 无权访问时抛出。
        """
        if node is None:
            raise ApiConfigNotFoundError("节点不存在")
        if not scope.can_access(node.get("created_by_user_id")):
            raise ApiConfigNotFoundError("节点不存在")
        return node

    def get_node_internal(self, node_id: int) -> Optional[Dict[str, Any]]:
        """系统内部获取节点（绕过归属隔离）。

        仅供调度器等已校验过归属的内部场景使用；HTTP 路由层禁止调用。
        数据来源于 ``preload_all`` 建立的内存缓存，db 为 None 时返回空缓存，
        调度器走 lifespan 注入路径，db 必为真。

        参数:
            node_id: 节点 ID。

        返回:
            Optional[Dict[str, Any]]: 节点字典；不存在时返回 ``None``。
        """
        return self._nodes.get(node_id)

    @staticmethod
    def _decode_jsonb(value: Any, default: Any) -> Any:
        """防御性反序列化 JSONB 字段。

        参数:
            value: 数据库返回值，可能为 None / str / list / dict。
            default: 解析失败或为空时返回的默认值。

        返回:
            Any: 解析后的 Python 对象。
        """
        if value is None:
            return default
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                logger.warning("Failed to decode api config JSONB value")
                return default
        return value

    @classmethod
    def _decode_node_row(cls, row: Any) -> Optional[Dict[str, Any]]:
        """将节点 DB row 转换为 dict。

        参数:
            row: asyncpg Record 或 dict。

        返回:
            Optional[Dict[str, Any]]: 节点字典，row 为空时返回 None。
        """
        if row is None:
            return None
        return dict(row)

    @classmethod
    def _decode_config_row(cls, row: Any) -> Optional[Dict[str, Any]]:
        """将配置 DB row 转换为 dict，并规整 JSONB 字段。

        参数:
            row: asyncpg Record 或 dict。

        返回:
            Optional[Dict[str, Any]]: 配置字典，row 为空时返回 None。
        """
        if row is None:
            return None
        result = dict(row)
        for field in ("params", "headers", "form_fields", "expectations"):
            result[field] = cls._decode_jsonb(result.get(field), [])
        return result

    async def preload_all(self) -> None:
        """启动时把全部节点与配置载入内存缓存。

        返回:
            None。
        """
        if self._db is None:
            return
        try:
            node_rows = await self._db.fetch(
                "SELECT * FROM api_config_nodes ORDER BY id ASC"
            )
            config_rows = await self._db.fetch("SELECT * FROM api_configs")
            for row in node_rows:
                node = self._decode_node_row(row)
                if node:
                    self._nodes[node["id"]] = node
            for row in config_rows:
                config = self._decode_config_row(row)
                if config:
                    self._configs[config["node_id"]] = config
            logger.info(
                "[api_config_service] preloaded %d node(s), %d config(s)",
                len(self._nodes), len(self._configs),
            )
        except Exception as exc:
            logger.warning(
                "[api_config_service] preload failed: %s", exc, exc_info=True
            )

    async def get_tree(self, scope: OwnershipScope) -> List[Dict[str, Any]]:
        """返回节点平铺列表，按 ``scope`` 过滤可见性。

        admin / system 透传全量；普通用户仅返回自己创建的节点。若过滤后某
        节点的 ``parent_id`` 不在可见集合内，则将其 ``parent_id`` 重写为
        ``None``（提升为根）以便前端组树时仍能渲染——同时不会泄露隐藏父
        节点的存在。

        参数:
            scope: 调用方归属上下文；通常由 ``OwnershipScope.from_request(request)``
                或 ``OwnershipScope.system_scope()`` 构造。

        返回:
            List[Dict[str, Any]]: 节点列表，按 id 升序。
        """
        all_nodes = sorted(self._nodes.values(), key=lambda n: n["id"])
        if scope.system or scope.is_admin:
            return all_nodes
        visible_ids = {
            n["id"] for n in all_nodes
            if scope.can_access(n.get("created_by_user_id"))
        }
        result: List[Dict[str, Any]] = []
        for node in all_nodes:
            if node["id"] not in visible_ids:
                continue
            copied = dict(node)
            parent_id = copied.get("parent_id")
            if parent_id is not None and parent_id not in visible_ids:
                copied["parent_id"] = None
            result.append(copied)
        return result

    async def create_node(
        self,
        parent_id: Optional[int],
        node_type: str,
        name: str,
        scope: OwnershipScope,
    ) -> Dict[str, Any]:
        """创建节点；node_type='api' 时自动创建默认 api_configs 行。

        非 admin 创建节点的归属为 ``scope.user_id``，父节点必须是 ``None``
        或当前用户可见（且为 folder）的节点；不可见的父节点一律报「父节点
        不存在」，不泄露他人节点的存在。

        参数:
            parent_id: 父节点 ID；None 表示根节点。
            node_type: 节点类型，'folder' 或 'api'。
            name: 节点名称。
            scope: 调用方归属上下文。

        返回:
            Dict[str, Any]: 新建节点字典。

        异常:
            ValueError: node_type 非法、name 为空、``scope.user_id`` 缺失、
                父节点不存在或父节点不是 folder 时抛出。
            RuntimeError: 数据库未启用时抛出。
        """
        self._require_db()
        if scope.user_id is None:
            raise ValueError("无法确定创建人用户，请通过 HTTP 路由调用")
        if node_type not in NODE_TYPES:
            raise ValueError(f"node_type 必须是 {NODE_TYPES} 之一，当前为: {node_type!r}")
        if not str(name or "").strip():
            raise ValueError("节点名称不能为空")
        if parent_id is not None:
            try:
                parent = self._assert_node_access(self._nodes.get(parent_id), scope)
            except ApiConfigNotFoundError:
                # 缺失与越权统一报「父节点不存在」，不泄露他人节点的存在性
                raise ValueError(f"父节点不存在: {parent_id}") from None
            if parent.get("node_type") != "folder":
                raise ValueError(f"父节点必须是 folder 类型: {parent_id}")
        row = await self._db.fetchrow(
            """
            INSERT INTO api_config_nodes (parent_id, node_type, name, sort_order, created_by_user_id)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
            """,
            parent_id,
            node_type,
            name,
            0,
            scope.user_id,
        )
        node = self._decode_node_row(row)
        self._nodes[node["id"]] = node
        if node_type == "api":
            # 同事务语义：紧随节点创建写入默认配置行，任何一步失败向上抛出
            config_row = await self._db.fetchrow(
                "INSERT INTO api_configs (node_id) VALUES ($1) RETURNING *",
                node["id"],
            )
            config = self._decode_config_row(config_row)
            if config:
                self._configs[node["id"]] = config
        return node

    def _assert_valid_parent(self, node_id: int, parent_id: int, scope: OwnershipScope) -> None:
        """校验 parent_id 可作为 node_id 的新父节点（可见、folder、无环）。

        参数:
            node_id: 待移动节点 ID。
            parent_id: 目标父节点 ID。
            scope: 调用方归属上下文；不可见父节点一律报「不存在」。

        返回:
            None。

        异常:
            ValueError: 目标父节点不可见 / 不是 folder / 是节点自身或节点
                的后代（形成环）时抛出。
        """
        try:
            parent = self._assert_node_access(self._nodes.get(parent_id), scope)
        except ApiConfigNotFoundError:
            raise ValueError(f"父节点不存在: {parent_id}") from None
        if parent.get("node_type") != "folder":
            raise ValueError(f"父节点必须是 folder 类型: {parent_id}")
        # 沿祖先链向上走，若遇到 node_id 说明目标父节点是自身或后代（成环）
        cursor: Optional[int] = parent_id
        while cursor is not None:
            if cursor == node_id:
                raise ValueError("目标父节点是节点自身或其后代，拒绝成环")
            cursor = self._nodes.get(cursor, {}).get("parent_id")

    async def update_node(
        self,
        node_id: int,
        scope: OwnershipScope,
        name: Optional[str] = None,
        parent_id: Optional[int] = None,
        sort_order: Optional[int] = None,
    ) -> Dict[str, Any]:
        """更新节点名称 / 父节点 / 排序权重。

        参数:
            node_id: 节点 ID。
            scope: 调用方归属上下文。
            name: 新名称；None 表示不修改。
            parent_id: 新父节点 ID；None 表示不修改。
            sort_order: 新排序权重；None 表示不修改。

        返回:
            Dict[str, Any]: 更新后的节点字典。

        异常:
            ApiConfigNotFoundError: 节点不存在或当前 scope 无权访问时抛出。
            ValueError: name 为空串、父节点校验失败（不可见 / 非 folder /
                成环）时抛出。
            RuntimeError: 数据库未启用时抛出。
        """
        self._require_db()
        self._assert_node_access(self._nodes.get(node_id), scope)
        if name is not None and not str(name).strip():
            raise ValueError("节点名称不能为空")
        if parent_id is not None:
            self._assert_valid_parent(node_id, parent_id, scope)
        row = await self._db.fetchrow(
            """
            UPDATE api_config_nodes
            SET name = COALESCE($2, name),
                parent_id = COALESCE($3, parent_id),
                sort_order = COALESCE($4, sort_order),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $1
            RETURNING *
            """,
            node_id,
            name,
            parent_id,
            sort_order,
        )
        node = self._decode_node_row(row)
        if node is None:
            raise ApiConfigNotFoundError(f"节点不存在: {node_id}")
        self._nodes[node_id] = node
        return node

    async def delete_node(self, node_id: int, scope: OwnershipScope) -> None:
        """删除节点；api 节点级联删除配置与调用历史。

        非空判定统计**全部**子节点（包括当前用户不可见的他人节点），
        防止误删隐藏内容；满足「不泄露他人节点存在」与「安全删除」两个
        约束。

        参数:
            node_id: 节点 ID。
            scope: 调用方归属上下文。

        返回:
            None。

        异常:
            ApiConfigNotFoundError: 节点不存在或当前 scope 无权访问时抛出。
            ValueError: 文件夹非空（仍有子节点）时抛出。
            RuntimeError: 数据库未启用时抛出。
        """
        self._require_db()
        node = self._assert_node_access(self._nodes.get(node_id), scope)
        children = [n for n in self._nodes.values() if n.get("parent_id") == node_id]
        if children:
            raise ValueError("文件夹非空，拒绝删除")
        await self._db.execute(
            "DELETE FROM api_config_nodes WHERE id = $1",
            node_id,
        )
        # DB 层 ON DELETE CASCADE 已级联删除 api_configs / api_check_runs，
        # 内存缓存同步移除
        del self._nodes[node_id]
        self._configs.pop(node_id, None)

    @staticmethod
    def _validate_config_payload(
        method: str,
        body_type: str,
        expectations: List[Dict[str, Any]],
    ) -> None:
        """校验配置字段枚举与 expectations 结构。

        参数:
            method: HTTP 方法。
            body_type: 请求体类型。
            expectations: 预期结果断言规则列表。

        返回:
            None。

        异常:
            ValueError: 枚举非法或 expectations 结构非法时抛出。
        """
        if method not in METHODS:
            raise ValueError(f"method 必须是 {METHODS} 之一，当前为: {method!r}")
        if body_type not in BODY_TYPES:
            raise ValueError(f"body_type 必须是 {BODY_TYPES} 之一，当前为: {body_type!r}")
        if not isinstance(expectations, list):
            raise ValueError("expectations 必须是数组")
        for rule in expectations:
            if not isinstance(rule, dict) or rule.get("type") not in EXPECTATION_TYPES:
                raise ValueError(
                    f"expectations 元素的 type 必须是 {EXPECTATION_TYPES} 之一"
                )

    async def get_config(self, node_id: int, scope: OwnershipScope) -> Dict[str, Any]:
        """获取 api 节点的请求配置。

        参数:
            node_id: 节点 ID。
            scope: 调用方归属上下文。

        返回:
            Dict[str, Any]: 配置字典。

        异常:
            ApiConfigNotFoundError: 节点不存在或当前 scope 无权访问时抛出。
            ValueError: 节点存在但不是 api 类型 / 配置缺失时抛出。
        """
        node = self._assert_node_access(self._nodes.get(node_id), scope)
        if node.get("node_type") != "api":
            raise ValueError(f"节点不是 api 类型: {node_id}")
        config = self._configs.get(node_id)
        if config is None:
            raise ValueError(f"api 节点缺少配置: {node_id}")
        return config

    async def upsert_config(
        self,
        node_id: int,
        scope: OwnershipScope,
        *,
        method: str,
        url: str,
        params: List[Dict[str, Any]],
        headers: List[Dict[str, Any]],
        body_type: str,
        body_content: str,
        form_fields: List[Dict[str, Any]],
        expectations: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """全量 upsert api 节点的请求配置。

        参数:
            node_id: 节点 ID（必须为已存在的 api 节点）。
            scope: 调用方归属上下文。
            method: HTTP 方法，POST 或 PUT。
            url: 请求 URL。
            params: query 参数列表 [{name, value, description}]。
            headers: 请求头列表 [{name, value, description}]。
            body_type: 请求体类型。
            body_content: 请求体原文（json / xml / text 使用）。
            form_fields: 表单字段列表（form-data / x-www-form-urlencoded 使用）。
            expectations: 预期结果断言规则列表。

        返回:
            Dict[str, Any]: upsert 后的配置字典。

        异常:
            ApiConfigNotFoundError: 节点不存在或当前 scope 无权访问时抛出。
            ValueError: 节点不是 api 节点 / 枚举非法 / expectations 结构
                非法时抛出。
            RuntimeError: 数据库未启用时抛出。
        """
        self._require_db()
        await self.get_config(node_id, scope)
        self._validate_config_payload(method, body_type, expectations)
        row = await self._db.fetchrow(
            """
            INSERT INTO api_configs (
                node_id, method, url, params, headers, body_type,
                body_content, form_fields, expectations
            ) VALUES (
                $1, $2, $3, $4::jsonb, $5::jsonb, $6, $7, $8::jsonb, $9::jsonb
            )
            ON CONFLICT (node_id) DO UPDATE SET
                method = EXCLUDED.method,
                url = EXCLUDED.url,
                params = EXCLUDED.params,
                headers = EXCLUDED.headers,
                body_type = EXCLUDED.body_type,
                body_content = EXCLUDED.body_content,
                form_fields = EXCLUDED.form_fields,
                expectations = EXCLUDED.expectations,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
            """,
            node_id,
            method,
            url or "",
            json.dumps(params or [], ensure_ascii=False),
            json.dumps(headers or [], ensure_ascii=False),
            body_type,
            body_content or "",
            json.dumps(form_fields or [], ensure_ascii=False),
            json.dumps(expectations or [], ensure_ascii=False),
        )
        config = self._decode_config_row(row)
        if config:
            self._configs[node_id] = config
        return config

    @staticmethod
    def _kv_list_to_dict(items: List[Dict[str, Any]]) -> Dict[str, str]:
        """把 [{name, value, description}] 列表转为 {name: value} 字典。

        参数:
            items: 键值列表，name 为空的项被跳过。

        返回:
            Dict[str, str]: 键值字典。
        """
        result: Dict[str, str] = {}
        for item in items or []:
            name = str(item.get("name") or "")
            if name:
                result[name] = str(item.get("value") or "")
        return result

    @classmethod
    def _build_request_kwargs(cls, config: Dict[str, Any]) -> Dict[str, Any]:
        """按配置组装 httpx.request 的关键字参数。

        参数:
            config: 配置字典。

        返回:
            Dict[str, Any]: 传给 httpx.AsyncClient.request 的 kwargs，
                可能包含 params / headers / json / content / data。
        """
        kwargs: Dict[str, Any] = {}
        params = cls._kv_list_to_dict(config.get("params") or [])
        if params:
            kwargs["params"] = params
        headers = cls._kv_list_to_dict(config.get("headers") or [])
        if headers:
            kwargs["headers"] = headers
        body_type = config.get("body_type") or "none"
        body_content = config.get("body_content") or ""
        if body_type == "json":
            if body_content:
                try:
                    kwargs["json"] = json.loads(body_content)
                except (json.JSONDecodeError, TypeError):
                    # 非法 JSON 时按 raw text 发送
                    kwargs["content"] = body_content
        elif body_type in ("xml", "text"):
            if body_content:
                kwargs["content"] = body_content
        elif body_type in ("form-data", "x-www-form-urlencoded"):
            data = cls._kv_list_to_dict(config.get("form_fields") or [])
            if data:
                kwargs["data"] = data
        return kwargs

    @staticmethod
    def _resolve_json_path(payload: Any, path: str) -> tuple:
        """按点号路径在 JSON 对象中下钻取值，支持 dict 键与 list 数字索引。

        参数:
            payload: 已解析的 JSON 对象。
            path: 点号分隔路径，如 ``data.items.0.id``。

        返回:
            tuple: (value, found)；found=False 时 value 为 None。
        """
        current = payload
        for segment in str(path or "").split("."):
            if isinstance(current, dict):
                if segment not in current:
                    return None, False
                current = current[segment]
            elif isinstance(current, list):
                try:
                    index = int(segment)
                except (TypeError, ValueError):
                    return None, False
                if index < 0 or index >= len(current):
                    return None, False
                current = current[index]
            else:
                return None, False
        return current, True

    @staticmethod
    def _evaluate_expectations(
        expectations: List[Dict[str, Any]],
        http_status: Optional[int],
        response_text: str,
    ) -> List[Dict[str, Any]]:
        """按预期结果规则校验响应。

        参数:
            expectations: 断言规则列表，type 为 status_code / body_contains /
                json_field 之一。
            http_status: 实际 HTTP 状态码；网络异常时为 None。
            response_text: 响应体原文。

        返回:
            List[Dict[str, Any]]: 每条规则的校验结果，
                形如 {rule, passed, detail}。
        """
        results: List[Dict[str, Any]] = []
        parsed_json: Any = None
        json_parsed = False
        for rule in expectations or []:
            rtype = rule.get("type")
            passed = False
            detail = ""
            if rtype == "status_code":
                expected = rule.get("value")
                operator = rule.get("operator") or "eq"
                if operator == "eq":
                    try:
                        passed = http_status == int(expected)
                    except (TypeError, ValueError):
                        passed = False
                detail = f"expect status_code {operator} {expected}, got {http_status}"
            elif rtype == "body_contains":
                needle = str(rule.get("value") or "")
                passed = needle in (response_text or "")
                detail = f"expect body contains {needle!r}"
            elif rtype == "json_field":
                if not json_parsed:
                    json_parsed = True
                    try:
                        parsed_json = json.loads(response_text or "")
                    except (json.JSONDecodeError, TypeError):
                        parsed_json = None
                if parsed_json is None:
                    detail = "response body is not valid JSON"
                else:
                    value, found = ApiConfigService._resolve_json_path(
                        parsed_json, rule.get("path") or ""
                    )
                    operator = rule.get("operator") or "exists"
                    if operator == "exists":
                        passed = found
                    elif operator == "eq":
                        passed = found and value == rule.get("value")
                    detail = (
                        f"expect json_field {rule.get('path')} {operator}"
                        f" {rule.get('value') if operator == 'eq' else ''}".strip()
                    )
            results.append({"rule": rule, "passed": passed, "detail": detail})
        return results

    async def send_request(self, node_id: int, scope: OwnershipScope) -> Dict[str, Any]:
        """按节点配置代理发送 HTTP 请求并校验预期结果、落库调用历史。

        参数:
            node_id: api 节点 ID。
            scope: 调用方归属上下文；脚本运行时使用 ``OwnershipScope.system_scope()``
                绕过隔离（配置期校验已确保 ``api_list`` 归属）。

        返回:
            Dict[str, Any]: 调用结果，含 run_id / http_status / duration_ms /
                response_body（截断 4000 字符）/ check_passed /
                assertion_results[{rule, passed, detail}] / error_message。

        异常:
            ApiConfigNotFoundError: 节点不存在或当前 scope 无权访问时抛出。
            ValueError: 节点不是 api 节点 / 配置缺失时抛出。
            RuntimeError: 数据库未启用时抛出。
        """
        self._require_db()
        config = await self.get_config(node_id, scope)
        kwargs = self._build_request_kwargs(config)
        started = time.perf_counter()
        http_status: Optional[int] = None
        response_text = ""
        error_message = ""
        assertion_results: List[Dict[str, Any]] = []
        check_passed = False
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.request(
                    config.get("method") or "POST",
                    config.get("url") or "",
                    **kwargs,
                )
            http_status = response.status_code
            response_text = response.text or ""
            assertion_results = self._evaluate_expectations(
                config.get("expectations") or [], http_status, response_text
            )
            check_passed = all(item["passed"] for item in assertion_results)
        except Exception as exc:  # noqa: BLE001 网络异常统一落库，不向上抛
            error_message = f"{type(exc).__name__}: {exc}"
        duration_ms = int((time.perf_counter() - started) * 1000)
        response_excerpt = response_text[:RESPONSE_EXCERPT_MAX_LEN]
        run_row = await self._db.fetchrow(
            """
            INSERT INTO api_check_runs (
                config_id, http_status, duration_ms, check_passed,
                response_excerpt, error_message
            ) VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            config["id"],
            http_status,
            duration_ms,
            check_passed,
            response_excerpt,
            error_message,
        )
        return {
            "run_id": run_row["id"] if run_row else None,
            "http_status": http_status,
            "duration_ms": duration_ms,
            "response_body": response_excerpt,
            "check_passed": check_passed,
            "assertion_results": assertion_results,
            "error_message": error_message,
        }

    async def list_runs(
        self,
        node_id: int,
        scope: OwnershipScope,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """查询 api 节点的调用历史。

        参数:
            node_id: api 节点 ID。
            scope: 调用方归属上下文。
            limit: 最大返回条数，默认 20。

        返回:
            List[Dict[str, Any]]: 调用历史列表，按创建时间倒序。

        异常:
            ApiConfigNotFoundError: 节点不存在或当前 scope 无权访问时抛出。
            ValueError: 节点不是 api 节点 / 配置缺失时抛出。
        """
        if self._db is None:
            return []
        config = await self.get_config(node_id, scope)
        rows = await self._db.fetch(
            """
            SELECT * FROM api_check_runs
            WHERE config_id = $1
            ORDER BY created_at DESC, id DESC
            LIMIT $2
            """,
            config["id"],
            limit,
        )
        return [dict(row) for row in rows]
