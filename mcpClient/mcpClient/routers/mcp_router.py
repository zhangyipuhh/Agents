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


@router.get("/tools-formatted")
async def list_tools_formatted():
    """
    获取所有工具的格式化列表，供 Agent 直接使用

    返回格式化的工具信息，包含完整的工具描述和参数信息

    Returns:
        格式化的工具列表
    """
    if not _client_pool:
        raise HTTPException(status_code=503, detail="MCP client pool not initialized")

    formatted_tools = []
    for name, server in _client_pool._servers.items():
        for tool in server._tools:
            tool_info = {
                "server": name,
                "name": tool.name,
                "description": tool.description,
            }
            
            # 添加参数信息
            if hasattr(tool, 'inputSchema') and tool.inputSchema:
                schema = tool.inputSchema
                properties = schema.get('properties', {})
                required = schema.get('required', [])
                
                params = []
                for param_name, param_info in properties.items():
                    param_desc = param_info.get('description', '')
                    param_type = param_info.get('type', 'string')
                    is_required = param_name in required
                    
                    req_mark = "(必填)" if is_required else "(可选)"
                    params.append(f"  - {param_name} {req_mark}: {param_desc} ({param_type})")
                
                if params:
                    tool_info["parameters"] = params
            
            formatted_tools.append(tool_info)
    
    return {
        "total": len(formatted_tools),
        "tools": formatted_tools
    }


@router.get("/tools-for-llm")
async def list_tools_for_llm():
    """
    获取适合 LLM 使用的工具描述

    返回格式化的工具描述文本，可以直接插入到 LLM 的 system prompt 中

    Returns:
        工具描述文本
    """
    if not _client_pool:
        raise HTTPException(status_code=503, detail="MCP client pool not initialized")

    descriptions = []
    descriptions.append("# 可用工具列表\n")
    
    for name, server in _client_pool._servers.items():
        descriptions.append(f"\n## 服务器: {name}\n")
        
        for tool in server._tools:
            descriptions.append(f"\n### {tool.name}")
            descriptions.append(f"描述: {tool.description}")
            
            # 添加参数信息
            if hasattr(tool, 'inputSchema') and tool.inputSchema:
                schema = tool.inputSchema
                properties = schema.get('properties', {})
                required = schema.get('required', [])
                
                if properties:
                    descriptions.append("参数:")
                    for param_name, param_info in properties.items():
                        param_desc = param_info.get('description', '')
                        param_type = param_info.get('type', 'string')
                        is_required = param_name in required
                        
                        req_mark = "必填" if is_required else "可选"
                        descriptions.append(f"  - {param_name} ({param_type}, {req_mark}): {param_desc}")
            
            descriptions.append("")  # 空行
    
    return {
        "description": "\n".join(descriptions),
        "tool_count": sum(len(server._tools) for server in _client_pool._servers.values())
    }
