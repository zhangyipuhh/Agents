#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
mcp服务器工具集模块
date: 2026-01-13
author: 张镒谱
"""

from langchain_mcp_adapters.client import MultiServerMCPClient  

class MCPServersTools:
    """
    mcp服务器工具集类
    """
    def __init__(self):
        """
        初始化方法
        """
        pass
    async def query_mcp_server(self) -> list:
        """
        查询指定mcp服务器的方法
        """
        client = MultiServerMCPClient(  
            {
                "高德地图": {
                    "transport": "http",  # HTTP-based remote server
                    # Ensure you start your weather server on port 8000
                    "url": "https://mcp.amap.com/sse?key=df6d69f0846583058f276495acc9d487",
                }
            }
        )

        return await client.get_tools()  