#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
MCP API 路由模块

提供 MCP 服务器工具调用的 API 端点
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/mcp", tags=["MCP"])

# 全局连接池引用
_client_pool = None


def set_client_pool(pool):
    """设置全局连接池"""
    global _client_pool
    _client_pool = pool


class ToolCallRequest(BaseModel):
    """工具调用请求"""
    server_name: str
    tool_name: str
    arguments: Dict[str, Any] = {}


class ToolCallResponse(BaseModel):
    """工具调用响应"""
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None


class ServerInfo(BaseModel):
    """服务器信息"""
    name: str
    connected: bool
    tools: List[str]


@router.get("/servers", response_model=List[ServerInfo])
async def list_servers():
    """
    列出所有已连接的 MCP 服务器及其工具
    """
    if not _client_pool:
        raise HTTPException(status_code=503, detail="MCP client pool not initialized")

    servers = []
    for name, server in _client_pool._servers.items():
        servers.append(ServerInfo(
            name=name,
            connected=server.session is not None,
            tools=[tool.name for tool in server._tools]
        ))
    return servers


@router.post("/call", response_model=ToolCallResponse)
async def call_tool(request: ToolCallRequest):
    """
    调用 MCP 服务器工具

    Args:
        request: 工具调用请求，包含 server_name, tool_name, arguments

    Returns:
        工具调用结果

    Example:
        ```json
        {
            "server_name": "高德地图mcp",
            "tool_name": "maps_geo",
            "arguments": {
                "address": "北京市朝阳区"
            }
        }
        ```
    """
    if not _client_pool:
        raise HTTPException(status_code=503, detail="MCP client pool not initialized")

    try:
        result = await _client_pool.call_tool(
            request.server_name,
            request.tool_name,
            request.arguments
        )
        return ToolCallResponse(success=True, result=result)
    except Exception as e:
        return ToolCallResponse(success=False, error=str(e))


@router.get("/tools/{server_name}")
async def list_tools(server_name: str):
    """
    列出指定服务器的所有可用工具

    Args:
        server_name: MCP 服务器名称

    Returns:
        工具列表
    """
    if not _client_pool:
        raise HTTPException(status_code=503, detail="MCP client pool not initialized")

    server = _client_pool._servers.get(server_name)
    if not server:
        raise HTTPException(status_code=404, detail=f"Server '{server_name}' not found")

    tools = []
    for tool in server._tools:
        tools.append({
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.inputSchema if hasattr(tool, 'inputSchema') else None
        })
    return {"server": server_name, "tools": tools}
