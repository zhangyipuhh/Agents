# -*- coding:utf-8 -*-
"""
测试 app.core.dependencies 依赖注入模块

验证 get_mcp_registry 与 get_mcp_tools 函数可调用性以及未初始化时抛出 503 异常。
"""

import pytest
from fastapi import HTTPException, Request
from unittest.mock import Mock

from app.core.dependencies import get_mcp_registry, get_mcp_tools


def test_get_mcp_registry_exists_and_callable():
    """
    测试 get_mcp_registry 函数存在且可调用。

    Returns:
        None

    异常:
        AssertionError: 函数不存在或不可调用时抛出
    """
    assert callable(get_mcp_registry)


def test_get_mcp_tools_exists_and_callable():
    """
    测试 get_mcp_tools 函数存在且可调用。

    Returns:
        None

    异常:
        AssertionError: 函数不存在或不可调用时抛出
    """
    assert callable(get_mcp_tools)


def test_get_mcp_registry_raises_503_when_registry_is_none():
    """
    测试当 request.app.state.mcp_registry 为 None 时 get_mcp_registry 抛出 HTTPException 503。

    参数:
        构造 Mock Request 对象，模拟 mcp_registry 为 None 的场景

    返回值:
        None

    异常:
        HTTPException: 状态码 503，当注册表未初始化时抛出
    """
    mock_request = Mock(spec=Request)
    mock_request.app.state.mcp_registry = None

    with pytest.raises(HTTPException) as exc_info:
        get_mcp_registry(mock_request)

    assert exc_info.value.status_code == 503
    assert "MCPToolsRegistry not initialized" in exc_info.value.detail


def test_get_mcp_tools_raises_503_when_registry_is_none():
    """
    测试当 request.app.state.mcp_registry 为 None 时 get_mcp_tools 抛出 HTTPException 503。

    参数:
        构造 Mock Request 对象，模拟 mcp_registry 为 None 的场景

    返回值:
        None

    异常:
        HTTPException: 状态码 503，当注册表未初始化时抛出
    """
    mock_request = Mock(spec=Request)
    mock_request.app.state.mcp_registry = None

    with pytest.raises(HTTPException) as exc_info:
        get_mcp_tools(mock_request)

    assert exc_info.value.status_code == 503
    assert "MCPToolsRegistry not initialized" in exc_info.value.detail
