# -*- coding:utf-8 -*-
"""
shared 测试目录的本地 conftest

在测试模块导入前 mock 缺失的外部依赖，防止 app.core.database、
app.shared.utils.memory 等导入时因缺少包而报错。
"""
import sys
import types
from unittest.mock import MagicMock

# mock asyncpg，避免 app.core.database 导入失败
sys.modules["asyncpg"] = MagicMock()

# mock langgraph 相关子模块，避免 app.shared.utils.memory 导入失败
sys.modules["langgraph"] = MagicMock()
sys.modules["langgraph.store"] = MagicMock()
sys.modules["langgraph.store.memory"] = MagicMock()
sys.modules["langgraph.checkpoint"] = MagicMock()
sys.modules["langgraph.checkpoint.base"] = MagicMock()
sys.modules["langgraph.checkpoint.memory"] = MagicMock()
sys.modules["langgraph.checkpoint.postgres"] = MagicMock()
sys.modules["langgraph.checkpoint.postgres.aio"] = MagicMock()

# mock mcpClient 包（需使用真正的模块对象以支持子模块导入）
_mcp_client = types.ModuleType("mcpClient")
_mcp_client_core = types.ModuleType("mcpClient.core")
_mcp_client_core_unified = types.ModuleType("mcpClient.core.unified_mcp_client")
_mcp_client_shared = types.ModuleType("mcpClient.shared")
_mcp_client_shared_config = types.ModuleType("mcpClient.shared.config_loader")

_mcp_client.core = _mcp_client_core
_mcp_client_core.unified_mcp_client = _mcp_client_core_unified
_mcp_client_core_unified.UnifiedMCPClient = MagicMock
_mcp_client.shared = _mcp_client_shared
_mcp_client_shared.config_loader = _mcp_client_shared_config
_mcp_client_shared_config.load_mcp_config = MagicMock(return_value={})

sys.modules["mcpClient"] = _mcp_client
sys.modules["mcpClient.core"] = _mcp_client_core
sys.modules["mcpClient.core.unified_mcp_client"] = _mcp_client_core_unified
sys.modules["mcpClient.shared"] = _mcp_client_shared
sys.modules["mcpClient.shared.config_loader"] = _mcp_client_shared_config

# mock langchain_core，避免 DocumentLoader 导入失败
_langchain_core = types.ModuleType("langchain_core")
_langchain_core_documents = types.ModuleType("langchain_core.documents")


class _MockDocument:
    """Mock Document 类，满足 DocumentLoader 的导入需求。"""

    def __init__(self, page_content="", metadata=None):
        self.page_content = page_content
        self.metadata = metadata or {}


_langchain_core_documents.Document = _MockDocument
_langchain_core.documents = _langchain_core_documents

sys.modules["langchain_core"] = _langchain_core
sys.modules["langchain_core.documents"] = _langchain_core_documents

# mock langchain_community，避免 TextLoader 等导入失败
sys.modules["langchain_community"] = MagicMock()
sys.modules["langchain_community.document_loaders"] = MagicMock()

# mock deepagents，避免 filesystem_encoding_fix 导入失败
sys.modules["deepagents"] = MagicMock()
sys.modules["deepagents.backends"] = MagicMock()
sys.modules["deepagents.backends.filesystem"] = MagicMock()
