# -*- coding:utf-8 -*-
"""
测试 app.core.server FastAPI 服务器配置模块

验证 create_app() 返回的实例、 lifespan 事件注册以及中间件注册行为。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.server import create_app


def test_create_app_returns_fastapi_instance():
    """
    测试 create_app() 返回非 None 的 FastAPI 实例。

    Returns:
        None

    异常:
        AssertionError: 返回实例类型不符合预期时抛出
    """
    app = create_app()
    assert app is not None
    assert isinstance(app, FastAPI)


def test_lifespan_context_registered():
    """
    测试 lifespan 事件已注册到 FastAPI 应用路由器。

    Returns:
        None

    异常:
        AssertionError: lifespan_context 不存在时抛出
    """
    app = create_app()
    assert hasattr(app.router, "lifespan_context")
    assert app.router.lifespan_context is not None


def test_cors_middleware_registered():
    """
    测试 CORS 中间件已正确注册到 FastAPI 应用。

    Returns:
        None

    异常:
        AssertionError: CORS 中间件未注册时抛出
    """
    app = create_app()
    middleware_classes = [m.cls for m in app.user_middleware]
    assert CORSMiddleware in middleware_classes
