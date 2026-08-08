# -*- coding:utf-8 -*-
"""
密码强度验证工具（2026-08-07 新增）。

集中 ``注册 / 管理员创建用户 / 修改密码`` 三处共同使用的密码规则：

- **最小长度**：8（与 ``等保三级`` + ``AGENTS.md`` 强制约束对齐）
- **必须包含**：大写字母 / 小写字母 / 数字 / 特殊字符（``!@#$%^&*()_+\-=\[\]{}|;:,.<>?``）

调用方：

- ``app.shared.routers.auth_router.register`` —— 注册时校验
- ``app.shared.routers.user_router`` —— 管理员创建用户 / 用户改密码

返回 ``(is_valid, error_message)``，错误消息详细说明不满足哪一类，方便前端展示。

Author: AI Assistant
Date: 2026-08-07
"""
from __future__ import annotations

import re
from typing import Tuple

# 密码特殊字符集（与项目历史 register / user_router 行为保持一致）
_SPECIAL_CHARS = r"!@#$%^&*()_+\-=\[\]{}|;:,.<>?"


def validate_password(password: str) -> Tuple[bool, str | None]:
    """校验密码强度是否符合项目统一规则。

    Args:
        password: 明文密码。

    Returns:
        Tuple[bool, Optional[str]]: ``(is_valid, error_message)``。
        通过时 ``error_message=None``；拒绝时为具体原因（中文字符串）。
    """
    if not isinstance(password, str) or not password:
        return False, "密码长度不能少于8位"
    if len(password) < 8:
        return False, "密码长度不能少于8位"
    if not re.search(r"[A-Z]", password):
        return False, "密码必须包含大写字母"
    if not re.search(r"[a-z]", password):
        return False, "密码必须包含小写字母"
    if not re.search(r"\d", password):
        return False, "密码必须包含数字"
    if not re.search(f"[{re.escape(_SPECIAL_CHARS)}]", password):
        return False, "密码必须包含特殊字符"
    return True, None
