# -*- coding:utf-8 -*-
"""
第三方命令执行器子包。

提供 ``execute_command`` 工具走第三方分支时所需的全部组件：
    - ``endpoints``: 端点注册表（从 ``.env`` 加载）
    - ``third_party_executor``: 加密 + HTTP 调度
    - ``errors``: 统一异常类型 + 错误码常量
"""

from app.shared.utils.executor.endpoints import (
    ThirdPartyEndpoint,
    ThirdPartyEndpointRegistry,
)
from app.shared.utils.executor.errors import ThirdPartyExecutorError
from app.shared.utils.executor.third_party_executor import dispatch, normalize_response

__all__ = [
    "ThirdPartyEndpoint",
    "ThirdPartyEndpointRegistry",
    "ThirdPartyExecutorError",
    "dispatch",
    "normalize_response",
]