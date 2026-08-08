# -*- coding:utf-8 -*-
"""
JWTAuth.generate_token / generate_refresh_token 新增 auth_methods (amr) 单元测试。

覆盖：
- 默认（未传 auth_methods）行为：payload 不含 amr，向后兼容。
- 显式传 list：payload 含 amr 字段，元素顺序保留。
- refresh token 也支持 auth_methods 参数。
- /refresh 透传 amr：从旧 token 提取 amr 后写入新 token（行为由后续路由器保证）。

Author: AI Assistant
Date: 2026-08-07
"""

import asyncio
import sys
from unittest.mock import MagicMock

if "asyncpg" not in sys.modules:
    sys.modules["asyncpg"] = MagicMock()

import jwt
import pytest

from app.shared.utils.auth.Safety import JWTAuth


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_generate_token_legacy_no_amr(jwt_auth):
    """P1: 旧调用（不传 auth_methods）生成的 token 不含 amr 字段。"""
    token = _run_async(jwt_auth.generate_token("admin"))
    payload = jwt.decode(
        token, jwt_auth.secret_key, algorithms=[jwt_auth.algorithm]
    )
    assert "amr" not in payload
    assert payload["username"] == "admin"
    assert payload["type"] == "access"


def test_generate_token_with_amr(jwt_auth):
    """P1: 传 auth_methods=["pwd","totp"] 时 payload 含 amr 字段。"""
    token = _run_async(
        jwt_auth.generate_token("admin", auth_methods=["pwd", "totp"])
    )
    payload = jwt.decode(
        token, jwt_auth.secret_key, algorithms=[jwt_auth.algorithm]
    )
    assert payload.get("amr") == ["pwd", "totp"]


def test_generate_token_with_recovery_code_amr(jwt_auth):
    """P1: 恢复码登录走 auth_methods=['pwd', 'recovery_code']。"""
    token = _run_async(
        jwt_auth.generate_token("user1", auth_methods=["pwd", "recovery_code"])
    )
    payload = jwt.decode(
        token, jwt_auth.secret_key, algorithms=[jwt_auth.algorithm]
    )
    assert payload.get("amr") == ["pwd", "recovery_code"]


def test_generate_token_with_empty_amr(jwt_auth):
    """P1: 显式传空 list 时不写入 amr 字段（与未传等价）。"""
    token = _run_async(jwt_auth.generate_token("admin", auth_methods=[]))
    payload = jwt.decode(
        token, jwt_auth.secret_key, algorithms=[jwt_auth.algorithm]
    )
    assert "amr" not in payload


def test_generate_refresh_token_with_amr(jwt_auth):
    """P1: generate_refresh_token 也支持 auth_methods，传 list 时 payload 含 amr。"""
    token = _run_async(
        jwt_auth.generate_refresh_token(
            "admin", auth_methods=["pwd", "totp"]
        )
    )
    payload = jwt.decode(
        token, jwt_auth.secret_key, algorithms=[jwt_auth.algorithm]
    )
    assert payload.get("amr") == ["pwd", "totp"]
    assert payload["type"] == "refresh"


def test_generate_refresh_token_legacy_no_amr(jwt_auth):
    """P1: 旧 refresh 调用不传 auth_methods 时不含 amr。"""
    token = _run_async(jwt_auth.generate_refresh_token("admin"))
    payload = jwt.decode(
        token, jwt_auth.secret_key, algorithms=[jwt_auth.algorithm]
    )
    assert "amr" not in payload


def test_generate_token_invalid_amr_type_raises(jwt_auth):
    """P1: 非法 auth_methods（非 list）应抛 TypeError，便于调用方尽早发现。"""
    with pytest.raises(TypeError):
        _run_async(jwt_auth.generate_token("admin", auth_methods="pwd,totp"))
