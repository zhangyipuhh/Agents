#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
mcp服务器工具集模块
date: 2026-01-13
author: 张镒谱
"""
import asyncio
import threading
from typing import Any
from langchain_mcp_adapters.client import MultiServerMCPClient  

 

class MCPServersTools:
    """
    mcp服务器工具集类
    """
    def __init__(self):
        """
        初始化方法
        """
        self.mcp_tools = []
    
    async def get_mcp_method_list(self) -> list:
        """
        获取MCP服务器的工具列表
        连接失败时返回空列表，不影响主程序运行
        """
        try:
            print("正在连接MCP服务器...")
            client = MultiServerMCPClient(
                {
                    "高德地图": {
                        "transport": "sse",
                        "url": "https://mcp.amap.com/sse?key=df6d69f0846583058f276495acc9d487"
                    }
                }
            )
            self.mcp_tools = await client.get_tools()
            print(f"MCP工具加载成功，共 {len(self.mcp_tools)} 个工具")
            return self.mcp_tools
            
        except Exception as e:
            print(f"⚠️ MCP服务器连接失败: {e}")
            print("将使用静态工具，MCP功能不可用")
            self.mcp_tools = []
            return []  
    
    def get_mcp_method_names(self) -> list:
        """
        获取所有mcp服务器工具的方法名称列表
        """
        return [tool.name for tool in self.mcp_tools]
    
    def get_mcp_methods(self) -> dict[str, Any]:
        """
        获取所有mcp服务器工具的方法字典
        """
        return {tool.name: tool for tool in self.mcp_tools}
