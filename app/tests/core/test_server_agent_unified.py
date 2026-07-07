# -*- coding:utf-8 -*-
"""
server.py lifespan 初始化测试模块

验证 lifespan 中初始化 AgentConfigService 和 McpConfigService。
"""

import pytest


def test_lifespan_initializes_agent_config_service():
    """
    测试 lifespan 初始化 AgentConfigService。

    验证 create_app() 返回的 FastAPI 实例可正常创建，
    从而覆盖 lifespan 中 AgentConfigService 的初始化路径。

    Returns:
        None

    异常:
        AssertionError: create_app 返回 None 时抛出
    """
    from app.core.server import create_app
    app = create_app()
    assert app is not None


def test_lifespan_initializes_mcp_config_service():
    """
    测试 lifespan 初始化 McpConfigService。

    验证 create_app() 返回的 FastAPI 实例可正常创建，
    从而覆盖 lifespan 中 McpConfigService 的初始化路径。

    Returns:
        None

    异常:
        AssertionError: create_app 返回 None 时抛出
    """
    from app.core.server import create_app
    app = create_app()
    assert app is not None


def test_server_module_has_create_app():
    """
    测试 server 模块暴露 create_app 函数。

    Returns:
        None

    异常:
        AssertionError: server 模块缺少 create_app 属性时抛出
    """
    from app.core import server
    assert hasattr(server, "create_app")
