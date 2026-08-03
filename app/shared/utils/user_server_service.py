#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
UserServerService - 用户服务器配置管理服务（2026-07-24 新增）

职责：
    - 为每个登录用户维护一个**私有**的服务器配置 tree
    - 节点类型：folder（多级文件夹）/ server（引用 devops_servers 一行）
    - 共享引用策略：server 节点不存 ip/port/账号/密码/白名单/巡检脚本，
      全部从 devops_servers JOIN 读（实时联动底层修改）
    - 多对多关系：两个用户可"添加"同一台 devops_servers 行；
      每个用户导入时生成独立的 user_server_nodes 行（同 source_devops_server_id），
      通过 created_by_user_id 区分归属
    - 归属隔离：admin 看全；普通用户仅看自己 created_by_user_id 的节点
    - 父节点不可见时把节点 parent_id 重写为 None（提升为根），不泄露隐藏父节点

设计要点：
    - 数据库是真相源；启动时 ``preload_all`` 把节点载入内存缓存
    - 所有写操作同步内存与 DB
    - 复用 OwnershipScope 与 api_config_service 的成熟模式

调用关系：
    - lifespan → UserServerService(db, devops_server_service) → app.state.user_server_service
    - user_server_router → service.list_nodes / create_node / update_node / delete_node / get_node_config / import_from_devops_servers
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from app.shared.utils.auth.ownership_scope import OwnershipScope


logger = logging.getLogger(__name__)


# 节点类型枚举（与 DB CHECK 约束对齐）
NODE_TYPES = ("folder", "server")

# server 节点详情白名单（与「服务器扫描入库」详情端点同口径）
# 2026-08-03 改造：devops_servers 表删除 inspection_script / inspection_parser /
# inspection_fields 三列，仅保留 inspection_script_id 外键。
# 因此 server 节点详情也改为返回 inspection_script_id / inspection_script_name /
# inspection_script_display_name 三键（service 层通过 InspectionScriptService 解析）。
_DETAIL_FIELDS = (
    "id",
    "business_name",
    "server_type",
    "updated_at",
    "whitelist",
    "inspection_script_id",
    "inspection_script_name",
    "inspection_script_display_name",
)


class UserServerNodeNotFoundError(LookupError):
    """节点不存在或越权时抛出（路由层映射 404）。

    不区分"不存在"与"无权访问"，防止通过状态码差异探测节点存在性。
    """


class UserServerNodeNotEmptyError(ValueError):
    """folder 非空时抛出（路由层映射 400）。"""


