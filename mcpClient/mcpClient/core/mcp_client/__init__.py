# mcpClient.core.mcp_client

"""
MCP Client 模块

兼容旧导入路径，新代码请使用 mcpClient.core.unified_mcp_client。
"""

from mcpClient.core.unified_mcp_client import (
    UnifiedMCPClient,
    SamplingCallback,
    StreamOutputWrapper,
)

__all__ = [
    "UnifiedMCPClient",
    "SamplingCallback",
    "StreamOutputWrapper",
]
