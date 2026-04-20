#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Agent 集成 MCP 服务的示例

展示了如何在 Agent 初始化时从 mcpClient 服务加载工具
"""

import requests
from typing import List, Dict, Any, Optional


class MCPServiceClient:
    """
    MCP 服务客户端
    
    用于与 mcpClient 服务通信，获取工具列表和调用工具
    """
    
    def __init__(self, base_url: str = "http://localhost:10002"):
        self.base_url = base_url.rstrip("/")
        self._tools_cache: Optional[List[Dict]] = None
    
    def get_tools_for_llm(self) -> str:
        """
        获取适合 LLM 使用的工具描述
        
        Returns:
            格式化的工具描述文本，可直接插入 system prompt
        """
        response = requests.get(f"{self.base_url}/mcp/tools-for-llm")
        response.raise_for_status()
        return response.json()["description"]
    
    def get_formatted_tools(self) -> List[Dict]:
        """
        获取格式化的工具列表
        
        Returns:
            工具列表，包含名称、描述、参数等信息
        """
        if self._tools_cache is None:
            response = requests.get(f"{self.base_url}/mcp/tools-formatted")
            response.raise_for_status()
            self._tools_cache = response.json()["tools"]
        return self._tools_cache
    
    def call_tool(self, server_name: str, tool_name: str, arguments: Dict) -> Dict:
        """
        调用 MCP 工具
        
        Args:
            server_name: 服务器名称
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            工具调用结果
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
    
    def clear_cache(self):
        """清除工具缓存"""
        self._tools_cache = None


# ============ Agent 集成示例 ============

class AgentWithMCP:
    """
    集成 MCP 工具的 Agent 示例
    
    在初始化时从 mcpClient 服务加载工具信息
    """
    
    def __init__(self, mcp_service_url: str = "http://localhost:10002"):
        """
        初始化 Agent
        
        Args:
            mcp_service_url: MCP 服务地址
        """
        self.mcp_client = MCPServiceClient(mcp_service_url)
        self.system_prompt = self._build_system_prompt()
    
    def _build_system_prompt(self) -> str:
        """
        构建系统提示词，包含 MCP 工具描述
        
        在服务初始化时调用，只执行一次
        """
        base_prompt = """你是一个智能助手，可以帮助用户完成各种任务。

你可以使用以下工具来完成任务。当需要调用工具时，请使用以下格式：

工具调用格式：
```tool
server: <服务器名称>
tool: <工具名称>
args:
  <参数1>: <值1>
  <参数2>: <值2>
```

"""
        
        # 从 MCP 服务获取工具描述
        try:
            tools_description = self.mcp_client.get_tools_for_llm()
            return base_prompt + tools_description
        except Exception as e:
            print(f"加载 MCP 工具失败: {e}")
            return base_prompt
    
    async def process(self, user_input: str) -> str:
        """
        处理用户输入
        
        这里简化处理，实际应该调用 LLM 并根据响应决定是否需要调用工具
        """
        # 实际实现中，这里应该：
        # 1. 将 system_prompt + user_input 发送给 LLM
        # 2. 解析 LLM 响应，判断是否需要调用工具
        # 3. 如果需要，调用 MCP 工具
        # 4. 将工具结果返回给 LLM
        # 5. 返回最终响应给用户
        
        return f"System prompt 长度: {len(self.system_prompt)} 字符"


# ============ 使用示例 ============

def main():
    print("=== Agent 集成 MCP 服务示例 ===\n")
    
    # 创建 MCP 服务客户端
    mcp_client = MCPServiceClient("http://localhost:10002")
    
    # 1. 获取工具列表（格式化）
    print("1. 获取格式化工具列表:")
    try:
        tools = mcp_client.get_formatted_tools()
        print(f"   共 {len(tools)} 个工具")
        for tool in tools[:3]:
            print(f"\n   - {tool['server']}.{tool['name']}")
            print(f"     描述: {tool['description'][:50]}...")
            if 'parameters' in tool:
                print(f"     参数:")
                for param in tool['parameters'][:2]:
                    print(f"       {param}")
    except Exception as e:
        print(f"   错误: {e}")
    
    # 2. 获取适合 LLM 的工具描述
    print("\n\n2. 获取适合 LLM 的工具描述:")
    try:
        description = mcp_client.get_tools_for_llm()
        print(f"   描述长度: {len(description)} 字符")
        print(f"   前 500 字符:\n{description[:500]}...")
    except Exception as e:
        print(f"   错误: {e}")
    
    # 3. 调用工具
    print("\n\n3. 调用 maps_geo 工具:")
    try:
        result = mcp_client.call_tool(
            "高德地图mcp",
            "maps_geo",
            {"address": "北京市天安门"}
        )
        if result.get("success"):
            import json
            content = json.loads(result["result"]["content"][0]["text"])
            print(f"   查询结果:")
            for item in content.get("results", [])[:1]:
                print(f"     地址: {item.get('province', '')}{item.get('city', '')}{item.get('district', '')}")
                print(f"     坐标: {item.get('location', '')}")
        else:
            print(f"   调用失败: {result.get('error')}")
    except Exception as e:
        print(f"   错误: {e}")
    
    # 4. 创建 Agent
    print("\n\n4. 创建集成 MCP 的 Agent:")
    try:
        agent = AgentWithMCP("http://localhost:10002")
        print(f"   Agent 创建成功")
        print(f"   System prompt 长度: {len(agent.system_prompt)} 字符")
    except Exception as e:
        print(f"   错误: {e}")
    
    print("\n=== 示例完成 ===")


if __name__ == "__main__":
    main()