class UserServerService:
    """用户服务器配置服务（结构对标 ApiConfigService）。

    参数:
        db: 数据库连接池（asyncpg），需支持 fetch / fetchrow / execute；
            None 表示内存降级模式（写操作抛 RuntimeError）。
        devops_server_service: DevOpsServerService 实例；用于读取
            devops_servers 脱敏列表（导入源）与节点详情 JOIN。
            None 时 import 仍能调但 get_node_config 的 server 详情会失败。
    """

    def __init__(self, db: Any, devops_server_service: Any = None) -> None:
        """初始化服务。

        参数:
            db: 数据库连接池；None 时进入降级模式（写操作抛 RuntimeError）。
            devops_server_service: DevOpsServerService 实例（lifespan 注入）；
                提供 list_public_servers 与 get_server_detail。
        """
        self._db = db
        self._devops_server_service = devops_server_service
        # 内存缓存：node_id -> 节点 dict
        self._nodes: Dict[int, Dict[str, Any]] = {}
        # devops_servers 索引：id -> devops_servers 脱敏行（由 _ensure_devops_index 懒加载）
        self._devops_index: Dict[int, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # DB availability
    # ------------------------------------------------------------------

    def _require_db(self) -> None:
        """确认数据库可用。

        返回:
            None。

        异常:
            RuntimeError: db 为 None（数据库未启用）时抛出。
        """
        if self._db is None:
            raise RuntimeError("数据库未启用")

    # ------------------------------------------------------------------
    # Preload from DB
    # ------------------------------------------------------------------

    async def preload_all(self) -> None:
        """启动时把全部 user_server_nodes 行载入内存缓存。

        返回:
            None。
        """
        if self._db is None:
            return
        try:
            rows = await self._db.fetch(
                "SELECT * FROM user_server_nodes ORDER BY id ASC"
            )
            for row in rows:
                node = dict(row)
                self._nodes[node["id"]] = node
            logger.info(
                "[user_server_service] preloaded %d node(s)",
                len(self._nodes),
            )
        except Exception as exc:
            logger.warning(
                "[user_server_service] preload failed: %s", exc, exc_info=True
            )

    # ------------------------------------------------------------------
    # Ownership helpers
    # ------------------------------------------------------------------

    def _assert_node_access(
        self,
        node: Optional[Dict[str, Any]],
        scope: OwnershipScope,
    ) -> Dict[str, Any]:
        """校验当前 scope 对节点的可见性。

        缺失与越权不区分（防止通过 404/403 探测节点存在性）。

        参数:
            node: 节点 dict（来自内存缓存）；None 表示不存在。
            scope: 调用方归属上下文。

        返回:
            Dict[str, Any]: 节点 dict（便于链式调用）。

        异常:
            UserServerNodeNotFoundError: 节点不存在或越权时抛出。
        """
        if node is None:
            raise UserServerNodeNotFoundError("节点不存在")
        if not scope.can_access(node.get("created_by_user_id")):
            raise UserServerNodeNotFoundError("节点不存在")
        return node

    # ------------------------------------------------------------------
    # List nodes (tree-flat, scope-filtered)
    # ------------------------------------------------------------------

    def list_nodes(self, scope: OwnershipScope) -> List[Dict[str, Any]]:
        """返回节点平铺列表，按 ``scope`` 过滤可见性。

        admin / system 透传全量；普通用户仅返回自己创建的节点。若过滤后
        某节点的 ``parent_id`` 不在可见集合内，则将其 ``parent_id`` 重写
        为 ``None``（提升为根）以便前端组树时仍能渲染——同时不会泄露
        隐藏父节点的存在。

        对 ``node_type='server'`` 的节点附带 ``business_name`` / ``server_type``
        （2026-07-26 新增）：由 ``source_devops_server_id`` 关联到
        ``devops_servers`` 内存缓存（``list_public_servers`` 已是脱敏 4
        字段白名单，零 DB 开销），供「编辑任务」表单的 server_list 候选
        直接复用。源行已被删除（外键 CASCADE 正常会清掉引用节点，但保留
        防御）时 ``business_name`` / ``server_type`` 留 ``None``，由前端
        maskServers 过滤掉。

        参数:
            scope: 调用方归属上下文。

        返回:
            List[Dict[str, Any]]: 节点列表，按 id 升序。
        """
        all_nodes = sorted(self._nodes.values(), key=lambda n: n["id"])
        # 2026-07-26：devops_servers 脱敏列表用于 server 节点附加字段
        devops_index = self._build_devops_index()
        if scope.system or scope.is_admin:
            return [self._attach_devops_fields(dict(n), devops_index) for n in all_nodes]
        visible_ids: Set[int] = {
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
            result.append(self._attach_devops_fields(copied, devops_index))
        return result

    def _build_devops_index(self) -> Dict[int, Dict[str, Any]]:
        """拉取 devops_servers 脱敏列表并构造成 id → row 索引。

        返回:
            Dict[int, Dict[str, Any]]: devops_servers 行索引，键为 id。
            devops_server_service 未注入时返回空字典。
        """
        if self._devops_server_service is None:
            return {}
        rows = self._devops_server_service.list_public_servers() or []
        return {row.get("id"): row for row in rows if row.get("id") is not None}

    @staticmethod
    def _attach_devops_fields(
        node: Dict[str, Any], devops_index: Dict[int, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """对 server 节点附加 ``business_name`` / ``server_type``。

        参数:
            node: 节点 dict（已被复制）。
            devops_index: devops_servers 行索引。

        返回:
            Dict[str, Any]: 节点 dict（server 节点附带 2 个字段）。
        """
        if node.get("node_type") != "server":
            return node
        source_id = node.get("source_devops_server_id")
        if source_id is None:
            return node
        devops_row = devops_index.get(source_id)
        if devops_row is None:
            return node
        node["business_name"] = devops_row.get("business_name")
        node["server_type"] = devops_row.get("server_type")
        return node

    # ------------------------------------------------------------------
    # Create / update / delete
    # ------------------------------------------------------------------

    async def create_node(
        self,
        parent_id: Optional[int],
        node_type: str,
        name: str,
        scope: OwnershipScope,
        source_devops_server_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """创建节点（folder / server）。

        folder 节点：``source_devops_server_id`` 必须为 None。
        server 节点：``source_devops_server_id`` 必须指向已存在的 devops_servers.id。

        非 admin 创建节点的归属为 ``scope.user_id``；父节点必须是 ``None``
        或当前用户可见（且为 folder）的节点；不可见的父节点一律报「父节点
        不存在」，不泄露他人节点的存在。

        参数:
            parent_id: 父节点 ID；None 表示根节点。
            node_type: 节点类型，'folder' 或 'server'。
            name: 节点名称。
            scope: 调用方归属上下文。
            source_devops_server_id: server 节点引用的 devops_servers.id；
                folder 节点必须为 None。

        返回:
            Dict[str, Any]: 新建节点字典。

        异常:
            ValueError: node_type 非法、name 为空、``scope.user_id`` 缺失、
                父节点不存在或父节点不是 folder 类型、server 节点缺少
                source_devops_server_id、folder 节点传了 source_devops_server_id、
                源 devops_servers 不存在时抛出。
            RuntimeError: 数据库未启用 / DevOpsServerService 未注入时抛出。
        """
        self._require_db()
        if scope.user_id is None:
            raise ValueError("无法确定创建人用户，请通过 HTTP 路由调用")
        if node_type not in NODE_TYPES:
            raise ValueError(
                f"node_type 必须是 {NODE_TYPES} 之一，当前为: {node_type!r}"
            )
        if not str(name or "").strip():
            raise ValueError("节点名称不能为空")
        if node_type == "folder":
            if source_devops_server_id is not None:
                raise ValueError("folder 节点不能引用 devops_servers")
        else:  # server
            if source_devops_server_id is None:
                raise ValueError("server 节点必须指定 source_devops_server_id")
            # 验证 devops_servers 行存在（不暴露其内容，仅校验可见性）
            await self._assert_devops_server_exists(source_devops_server_id)

        if parent_id is not None:
            try:
                parent = self._assert_node_access(self._nodes.get(parent_id), scope)
            except UserServerNodeNotFoundError:
                raise ValueError(f"父节点不存在: {parent_id}") from None
            if parent.get("node_type") != "folder":
                raise ValueError(f"父节点必须是 folder 类型: {parent_id}")

        row = await self._db.fetchrow(
            """
            INSERT INTO user_server_nodes
                (parent_id, node_type, name, sort_order,
                 source_devops_server_id, created_by_user_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            parent_id,
            node_type,
            name,
            0,
            source_devops_server_id,
            scope.user_id,
        )
        node = dict(row)
        self._nodes[node["id"]] = node
        return node

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
            UserServerNodeNotFoundError: 节点不存在或越权时抛出。
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
            UPDATE user_server_nodes
            SET name = COALESCE($2, name),
                parent_id = COALESCE($3, parent_id),
                sort_order = COALESCE($4, sort_order),
                updated_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            node_id,
            name,
            parent_id,
            sort_order,
        )
        if row is None:
            raise UserServerNodeNotFoundError(f"节点不存在: {node_id}")
        node = dict(row)
        self._nodes[node_id] = node
        return node

    def _assert_valid_parent(
        self, node_id: int, parent_id: int, scope: OwnershipScope
    ) -> None:
        """校验 parent_id 可作为 node_id 的新父节点（可见、folder、无环）。

        参数:
            node_id: 待移动节点 ID。
            parent_id: 目标父节点 ID。
            scope: 调用方归属上下文。

        返回:
            None。

        异常:
            ValueError: 目标父节点不可见 / 不是 folder / 是节点自身或节点
                后代时抛出。
        """
        try:
            parent = self._assert_node_access(self._nodes.get(parent_id), scope)
        except UserServerNodeNotFoundError:
            raise ValueError(f"父节点不存在: {parent_id}") from None
        if parent.get("node_type") != "folder":
            raise ValueError(f"父节点必须是 folder 类型: {parent_id}")
        # 沿祖先链向上走，若遇到 node_id 说明目标父节点是自身或后代
        cursor: Optional[int] = parent_id
        while cursor is not None:
            if cursor == node_id:
                raise ValueError("目标父节点是节点自身或其后代，拒绝成环")
            cursor = self._nodes.get(cursor, {}).get("parent_id")

    async def delete_node(self, node_id: int, scope: OwnershipScope) -> None:
        """删除节点；folder 非空时拒绝。

        非空判定统计**全部**子节点（包括当前用户不可见的他人节点），
        防止误删隐藏内容；满足「不泄露他人节点存在」与「安全删除」两个
        约束。

        参数:
            node_id: 节点 ID。
            scope: 调用方归属上下文。

        返回:
            None。

        异常:
            UserServerNodeNotFoundError: 节点不存在或越权时抛出。
            UserServerNodeNotEmptyError: 文件夹非空时抛出。
            RuntimeError: 数据库未启用时抛出。
        """
        self._require_db()
        self._assert_node_access(self._nodes.get(node_id), scope)
        children = [n for n in self._nodes.values() if n.get("parent_id") == node_id]
        if children:
            raise UserServerNodeNotEmptyError("文件夹非空，拒绝删除")
        await self._db.execute(
            "DELETE FROM user_server_nodes WHERE id = $1",
            node_id,
        )
        # DB 层 ON DELETE CASCADE 已级联删除 user_server_configs
        del self._nodes[node_id]

    # ------------------------------------------------------------------
    # Node config (server 节点详情 JOIN devops_servers)
    # ------------------------------------------------------------------

    async def get_node_config(
        self, node_id: int, scope: OwnershipScope
    ) -> Dict[str, Any]:
        """获取节点详情。

        folder 节点：返回 ``{"node_type": "folder", "name": ..., ...}``。
        server 节点：返回 user_server_nodes 行 + JOIN devops_servers 的白名单
        字段（business_name / server_type / updated_at / whitelist /
        inspection_script_id / inspection_script_name /
        inspection_script_display_name，2026-08-03 巡检脚本库改造后）。

        参数:
            node_id: 节点 ID。
            scope: 调用方归属上下文。

        返回:
            Dict[str, Any]: 节点详情字典。

        异常:
            UserServerNodeNotFoundError: 节点不存在或越权时抛出。
            ValueError: server 节点引用的 devops_servers 行已被删除时抛出。
            RuntimeError: 数据库未启用时抛出。
        """
        self._require_db()
        node = self._assert_node_access(self._nodes.get(node_id), scope)
        if node.get("node_type") == "folder":
            return {
                "node_type": "folder",
                "id": node.get("id"),
                "parent_id": node.get("parent_id"),
                "name": node.get("name"),
                "sort_order": node.get("sort_order"),
                "created_by_user_id": node.get("created_by_user_id"),
                "created_at": node.get("created_at"),
                "updated_at": node.get("updated_at"),
            }
        # server 节点：从 devops_servers 实时 JOIN 取详情
        source_id = node.get("source_devops_server_id")
        if source_id is None:
            raise ValueError(
                f"server 节点缺少 source_devops_server_id: {node_id}"
            )
        devops_detail = await self._get_devops_server_detail(source_id)
        if devops_detail is None:
            raise ValueError(
                f"引用的 devops_servers 行不存在或已被删除: {source_id}"
            )
        return {
            "node_type": "server",
            "id": node.get("id"),
            "parent_id": node.get("parent_id"),
            "name": node.get("name"),
            "sort_order": node.get("sort_order"),
            "source_devops_server_id": source_id,
            "created_by_user_id": node.get("created_by_user_id"),
            "created_at": node.get("created_at"),
            "updated_at": node.get("updated_at"),
            # JOIN devops_servers 的白名单字段（2026-08-03 改造：返回脚本元数据而非原文）
            "business_name": devops_detail.get("business_name"),
            "server_type": devops_detail.get("server_type"),
            "devops_updated_at": devops_detail.get("updated_at"),
            "whitelist": list(devops_detail.get("whitelist") or []),
            "inspection_script_id": devops_detail.get("inspection_script_id"),
            "inspection_script_name": devops_detail.get("inspection_script_name"),
            "inspection_script_display_name": devops_detail.get("inspection_script_display_name"),
        }

    # ------------------------------------------------------------------
    # Import from devops_servers
    # ------------------------------------------------------------------

    async def import_from_devops_servers(
        self,
        parent_id: Optional[int],
        business_names: List[str],
        scope: OwnershipScope,
    ) -> Dict[str, Any]:
        """批量把 devops_servers 导入到用户私有 tree。

        行为：
            - 校验 parent_id（folder 类型且当前用户可见）；非空才合法
            - 校验 devops_server_service 可用
            - business_names 去重 + 校验非空
            - 按 devops_servers 实际行匹配（business_name 唯一）；
              找不到的 business_name 计入 failed
            - 同一用户对同一 devops_server 在同 parent_id 下重复导入 → 跳过 + 计入 skipped
            - 成功导入 → 写入 user_server_nodes（node_type='server'），
              source_devops_server_id 指向底层行

        参数:
            parent_id: 父 folder ID；None 表示根。
            business_names: 要导入的 devops_servers.business_name 列表。
            scope: 调用方归属上下文。

        返回:
            Dict[str, Any]: ``{"imported": int, "skipped": int, "failed": int, "node_ids": [int]}``

        异常:
            ValueError: 父节点非法 / business_names 为空 / DevOpsServerService 未注入。
            RuntimeError: 数据库未启用 / 底层服务缺失时抛出。
        """
        if not business_names:
            raise ValueError("business_names 不能为空")
        self._require_db()
        if self._devops_server_service is None:
            raise RuntimeError("DevOpsServerService 未注入，无法导入")

        # 1) 校验父节点（folder 类型且当前用户可见）
        if parent_id is not None:
            try:
                parent = self._assert_node_access(self._nodes.get(parent_id), scope)
            except UserServerNodeNotFoundError:
                raise ValueError(f"父节点不存在: {parent_id}") from None
            if parent.get("node_type") != "folder":
                raise ValueError(f"父节点必须是 folder 类型: {parent_id}")

        # 2) 拉取 devops_servers 全量（脱敏 4 字段）用于 business_name → id 映射
        public_servers = self._devops_server_service.list_public_servers()
        # public_servers 每项含 {id, business_name, server_type, updated_at}
        by_name: Dict[str, Dict[str, Any]] = {
            s.get("business_name"): s for s in public_servers if s.get("business_name")
        }

        # 3) 同一用户对同一 source_devops_server_id 在同 parent_id 下查重
        existing_pairs: Set[tuple] = {
            (n.get("source_devops_server_id"), n.get("parent_id"))
            for n in self._nodes.values()
            if scope.can_access(n.get("created_by_user_id"))
        }

        imported = 0
        skipped = 0
        failed = 0
        node_ids: List[int] = []
        seen_in_batch: Set[str] = set()  # 同一请求内去重
        for name in business_names:
            normalized = (name or "").strip()
            if not normalized or normalized in seen_in_batch:
                continue
            seen_in_batch.add(normalized)
            devops_row = by_name.get(normalized)
            if devops_row is None:
                failed += 1
                continue
            source_id = devops_row.get("id")
            if (source_id, parent_id) in existing_pairs:
                skipped += 1
                continue
            try:
                created = await self.create_node(
                    parent_id=parent_id,
                    node_type="server",
                    name=normalized,
                    scope=scope,
                    source_devops_server_id=source_id,
                )
                node_ids.append(created["id"])
                existing_pairs.add((source_id, parent_id))
                imported += 1
            except Exception as exc:  # noqa: BLE001 - 单条失败不阻断整批
                logger.warning(
                    "[user_server_service] import failed for %s: %s",
                    normalized,
                    type(exc).__name__,
                )
                failed += 1

        return {
            "imported": imported,
            "skipped": skipped,
            "failed": failed,
            "node_ids": node_ids,
        }

    # ------------------------------------------------------------------
    # Helpers: devops_servers lookup
    # ------------------------------------------------------------------

    async def _assert_devops_server_exists(self, server_id: int) -> None:
        """校验 devops_servers 行存在（用于创建 server 节点前的探测）。

        参数:
            server_id: devops_servers.id。

        返回:
            None。

        异常:
            ValueError: 行不存在 / DevOpsServerService 未注入。
        """
        if self._devops_server_service is None:
            raise RuntimeError("DevOpsServerService 未注入")
        exists = await self._devops_server_service.server_exists(server_id)
        if not exists:
            raise ValueError(f"devops_servers 行不存在: {server_id}")

    async def _get_devops_server_detail(
        self, server_id: int
    ) -> Optional[Dict[str, Any]]:
        """取 devops_servers 详情（白名单字段，admin-only 接口同口径）。

        参数:
            server_id: devops_servers.id。

        返回:
            Optional[Dict[str, Any]]: 详情 dict；行不存在时 None。
        """
        if self._devops_server_service is None:
            return None
        return self._devops_server_service.get_server_detail(server_id)
