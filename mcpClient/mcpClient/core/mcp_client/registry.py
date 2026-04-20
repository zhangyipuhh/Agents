#!/usr/bin/python
# -*- coding:utf-8 -*-
"""MCP 工具全局注册中心模块

提供 MCPToolsRegistry 单例类，用于集中管理所有 MCP 服务器的工具注册、
查询与刷新。支持按标签、名称、服务器等条件组合筛选工具。
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolEntry:
    """工具条目，封装 MCP 工具对象及其元信息

    Attributes:
        tool: MCP 工具对象
        server_name: 所属服务器名称
        tags: 继承自 server 配置的标签列表
    """

    tool: Any
    server_name: str
    tags: List[str] = field(default_factory=list)


class MCPToolsRegistry:
    """全局 MCP 工具注册中心（单例）

    集中管理来自多个 MCP 服务器的工具，支持按标签、名称、服务器等
    条件组合查询工具，并可通过 MCPClientPool 刷新工具列表。
    """

    _instance: Optional["MCPToolsRegistry"] = None

    def __init__(self) -> None:
        """初始化注册中心内部数据结构"""
        self._tools: Dict[str, ToolEntry] = {}       # tool_name -> ToolEntry
        self._server_tags: Dict[str, List[str]] = {}  # server_name -> tags
        self._pool: Optional[Any] = None              # MCPClientPool 引用

    @classmethod
    def get_instance(cls) -> "MCPToolsRegistry":
        """获取单例实例

        Returns:
            MCPToolsRegistry: 全局唯一的注册中心实例
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_tools(
        self,
        tools: List[Any],
        server_name: str,
        tags: Optional[List[str]] = None,
    ) -> None:
        """注册 MCP 工具到全局注册表

        将工具列表中的每个工具以 tool_name 为键存入注册表，
        同时记录服务器与标签的映射关系。若同名工具已存在则覆盖。

        Args:
            tools: MCP 工具对象列表
            server_name: 所属服务器名称
            tags: 继承自服务器配置的标签列表，默认为空
        """
        tags = tags or []
        self._server_tags[server_name] = tags
        for tool in tools:
            tool_name = tool.name if hasattr(tool, "name") else str(tool)
            self._tools[tool_name] = ToolEntry(
                tool=tool,
                server_name=server_name,
                tags=list(tags),
            )
            logger.debug(
                "Registered tool '%s' from server '%s' with tags %s",
                tool_name,
                server_name,
                tags,
            )

    def get_tools(
        self,
        tags: Optional[List[str]] = None,
        names: Optional[List[str]] = None,
        server: Optional[str] = None,
    ) -> List[Any]:
        """按条件选取工具，支持组合条件（AND 逻辑）

        - tags 内部为 OR 匹配（工具 tags 中至少有一个匹配即可）
        - names 为精确匹配
        - server 为精确匹配
        - 多条件组合为 AND 逻辑

        Args:
            tags: 标签过滤列表，工具标签中至少命中一个即匹配
            names: 工具名称精确匹配列表
            server: 服务器名称精确匹配

        Returns:
            List[Any]: 符合所有指定条件的工具对象列表
        """
        results: List[ToolEntry] = list(self._tools.values())

        if tags:
            results = [e for e in results if any(t in e.tags for t in tags)]

        if names:
            results = [
                e
                for e in results
                if hasattr(e.tool, "name") and e.tool.name in names
            ]

        if server:
            results = [e for e in results if e.server_name == server]

        return [e.tool for e in results]

    async def refresh_tools(self, server_name: Optional[str] = None) -> None:
        """刷新工具列表

        通过 MCPClientPool 重新获取服务器工具信息并更新注册表。
        当 server_name 为 None 时刷新所有已注册的服务器。

        Args:
            server_name: 指定刷新的服务器名称，为 None 时刷新全部

        Raises:
            RuntimeError: 当 MCPClientPool 尚未设置时抛出
        """
        if self._pool is None:
            raise RuntimeError("MCPClientPool not set. Call set_pool() first.")

        if server_name:
            await self._refresh_server(server_name)
        else:
            for name in list(self._server_tags.keys()):
                await self._refresh_server(name)

    async def _refresh_server(self, server_name: str) -> None:
        """刷新指定服务器的工具列表

        从 MCPClientPool 获取指定服务器的工具信息，并重新注册。

        Args:
            server_name: 需要刷新的服务器名称
        """
        if self._pool is None:
            return

        server_info = self._pool.get_server_tools(server_name)
        if server_info:
            tools = server_info.get("tools", [])
            tags = server_info.get("tags", [])
            self.register_tools(tools, server_name, tags)
            logger.info("Refreshed tools for server '%s'", server_name)

    def get_all_tools(self) -> List[Any]:
        """获取所有已注册的工具

        Returns:
            List[Any]: 所有已注册的工具对象列表
        """
        return [e.tool for e in self._tools.values()]

    def set_pool(self, pool: Any) -> None:
        """设置 MCPClientPool 引用

        Args:
            pool: MCPClientPool 实例，用于后续刷新工具列表
        """
        self._pool = pool

    async def initialize(
        self,
        pool: Any,
        server_configs: Dict[str, dict],
    ) -> None:
        """从配置初始化注册表

        遍历服务器配置，通过 MCPClientPool 获取每个服务器的工具信息
        并完成注册。

        Args:
            pool: MCPClientPool 实例
            server_configs: 服务器配置字典，格式为 {server_name: config}，
                config 中可包含 "tags" 字段
        """
        self._pool = pool
        for name, config in server_configs.items():
            server_info = pool.get_server_tools(name)
            if server_info:
                tools = server_info.get("tools", [])
                tags = config.get("tags", [])
                self.register_tools(tools, name, tags)
                logger.info(
                    "Initialized tools for server '%s' with tags %s",
                    name,
                    tags,
                )

    def clear(self) -> None:
        """清空注册表

        移除所有已注册的工具条目和服务器标签映射，但保留 pool 引用。
        """
        self._tools.clear()
        self._server_tags.clear()
        logger.debug("Registry cleared")
