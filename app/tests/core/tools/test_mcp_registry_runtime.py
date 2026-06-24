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


# =============================================================================
# 工具适配器包装测试（2026-06-24 新增）
# 验证 _get_tools_with_server_async 用 MCPToolToLangChainAdapter 包装原生工具
# =============================================================================


def test_get_tools_with_server_wraps_with_adapter():
    """
    测试 _get_tools_with_server_async：原生工具被 MCPToolToLangChainAdapter 包装。

    验证：
    - server_config["tool_config"] 被传入适配器
    - 返回元组第 1 项是 MCPToolToLangChainAdapter 实例

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 工具未被正确包装时抛出
    """
    from app.core.tools.mcp_tool_adapter import MCPToolToLangChainAdapter, MCPToolConfig
    from unittest.mock import AsyncMock, MagicMock

    registry = MCPToolsRegistry()
    registry._initialized = True

    # mock client：返回 1 个原生工具
    fake_tool = MagicMock()
    fake_tool.name = "search"
    fake_tool.description = "搜索工具"

    mock_client = MagicMock()
    mock_client.get_server_names = MagicMock(return_value=["amap"])
    mock_client.get_server_tools = AsyncMock(return_value={"tools": [fake_tool]})
    registry._client = mock_client

    # server_config 含 tool_config
    registry._server_configs["amap"] = {
        "type": "sse",
        "url": "http://x",
        "tags": ["map"],
        "tool_config": {
            "enable_injection": True,
            "default_param_keys": ["session_id"],
            "hidden_param_keys": [],
            "unwrap_result": True,
        },
    }

    results = asyncio.run(registry._get_tools_with_server_async())

    assert len(results) == 1
    tool, server_name, server_config = results[0]
    assert isinstance(tool, MCPToolToLangChainAdapter)
    assert server_name == "amap"
    assert tool.tool_config.enable_injection is True
    assert tool.tool_config.default_param_keys == ["session_id"]
    assert tool.tool_config.unwrap_result is True


def test_get_tools_with_server_skips_already_wrapped():
    """
    测试 _get_tools_with_server_async：已是 MCPToolToLangChainAdapter 的工具不重复包装（幂等）。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 工具被重复包装时抛出
    """
    from app.core.tools.mcp_tool_adapter import MCPToolToLangChainAdapter, MCPToolConfig
    from unittest.mock import AsyncMock, MagicMock

    registry = MCPToolsRegistry()
    registry._initialized = True

    # 构造一个已包装的工具
    original_tool = MagicMock()
    original_tool.name = "search"
    original_tool.description = "搜索工具"
    already_wrapped = MCPToolToLangChainAdapter(
        mcp_tool=original_tool,
        mcp_server_name="amap",
        tool_config=MCPToolConfig(unwrap_result=False),
    )

    mock_client = MagicMock()
    mock_client.get_server_names = MagicMock(return_value=["amap"])
    mock_client.get_server_tools = AsyncMock(return_value={"tools": [already_wrapped]})
    registry._client = mock_client

    registry._server_configs["amap"] = {
        "type": "sse",
        "tool_config": {"unwrap_result": True},
    }

    results = asyncio.run(registry._get_tools_with_server_async())

    assert len(results) == 1
    tool, _, _ = results[0]
    # 幂等：返回的就是原包装实例，未被二次包装
    assert tool is already_wrapped
    # tool_config 保持原值（未被 server_config 覆盖）
    assert tool.tool_config.unwrap_result is False
