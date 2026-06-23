# -*- coding:utf-8 -*-
"""
端到端集成测试：/api/agent/chat 完整流程

验证 /api/agent/chat 端点的完整链路：
1. 正常请求返回 SSE 流式响应（含 data: 前缀与 end 事件）
2. 未知 agent 返回 404

测试策略：
- Mock AgentConfigService.get_agent_config 返回伪造的 UnifiedAgentConfig
- Mock get_async_checkpointer 避免真实数据库连接
- Mock Agent 与 AgentConfig 类避免真实 Agent 初始化
- Mock generate_stream_response 返回简单 SSE 流
- Mock session_cache.verify_session 绕过 Session 校验

Date: 2026-06-23
"""

from unittest.mock import AsyncMock, Mock

import pytest


# =============================================================================
# 辅助 Fixture
# =============================================================================


@pytest.fixture
def agent_chat_env(client, monkeypatch):
    """
    初始化 /api/agent/chat 测试所需的环境。

    注入 AgentConfigService 到 app.state，并 Mock session_cache.verify_session
    绕过 /api/agent/ 前缀的 Session 校验。

    Args:
        client: FastAPI TestClient fixture
        monkeypatch: pytest monkeypatch fixture

    Returns:
        TestClient: 已配置好环境的 TestClient 实例
    """
    # 注入 AgentConfigService（lifespan 集成尚未完成，手动注入）
    from app.shared.utils.agent.agent_config_service import AgentConfigService
    from app.shared.utils.agent.agents_md_loader import AgentsMdLoader
    client.app.state.agent_config_service = AgentConfigService(
        db=None, agents_md_loader=AgentsMdLoader(),
    )

    # Mock session_cache.verify_session 绕过 /api/agent/ 路径的 Session 校验
    monkeypatch.setattr(
        "app.shared.utils.Session.SessionCache.session_cache.verify_session",
        AsyncMock(return_value=True),
    )

    return client


# =============================================================================
# 端到端测试
# =============================================================================


def test_agent_chat_returns_sse_stream(agent_chat_env, admin_headers, monkeypatch):
    """
    验证正常请求 /api/agent/chat 返回 SSE 流式响应。

    通过 Mock Agent / AgentConfig / generate_stream_response / get_async_checkpointer，
    确保请求走完完整链路并返回 text/event-stream 格式的 SSE 数据。

    Args:
        agent_chat_env: 已配置环境的 TestClient fixture
        admin_headers: 管理员认证头 fixture
        monkeypatch: pytest monkeypatch fixture

    Returns:
        None

    Raises:
        AssertionError: 响应状态码、content-type 或 SSE 数据格式不符合预期时抛出
    """
    # Mock AgentConfigService.get_agent_config 返回伪造配置
    from app.shared.utils.agent.agent_config_service import UnifiedAgentConfig

    async def fake_get_agent_config(self, agent_name):
        """伪造的 get_agent_config，返回最小化 UnifiedAgentConfig。"""
        return UnifiedAgentConfig(
            name=agent_name,
            display_name="测试智能体",
            description="测试用",
            system_prompt="你是测试智能体",
            state_class=Mock(return_value={"messages": []}),
            context_class=Mock(return_value=Mock()),
            mcp_tags=[],
            enabled_tool_names=[],
            enabled_skill_names=[],
            agents_md_path="mock",
        )

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.get_agent_config",
        fake_get_agent_config,
    )

    # Mock get_async_checkpointer 避免真实数据库连接
    monkeypatch.setattr(
        "app.routers.agent_router.get_async_checkpointer",
        AsyncMock(return_value=Mock()),
    )

    # Mock Agent 类：构造返回 Mock 实例，__ainit__ 为 no-op AsyncMock
    mock_agent_instance = Mock()
    mock_agent_instance.__ainit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.core.agent.agent.Agent",
        Mock(return_value=mock_agent_instance),
    )

    # Mock AgentConfig 类：接受任意参数返回 Mock
    monkeypatch.setattr(
        "app.core.agent.AgentConfig.AgentConfig",
        Mock(return_value=Mock()),
    )

    # Mock generate_stream_response 返回简单 SSE 流
    async def fake_stream(agent, input_state, context, session_id, request):
        """伪造的 SSE 生成器，yield 一条 update 事件和一条 end 事件。"""
        yield 'data: {"type": "update", "data": {}}\n\n'
        yield 'data: {"type": "end"}\n\n'

    monkeypatch.setattr(
        "app.routers.agent_router.generate_stream_response",
        fake_stream,
    )

    # 发送请求
    headers = {**admin_headers, "X-Session-ID": "test-session"}
    response = agent_chat_env.post(
        "/api/agent/chat",
        headers=headers,
        json={
            "message": "你好",
            "agent_name": "map_agent",
            "session_id": "test-session",
        },
    )

    # 验证响应状态码
    assert response.status_code == 200, f"正常请求应返回 200，实际：{response.status_code}"

    # 验证 content-type 为 text/event-stream
    content_type = response.headers.get("content-type", "")
    assert "text/event-stream" in content_type, (
        f"content-type 应为 text/event-stream，实际：{content_type}"
    )

    # 验证响应体包含 SSE data: 前缀
    body = response.text
    assert "data: " in body, "响应体应包含 SSE data: 前缀"

    # 验证 SSE 流以 end 事件结束
    assert '"type": "end"' in body, "SSE 流应包含 end 事件"


def test_agent_chat_unknown_agent_returns_404(agent_chat_env, admin_headers, monkeypatch):
    """
    验证请求未知 agent 时 /api/agent/chat 返回 404。

    Mock AgentConfigService.get_agent_config 抛出 AgentNotFoundError，
    验证路由将其映射为 HTTP 404 响应。

    Args:
        agent_chat_env: 已配置环境的 TestClient fixture
        admin_headers: 管理员认证头 fixture
        monkeypatch: pytest monkeypatch fixture

    Returns:
        None

    Raises:
        AssertionError: 响应状态码不为 404 时抛出
    """
    from app.shared.utils.agent.agent_config_service import AgentNotFoundError

    async def fake_get_agent_config(self, agent_name):
        """伪造的 get_agent_config，抛出 AgentNotFoundError 模拟 agent 不存在。"""
        raise AgentNotFoundError(f"Agent {agent_name} not found or disabled")

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.get_agent_config",
        fake_get_agent_config,
    )

    # 发送请求
    headers = {**admin_headers, "X-Session-ID": "test-session"}
    response = agent_chat_env.post(
        "/api/agent/chat",
        headers=headers,
        json={
            "message": "你好",
            "agent_name": "non_existent_agent",
            "session_id": "test-session",
        },
    )

    # 验证响应状态码为 404
    assert response.status_code == 404, (
        f"未知 agent 应返回 404，实际：{response.status_code}"
    )
