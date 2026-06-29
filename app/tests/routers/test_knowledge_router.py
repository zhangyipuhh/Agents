# -*- coding:utf-8 -*-
"""
Knowledge Router 测试模块

验证 knowledge_router 中 AgentConfig 构造时正确传入 enabled_skill_names，
确保聊天时不会加载未绑定的 skill。
"""

from unittest.mock import MagicMock, AsyncMock


def test_knowledge_chat_passes_enabled_skill_names(client, admin_headers, monkeypatch):
    """测试 /api/map/knowledge-chat 构造 AgentConfig 时传入 enabled_skill_names。

    验证 knowledge_router 在直接构造 AgentConfig 时，不会遗漏
    enabled_skill_names 字段（修复前该字段为 None，导致 SkillsAwarePrompt
    回退到加载全部 skill）。
    """
    captured_configs = []

    class FakeAgent:
        def __init__(self, config):
            captured_configs.append(config)

        async def __ainit__(self):
            pass

    # 由于 knowledge_router.py 中 Agent 的导入在函数内部（from app.core.agent.agent import Agent），
    # monkeypatch 模块属性后，内部导入会获取到 FakeAgent
    monkeypatch.setattr("app.core.agent.agent.Agent", FakeAgent)

    # mock service.get_agent_config 返回含 enabled_skill_names 的配置
    async def fake_get(self, name):
        from app.shared.utils.agent.agent_config_service import UnifiedAgentConfig
        return UnifiedAgentConfig(
            name="map_agent",
            display_name="地图",
            description="",
            system_prompt="# test",
            state_class=MagicMock(return_value={"messages": []}),
            context_class=MagicMock(return_value={"session_id": "test"}),
            enabled_skill_names=["hgsc"],
            agents_md_path="x",
        )

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.get_agent_config",
        fake_get,
    )

    # mock checkpointer
    async def fake_cp():
        return MagicMock()

    monkeypatch.setattr(
        "app.shared.utils.memory.get_async_checkpointer",
        fake_cp,
    )

    # mock stream_with_concurrency 为 async generator（必须有 yield）
    async def fake_stream_with_concurrency(request, dep, generator):
        yield b"data: test\n\n"

    monkeypatch.setattr(
        "app.core.concurrency.stream_with_concurrency",
        fake_stream_with_concurrency,
    )

    # mock generate_stream_response 为 async generator
    async def fake_generate_stream(*args, **kwargs):
        yield b"data: test\n\n"

    monkeypatch.setattr(
        "app.routers._stream_helper.generate_stream_response",
        fake_generate_stream,
    )

    headers = {**admin_headers, "X-Session-ID": "test-session"}
    response = client.post("/api/map/knowledge-chat", json={
        "message": "hello",
        "session_id": "test-session",
    }, headers=headers)

    # 只要成功触发到 Agent 构造即可（不关心最终 HTTP 状态码，
    # 因为 StreamingResponse 在测试 client 中的行为受多种 mock 影响）
    assert len(captured_configs) >= 1
    agent_config = captured_configs[-1]
    assert getattr(agent_config, "enabled_skill_names", None) is not None
    assert agent_config.enabled_skill_names == ["hgsc"]
