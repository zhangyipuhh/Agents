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

import pytest


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
_protocol_mod = ModuleType("deepagents.backends.protocol")
_protocol_mod.FileData = _FileData
_protocol_mod.ReadResult = _ReadResult
_protocol_mod.ExecuteResponse = type("ExecuteResponse", (), {})
_protocol_mod.FileUploadResponse = type("FileUploadResponse", (), {})
_protocol_mod.FileDownloadResponse = type("FileDownloadResponse", (), {})
sys.modules["deepagents.backends.protocol"] = _protocol_mod

# 提供 docker_sandbox_backend 导入所需的其他 deepagents 子模块
_sandbox_mod = ModuleType("deepagents.backends.sandbox")
_sandbox_mod.BaseSandbox = type("BaseSandbox", (), {})
sys.modules["deepagents.backends.sandbox"] = _sandbox_mod

_local_shell_mod = ModuleType("deepagents.backends.local_shell")
_local_shell_mod.LocalShellBackend = type("LocalShellBackend", (), {})
sys.modules["deepagents.backends.local_shell"] = _local_shell_mod

_mw_fs_mod = ModuleType("deepagents.middleware.filesystem")
_mw_fs_mod.FilesystemMiddleware = type("FilesystemMiddleware", (), {})
sys.modules["deepagents.middleware.filesystem"] = _mw_fs_mod

# 备份全局 conftest 对 filesystem_encoding_fix 的 mock，并在测试模块导入前移除它
_fs_fix_stub = sys.modules.pop("app.shared.tools.middleware.filesystem_encoding_fix", None)


@pytest.fixture(autouse=True, scope="module")
def _restore_filesystem_encoding_fix_stub():
    """
    模块级 autouse fixture：本模块测试结束后恢复全局 filesystem_encoding_fix mock。

    这样可以保证同一会话中后续依赖该 mock 的测试（如通过 app fixture 导入 app.main）
    仍然拿到 stub 模块而非真实模块，避免触发真实的 deepagents monkey patch。
    """
    yield
    if _fs_fix_stub is not None:
        sys.modules["app.shared.tools.middleware.filesystem_encoding_fix"] = _fs_fix_stub
