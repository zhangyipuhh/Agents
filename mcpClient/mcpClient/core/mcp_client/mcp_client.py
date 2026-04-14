#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
MCP 客户端模块

提供与 MCP 服务通信的客户端类
"""

from typing import Any, Dict, List, Optional
import requests


class MCPClient:
    """
    MCP 客户端，用于与 MCP 服务通信
    
    提供发现工具、调用工具等功能
    
    Attributes:
        base_url: MCP 服务地址
        _tools_cache: 工具列表缓存
    
    Example:
        >>> client = MCPClient("http://localhost:10001")
        >>> servers = client.list_servers()
        >>> result = client.call_tool("高德地图mcp", "maps_geo", {"address": "北京市"})
    """

    def __init__(self, base_url: str = "http://localhost:10001"):
        """
        初始化 MCP 客户端

        Args:
            base_url: MCP 服务地址，默认 http://localhost:10001
        """
        self.base_url = base_url.rstrip("/")
        self._tools_cache: Optional[List[Dict]] = None

    def list_servers(self) -> List[Dict]:
        """
        获取所有已连接的 MCP 服务器

        Returns:
            服务器列表，每个服务器包含 name, connected, tools 等信息

        Example:
            >>> client = MCPClient()
            >>> servers = client.list_servers()
            >>> print(servers)
            [{'name': '高德地图mcp', 'connected': True, 'tools': [...]}]
        """
        response = requests.get(f"{self.base_url}/mcp/servers")
        response.raise_for_status()
        return response.json()

    def list_tools(self, server_name: str) -> Dict:
        """
        获取指定服务器的工具列表

        Args:
            server_name: 服务器名称

        Returns:
            工具列表信息，包含 server 和 tools 字段

        Example:
            >>> tools_info = client.list_tools("高德地图mcp")
            >>> print(tools_info['tools'])
            [{'name': 'maps_geo', 'description': '...', 'inputSchema': {...}}]
        """
        response = requests.get(f"{self.base_url}/mcp/tools/{server_name}")
        response.raise_for_status()
        return response.json()

    def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Dict:
        """
        调用 MCP 工具

        Args:
            server_name: 服务器名称
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            工具调用结果，包含 success, result, error 字段

        Example:
            >>> result = client.call_tool(
            ...     "高德地图mcp",
            ...     "maps_geo",
            ...     {"address": "北京市朝阳区"}
            ... )
            >>> print(result['success'])
            True
        """
        response = requests.post(
            f"{self.base_url}/mcp/call",
            json={
                "server_name": server_name,
                "tool_name": tool_name,
                "arguments": arguments
            }
        )
        response.raise_for_status()
        return response.json()

    def get_all_tools(self, use_cache: bool = True) -> List[Dict]:
        """
        获取所有可用的工具

        从所有已连接的服务器收集工具信息

        Args:
            use_cache: 是否使用缓存，默认为 True

        Returns:
            工具列表，每个工具包含 server, name, description, inputSchema 字段

        Example:
            >>> tools = client.get_all_tools()
            >>> for tool in tools:
            ...     print(f"{tool['server']}.{tool['name']}")
        """
        if use_cache and self._tools_cache is not None:
            return self._tools_cache

        self._tools_cache = []
        servers = self.list_servers()

        for server in servers:
            server_name = server["name"]
            try:
                tools_info = self.list_tools(server_name)
                for tool in tools_info.get("tools", []):
                    self._tools_cache.append({
                        "server": server_name,
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "inputSchema": tool.get("inputSchema", {})
                    })
            except Exception as e:
                print(f"获取服务器 '{server_name}' 的工具失败: {e}")

        return self._tools_cache

    def clear_cache(self) -> None:
        """
        清除工具列表缓存

        在工具列表发生变化时调用
        """
        self._tools_cache = None

    def health_check(self) -> bool:
        """
        检查 MCP 服务是否健康

        Returns:
            如果服务正常返回 True，否则返回 False
        """
        try:
            response = requests.get(f"{self.base_url}/", timeout=5)
            return response.status_code == 200
        except Exception:
            return False


# 全局默认客户端实例
_default_client: Optional[MCPClient] = None


def get_mcp_client(base_url: str = "http://localhost:10001") -> MCPClient:
    """
    获取 MCP 客户端实例

    返回全局默认客户端实例，如果不存在则创建

    Args:
        base_url: MCP 服务地址

    Returns:
        MCPClient 实例

    Example:
        >>> client = get_mcp_client()
        >>> servers = client.list_servers()
    """
    global _default_client
    if _default_client is None:
        _default_client = MCPClient(base_url)
    return _default_client


def reset_mcp_client() -> None:
    """
    重置全局 MCP 客户端实例

    在需要重新创建客户端时调用
    """
    global _default_client
    _default_client = None
