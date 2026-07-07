# -*- coding:utf-8 -*-
"""
主应用路由注册验证测试模块

验证 mcp_admin_router 和 agent_router 已在 main.py 中注册，
且旧 /api/map/chat 路由已移除（被 /api/agent/chat 替换）。
"""


def test_mcp_admin_router_registered(client):
    """
    测试 /api/admin/mcp 前缀路由已注册。

    Args:
        client: FastAPI TestClient fixture，提供 app.routes 访问能力。

    Returns:
        None

    Raises:
        AssertionError: 当未找到任何 /api/admin/mcp 前缀路由时触发。
    """
    routes = [r.path for r in client.app.routes]
    mcp_routes = [r for r in routes if r.startswith("/api/admin/mcp")]
    assert len(mcp_routes) > 0, "未找到 /api/admin/mcp 路由"


def test_agent_router_registered(client):
    """
    测试 /api/agent 前缀路由已注册。

    Args:
        client: FastAPI TestClient fixture，提供 app.routes 访问能力。

    Returns:
        None

    Raises:
        AssertionError: 当未找到任何 /api/agent 前缀路由时触发。
    """
    routes = [r.path for r in client.app.routes]
    agent_routes = [r for r in routes if r.startswith("/api/agent")]
    assert len(agent_routes) > 0, "未找到 /api/agent 路由"


def test_old_map_chat_route_removed(client):
    """
    测试旧 /api/map/chat 路由已移除（决策 4：直接替换不留兼容）。

    Args:
        client: FastAPI TestClient fixture，提供 app.routes 访问能力。

    Returns:
        None

    Raises:
        AssertionError: 当 /api/map/chat 路由仍存在时触发。
    """
    routes = [r.path for r in client.app.routes]
    assert "/api/map/chat" not in routes, "旧 /api/map/chat 路由仍存在，应已替换为 /api/agent/chat"
