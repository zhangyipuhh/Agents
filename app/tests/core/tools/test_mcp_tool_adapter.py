# -*- coding:utf-8 -*-
"""
测试 app.core.tools.mcp_tool_adapter MCP 工具适配器模块

验证模块可正常导入，以及主要类与函数在模块中存在。
"""

import inspect

from app.core.tools import mcp_tool_adapter as adapter


# =============================================================================
# 模块导入与存在性测试
# =============================================================================


def test_mcp_tool_adapter_importable():
    """
    测试 mcp_tool_adapter 模块可正常导入且不抛出异常。

    参数:
        无

    返回值:
        None

    异常:
        ImportError: 模块导入失败时抛出
    """
    assert adapter is not None


# =============================================================================
# 主要函数存在性测试
# =============================================================================


def test_resolve_ref_exists():
    """
    测试 _resolve_ref 函数存在且可调用。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 函数不存在或不可调用时抛出
    """
    assert hasattr(adapter, "_resolve_ref")
    assert callable(adapter._resolve_ref)


def test_collect_defs_exists():
    """
    测试 _collect_defs 函数存在且可调用。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 函数不存在或不可调用时抛出
    """
    assert hasattr(adapter, "_collect_defs")
    assert callable(adapter._collect_defs)


def test_normalize_schema_exists():
    """
    测试 _normalize_schema 函数存在且可调用。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 函数不存在或不可调用时抛出
    """
    assert hasattr(adapter, "_normalize_schema")
    assert callable(adapter._normalize_schema)


def test_json_schema_to_pydantic_model_exists():
    """
    测试 json_schema_to_pydantic_model 函数存在且可调用。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 函数不存在或不可调用时抛出
    """
    assert hasattr(adapter, "json_schema_to_pydantic_model")
    assert callable(adapter.json_schema_to_pydantic_model)


def test_adapt_mcp_tool_exists():
    """
    测试 adapt_mcp_tool 函数存在且可调用。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 函数不存在或不可调用时抛出
    """
    assert hasattr(adapter, "adapt_mcp_tool")
    assert callable(adapter.adapt_mcp_tool)


def test_adapt_mcp_tools_exists():
    """
    测试 adapt_mcp_tools 函数存在且可调用。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 函数不存在或不可调用时抛出
    """
    assert hasattr(adapter, "adapt_mcp_tools")
    assert callable(adapter.adapt_mcp_tools)


def test_is_mcp_tool_exists():
    """
    测试 is_mcp_tool 函数存在且可调用。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 函数不存在或不可调用时抛出
    """
    assert hasattr(adapter, "is_mcp_tool")
    assert callable(adapter.is_mcp_tool)


# =============================================================================
# 主要类存在性测试
# =============================================================================


def test_normalized_schema_model_exists():
    """
    测试 _NormalizedSchemaModel 内部类存在。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 类不存在时抛出
    """
    assert hasattr(adapter, "_NormalizedSchemaModel")
    assert inspect.isclass(adapter._NormalizedSchemaModel)


def test_mcp_tool_config_exists():
    """
    测试 MCPToolConfig 配置类存在且可实例化。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 类不存在或实例化失败时抛出
    """
    assert hasattr(adapter, "MCPToolConfig")
    assert inspect.isclass(adapter.MCPToolConfig)
    config = adapter.MCPToolConfig()
    assert config.enable_injection is True


def test_mcp_tool_to_langchain_adapter_exists():
    """
    测试 MCPToolToLangChainAdapter 适配器类存在。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 类不存在时抛出
    """
    assert hasattr(adapter, "MCPToolToLangChainAdapter")
    assert inspect.isclass(adapter.MCPToolToLangChainAdapter)


# =============================================================================
# MCPToolConfig.from_dict 工厂方法测试（2026-06-24 新增）
# =============================================================================


def test_mcp_tool_config_from_dict_none():
    """
    测试 from_dict：传入 None 应返回默认实例。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 返回值不是默认实例时抛出
    """
    config = adapter.MCPToolConfig.from_dict(None)
    assert config.enable_injection is True
    assert config.default_param_keys == []
    assert config.hidden_param_keys == []
    assert config.unwrap_result is False


def test_mcp_tool_config_from_dict_empty():
    """
    测试 from_dict：传入空 dict 应返回默认实例。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 返回值不是默认实例时抛出
    """
    config = adapter.MCPToolConfig.from_dict({})
    assert config.enable_injection is True
    assert config.default_param_keys == []
    assert config.hidden_param_keys == []
    assert config.unwrap_result is False


def test_mcp_tool_config_from_dict_full():
    """
    测试 from_dict：传入完整 dict 应正确构造配置。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 字段值与输入不一致时抛出
    """
    config = adapter.MCPToolConfig.from_dict({
        "enable_injection": False,
        "default_param_keys": ["session_id", "geometry_data"],
        "hidden_param_keys": ["geometry_data"],
        "unwrap_result": True,
    })
    assert config.enable_injection is False
    assert config.default_param_keys == ["session_id", "geometry_data"]
    assert config.hidden_param_keys == ["geometry_data"]
    assert config.unwrap_result is True


def test_mcp_tool_config_from_dict_partial():
    """
    测试 from_dict：传入部分键应使用默认值补齐缺失键。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 缺失键未使用默认值时抛出
    """
    config = adapter.MCPToolConfig.from_dict({
        "default_param_keys": ["session_id"],
    })
    assert config.enable_injection is True
    assert config.default_param_keys == ["session_id"]
    assert config.hidden_param_keys == []
    assert config.unwrap_result is False
