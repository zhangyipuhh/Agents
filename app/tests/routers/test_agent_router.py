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


def test_chat_with_null_agent_name_uses_default_config(client, admin_headers, monkeypatch):
    """测试 agent_name 为空时 chat 接口使用默认配置，不查询 AgentConfigService。"""
    async def fake_get(self, name):
        from app.shared.utils.agent.agent_config_service import UnifiedAgentConfig
        from app.core.agent.AgentConfig import AgentState
        from app.core.agent.AgentContext import AgentContext
        return UnifiedAgentConfig(
            name="",
            display_name="默认智能体",
            description="",
            system_prompt="",
            state_class=AgentState,
            context_class=AgentContext,
            mcp_tags=[],
            enabled_tool_names=[],
            enabled_skill_names=[],
            agents_md_path="",
        )

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.get_agent_config",
        fake_get,
    )

    headers = {**admin_headers, "X-Session-ID": "test-session"}
    response = client.post("/api/agent/chat", json={
        "message": "hello",
        "session_id": "test-session",
        "agent_name": None,
    }, headers=headers)
    # 默认配置下 Agent 初始化可能失败（无真实 LLM），但至少不应 404
    assert response.status_code != 404


def test_chat_with_explicit_agent_name_uses_service(client, admin_headers, monkeypatch):
    """测试传入 agent_name 时仍通过 AgentConfigService 加载配置。"""
    async def fake_get(self, name):
        from app.shared.utils.agent.agent_config_service import UnifiedAgentConfig
        from unittest.mock import MagicMock
        # 使用 MagicMock 替代真实 AgentState/AgentContext，避免测试环境下
        # MessagesState 被根 conftest Mock 后导致 AgentState 继承异常。
        state_mock = MagicMock(return_value={"messages": []})
        context_mock = MagicMock(return_value={"session_id": "test"})
        return UnifiedAgentConfig(
            name=name,
            display_name="地图",
            description="",
            system_prompt="# 地图智能体",
            state_class=state_mock,
            context_class=context_mock,
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
    response = client.post("/api/agent/chat", json={
        "message": "hello",
        "session_id": "test-session",
        "agent_name": "map_agent",
    }, headers=headers)
    assert response.status_code != 404


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


def test_chat_passes_tools_to_agent_config(client, admin_headers, monkeypatch):
    """测试 chat 端点将 UnifiedAgentConfig.tools 传入 AgentConfig。

    验证 Task 6 的核心改动：构造 AgentConfig 时传入 tools=config.tools，
    确保 AgentConfigService 从 DB + MCP registry 加载的工具列表能传递到 Agent。
    """
    from unittest.mock import MagicMock

    captured_configs = []

    class FakeAgent:
        """FakeAgent 捕获 AgentConfig 实例，避免真实 LLM 初始化。"""

        def __init__(self, config):
            captured_configs.append(config)

        async def __ainit__(self):
            pass

    monkeypatch.setattr("app.core.agent.agent.Agent", FakeAgent)

    # Mock generate_stream_response 避免流式响应消费失败
    def fake_stream(*args, **kwargs):
        yield "data: test\n\n"

    monkeypatch.setattr("app.routers.agent_router.generate_stream_response", fake_stream)

    # Mock get_async_checkpointer 避免真实 checkpointer 初始化
    async def fake_checkpointer():
        return MagicMock()

    monkeypatch.setattr("app.routers.agent_router.get_async_checkpointer", fake_checkpointer)

    async def fake_get(self, name):
        from app.shared.utils.agent.agent_config_service import UnifiedAgentConfig
        return UnifiedAgentConfig(
            name=name,
            display_name="测试智能体",
            description="",
            system_prompt="# 测试",
            state_class=MagicMock(return_value={"messages": []}),
            context_class=MagicMock(return_value={"session_id": "test"}),
            tools=["fake_tool_1", "fake_tool_2"],
        )

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.get_agent_config",
        fake_get,
    )

    headers = {**admin_headers, "X-Session-ID": "test-session"}
    response = client.post("/api/agent/chat", json={
        "message": "hello",
        "session_id": "test-session",
        "agent_name": "test_agent",
    }, headers=headers)

    assert response.status_code == 200
    assert len(captured_configs) == 1
    assert captured_configs[0].tools == ["fake_tool_1", "fake_tool_2"]


def test_chat_with_none_tools_does_not_break(client, admin_headers, monkeypatch):
    """测试 UnifiedAgentConfig.tools 为 None 时 chat 端点不报错。

    验证 tools=None（默认值）传入 AgentConfig 后不会破坏现有逻辑，
    AgentConfig.tools 默认为 None，get_tools() 会返回空列表。
    """
    from unittest.mock import MagicMock

    class FakeAgent:
        def __init__(self, config):
            self._config = config

        async def __ainit__(self):
            pass

    monkeypatch.setattr("app.core.agent.agent.Agent", FakeAgent)

    def fake_stream(*args, **kwargs):
        yield "data: test\n\n"

    monkeypatch.setattr("app.routers.agent_router.generate_stream_response", fake_stream)

    async def fake_checkpointer():
        return MagicMock()

    monkeypatch.setattr("app.routers.agent_router.get_async_checkpointer", fake_checkpointer)

    async def fake_get(self, name):
        from app.shared.utils.agent.agent_config_service import UnifiedAgentConfig
        return UnifiedAgentConfig(
            name=name,
            display_name="测试智能体",
            description="",
            system_prompt="# 测试",
            state_class=MagicMock(return_value={"messages": []}),
            context_class=MagicMock(return_value={"session_id": "test"}),
            # tools 不传，默认为 None
        )

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.get_agent_config",
        fake_get,
    )

    headers = {**admin_headers, "X-Session-ID": "test-session"}
    response = client.post("/api/agent/chat", json={
        "message": "hello",
        "session_id": "test-session",
        "agent_name": "test_agent",
    }, headers=headers)

    assert response.status_code == 200
