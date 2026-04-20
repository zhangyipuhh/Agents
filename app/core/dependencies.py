#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FastAPI 依赖注入函数模块

提供 MCPToolsRegistry 相关的依赖注入函数，用于在路由处理函数中
获取 MCP 工具注册表实例和工具列表。

Date: 2026-04-18
Author: 张镒谱
"""

from typing import Any, List, Optional

from fastapi import HTTPException, Request

from app.core.tools.mcp_registry import MCPToolsRegistry


def get_mcp_registry(request: Request) -> MCPToolsRegistry:
    """
    从应用状态中获取 MCPToolsRegistry 实例的依赖注入函数。

    该函数作为 FastAPI 依赖使用，从 request.app.state 中提取
    已初始化的 MCPToolsRegistry 实例。若实例未初始化则抛出 503 异常。

    Args:
        request: FastAPI 请求对象，用于访问应用状态。

    Returns:
        MCPToolsRegistry: 已初始化的 MCP 工具注册表实例。

    Raises:
        HTTPException: 当 mcp_registry 未初始化时，返回 503 状态码。
    """
    # 从应用状态中获取 mcp_registry
    mcp_registry = getattr(request.app.state, "mcp_registry", None)

    # 若 mcp_registry 未初始化，抛出 503 异常
    if mcp_registry is None:
        raise HTTPException(
            status_code=503,
            detail="MCPToolsRegistry not initialized",
        )

    return mcp_registry


def get_mcp_tools(
    request: Request,
    tags: Optional[List[str]] = None,
    names: Optional[List[str]] = None,
    server: Optional[str] = None,
) -> List[Any]:
    """
    从 MCPToolsRegistry 中获取工具列表的依赖注入函数。

    该函数作为 FastAPI 依赖使用，支持按标签、名称和服务器筛选工具。
    若注册表未初始化则抛出 503 异常。

    Args:
        request: FastAPI 请求对象，用于访问应用状态。
        tags: 可选的工具标签列表，用于按标签筛选工具。
        names: 可选的工具名称列表，用于按名称筛选工具。
        server: 可选的服务器标识，用于按服务器筛选工具。

    Returns:
        List[Any]: 符合筛选条件的 MCP 工具列表。

    Raises:
        HTTPException: 当 mcp_registry 未初始化时，返回 503 状态码。
    """
    # 从应用状态中获取 mcp_registry
    mcp_registry = getattr(request.app.state, "mcp_registry", None)

    # 若 mcp_registry 未初始化，抛出 503 异常
    if mcp_registry is None:
        raise HTTPException(
            status_code=503,
            detail="MCPToolsRegistry not initialized",
        )

    # 调用 registry 的 get_tools 方法获取工具列表
    tools = mcp_registry.get_tools(tags=tags, names=names, server=server)

    return tools
