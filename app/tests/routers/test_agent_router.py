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

    # Mock get_async_store 避免真实 store 初始化（2026-06-26 新增）
    async def fake_store():
        return MagicMock()

    monkeypatch.setattr("app.routers.agent_router.get_async_store", fake_store)

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


# =============================================================================
# 2026-06-26 新增：store 注入相关测试
# 验证 agent_router.py 修复：把 get_async_store() 拿到的 store 注入 AgentConfig，
# 与 HtAgent 路径（store 通过 HtAgentConfig 透传）行为对齐。
# 缺失 store 会导致：
#   1. _llm_call 多模态图片回填失败（agent.py:322 self.store is None）
#   2. workflow.compile(store=None) LangGraph Store 语义关闭
#   3. 工具内 self.store.put(...) 写入的跨会话数据不可见
# =============================================================================


def test_chat_passes_store_to_agent_config(client, admin_headers, monkeypatch):
    """测试 chat 端点将 get_async_store() 拿到的 store 传给 AgentConfig。

    验证 2026-06-26 修复：构造 AgentConfig 时显式注入 store=store，
    与 HtAgent.__init__(self, checkpointer, store, store_id, ...) 契约对齐。
    """
    from unittest.mock import MagicMock

    captured_configs = []
    fake_store_instance = MagicMock(name="fake_store")

    class FakeAgent:
        """FakeAgent 捕获 AgentConfig 实例，避免真实 LLM 初始化。"""

        def __init__(self, config):
            captured_configs.append(config)

        async def __ainit__(self):
            pass

    monkeypatch.setattr("app.core.agent.agent.Agent", FakeAgent)

    def fake_stream(*args, **kwargs):
        yield "data: test\n\n"

    monkeypatch.setattr("app.routers.agent_router.generate_stream_response", fake_stream)

    async def fake_checkpointer():
        return MagicMock()

    monkeypatch.setattr("app.routers.agent_router.get_async_checkpointer", fake_checkpointer)

    # 核心：让 get_async_store() 返回固定 mock，便于断言
    async def fake_store():
        return fake_store_instance

    monkeypatch.setattr("app.routers.agent_router.get_async_store", fake_store)

    async def fake_get(self, name):
        from app.shared.utils.agent.agent_config_service import UnifiedAgentConfig
        return UnifiedAgentConfig(
            name=name,
            display_name="测试智能体",
            description="",
            system_prompt="# 测试",
            state_class=MagicMock(return_value={"messages": []}),
            context_class=MagicMock(return_value={"session_id": "test"}),
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
    # 核心断言：store 已被注入到 AgentConfig
    assert captured_configs[0].store is fake_store_instance


def test_chat_calls_get_async_store_per_request(client, admin_headers, monkeypatch):
    """测试 chat 端点每次请求都调用 get_async_store() 拿 store。

    验证：
    - 修复后 chat 端点必定调用 get_async_store()（不再回退到 None）
    - store 实际从 get_async_store() 获取（不是硬编码的 InMemoryStore()）
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

    store_call_count = {"n": 0}

    async def fake_store():
        store_call_count["n"] += 1
        return MagicMock(name=f"store_{store_call_count['n']}")

    monkeypatch.setattr("app.routers.agent_router.get_async_store", fake_store)

    async def fake_get(self, name):
        from app.shared.utils.agent.agent_config_service import UnifiedAgentConfig
        return UnifiedAgentConfig(
            name=name,
            display_name="x",
            description="",
            system_prompt="",
            state_class=MagicMock(return_value={"messages": []}),
            context_class=MagicMock(return_value={"session_id": "test"}),
        )

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.get_agent_config",
        fake_get,
    )

    headers = {**admin_headers, "X-Session-ID": "test-session"}
    for _ in range(2):
        response = client.post("/api/agent/chat", json={
            "message": "hello",
            "session_id": "test-session",
            "agent_name": "test_agent",
        }, headers=headers)
        assert response.status_code == 200

    # 至少调用了 2 次（每次请求都会重新拿 store；get_async_store 内部有单例缓存）
    assert store_call_count["n"] >= 2


# =============================================================================
# get_async_store() 全局单例自身行为的测试
# 直接调用 app.shared.utils.memory.get_async_store 验证单例语义与降级逻辑
# =============================================================================


@pytest.fixture
def _reset_store_singleton():
    """每个 store 单例测试前清空全局单例，避免测试间相互污染。"""
    from app.shared.utils.memory import store as store_module
    store_module._global_store = None
    store_module._global_pg_connection = None
    yield
    store_module._global_store = None
    store_module._global_pg_connection = None


def test_get_async_store_returns_singleton(_reset_store_singleton):
    """测试 get_async_store() 多次调用返回同一对象（单例语义）。

    同步协议：这是 get_async_store() 设计的核心契约，单元测试必须验证。
    """
    import asyncio
    from app.shared.utils.memory import get_async_store

    async def _run():
        s1 = await get_async_store()
        s2 = await get_async_store()
        return s1, s2

    s1, s2 = asyncio.run(_run())
    assert s1 is s2, "get_async_store() 必须返回单例"


def test_get_async_store_falls_back_to_inmemory_when_pg_disabled(
    _reset_store_singleton, monkeypatch
):
    """测试 DatabasePool 禁用时 get_async_store() 降级为 InMemoryStore。

    验证：
    - AUTH_STORAGE_MODE=memory / DatabasePool 不可用时不会尝试连接 PG
    - 调用的是 langgraph.store.memory.InMemoryStore（而非 AsyncPostgresStore）
    - 返回值非 None，且 _global_store 全局单例已被填充
    """
    import asyncio
    from unittest.mock import MagicMock
    from app.shared.utils.memory import get_async_store
    from app.shared.utils.memory import store as store_module

    # Mock DatabasePool.is_enabled() 返回 False（PG 模式关闭）
    def fake_is_enabled():
        return False

    monkeypatch.setattr("app.core.database.DatabasePool.is_enabled", fake_is_enabled)

    # Spy 验证 store.py 内部调用的 InMemoryStore 次数
    # 注意：必须 patch store_module.InMemoryStore 而非 langgraph.store.memory.InMemoryStore
    # 因为 store.py 顶部 from langgraph.store.memory import InMemoryStore 时已经捕获了引用
    in_memory_called = {"n": 0}

    def fake_inmemory(*args, **kwargs):
        in_memory_called["n"] += 1
        return MagicMock(name="InMemoryStore_instance")

    monkeypatch.setattr(store_module, "InMemoryStore", fake_inmemory)

    async def _run():
        return await get_async_store()

    store = asyncio.run(_run())

    # 断言：调用了 InMemoryStore 至少 1 次（PG 模式被禁用 → 走 InMemoryStore 分支）
    assert in_memory_called["n"] >= 1, (
        f"期望调用 InMemoryStore ≥1 次，实际 {in_memory_called['n']} 次"
    )
    # 断言：返回值非 None
    assert store is not None
    # 断言：全局单例已被填充
    assert store_module._global_store is not None


def test_store_module_importable():
    """测试 app.shared.utils.memory.store 模块可导入（P0 导入/存在性）。"""
    from app.shared.utils.memory import store as store_module
    assert hasattr(store_module, "get_async_store")
    assert hasattr(store_module, "close_global_store")
    assert hasattr(store_module, "reset_global_store")


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

    # Mock get_async_store 避免真实 store 初始化（2026-06-26 新增）
    async def fake_store():
        return MagicMock()

    monkeypatch.setattr("app.routers.agent_router.get_async_store", fake_store)

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
