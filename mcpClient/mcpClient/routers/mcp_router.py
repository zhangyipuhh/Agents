#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
MCP API 路由模块

提供 MCP 服务器工具调用的 API 端点。
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/mcp", tags=["MCP"])

_unified_client = None


def set_unified_client(client):
    global _unified_client
    _unified_client = client


class ToolCallRequest(BaseModel):
    server_name: str
    tool_name: str
    arguments: Dict[str, Any] = {}


class ToolCallResponse(BaseModel):
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None


class ServerInfo(BaseModel):
    name: str
    connected: bool
    tools: List[str]


@router.get("/servers", response_model=List[ServerInfo])
async def list_servers():
    if not _unified_client:
        raise HTTPException(status_code=503, detail="MCP client not initialized")

    servers = []
    for name in _unified_client.get_server_names():
        server_tools_info = await _unified_client.get_server_tools(name)
        tool_names = []
        if server_tools_info:
            tool_names = [t.name for t in server_tools_info.get("tools", [])]
        servers.append(ServerInfo(name=name, connected=True, tools=tool_names))
    return servers


@router.post("/call", response_model=ToolCallResponse)
async def call_tool(request: ToolCallRequest):
    if not _unified_client:
        raise HTTPException(status_code=503, detail="MCP client not initialized")

    try:
        result = await _unified_client.call_tool(
            request.server_name,
            request.tool_name,
            request.arguments,
        )
        return ToolCallResponse(success=True, result=result)
    except Exception as e:
        return ToolCallResponse(success=False, error=str(e))


@router.get("/tools/{server_name}")
async def list_tools(server_name: str):
    if not _unified_client:
        raise HTTPException(status_code=503, detail="MCP client not initialized")

    server_tools_info = await _unified_client.get_server_tools(server_name)
    if not server_tools_info:
        raise HTTPException(status_code=404, detail=f"Server '{server_name}' not found")

    tools = []
    for tool in server_tools_info.get("tools", []):
        tools.append({
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.args_schema.schema() if hasattr(tool, "args_schema") and tool.args_schema else None,
        })
    return {"server": server_name, "tools": tools}
