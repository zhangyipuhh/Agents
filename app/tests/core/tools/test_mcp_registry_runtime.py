# -*- coding:utf-8 -*-
"""
MCPToolsRegistry 运行时管理测试模块

验证新增的 add_server / update_server / remove_server / toggle_server / toggle_method 方法
在运行时动态管理 MCP server 配置的能力，无需重启应用即可生效。

测试覆盖：
    - 方法存在性（5 个）
    - 配置存储 / 删除 / 启用状态切换（4 个）
"""
import asyncio
import pytest
from app.core.tools.mcp_registry import MCPToolsRegistry


# =============================================================================
# 方法存在性测试
# =============================================================================


def test_add_server_method_exists():
    """
    测试 MCPToolsRegistry 类具有 add_server 方法。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 当 add_server 方法不存在时抛出
    """
    assert hasattr(MCPToolsRegistry, "add_server")


def test_update_server_method_exists():
    """
    测试 MCPToolsRegistry 类具有 update_server 方法。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 当 update_server 方法不存在时抛出
    """
    assert hasattr(MCPToolsRegistry, "update_server")


def test_remove_server_method_exists():
    """
    测试 MCPToolsRegistry 类具有 remove_server 方法。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 当 remove_server 方法不存在时抛出
    """
    assert hasattr(MCPToolsRegistry, "remove_server")


def test_toggle_server_method_exists():
    """
    测试 MCPToolsRegistry 类具有 toggle_server 方法。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 当 toggle_server 方法不存在时抛出
    """
    assert hasattr(MCPToolsRegistry, "toggle_server")


def test_toggle_method_method_exists():
    """
    测试 MCPToolsRegistry 类具有 toggle_method 方法。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 当 toggle_method 方法不存在时抛出
    """
    assert hasattr(MCPToolsRegistry, "toggle_method")


# =============================================================================
# 配置存储 / 删除 / 启用状态切换测试
# =============================================================================


def test_add_server_stores_config():
    """
    测试 add_server 将配置存入 _server_configs 字典。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 当配置未正确存入 _server_configs 时抛出
    """
    registry = MCPToolsRegistry()
    config = {"type": "sse", "url": "http://x", "tags": ["map"]}
    asyncio.run(registry.add_server("test_server_001", config))
    assert "test_server_001" in registry._server_configs
    assert registry._server_configs["test_server_001"]["url"] == "http://x"


def test_remove_server_deletes_config():
    """
    测试 remove_server 从 _server_configs 删除指定 server 配置。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 当配置未被正确删除时抛出
    """
    registry = MCPToolsRegistry()
    registry._server_configs["to_remove"] = {"type": "sse"}
    asyncio.run(registry.remove_server("to_remove"))
    assert "to_remove" not in registry._server_configs


def test_toggle_server_sets_enabled():
    """
    测试 toggle_server 更新指定 server 的 enabled 字段。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 当 enabled 字段未被正确更新时抛出
    """
    registry = MCPToolsRegistry()
    registry._server_configs["toggle_test"] = {"enabled": True, "type": "sse"}
    asyncio.run(registry.toggle_server("toggle_test", False))
    assert registry._server_configs["toggle_test"]["enabled"] is False


def test_toggle_method_sets_enabled():
    """
    测试 toggle_method 更新指定 server 下指定 method 的 enabled 字段。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 当 method 的 enabled 字段未被正确更新时抛出
    """
    registry = MCPToolsRegistry()
    registry._server_configs["method_test"] = {
        "enabled": True,
        "methods": {"search": {"enabled": True}},
    }
    asyncio.run(registry.toggle_method("method_test", "search", False))
    assert registry._server_configs["method_test"]["methods"]["search"]["enabled"] is False
