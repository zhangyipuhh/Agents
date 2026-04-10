#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MCP 工具包装器模块

提供 MCP 工具的包装类，自动应用双重输出策略，
无需修改 tool_node 节点代码。

Date: 2026-04-08
Author: 张镒谱
"""

from typing import Any, Optional
from datetime import datetime
from langchain_core.tools import BaseTool, ToolException
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer


class MCPToolWrapper(BaseTool):
    """
    MCP 工具包装类
    
    包装 MCP 工具，自动应用双重输出策略：
    - 小数据：直接返回完整结果
    - 大数据：返回简短摘要，详细数据通过 get_stream_writer 发送
    
    这样 tool_node 不需要任何修改，只需要使用包装后的工具。
    """
    
    def __init__(
        self,
        original_tool: BaseTool,
        max_content_length: int = 500,
        **kwargs
    ):
        """
        初始化 MCP 工具包装器
        
        Args:
            original_tool: 原始 MCP 工具
            max_content_length: ToolMessage 最大内容长度（字符）
            **kwargs: 传递给 BaseTool 的其他参数
        """
        super().__init__(**kwargs)
        self.original_tool = original_tool
        self.max_content_length = max_content_length
        
        self.name = original_tool.name
        self.description = original_tool.description
        self.args_schema = original_tool.args_schema
    
    def _run(
        self,
        *args,
        config: Optional[RunnableConfig] = None,
        **kwargs
    ) -> str:
        """
        同步运行方法（不支持流式输出）
        
        Args:
            *args: 位置参数
            config: 运行时配置
            **kwargs: 关键字参数
        
        Returns:
            str: 工具执行结果
        """
        result = self.original_tool._run(*args, config=config, **kwargs)
        return self._process_result(result)
    
    async def _arun(
        self,
        *args,
        config: Optional[RunnableConfig] = None,
        **kwargs
    ) -> str:
        """
        异步运行方法（支持流式输出）
        
        Args:
            *args: 位置参数
            config: 运行时配置
            **kwargs: 关键字参数
        
        Returns:
            str: 工具执行结果（简短摘要或完整数据）
        """
        writer = get_stream_writer()
        
        tool_call_id = self._get_tool_call_id(config)
        
        try:
            # 1. 发送开始标记
            writer({
                "header": {
                    "tool_name": self.name,
                    "tool_call_id": tool_call_id,
                    "timestamp": datetime.now().isoformat(),
                    "status": "start",
                    "version": "1.0"
                },
                "body": {
                    "data": None,
                    "metadata": {
                        "tool_type": "mcp",
                        "args": kwargs
                    }
                },
                "footer": None
            })
            
            # 2. 调用原始 MCP 工具
            result = await self.original_tool._arun(*args, config=config, **kwargs)
            
            # 3. 分析结果数据
            result_str = str(result)
            result_length = len(result_str)
            
            # 4. 判断数据大小，决定处理方式
            if result_length <= self.max_content_length:
                # 小数据：直接返回
                writer({
                    "header": {
                        "tool_name": self.name,
                        "tool_call_id": tool_call_id,
                        "timestamp": datetime.now().isoformat(),
                        "status": "complete",
                        "version": "1.0"
                    },
                    "body": {
                        "data": result,
                        "metadata": {
                            "tool_type": "mcp",
                            "data_size": "small",
                            "result_length": result_length
                        }
                    },
                    "footer": {
                        "success": True,
                        "message": "执行成功",
                        "stats": {
                            "total": 1,
                            "processed": 1,
                            "failed": 0
                        }
                    }
                })
                
                return result_str
            
            else:
                # 大数据：分离处理
                # 4.1 流式发送详细数据
                writer({
                    "header": {
                        "tool_name": self.name,
                        "tool_call_id": tool_call_id,
                        "timestamp": datetime.now().isoformat(),
                        "status": "progress",
                        "version": "1.0"
                    },
                    "body": {
                        "data": result,  # 详细数据
                        "metadata": {
                            "tool_type": "mcp",
                            "data_size": "large",
                            "result_length": result_length
                        }
                    },
                    "footer": None
                })
                
                # 4.2 发送完成标记
                writer({
                    "header": {
                        "tool_name": self.name,
                        "tool_call_id": tool_call_id,
                        "timestamp": datetime.now().isoformat(),
                        "status": "complete",
                        "version": "1.0"
                    },
                    "body": {
                        "data": None,
                        "metadata": {
                            "tool_type": "mcp",
                            "data_size": "large"
                        }
                    },
                    "footer": {
                        "success": True,
                        "message": f"执行成功，返回 {result_length} 字符数据",
                        "stats": {
                            "total": 1,
                            "processed": 1,
                            "failed": 0
                        }
                    }
                })
                
                # 4.3 返回简短摘要
                summary = f"执行成功，返回 {result_length} 字符数据"
                if isinstance(result, (dict, list)):
                    summary = f"执行成功，返回 {type(result).__name__}，大小: {result_length} 字符"
                
                return summary
        
        except Exception as e:
            error_msg = f"工具调用失败: {self.name}, 错误: {str(e)}"
            
            # 发送错误标记
            writer({
                "header": {
                    "tool_name": self.name,
                    "tool_call_id": tool_call_id,
                    "timestamp": datetime.now().isoformat(),
                    "status": "error",
                    "version": "1.0"
                },
                "body": {
                    "data": None,
                    "metadata": {
                        "tool_type": "mcp",
                        "error": error_msg
                    }
                },
                "footer": {
                    "success": False,
                    "message": error_msg,
                    "stats": {
                        "total": 1,
                        "processed": 0,
                        "failed": 1
                    }
                }
            })
            
            return f"错误：{error_msg}"
    
    def _process_result(self, result: Any) -> str:
        """
        处理结果数据（非流式模式）
        
        Args:
            result: 工具执行结果
        
        Returns:
            str: 处理后的结果字符串
        """
        result_str = str(result)
        result_length = len(result_str)
        
        if result_length <= self.max_content_length:
            return result_str
        else:
            summary = f"执行成功，返回 {result_length} 字符数据"
            if isinstance(result, (dict, list)):
                summary = f"执行成功，返回 {type(result).__name__}，大小: {result_length} 字符"
            return summary
    
    def _get_tool_call_id(self, config: Optional[RunnableConfig]) -> str:
        """
        从配置中获取工具调用 ID
        
        Args:
            config: 运行时配置
        
        Returns:
            str: 工具调用 ID
        """
        if config and "configurable" in config:
            return config["configurable"].get("tool_call_id", "unknown")
        return "unknown"


def wrap_mcp_tools(
    mcp_tools: list[BaseTool],
    max_content_length: int = 500
) -> list[MCPToolWrapper]:
    """
    批量包装 MCP 工具
    
    Args:
        mcp_tools: MCP 工具列表
        max_content_length: ToolMessage 最大内容长度（字符）
    
    Returns:
        list[MCPToolWrapper]: 包装后的工具列表
    
    Example:
        >>> # 获取 MCP 工具
        >>> mcp_tools = await mcpservers_tools.get_mcp_method_list()
        >>> 
        >>> # 包装 MCP 工具
        >>> wrapped_tools = wrap_mcp_tools(mcp_tools, max_content_length=500)
        >>> 
        >>> # 合并工具列表
        >>> all_tools = static_tools + wrapped_tools
        >>> 
        >>> # 绑定到模型
        >>> model_with_tools = model.bind_tools(all_tools)
    """
    return [
        MCPToolWrapper(tool, max_content_length=max_content_length)
        for tool in mcp_tools
    ]
