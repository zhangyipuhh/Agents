#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MCPToolsRegistry 集成测试模块

使用 mock 模拟 mcpClient 的 MCPClientPool 和 MCPToolsRegistry，
对 MCPToolsRegistry 门面类的单例模式、工具查询和刷新功能进行集成测试。

Date: 2026-04-18
Author: 张镒谱
"""

import sys
from unittest.mock import MagicMock

# 在导入被测模块之前，mock 掉 mcpClient 子模块以避免 ModuleNotFoundError
_mcp_client_mock: MagicMock = MagicMock()
_mcp_core_mock: MagicMock = MagicMock()
sys.modules.setdefault("mcpClient", _mcp_client_mock)
sys.modules.setdefault("mcpClient.core", _mcp_core_mock)
sys.modules.setdefault("mcpClient.core.mcp_client", MagicMock())
sys.modules.setdefault(
    "mcpClient.core.mcp_client.client_pool", MagicMock()
)
sys.modules.setdefault(
    "mcpClient.core.mcp_client.registry", MagicMock()
)

import pytest
from unittest.mock import AsyncMock, patch

from app.core.tools.mcp_registry import MCPToolsRegistry


@pytest.fixture(autouse=True)
def reset_singleton() -> None:
    """每个测试前重置 MCPToolsRegistry 单例，确保测试隔离"""
    MCPToolsRegistry._instance = None


class TestMCPToolsRegistrySingleton:
    """MCPToolsRegistry 单例模式测试"""

    def test_singleton_same_instance(self) -> None:
        """
        多次调用 get_instance() 应返回同一实例

        验证单例模式的基本行为：连续两次调用返回的对象具有相同标识。
        """
        instance_a: MCPToolsRegistry = MCPToolsRegistry.get_instance()
        instance_b: MCPToolsRegistry = MCPToolsRegistry.get_instance()
        assert instance_a is instance_b

    def test_singleton_reset(self) -> None:
        """
        重置单例后，get_instance 应返回新实例

        将 _instance 置为 None 后再次获取，应得到一个不同的实例对象。
        """
        instance_a: MCPToolsRegistry = MCPToolsRegistry.get_instance()
        MCPToolsRegistry._instance = None
        instance_b: MCPToolsRegistry = MCPToolsRegistry.get_instance()
        assert instance_a is not instance_b


class TestMCPToolsRegistryGetTools:
    """MCPToolsRegistry 工具查询测试"""

    def test_get_tools_all(self) -> None:
        """
        无参数调用 get_tools() 应返回所有工具

        当内部 registry 已初始化且 get_tools 无过滤参数时，
        应委托给内部 registry 并返回其全部工具列表。
        """
        registry: MCPToolsRegistry = MCPToolsRegistry.get_instance()

        mock_tool_1: MagicMock = MagicMock()
        mock_tool_1.name = "maps_geo"
        mock_tool_2: MagicMock = MagicMock()
        mock_tool_2.name = "maps_direction"

        mock_inner_registry: MagicMock = MagicMock()
        mock_inner_registry.get_tools.return_value = [mock_tool_1, mock_tool_2]
        registry._registry = mock_inner_registry

        result = registry.get_tools()
        assert result == [mock_tool_1, mock_tool_2]
        mock_inner_registry.get_tools.assert_called_once_with(
            tags=None, names=None, server=None
        )

    def test_get_tools_by_tags(self) -> None:
        """
        按 tags 选取工具（OR 匹配）

        传入 tags 参数后，应将参数透传给内部 registry 的 get_tools 方法。
        """
        registry: MCPToolsRegistry = MCPToolsRegistry.get_instance()

        mock_tool_1: MagicMock = MagicMock()
        mock_tool_1.name = "maps_geo"
        mock_tool_2: MagicMock = MagicMock()
        mock_tool_2.name = "github_search"

        mock_inner_registry: MagicMock = MagicMock()
        mock_inner_registry.get_tools.return_value = [mock_tool_1, mock_tool_2]
        registry._registry = mock_inner_registry

        result = registry.get_tools(tags=["map", "github"])
        assert result == [mock_tool_1, mock_tool_2]
        mock_inner_registry.get_tools.assert_called_once_with(
            tags=["map", "github"], names=None, server=None
        )

    def test_get_tools_by_names(self) -> None:
        """
        按 names 选取工具（精确匹配）

        传入 names 参数后，应将参数透传给内部 registry 的 get_tools 方法。
        """
        registry: MCPToolsRegistry = MCPToolsRegistry.get_instance()

        mock_tool_1: MagicMock = MagicMock()
        mock_tool_1.name = "maps_geo"

        mock_inner_registry: MagicMock = MagicMock()
        mock_inner_registry.get_tools.return_value = [mock_tool_1]
        registry._registry = mock_inner_registry

        result = registry.get_tools(names=["maps_geo"])
        assert result == [mock_tool_1]
        mock_inner_registry.get_tools.assert_called_once_with(
            tags=None, names=["maps_geo"], server=None
        )

    def test_get_tools_by_server(self) -> None:
        """
        按 server 选取工具

        传入 server 参数后，应将参数透传给内部 registry 的 get_tools 方法。
        """
        registry: MCPToolsRegistry = MCPToolsRegistry.get_instance()

        mock_tool_1: MagicMock = MagicMock()
        mock_tool_1.name = "maps_geo"

        mock_inner_registry: MagicMock = MagicMock()
        mock_inner_registry.get_tools.return_value = [mock_tool_1]
        registry._registry = mock_inner_registry

        result = registry.get_tools(server="maps")
        assert result == [mock_tool_1]
        mock_inner_registry.get_tools.assert_called_once_with(
            tags=None, names=None, server="maps"
        )

    def test_get_tools_combined(self) -> None:
        """
        组合条件选取（AND 逻辑）

        同时传入 tags、names 和 server 参数，应全部透传给内部 registry，
        由内部 registry 实现 AND 逻辑的组合过滤。
        """
        registry: MCPToolsRegistry = MCPToolsRegistry.get_instance()

        mock_tool_1: MagicMock = MagicMock()
        mock_tool_1.name = "maps_geo"

        mock_inner_registry: MagicMock = MagicMock()
        mock_inner_registry.get_tools.return_value = [mock_tool_1]
        registry._registry = mock_inner_registry

        result = registry.get_tools(
            tags=["map"], names=["maps_geo"], server="maps"
        )
        assert result == [mock_tool_1]
        mock_inner_registry.get_tools.assert_called_once_with(
            tags=["map"], names=["maps_geo"], server="maps"
        )

    def test_get_tools_empty_registry(self) -> None:
        """
        registry 未初始化时返回空列表

        当 _registry 为 None 时，get_tools 应返回空列表而非抛出异常。
        """
        registry: MCPToolsRegistry = MCPToolsRegistry.get_instance()
        registry._registry = None

        result = registry.get_tools()
        assert result == []


class TestMCPToolsRegistryRefresh:
    """MCPToolsRegistry 工具刷新测试"""

    @pytest.mark.asyncio
    async def test_refresh_tools_specific_server(self) -> None:
        """
        刷新指定服务器的工具列表

        传入 server_name 参数后，应委托给内部 registry 的 refresh_tools 方法。
        """
        registry: MCPToolsRegistry = MCPToolsRegistry.get_instance()

        mock_inner_registry: MagicMock = MagicMock()
        mock_inner_registry.refresh_tools = AsyncMock()
        registry._registry = mock_inner_registry

        await registry.refresh_tools(server_name="maps")
        mock_inner_registry.refresh_tools.assert_awaited_once_with(
            server_name="maps"
        )

    @pytest.mark.asyncio
    async def test_refresh_tools_all_servers(self) -> None:
        """
        刷新所有服务器的工具列表

        不传 server_name 参数时，应委托给内部 registry 刷新全部服务器。
        """
        registry: MCPToolsRegistry = MCPToolsRegistry.get_instance()

        mock_inner_registry: MagicMock = MagicMock()
        mock_inner_registry.refresh_tools = AsyncMock()
        registry._registry = mock_inner_registry

        await registry.refresh_tools()
        mock_inner_registry.refresh_tools.assert_awaited_once_with(
            server_name=None
        )

    @pytest.mark.asyncio
    async def test_refresh_tools_not_initialized(self) -> None:
        """
        registry 未初始化时刷新工具应抛出 RuntimeError

        当 _registry 为 None 时，refresh_tools 应抛出 RuntimeError，
        提示注册中心尚未初始化。
        """
        registry: MCPToolsRegistry = MCPToolsRegistry.get_instance()
        registry._registry = None

        with pytest.raises(RuntimeError, match="尚未初始化"):
            await registry.refresh_tools()
