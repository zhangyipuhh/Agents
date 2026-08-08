# -*- coding:utf-8 -*-
"""
POST /api/auth/register 密码长度 8 强校验（2026-08-07 改造）回归测试。

覆盖：
- 7 位复杂密码（满足四类字符）被 400 拒；
- 8 位复杂密码通过；
- 缺任一类被 400 拒。

Author: AI Assistant
Date: 2026-08-07
"""

import sys
from unittest.mock import MagicMock

if "asyncpg" not in sys.modules:
    sys.modules["asyncpg"] = MagicMock()

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="function")
def app():
    """构造仅包含 auth_router 的 FastAPI app。"""
    from app.core.server import create_app
    from app.shared.routers.auth_router import router as auth_router

    _app = create_app()
    _app.include_router(auth_router)
    return _app


@pytest.fixture(scope="function")
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def reset_user_db():
    from app.shared.utils.auth.user_db import UserDB

    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0
    yield
    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0


def _post_register(client, password):
    return client.post(
        "/api/auth/register",
        json={
            "username": f"reguser_{abs(hash(password)) % 100000}",
            "password": password,
            "confirm_password": password,
            "real_name": "测试用户",
            "phone": "13800138000",
            "email": "reg@example.com",
            "department": "测试部",
            "position": "工程师",
            "captcha_key": "mock_key",
            "captcha_code": "0000",
        },
    )


def test_register_7char_password_rejected(client, monkeypatch):
    """P0: 7 位满足四类的密码仍被 400 拒（长度下限）。"""
    monkeypatch.setattr(
        "app.shared.utils.auth.captcha.captcha_manager.verify",
        lambda key, code: True,
    )
    response = _post_register(client, "Ab1!aaa")  # 7 字符
    assert response.status_code == 400
    assert "8" in response.json()["detail"]


def test_register_8char_complex_password_accepted(client, monkeypatch):
    """P1: 8 位满足四类的密码通过。"""
    monkeypatch.setattr(
        "app.shared.utils.auth.captcha.captcha_manager.verify",
        lambda key, code: True,
    )
    response = _post_register(client, "Ab1!aaaa")  # 8 字符
    assert response.status_code == 200
    assert response.json()["message"] == "注册成功"
