# -*- coding:utf-8 -*-
"""
密码规则（最小长度 8 + 大写 + 小写 + 数字 + 特殊字符）单元测试。

覆盖：
- 7 位密码（含所有必需字符）被拒；
- 8 位密码（含所有必需字符）通过；
- 缺任何一类（upper / lower / digit / special）必须被拒；
- helper ``validate_password`` 暴露为共享工具（auth_router / user_router / mfa_router 复用）。

Author: AI Assistant
Date: 2026-08-07
"""

import asyncio
import sys
from unittest.mock import MagicMock

if "asyncpg" not in sys.modules:
    sys.modules["asyncpg"] = MagicMock()

import pytest


def test_validate_password_rejects_7_chars_with_all_classes():
    """7 位密码含所有类也被拒（长度下限）。"""
    from app.shared.utils.auth.password_policy import validate_password

    is_valid, error = validate_password("Aa1!aaa")  # 7 字符
    assert is_valid is False
    assert "长度" in error or "8" in error


def test_validate_password_accepts_8_chars_full_classes():
    """8 位密码含所有类（大小写+数字+特殊字符）通过。"""
    from app.shared.utils.auth.password_policy import validate_password

    is_valid, error = validate_password("Aa1!aaaa")
    assert is_valid is True, error
    assert error is None


def test_validate_password_rejects_when_missing_uppercase():
    """缺大写字母 → 拒。"""
    from app.shared.utils.auth.password_policy import validate_password

    is_valid, error = validate_password("aa1!aaaa")
    assert is_valid is False
    assert "大写" in error


def test_validate_password_rejects_when_missing_lowercase():
    """缺小写字母 → 拒。"""
    from app.shared.utils.auth.password_policy import validate_password

    is_valid, error = validate_password("AA1!AAAA")
    assert is_valid is False
    assert "小写" in error


def test_validate_password_rejects_when_missing_digit():
    """缺数字 → 拒。"""
    from app.shared.utils.auth.password_policy import validate_password

    is_valid, error = validate_password("Aaa!aaaa")
    assert is_valid is False
    assert "数字" in error


def test_validate_password_rejects_when_missing_special():
    """缺特殊字符 → 拒。"""
    from app.shared.utils.auth.password_policy import validate_password

    is_valid, error = validate_password("Aa1aaaaa")
    assert is_valid is False
    assert "特殊" in error


def test_validate_password_accepts_long_complex_password():
    """长且复杂密码通过。"""
    from app.shared.utils.auth.password_policy import validate_password

    pwd = "Tough!Pass2026"
    is_valid, error = validate_password(pwd)
    assert is_valid is True, error


def test_validate_password_empty_string_rejected():
    """空字符串被拒。"""
    from app.shared.utils.auth.password_policy import validate_password

    is_valid, error = validate_password("")
    assert is_valid is False
    assert "长度" in error or "8" in error
