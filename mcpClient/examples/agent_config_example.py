#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
在 AgentConfig 中集成 MCP 工具的示例

展示了如何继承 AgentConfig 并在 get_tools 方法中添加 MCP 工具
"""

from dataclasses import dataclass, field
from typing import Optional
from langgraph.prebuilt import ToolNode
from app.core.agent.AgentConfig import AgentConfig as BaseAgentConfig


@dataclass(kw_only=True)
class MCPAgentConfig(BaseAgentConfig):
    """
    集成 MCP 工具的 Agent 配置示例
    
    使用方式:
        config = MCPAgentConfig(
            mcp_base_url="http://localhost:10001",
            include_mcp_tools=True
        )
        tools, tool_node = config.get_tools()
    """
    
    mcp_base_url: str = field(default="http://localhost:10001")
    """MCP 服务地址"""
    
    include_mcp_tools: bool = field(default=True)
    """是否包含 MCP 工具"""
    
    def get_tools(self) -> tuple[list, ToolNode]:
        """
        获取所有工具（包括本地工具和 MCP 工具）
        
        Returns:
            tuple[list, ToolNode]: 工具列表和 ToolNode 对象
        """
        # 1. 先获取基础工具（来自父类）
        tools, _ = super().get_tools()
        
        # 2. 添加 MCP 工具
        if self.include_mcp_tools:
            mcp_tools = self._get_mcp_tools()
            tools.extend(mcp_tools)
            print(f"已加载 {len(mcp_tools)} 个 MCP 工具")
        
        return tools, ToolNode(tools)
    
    def _get_mcp_tools(self) -> list:
        """
        从 MCP 服务获取工具并转换为 LangChain 工具
        
        Returns:
            LangChain 工具列表
        """
        try:
            # 导入 MCPClient
            import sys
            from pathlib import Path
            mcp_client_path = Path(__file__).parent.parent
            if str(mcp_client_path) not in sys.path:
                sys.path.insert(0, str(mcp_client_path))
            
            from mcpClient.core.mcp_client import MCPClient
            
            # 创建客户端
            client = MCPClient(self.mcp_base_url)
            
            # 检查服务健康
            if not client.health_check():
                print(f"MCP 服务 {self.mcp_base_url} 不可用")
                return []
            
            # 获取所有工具信息
            tools_info = client.get_all_tools()
            
            # 转换为 LangChain 工具
            lc_tools = []
            for tool_info in tools_info:
                lc_tool = self._convert_to_langchain_tool(client, tool_info)
                if lc_tool:
                    lc_tools.append(lc_tool)
            
            return lc_tools
            
        except Exception as e:
            print(f"加载 MCP 工具失败: {e}")
            return []
    
    def _convert_to_langchain_tool(self, client: "MCPClient", tool_info: dict):
        """
        将 MCP 工具信息转换为 LangChain 工具
        
        Args:
            client: MCPClient 实例
            tool_info: 工具信息字典
            
        Returns:
            LangChain 工具对象
        """
        from langchain_core.tools import StructuredTool
        from pydantic import BaseModel, Field
        
        server_name = tool_info["server"]
        tool_name = tool_info["name"]
        description = tool_info.get("description", "")
        input_schema = tool_info.get("inputSchema", {})
        
        # 根据 inputSchema 创建参数模型
        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])
        
        # 构建参数字段
        annotations = {}
        for param_name, param_info in properties.items():
            param_type = param_info.get("type", "string")
            param_desc = param_info.get("description", "")
            
            if param_type == "string":
                annotations[param_name] = (str, Field(description=param_desc))
            elif param_type == "integer":
                annotations[param_name] = (int, Field(description=param_desc))
            elif param_type == "number":
                annotations[param_name] = (float, Field(description=param_desc))
            elif param_type == "boolean":
                annotations[param_name] = (bool, Field(description=param_desc))
        
        # 创建参数模型类
        class ArgsModel(BaseModel):
            model_config = {"arbitrary_types_allowed": True}
            
        for name, (type_, field_info) in annotations.items():
            setattr(ArgsModel, name, field_info)
            ArgsModel.__annotations__[name] = type_
        
        # 定义工具函数
        def tool_func(**kwargs):
            result = client.call_tool(server_name, tool_name, kwargs)
            if result.get("success"):
                # 提取文本内容
                content = result["result"]["content"][0]["text"]
                return content
            else:
                return f"Error: {result.get('error')}"
        
        # 创建 StructuredTool
        return StructuredTool.from_function(
            func=tool_func,
            name=tool_name,
            description=description,
            args_schema=ArgsModel
        )


# ============ 使用示例 ============

if __name__ == "__main__":
    print("=== AgentConfig MCP 集成示例 ===\n")
    
    # 创建配置
    config = MCPAgentConfig(
        system_prompt="""你是一个地图助手，可以帮助用户查询地理信息、规划路线等。

你可以使用以下工具：
- maps_geo: 将地址转换为经纬度坐标
- maps_regeocode: 将经纬度转换为地址
- maps_direction_driving: 驾车路线规划
- maps_weather: 查询天气
- maps_text_search: 搜索地点

请根据用户需求选择合适的工具。""",
        mcp_base_url="http://localhost:10001",
        include_mcp_tools=True
    )
    
    # 获取工具
    tools, tool_node = config.get_tools()
    
    print(f"\n总共 {len(tools)} 个工具:")
    for i, tool in enumerate(tools):
        print(f"  {i+1}. {tool.name if hasattr(tool, 'name') else str(tool)}")
