# -*- coding:utf-8 -*-
"""
统一 Agent Router 测试模块

验证 /api/agent/chat 和 /api/agent/list 路由注册与基本响应。
"""
import pytest


def test_agent_router_importable():
    """测试 agent_router 模块可导入。"""
    from app.routers import agent_router
    assert hasattr(agent_router, "router")


def test_chat_endpoint_registered(client):
    """测试 POST /api/agent/chat 路由已注册。"""
    routes = [r.path for r in client.app.routes]
    assert "/api/agent/chat" in routes


def test_list_endpoint_registered(client):
    """测试 GET /api/agent/list 路由已注册。"""
    routes = [r.path for r in client.app.routes]
    assert "/api/agent/list" in routes


def test_agents_md_endpoint_registered(client):
    """测试 GET /api/agent/{agent_name}/agents-md 路由已注册。"""
    routes = [r.path for r in client.app.routes]
    assert "/api/agent/{agent_name}/agents-md" in routes


def test_list_agents_returns_200(client, admin_headers, monkeypatch):
    """测试 GET /api/agent/list 返回 200。"""
    async def fake_list(self):
        return [{"name": "map_agent", "display_name": "地图智能体"}]

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.list_agents",
        fake_list,
    )

    headers = {**admin_headers, "X-Session-ID": "test-session"}
    response = client.get("/api/agent/list", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["name"] == "map_agent"


def test_get_agents_md_returns_content(client, admin_headers, monkeypatch):
    """测试 GET /api/agent/{name}/agents-md 返回 markdown 内容。"""
    async def fake_get(self, name):
        from app.shared.utils.agent.agent_config_service import UnifiedAgentConfig
        return UnifiedAgentConfig(
            name=name,
            display_name="地图",
            description="",
            system_prompt="# 地图智能体",
            state_class=type("S", (), {}),
            context_class=type("C", (), {}),
            mcp_tags=[],
            enabled_tool_names=[],
            enabled_skill_names=[],
            agents_md_path="x",
        )

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.get_agent_config",
        fake_get,
    )

    headers = {**admin_headers, "X-Session-ID": "test-session"}
    response = client.get("/api/agent/map_agent/agents-md", headers=headers)
    assert response.status_code == 200
    assert response.json()["content"] == "# 地图智能体"
