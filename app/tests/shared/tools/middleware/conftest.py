# -*- coding:utf-8 -*-
"""
FilesystemEncodingFix 测试目录本地 conftest

全局 conftest 将 filesystem_encoding_fix 模块 mock 为仅含 apply_fix 的 stub，
以便 app.main 在测试环境中导入时不会触发真实的 deepagents  monkey patch。
但本目录的测试需要导入真实的 filesystem_encoding_fix 模块来验证其内部函数，
因此在此提供必要的 deepagents.backends.protocol mock，并在测试模块导入前移除
sys.modules 中的 filesystem_encoding_fix stub；测试结束后恢复该 stub，避免影响
同一会话中其他依赖 mock 的测试。
"""
import sys
from types import ModuleType
from unittest.mock import MagicMock



class _FileData(dict):
    """模拟 deepagents.backends.protocol.FileData，支持属性与字典两种访问方式。"""

    def __init__(self, content=None, encoding=None):
        super().__init__(content=content, encoding=encoding)
        self.content = content
        self.encoding = encoding


class _ReadResult:
    """模拟 deepagents.backends.protocol.ReadResult，供 filesystem_encoding_fix 导入。"""

    def __init__(self, file_data=None, error=None):
        self.file_data = file_data
        self.error = error


# 提供 deepagents.backends.protocol 模块，使 filesystem_encoding_fix 能正常导入
# 注意：本目录其它测试（如 docker_sandbox_backend）依赖 deepagents 子模块的 MagicMock 行为，
# 因此此处仅补充 filesystem_encoding_fix 所需的 protocol，不覆盖已有的 sandbox / middleware mock。
_protocol_mod = ModuleType("deepagents.backends.protocol")
_protocol_mod.FileData = _FileData
_protocol_mod.ReadResult = _ReadResult
_protocol_mod.ExecuteResponse = MagicMock()
_protocol_mod.FileUploadResponse = MagicMock()
_protocol_mod.FileDownloadResponse = MagicMock()
sys.modules["deepagents.backends.protocol"] = _protocol_mod
