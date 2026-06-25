#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
MCP Admin Router 模块

提供 MCP server 配置的增删改查 + 方法列表刷新 + server/method 两级开关。
所有路由前缀 /api/admin/mcp，需 admin 权限。

Date: 2026-06-23
Author: AI Assistant
"""

import dataclasses
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request, status

from app.shared.utils.agent.mcp_service import McpConfigService, McpServerConfig


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/mcp", tags=["MCP Admin"])


def _get_service(request: Request) -> McpConfigService:
    """从 app.state 获取 McpConfigService 实例。

    参数:
        request: FastAPI Request 对象

    返回:
        McpConfigService: 服务实例

    异常:
        HTTPException: 服务未初始化时抛出 500
    """
    service = getattr(request.app.state, "mcp_config_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="McpConfigService not initialized",
        )
    return service


def _get_registry(request: Request):
    """从 app.state 获取 MCPToolsRegistry 实例。

    找不到时返回 None（不抛 500），让调用方决定是否降级处理。
    生产对等初始化点：app/core/server.py lifespan 中
    `app.state.mcp_registry = registry`。

    参数:
        request: FastAPI Request 对象

    返回:
        MCPToolsRegistry 或 None
    """
    return getattr(request.app.state, "mcp_registry", None)


async def _invalidate_agent_config_cache(request: Request) -> None:
    """失效 agent_config 缓存（MCP 变更影响 agent 工具列表）。

    MCP server 配置变更（新增/更新/删除/启停）后，所有 agent 的工具列表
    可能受影响，需清空 AgentConfigService 全部缓存强制下次重新加载。

    生产对等初始化点：app/core/server.py lifespan 中
    `app.state.agent_config_service = AgentConfigService(...)`。
    服务未初始化时静默跳过（不抛异常），避免 MCP 写操作因缓存失效失败。

    参数:
        request: FastAPI Request 对象
    """
    agent_service = getattr(request.app.state, "agent_config_service", None)
    if agent_service is not None:
        await agent_service.invalidate_all_cache()


def _build_config_dict(server: McpServerConfig) -> dict:
    """将 McpServerConfig 转为 dict 供 registry 使用。

    参数:
        server: McpServerConfig dataclass 实例

    返回:
        dict: 含所有字段的配置字典（含 args/env/headers/connect_timeout 等）
    """
    return dataclasses.asdict(server)


@router.get("/servers")
async def list_servers(request: Request) -> List[Dict[str, Any]]:
    """列出所有 MCP server 配置。"""
    service = _get_service(request)
    return await service.list_servers()


@router.post("/servers", status_code=status.HTTP_201_CREATED)
async def create_server(request: Request, config: McpServerConfig) -> Dict[str, Any]:
    """新增 MCP server。

    DB 写入后同步到 mcp_registry（热更新），registry 调用失败仅 warning。

    异常:
        HTTPException: name 已存在时抛出 409
    """
    service = _get_service(request)
    try:
        result = await service.create_server(config)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    # 同步到 registry（热更新）
    registry = _get_registry(request)
    if registry is not None:
        try:
            await registry.add_server(config.name, _build_config_dict(config))
        except Exception as e:
            logger.warning(
                "Failed to sync registry after create_server '%s': %s",
                config.name, e,
            )

    # 失效 agent_config 缓存（MCP 变更影响 agent 工具列表）
    await _invalidate_agent_config_cache(request)
    return result


@router.put("/servers/{name}")
async def update_server(request: Request, name: str, config: McpServerConfig) -> Dict[str, Any]:
    """更新 MCP server 配置。

    DB 写入后同步到 mcp_registry（热更新），registry 调用失败仅 warning。

    异常:
        HTTPException: server 不存在时抛出 404
    """
    service = _get_service(request)
    try:
        result = await service.update_server(name, config)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    # 同步到 registry（热更新）
    registry = _get_registry(request)
    if registry is not None:
        try:
            await registry.update_server(name, _build_config_dict(config))
        except Exception as e:
            logger.warning(
                "Failed to sync registry after update_server '%s': %s",
                name, e,
            )

    # 失效 agent_config 缓存（MCP 变更影响 agent 工具列表）
    await _invalidate_agent_config_cache(request)
    return result


@router.delete("/servers/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(request: Request, name: str) -> None:
    """删除 MCP server 及其关联 methods。

    DB 删除后同步到 mcp_registry（热更新），registry 调用失败仅 warning。
    """
    service = _get_service(request)
    await service.delete_server(name)

    # 同步到 registry（热更新）
    registry = _get_registry(request)
    if registry is not None:
        try:
            await registry.remove_server(name)
        except Exception as e:
            logger.warning(
                "Failed to sync registry after delete_server '%s': %s",
                name, e,
            )

    # 失效 agent_config 缓存（MCP 变更影响 agent 工具列表）
    await _invalidate_agent_config_cache(request)


@router.post("/servers/{name}/toggle")
async def toggle_server(request: Request, name: str, enabled: bool) -> Dict[str, Any]:
    """启用/禁用 MCP server。

    DB 更新后同步到 mcp_registry（热更新），registry 调用失败仅 warning。

    参数:
        enabled: 是否启用（query 参数）
    """
    service = _get_service(request)
    await service.toggle_server(name, enabled)

    # 同步到 registry（热更新）
    registry = _get_registry(request)
    if registry is not None:
        try:
            await registry.toggle_server(name, enabled)
        except Exception as e:
            logger.warning(
                "Failed to sync registry after toggle_server '%s': %s",
                name, e,
            )

    # 失效 agent_config 缓存（MCP 变更影响 agent 工具列表）
    await _invalidate_agent_config_cache(request)
    return {"name": name, "enabled": enabled}


@router.get("/servers/{name}/methods")
async def list_methods(request: Request, name: str) -> List[Dict[str, Any]]:
    """列出 server 下所有 method。"""
    service = _get_service(request)
    return await service.list_methods(name)


@router.post("/servers/{name}/refresh-methods")
async def refresh_methods(request: Request, name: str) -> Dict[str, Any]:
    """重新从 MCP server 拉取 method 列表。

    异常:
        HTTPException: 拉取失败时抛出 502
    """
    service = _get_service(request)
    try:
        methods = await service.refresh_methods_from_server(name)
        return {"name": name, "methods_count": len(methods), "methods": methods}
    except Exception as e:
        logger.warning("Failed to refresh methods for server '%s': %s", name, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to refresh methods: {e}",
        )


@router.post("/servers/{name}/methods/{method}/toggle")
async def toggle_method(
    request: Request, name: str, method: str, enabled: bool
) -> Dict[str, Any]:
    """启用/禁用单个 method。"""
    service = _get_service(request)
    await service.toggle_method(name, method, enabled)
    return {"server_name": name, "method_name": method, "enabled": enabled}
