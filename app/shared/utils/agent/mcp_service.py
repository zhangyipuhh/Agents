#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
MCP 配置 CRUD 服务模块

提供 MCP server 配置的数据库 CRUD 操作，供 mcp_admin_router 调用。
启动时若 mcp_server_configs 表为空，从 YAML 种子文件导入。

Date: 2026-06-23
Author: AI Assistant
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


@dataclass
class McpServerConfig:
    """MCP 服务器配置数据类。"""
    name: str
    display_name: str = ""
    type: str = "sse"
    url: Optional[str] = None
    command: Optional[List[str]] = None
    timeout: int = 5
    read_timeout: int = 300
    tags: List[str] = field(default_factory=list)
    enabled: bool = True
    progress_reporting: Dict[str, Any] = field(default_factory=lambda: {"enabled": False})
    tool_config: Dict[str, Any] = field(default_factory=lambda: {
        "enable_injection": True, "default_param_keys": [],
        "hidden_param_keys": [], "unwrap_result": False,
    })
    sampling: Dict[str, Any] = field(default_factory=lambda: {"enabled": False})


class McpConfigService:
    """MCP 配置 CRUD 服务。

    参数:
        db: 数据库连接池（需支持 fetch/fetchrow/execute 异步方法）
    """

    # JSONB 字段：tags / progress_reporting / tool_config / sampling /
    # command 需要在读出时防御性反序列化为 list / dict
    _JSONB_FIELDS = ("tags", "progress_reporting", "tool_config", "sampling", "command")

    def __init__(self, db: Any) -> None:
        self._db = db

    @staticmethod
    def _decode_jsonb(value: Any, default: Any) -> Any:
        """防御性反序列化 JSONB 字段。

        asyncpg 默认不注册 JSONB codec，从数据库读出的 JSONB 字段是 str
        类型；如果将来连接池注册了 codec，则直接是 dict/list。两种情况
        都需兼容：str 用 json.loads 解析，dict/list 原样返回，None 走默认。

        参数:
            value: 数据库返回的字段值，可能为 None / str / dict / list
            default: 当 value 为 None 时返回的默认值

        返回:
            Any: 反序列化后的 Python 对象（dict / list / 默认值）
        """
        if value is None:
            return default
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                logger.warning("Failed to decode JSONB value, fallback to default")
                return default
        return value

    @classmethod
    def _decode_row(cls, row: Any) -> Dict[str, Any]:
        """将 DB row 转为 dict，并对其中的 JSONB 字段执行反序列化。

        用于统一 list_servers / get_server / create_server / update_server
        四个读路径，避免每处都重复 _decode_jsonb 调用。
        """
        if row is None:
            return None
        result = dict(row)
        for field in cls._JSONB_FIELDS:
            if field in result:
                # 字段缺省值：tags=[] / progress_reporting={"enabled": False} 等
                default: Any
                if field == "tags":
                    default = []
                elif field == "command":
                    default = None
                else:
                    default = {"enabled": False}
                result[field] = cls._decode_jsonb(result[field], default)
        return result

    async def list_servers(self) -> List[Dict[str, Any]]:
        """列出所有 MCP server 配置。"""
        rows = await self._db.fetch(
            "SELECT * FROM mcp_server_configs ORDER BY created_at"
        )
        return [self._decode_row(r) for r in rows]

    async def get_server(self, name: str) -> Optional[Dict[str, Any]]:
        """获取单个 server 配置。

        参数:
            name: server 名称

        返回:
            Dict 或 None
        """
        row = await self._db.fetchrow(
            "SELECT * FROM mcp_server_configs WHERE name = $1", name
        )
        return self._decode_row(row) if row else None

    async def create_server(self, config: McpServerConfig) -> Dict[str, Any]:
        """新增 MCP server。

        参数:
            config: server 配置

        返回:
            Dict: 新建的 server 配置

        异常:
            ValueError: name 已存在时抛出
        """
        existing = await self.get_server(config.name)
        if existing:
            raise ValueError(f"MCP server '{config.name}' already exists")

        row = await self._db.fetchrow(
            """
            INSERT INTO mcp_server_configs
                (name, display_name, type, url, command, timeout, read_timeout,
                 tags, enabled, progress_reporting, tool_config, sampling)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING *
            """,
            config.name, config.display_name, config.type, config.url,
            json.dumps(config.command) if config.command else None,
            config.timeout, config.read_timeout,
            json.dumps(config.tags), config.enabled,
            json.dumps(config.progress_reporting),
            json.dumps(config.tool_config),
            json.dumps(config.sampling),
        )
        return dict(row)

    async def update_server(self, name: str, config: McpServerConfig) -> Dict[str, Any]:
        """更新 MCP server 配置。

        异常:
            ValueError: server 不存在时抛出
        """
        row = await self._db.fetchrow(
            """
            UPDATE mcp_server_configs SET
                display_name = $2, type = $3, url = $4, command = $5,
                timeout = $6, read_timeout = $7, tags = $8, enabled = $9,
                progress_reporting = $10, tool_config = $11, sampling = $12,
                updated_at = CURRENT_TIMESTAMP
            WHERE name = $1
            RETURNING *
            """,
            name, config.display_name, config.type, config.url,
            json.dumps(config.command) if config.command else None,
            config.timeout, config.read_timeout,
            json.dumps(config.tags), config.enabled,
            json.dumps(config.progress_reporting),
            json.dumps(config.tool_config),
            json.dumps(config.sampling),
        )
        if not row:
            raise ValueError(f"MCP server '{name}' not found")
        return dict(row)

    async def delete_server(self, name: str) -> None:
        """删除 MCP server 及其关联 methods。"""
        await self._db.execute(
            "DELETE FROM mcp_server_methods WHERE server_name = $1", name
        )
        await self._db.execute(
            "DELETE FROM mcp_server_configs WHERE name = $1", name
        )

    async def toggle_server(self, name: str, enabled: bool) -> None:
        """启用/禁用 MCP server。"""
        await self._db.execute(
            "UPDATE mcp_server_configs SET enabled = $2, updated_at = CURRENT_TIMESTAMP WHERE name = $1",
            name, enabled,
        )

    async def list_methods(self, server_name: str) -> List[Dict[str, Any]]:
        """列出 server 下所有 method。"""
        rows = await self._db.fetch(
            "SELECT * FROM mcp_server_methods WHERE server_name = $1 ORDER BY method_name",
            server_name,
        )
        return [dict(r) for r in rows]

    async def toggle_method(self, server_name: str, method_name: str, enabled: bool) -> None:
        """启用/禁用单个 method。"""
        await self._db.execute(
            "UPDATE mcp_server_methods SET enabled = $3 WHERE server_name = $1 AND method_name = $2",
            server_name, method_name, enabled,
        )

    async def upsert_methods(self, server_name: str, methods: List[Dict[str, Any]]) -> None:
        """批量 upsert method 列表（刷新方法列表时调用）。"""
        for m in methods:
            await self._db.execute(
                """
                INSERT INTO mcp_server_methods (server_name, method_name, enabled, description)
                VALUES ($1, $2, TRUE, $3)
                ON CONFLICT (server_name, method_name) DO UPDATE SET
                    description = EXCLUDED.description
                """,
                server_name, m.get("method_name", ""), m.get("description", ""),
            )
        await self._db.execute(
            "UPDATE mcp_server_configs SET methods_synced_at = CURRENT_TIMESTAMP WHERE name = $1",
            server_name,
        )

    async def refresh_methods_from_server(self, server_name: str) -> List[Dict[str, Any]]:
        """从 MCP server 拉取最新 method 列表并更新数据库。

        参数:
            server_name: MCP server 名称

        返回:
            List[Dict]: method 列表

        异常:
            ValueError: server 不存在时抛出
            Exception: MCP server 连接失败时抛出
        """
        server = await self.get_server(server_name)
        if not server:
            raise ValueError(f"MCP server '{server_name}' not found")

        # 从 MCPToolsRegistry 获取已注册的 tools（methods）
        try:
            from app.core.tools.mcp_registry import MCPToolsRegistry
            registry = MCPToolsRegistry.get_instance()
            tools_with_server = registry.get_tools_with_server(server=server_name)

            methods = []
            for tool, srv_name, srv_config in tools_with_server:
                methods.append({
                    "method_name": getattr(tool, "name", str(tool)),
                    "description": getattr(tool, "description", ""),
                })

            await self.upsert_methods(server_name, methods)
            return methods
        except Exception as e:
            logger.warning("Failed to refresh methods from server '%s': %s", server_name, e)
            raise

    async def seed_from_yaml_if_empty(self) -> None:
        """数据库为空时从 YAML 种子文件导入。"""
        rows = await self._db.fetch("SELECT name FROM mcp_server_configs")
        if rows:
            logger.info("MCP server configs already seeded (%d rows), skip YAML import", len(rows))
            return

        yaml_configs = self._load_yaml_seed()
        if not yaml_configs:
            logger.warning("No MCP seed configs found in YAML")
            return

        for name, cfg in yaml_configs.items():
            config = McpServerConfig(
                name=name,
                display_name=cfg.get("display_name", name),
                type=cfg.get("type", "sse"),
                url=cfg.get("url"),
                command=cfg.get("command"),
                timeout=cfg.get("timeout", 5),
                read_timeout=cfg.get("read_timeout", 300),
                tags=cfg.get("tags", []),
                enabled=cfg.get("enabled", True),
                progress_reporting=cfg.get("progress_reporting", {"enabled": False}),
                tool_config=cfg.get("tool_config", {
                    "enable_injection": True, "default_param_keys": [],
                    "hidden_param_keys": [], "unwrap_result": False,
                }),
                sampling=cfg.get("sampling", {"enabled": False}),
            )
            await self.create_server(config)
            logger.info("Seeded MCP server '%s' from YAML", name)

    def _load_yaml_seed(self) -> Dict[str, Dict[str, Any]]:
        """从 YAML 种子文件加载配置。

        settings.mcp.mcp_config_path 是 Pydantic str 字段，但
        load_mcp_config 需要 Path 对象以调用 .exists()。在传入前
        显式转为 Path，修复 lifespan 启动种子失败的 bug。
        """
        try:
            from pathlib import Path
            from app.core.config.config import settings
            config_path = Path(settings.mcp.mcp_config_path)
            from mcpClient.shared.config_loader import load_mcp_config
            return load_mcp_config(config_path) or {}
        except Exception as e:
            logger.warning("Failed to load MCP YAML seed: %s", e)
            return {}
