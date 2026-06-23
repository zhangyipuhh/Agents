#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MCPToolsRegistry 门面模块

该模块实现了 MCPToolsRegistry 门面类，作为 app/core 与 mcpClient 之间的桥梁，
封装 mcpClient 的 UnifiedMCPClient，提供统一的工具注册与选择接口。

Date: 2026-04-20
Author: 张镒谱
"""

import logging
from typing import Any, Dict, List, Optional

from mcpClient.core.unified_mcp_client import UnifiedMCPClient

logger = logging.getLogger(__name__)


class MCPToolsRegistry:
    """
    MCP 工具注册中心门面类

    作为 app/core 与 mcpClient 之间的桥梁，封装 mcpClient 的 UnifiedMCPClient，
    提供统一的工具注册与选择接口。

    采用单例模式，确保全局只有一个注册中心实例。

    Attributes:
        _instance: 类级别的单例实例
        _client: mcpClient 的 UnifiedMCPClient 实例
        _initialized: 是否已初始化
        _server_configs: 服务器配置
    """

    _instance: Optional["MCPToolsRegistry"] = None

    def __init__(self) -> None:
        self._client: Optional[UnifiedMCPClient] = None
        self._initialized: bool = False
        self._server_configs: Dict[str, dict] = {}

    @classmethod
    def get_instance(cls) -> "MCPToolsRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def initialize(self, configs: Dict[str, dict]) -> None:
        """
        初始化 MCP 工具注册中心

        创建 UnifiedMCPClient 实例并连接所有配置的 MCP 服务器。

        Args:
            configs: MCP 服务器配置字典，格式为 {server_name: {type, url, tags, ...}}
        """
        logger.info("开始初始化 MCPToolsRegistry，配置了 %d 个服务器", len(configs))
        self._server_configs = configs
        self._client = UnifiedMCPClient(configs)
        self._client.set_progress_callback(self._on_mcp_progress)
        self._initialized = True
        logger.info("MCPToolsRegistry 初始化完成，共配置 %d 个服务器", len(configs))

    async def _on_mcp_progress(self, progress, total, message, server_name):
        """MCP 进度通知 → LangGraph stream_writer → 前端"""
        try:
            from langgraph.config import get_stream_writer
            writer = get_stream_writer()
        except (ImportError, RuntimeError):
            return

        from app.core.tools.events import create_tool_event
        event = create_tool_event(
            event_type="tool_progress",
            tool=server_name,
            tool_call_id="mcp_progress",
            data={
                "progress": progress,
                "total": total,
                "message": message,
                "server_name": server_name,
            },
        )
        try:
            writer(dict(event))
        except Exception:
            pass

    async def get_tools(self) -> List[Any]:
        """
        获取所有 MCP 工具列表（带流式输出包装）

        Returns:
            List[Any]: 工具列表；如果注册中心未初始化则返回空列表
        """
        if self._client is None:
            logger.warning("MCPToolsRegistry 尚未初始化，无法查询工具")
            return []
        return await self._client.get_tools()

    def get_tools_with_server(
        self,
        tags: Optional[List[str]] = None,
        names: Optional[List[str]] = None,
        server: Optional[str] = None,
    ) -> List[tuple[Any, str, dict]]:
        """
        获取工具列表（带服务器信息）

        Args:
            tags: 工具标签过滤列表，可选
            names: 工具名称过滤列表，可选
            server: 服务器名称过滤，可选

        Returns:
            List[tuple[Any, str, dict]]: 工具及其服务器名称、服务器配置的元组列表
        """
        if self._client is None:
            logger.warning("MCPToolsRegistry 尚未初始化，无法查询工具")
            return []

        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        def run_async_in_thread():
            return asyncio.run(self._get_tools_with_server_async(tags, names, server))

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(run_async_in_thread)
                    return future.result(timeout=60)
            else:
                return loop.run_until_complete(
                    self._get_tools_with_server_async(tags, names, server)
                )
        except RuntimeError:
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(run_async_in_thread)
                    return future.result(timeout=60)
            except Exception as e:
                logger.warning("线程池获取工具失败: %r", e)
                return []
        except Exception as e:
            logger.warning("获取工具失败: %r", e)
            return []

    def _collect_tools_sync(
        self,
        server_names: List[str],
        tags: Optional[List[str]] = None,
        names: Optional[List[str]] = None,
        server: Optional[str] = None,
    ) -> List[tuple[Any, str, dict]]:
        """
        同步收集工具列表（带服务器信息）- 使用线程池执行异步代码

        注意：此方法使用线程池执行异步代码，适用于事件循环正在运行的场景。
        """
        from concurrent.futures import ThreadPoolExecutor
        import asyncio

        def run_async_in_thread():
            return asyncio.run(self._get_tools_with_server_async(tags, names, server))

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_async_in_thread)
                return future.result(timeout=60)
        except Exception as e:
            logger.warning("线程池方式获取工具失败: %r", e)
            return []

    async def _get_tools_with_server_async(
        self,
        tags: Optional[List[str]] = None,
        names: Optional[List[str]] = None,
        server: Optional[str] = None,
    ) -> List[tuple[Any, str, dict]]:
        """
        异步获取工具列表（带服务器信息）

        Args:
            tags: 工具标签过滤列表，可选
            names: 工具名称过滤列表，可选
            server: 服务器名称过滤，可选

        Returns:
            List[tuple[Any, str, dict]]: 工具及其服务器名称、服务器配置的元组列表
        """
        if self._client is None:
            logger.warning("MCPToolsRegistry 尚未初始化，无法查询工具")
            return []

        results: List[tuple[Any, str, dict]] = []
        server_names = self._client.get_server_names()
        
        if not server_names:
            logger.debug("没有配置任何 MCP 服务器")
            return []

        for server_name in server_names:
            if server and server_name != server:
                continue
            server_config = self._server_configs.get(server_name, {})
            server_tags = server_config.get("tags", [])
            if tags and not any(t in server_tags for t in tags):
                logger.debug(
                    "服务器 '%s' 的标签 %s 不匹配过滤标签 %s，跳过",
                    server_name, server_tags, tags
                )
                continue

            try:
                logger.debug("正在从服务器 '%s' 获取工具...", server_name)
                server_tools_info = await self._client.get_server_tools(server_name)
                
                if not server_tools_info:
                    logger.warning(
                        "服务器 '%s' 返回空的工具信息，可能是连接问题或验证错误",
                        server_name
                    )
                    continue

                tools = server_tools_info.get("tools", [])
                logger.info(
                    "从服务器 '%s' 获取到 %d 个工具",
                    server_name, len(tools)
                )

                for tool in tools:
                    tool_name = getattr(tool, "name", str(tool))
                    if names and tool_name not in names:
                        continue
                    results.append((tool, server_name, server_config))

            except Exception as e:
                error_msg = str(e)
                if "validation" in error_msg.lower() or "notification" in error_msg.lower():
                    logger.warning(
                        "服务器 '%s' 存在协议验证问题: %s (工具获取失败)",
                        server_name, error_msg
                    )
                else:
                    logger.error(
                        "从服务器 '%s' 获取工具时出错: %s",
                        server_name, error_msg, exc_info=True
                    )
                continue

        if not results:
            logger.debug(
                "未找到匹配的工具 (tags=%s, names=%s, server=%s)",
                tags, names, server
            )
        
        return results

    async def get_tools_with_server_async(
        self,
        tags: Optional[List[str]] = None,
        names: Optional[List[str]] = None,
        server: Optional[str] = None,
    ) -> List[tuple[Any, str, dict]]:
        """
        异步获取工具列表（带服务器信息）- 显式异步版本

        Args:
            tags: 工具标签过滤列表，可选
            names: 工具名称过滤列表，可选
            server: 服务器名称过滤，可选

        Returns:
            List[tuple[Any, str, dict]]: 工具及其服务器名称、服务器配置的元组列表
        """
        return await self._get_tools_with_server_async(tags, names, server)

    async def refresh_tools(self, server_name: Optional[str] = None) -> None:
        """
        刷新工具列表

        UnifiedMCPClient 通过 MultiServerMCPClient 自动管理工具发现，
        此方法为兼容接口，无需手动刷新。

        Args:
            server_name: 指定刷新的服务器名称（兼容参数，实际不使用）
        """
        logger.info(
            "工具列表刷新完成（UnifiedMCPClient 自动管理），server_name=%s", server_name
        )

    async def add_server(self, name: str, config: dict) -> None:
        """
        运行时新增 MCP server 配置

        将配置存入 _server_configs，并在客户端已初始化时尝试连接新服务器。
        连接失败仅记录 warning，不抛出异常，保证配置至少被持久化。

        Args:
            name: server 名称，作为 _server_configs 的键
            config: server 配置字典，格式为 {type, url, tags, ...}

        Returns:
            None

        Raises:
            不主动抛出异常；客户端连接失败时仅记录日志
        """
        self._server_configs[name] = config
        if self._client and self._initialized:
            try:
                await self._client.add_server(name, config)
            except Exception as e:
                logger.warning(
                    "运行时新增 MCP server '%s' 连接失败: %s", name, e
                )

    async def update_server(self, name: str, config: dict) -> None:
        """
        更新 MCP server 配置

        覆盖 _server_configs 中的旧配置，并在客户端已初始化时
        先移除旧服务器再添加新配置以重建连接。

        Args:
            name: server 名称
            config: 新的 server 配置字典

        Returns:
            None

        Raises:
            不主动抛出异常；客户端重建连接失败时仅记录日志
        """
        self._server_configs[name] = config
        if self._client and self._initialized:
            try:
                await self._client.remove_server(name)
                await self._client.add_server(name, config)
            except Exception as e:
                logger.warning(
                    "运行时更新 MCP server '%s' 连接失败: %s", name, e
                )

    async def remove_server(self, name: str) -> None:
        """
        移除 MCP server

        从 _server_configs 中删除指定配置，并在客户端已初始化时
        断开对应连接。配置不存在时静默忽略。

        Args:
            name: 要移除的 server 名称

        Returns:
            None

        Raises:
            不主动抛出异常；客户端断开失败时仅记录日志
        """
        self._server_configs.pop(name, None)
        if self._client and self._initialized:
            try:
                await self._client.remove_server(name)
            except Exception as e:
                logger.warning(
                    "运行时移除 MCP server '%s' 连接失败: %s", name, e
                )

    async def toggle_server(self, name: str, enabled: bool) -> None:
        """
        启用/禁用 MCP server

        更新 _server_configs 中指定 server 的 enabled 字段。
        server 不存在时静默忽略。

        Args:
            name: server 名称
            enabled: 目标启用状态，True 为启用，False 为禁用

        Returns:
            None

        Raises:
            不抛出异常
        """
        if name in self._server_configs:
            self._server_configs[name]["enabled"] = enabled

    async def toggle_method(
        self, server_name: str, method_name: str, enabled: bool
    ) -> None:
        """
        启用/禁用单个 method

        更新 _server_configs 中指定 server 下指定 method 的 enabled 字段。
        server 或 method 不存在时静默忽略。

        Args:
            server_name: server 名称
            method_name: method 名称
            enabled: 目标启用状态，True 为启用，False 为禁用

        Returns:
            None

        Raises:
            不抛出异常
        """
        if server_name in self._server_configs:
            methods = self._server_configs[server_name].setdefault("methods", {})
            if method_name in methods:
                methods[method_name]["enabled"] = enabled

    async def shutdown(self) -> None:
        """
        关闭注册中心，释放所有连接资源
        """
        if self._client is not None:
            await self._client.shutdown()
            logger.info("UnifiedMCPClient 已关闭")
        self._initialized = False
        logger.info("MCPToolsRegistry 已关闭")

    def get_all_tools(self) -> List[Any]:
        """
        获取所有已注册的工具列表

        注意：此方法为同步方法，返回缓存的工具列表。
        推荐使用异步的 get_tools() 方法获取最新工具列表。

        Returns:
            List[Any]: 所有已注册的工具列表；如果注册中心未初始化则返回空列表
        """
        if self._client is None:
            logger.warning("MCPToolsRegistry 尚未初始化，无法获取工具列表")
            return []
        return []

    @property
    def _pool(self):
        return self._client
