# -*- coding:utf-8 -*-
"""
第三方执行器异常类型（2026-08-03 新增）。

``SSHTools.execute_command`` 走第三方分支时，所有第三方调用相关错误
（HTTP 失败 / 超时 / 加密失败 / 响应非法）都封装为 ``ThirdPartyExecutorError``，
由调用方统一捕获并转换为审计日志 + ToolMessage。

Date: 2026-08-03
Author: AI Assistant
"""
from __future__ import annotations

from typing import Optional


class ThirdPartyExecutorError(Exception):
    """第三方命令执行器调用失败的统一异常。"""

    def __init__(
        self,
        error_code: str,
        reason: str,
        user_message: Optional[str] = None,
    ) -> None:
        """初始化异常。

        Args:
            error_code: 错误码（写入审计日志 ``error_code`` 字段，便于聚合）
            reason: 详细原因（仅写入审计日志 metadata）
            user_message: 返回给 LLM / 前端的通用错误文案（避免泄漏 URL / key）
        """
        super().__init__(reason)
        self.error_code = error_code
        self.reason = reason
        self.user_message = user_message or "第三方命令执行失败"


# 错误码常量（统一前缀 ``third_party_``，便于审计聚合）
ERR_CONFIG_MISSING = "third_party_config_missing"
ERR_CONFIG_DISABLED = "third_party_config_disabled"
ERR_CRYPTO_ENCRYPT = "third_party_crypto_error"
ERR_HTTP = "third_party_http_error"
ERR_TIMEOUT = "third_party_timeout"
ERR_INVALID_RESPONSE = "third_party_invalid_response"