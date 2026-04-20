#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MCPToolsRegistry 门面模块

该模块实现了 MCPToolsRegistry 门面类，作为 app/core 与 mcpClient 之间的桥梁，
封装 mcpClient 的 MCPClientPool 和 MCPToolsRegistry，提供统一的工具注册与选择接口。

Date: 2026-04-18
Author: 张镒谱
"""

import logging
from typing import Any, Dict, List, Optional

from mcpClient.core.mcp_client.client_pool import MCPClientPool
from mcpClient.core.mcp_client.registry import MCPToolsRegistry as _MCPToolsRegistry

logger = logging.getLogger(__name__)


class MCPToolsRegistry:
    """
    MCP 工具注册中心门面类

    作为 app/core 与 mcpClient 之间的桥梁，封装 mcpClient 的 MCPClientPool
    和 MCPToolsRegistry，提供统一的工具注册与选择接口。

    采用单例模式，确保全局只有一个注册中心实例。

    Attributes:
        _instance: 类级别的单例实例
        _pool: mcpClient 的连接池实例
        _registry: mcpClient 的 MCPToolsRegistry 实例（使用 Any 类型避免循环导入）
        _initialized: 是否已初始化
    """

    _instance: Optional["MCPToolsRegistry"] = None

    def __init__(self) -> None:
        """初始化门面类，所有内部属性置为空值"""
        self._pool: Optional[MCPClientPool] = None
        self._registry: Any = None
        self._initialized: bool = False

    @classmethod
    def get_instance(cls) -> "MCPToolsRegistry":
        """
        获取 MCPToolsRegistry 单例实例

        如果实例不存在则创建，否则返回已有实例。

        Returns:
            MCPToolsRegistry: 全局唯一的注册中心实例
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def initialize(self, configs: Dict[str, dict]) -> None:
        """
        初始化 MCP 工具注册中心

        创建连接池并连接所有配置的 MCP 服务器，然后初始化 mcpClient 的
        MCPToolsRegistry。如果某个服务器连接失败，记录日志但不中断整体初始化流程。

        Args:
            configs: MCP 服务器配置字典，格式为 {server_name: {type, url, tags, ...}}
        """
        # 创建连接池实例
        self._pool = MCPClientPool()

        # 遍历配置，逐个连接服务器
        for server_name, config in configs.items():
            try:
                await self._pool.connect(server_name, config)
                logger.info("MCP 服务器 [%s] 连接成功", server_name)
            except Exception:
                logger.exception("MCP 服务器 [%s] 连接失败，跳过", server_name)

        # 获取 mcpClient 的 MCPToolsRegistry 单例并初始化
        self._registry = _MCPToolsRegistry.get_instance()
        await self._registry.initialize(self._pool, configs)

        self._initialized = True
        logger.info("MCPToolsRegistry 初始化完成，共配置 %d 个服务器", len(configs))

    def get_tools(
        self,
        tags: Optional[List[str]] = None,
        names: Optional[List[str]] = None,
        server: Optional[str] = None,
    ) -> List[Any]:
        """
        根据条件查询工具列表

        委托给 mcpClient 的 MCPToolsRegistry 进行工具查询，支持按标签、
        名称和服务器名称进行过滤。

        Args:
            tags: 工具标签过滤列表，可选
            names: 工具名称过滤列表，可选
            server: 服务器名称过滤，可选

        Returns:
            List[Any]: 符合条件的工具列表；如果注册中心未初始化则返回空列表
        """
        if self._registry is None:
            logger.warning("MCPToolsRegistry 尚未初始化，无法查询工具")
            return []
        return self._registry.get_tools(tags=tags, names=names, server=server)

    def get_tools_with_server(
        self,
        tags: Optional[List[str]] = None,
        names: Optional[List[str]] = None,
        server: Optional[str] = None,
    ) -> List[tuple[Any, str]]:
        """
        根据条件查询工具列表，返回工具及其服务器名称

        Args:
            tags: 工具标签过滤列表，可选
            names: 工具名称过滤列表，可选
            server: 服务器名称过滤，可选

        Returns:
            List[tuple[Any, str]]: 工具及其服务器名称的元组列表；如果注册中心未初始化则返回空列表
        """
        if self._registry is None:
            logger.warning("MCPToolsRegistry 尚未初始化，无法查询工具")
            return []
        
        results: List[tuple[Any, str]] = []
        for entry in self._registry._tools.values():
            if tags and not any(t in entry.tags for t in tags):
                continue
            if names and (not hasattr(entry.tool, "name") or entry.tool.name not in names):
                continue
            if server and entry.server_name != server:
                continue
            results.append((entry.tool, entry.server_name))
        
        return results

    async def refresh_tools(self, server_name: Optional[str] = None) -> None:
        """
        刷新工具列表

        委托给 mcpClient 的 MCPToolsRegistry 刷新工具列表，可指定刷新
        某个服务器的工具，或不传参刷新所有服务器的工具。

        Args:
            server_name: 指定刷新的服务器名称，为 None 时刷新所有服务器

        Raises:
            RuntimeError: 注册中心未初始化时抛出
        """
        if self._registry is None:
            raise RuntimeError("MCPToolsRegistry 尚未初始化，无法刷新工具")
        await self._registry.refresh_tools(server_name=server_name)
        logger.info("工具列表刷新完成，server_name=%s", server_name)

    async def shutdown(self) -> None:
        """
        关闭注册中心，释放所有连接资源

        关闭连接池并重置初始化状态。
        """
        if self._pool is not None:
            await self._pool.shutdown()
            logger.info("MCPClientPool 已关闭")
        self._initialized = False
        logger.info("MCPToolsRegistry 已关闭")

    def get_all_tools(self) -> List[Any]:
        """
        获取所有已注册的工具列表

        委托给 mcpClient 的 MCPToolsRegistry 获取全部工具。

        Returns:
            List[Any]: 所有已注册的工具列表；如果注册中心未初始化则返回空列表
        """
        if self._registry is None:
            logger.warning("MCPToolsRegistry 尚未初始化，无法获取工具列表")
            return []
        return self._registry.get_all_tools()
