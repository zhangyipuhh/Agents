# -*- coding:utf-8 -*-
"""
app/core/server.py lifespan 初始化 MfaService 测试。

注意：禁止用 fixture 虚构生产 lifespan 不存在的 state 对象。
本测试断言 lifespan 真实挂载 ``app.state.mfa_service``。

通过 ``build_test_app()`` 重新构造独立 FastAPI 实例，并 ``with TestClient(app)``
触发 lifespan 上下文。避免依赖 ``app/tests/conftest.py`` 中的 session 级 fixture（其
已 patch 掉 ``DatabasePool.initialize`` 等，对真实 lifespan 初始化路径不可见）。
"""

import pytest


def _build_minimal_app():
    """构造最小 FastAPI 应用，仅包含 server 的 lifespan（无路由）。

    Returns:
        FastAPI: 一个未挂任何 router 的应用实例。
    """
    from contextlib import asynccontextmanager

    from fastapi import FastAPI

    # 复用 lifespan 而非 create_app() 以避开 create_app() 中的中间件 / 静态文件挂载
    # （它们在测试环境会触发其他副作用）
    from app.core import server as server_module

    lifespan_func = server_module.lifespan

    @asynccontextmanager
    async def _lifespan(app):
        async with lifespan_func(app):
            yield

    return FastAPI(lifespan=_lifespan)


def _set_valid_mfa_secret(monkeypatch):
    """为 lifespan 测试注入合法的 Fernet 密钥（恰好 32 字节 base64）。"""
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("MFA_SECRET_KEY", key)
    return key


def test_lifespan_initializes_mfa_service_in_memory_mode(monkeypatch):
    """memory 模式下 lifespan 必须真实挂载 ``app.state.mfa_service`` 为 MfaService 实例。"""
    monkeypatch.setenv("AUTH_STORAGE_MODE", "memory")
    _set_valid_mfa_secret(monkeypatch)

    from fastapi.testclient import TestClient

    from app.shared.utils.auth.mfa_service import MfaService

    app = _build_minimal_app()

    with TestClient(app) as client:
        mfa_service = getattr(app.state, "mfa_service", None)
        assert mfa_service is not None, (
            "lifespan 必须真实挂载 app.state.mfa_service，不得依赖测试 fixture 虚构。"
        )
        assert isinstance(mfa_service, MfaService)


def test_lifespan_mfa_service_removes_mfa_whitelisted_paths(monkeypatch):
    """lifespan 必须把 mfa public challenge 端点（3 个）加入 jwt_auth 白名单。"""
    monkeypatch.setenv("AUTH_STORAGE_MODE", "memory")
    _set_valid_mfa_secret(monkeypatch)

    from fastapi.testclient import TestClient

    from app.shared.utils.auth.Safety import jwt_auth

    app = _build_minimal_app()

    with TestClient(app):
        expected_paths = {
            "/api/auth/mfa/login/verify",
            "/api/auth/mfa/login/enroll/start",
            "/api/auth/mfa/login/enroll/confirm",
        }
        for path in expected_paths:
            assert jwt_auth.is_whitelisted(path), (
                f"{path} 必须在 lifespan 阶段被加入精确白名单"
            )


def test_lifespan_mfa_service_singleton_present_after_init(monkeypatch):
    """lifespan 完成时 MfaService.get_instance() 必须返回 lifespan 创建的同一实例。"""
    monkeypatch.setenv("AUTH_STORAGE_MODE", "memory")
    _set_valid_mfa_secret(monkeypatch)

    from fastapi.testclient import TestClient

    app = _build_minimal_app()

    with TestClient(app):
        from app.shared.utils.auth.mfa_service import MfaService

        svc_singleton = MfaService.get_instance()
        state_svc = getattr(app.state, "mfa_service", None)
        assert svc_singleton is state_svc, (
            "MfaService.get_instance() 必须等于 lifespan 注入的实例（单例管理）"
        )
