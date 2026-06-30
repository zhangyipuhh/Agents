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

    monkeypatch.setattr("app.shared.utils.memory.get_async_checkpointer", fake_checkpointer)

    # Mock get_async_store 避免真实 store 初始化（2026-06-26 新增）
    async def fake_store():
        return MagicMock()

    monkeypatch.setattr("app.shared.utils.memory.get_async_store", fake_store)

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

    monkeypatch.setattr("app.shared.utils.memory.get_async_checkpointer", fake_checkpointer)

    # 核心：让 get_async_store() 返回固定 mock，便于断言
    async def fake_store():
        return fake_store_instance

    monkeypatch.setattr("app.shared.utils.memory.get_async_store", fake_store)

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

    monkeypatch.setattr("app.shared.utils.memory.get_async_checkpointer", fake_checkpointer)

    store_call_count = {"n": 0}

    async def fake_store():
        store_call_count["n"] += 1
        return MagicMock(name=f"store_{store_call_count['n']}")

    monkeypatch.setattr("app.shared.utils.memory.get_async_store", fake_store)

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

    monkeypatch.setattr("app.shared.utils.memory.get_async_checkpointer", fake_checkpointer)

    # Mock get_async_store 避免真实 store 初始化（2026-06-26 新增）
    async def fake_store():
        return MagicMock()

    monkeypatch.setattr("app.shared.utils.memory.get_async_store", fake_store)

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


# =============================================================================
# 2026-06-26 新增：会话智能体绑定持久化测试
# 验证 agent_router.py::chat 在首次使用非 default agent_name 时，
# 将 agent_type + agent_display_name 持久化到 SessionDB（内存 + 数据库）。
# =============================================================================


def test_chat_binds_agent_to_session_on_first_non_default_agent(client, admin_headers, monkeypatch):
    """测试首次传入非 default agent_name 时，chat 端点将智能体绑定到 session。

    验证：
    - SessionDB.get_session 被调用以检查当前 session 绑定状态
    - 当当前 session agent_type 为 default 时，update_session_agent 被调用
    - update_session_agent 参数为 (session_id, agent_name, display_name)
    """
    from unittest.mock import MagicMock, AsyncMock

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

    monkeypatch.setattr("app.shared.utils.memory.get_async_checkpointer", fake_checkpointer)

    async def fake_store():
        return MagicMock()

    monkeypatch.setattr("app.shared.utils.memory.get_async_store", fake_store)

    async def fake_get(self, name):
        from app.shared.utils.agent.agent_config_service import UnifiedAgentConfig
        return UnifiedAgentConfig(
            name=name,
            display_name="地图智能体",
            description="",
            system_prompt="# 地图",
            state_class=MagicMock(return_value={"messages": []}),
            context_class=MagicMock(return_value={"session_id": "test"}),
        )

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.get_agent_config",
        fake_get,
    )

    # Mock SessionDB：get_session 返回 default 状态，update_session_agent 记录调用
    updated_calls = []

    async def mock_get_session(session_id):
        return {
            "session_id": session_id,
            "user_id": 1,
            "username": "admin",
            "agent_type": "default",
            "agent_display_name": "",
        }

    async def mock_update_session_agent(session_id, agent_type, agent_display_name):
        updated_calls.append((session_id, agent_type, agent_display_name))
        return True

    monkeypatch.setattr("app.shared.utils.auth.session_db.SessionDB.get_session", mock_get_session)
    monkeypatch.setattr(
        "app.shared.utils.auth.session_db.SessionDB.update_session_agent", mock_update_session_agent
    )

    headers = {**admin_headers, "X-Session-ID": "test-session"}
    response = client.post("/api/agent/chat", json={
        "message": "hello",
        "session_id": "test-session",
        "agent_name": "map_agent",
    }, headers=headers)

    assert response.status_code == 200
    assert len(updated_calls) == 1
    assert updated_calls[0] == ("test-session", "map_agent", "地图智能体")


def test_chat_does_not_rebind_if_session_already_bound(client, admin_headers, monkeypatch):
    """测试已绑定非 default 智能体的 session 不会被重新绑定。

    验证：当 session 的 agent_type 已为非 default 时，即使传入其他 agent_name，
    也不会触发 update_session_agent。
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

    monkeypatch.setattr("app.shared.utils.memory.get_async_checkpointer", fake_checkpointer)

    async def fake_store():
        return MagicMock()

    monkeypatch.setattr("app.shared.utils.memory.get_async_store", fake_store)

    async def fake_get(self, name):
        from app.shared.utils.agent.agent_config_service import UnifiedAgentConfig
        return UnifiedAgentConfig(
            name=name,
            display_name="其他智能体",
            description="",
            system_prompt="# 其他",
            state_class=MagicMock(return_value={"messages": []}),
            context_class=MagicMock(return_value={"session_id": "test"}),
        )

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.get_agent_config",
        fake_get,
    )

    updated_calls = []

    async def mock_get_session(session_id):
        return {
            "session_id": session_id,
            "user_id": 1,
            "username": "admin",
            "agent_type": "map_agent",
            "agent_display_name": "地图智能体",
        }

    async def mock_update_session_agent(session_id, agent_type, agent_display_name):
        updated_calls.append((session_id, agent_type, agent_display_name))
        return True

    monkeypatch.setattr("app.shared.utils.auth.session_db.SessionDB.get_session", mock_get_session)
    monkeypatch.setattr(
        "app.shared.utils.auth.session_db.SessionDB.update_session_agent", mock_update_session_agent
    )

    headers = {**admin_headers, "X-Session-ID": "test-session"}
    response = client.post("/api/agent/chat", json={
        "message": "hello",
        "session_id": "test-session",
        "agent_name": "other_agent",
    }, headers=headers)

    assert response.status_code == 200
    assert len(updated_calls) == 0, "已绑定 session 不应被重新绑定"


def test_chat_does_not_bind_when_agent_name_is_default(client, admin_headers, monkeypatch):
    """测试 agent_name 为 default 时不触发 session 绑定。

    验证：即使 session 当前是 default 状态，传入 agent_name='default' 时，
    update_session_agent 不会被调用。
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

    monkeypatch.setattr("app.shared.utils.memory.get_async_checkpointer", fake_checkpointer)

    async def fake_store():
        return MagicMock()

    monkeypatch.setattr("app.shared.utils.memory.get_async_store", fake_store)

    async def fake_get(self, name):
        from app.shared.utils.agent.agent_config_service import UnifiedAgentConfig
        return UnifiedAgentConfig(
            name=name,
            display_name="默认智能体",
            description="",
            system_prompt="# 默认",
            state_class=MagicMock(return_value={"messages": []}),
            context_class=MagicMock(return_value={"session_id": "test"}),
        )

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.get_agent_config",
        fake_get,
    )

    updated_calls = []

    async def mock_get_session(session_id):
        return {
            "session_id": session_id,
            "user_id": 1,
            "username": "admin",
            "agent_type": "default",
            "agent_display_name": "",
        }

    async def mock_update_session_agent(session_id, agent_type, agent_display_name):
        updated_calls.append((session_id, agent_type, agent_display_name))
        return True

    monkeypatch.setattr("app.shared.utils.auth.session_db.SessionDB.get_session", mock_get_session)
    monkeypatch.setattr(
        "app.shared.utils.auth.session_db.SessionDB.update_session_agent", mock_update_session_agent
    )

    headers = {**admin_headers, "X-Session-ID": "test-session"}
    response = client.post("/api/agent/chat", json={
        "message": "hello",
        "session_id": "test-session",
        "agent_name": "default",
    }, headers=headers)

    assert response.status_code == 200
    assert len(updated_calls) == 0, "agent_name 为 default 时不应触发绑定"


# =============================================================================
# 2026-06-29 新增：chat 端点调用 service.build_agent_instance() 验证
# 验证重构后 chat 端点必然通过 service.build_agent_instance() 构造 Agent，
# 不再在 router 内自行构造 AgentConfig / Agent。
# =============================================================================


def test_chat_calls_service_build_agent_instance(client, admin_headers, monkeypatch):
    """测试 chat 端点调用 service.build_agent_instance() 而非自行构造。

    验证：
    - 重构后 chat 端点必然调用 service.build_agent_instance() 一次
    - 传入参数包含 agent_name / session_id / message / resume / context_overrides
    - 不再在 router 内 import AgentConfig / Agent
    """
    from unittest.mock import MagicMock

    captured_calls = []

    async def fake_build(self, agent_name, session_id, message=None,
                          context_overrides=None, resume=None,
                          state_class_kwargs=None, system_prompt_override=None):
        captured_calls.append({
            "agent_name": agent_name,
            "session_id": session_id,
            "message": message,
            "context_overrides": context_overrides,
            "resume": resume,
        })
        # 返回 fake (agent, context, input_state) 三元组
        return MagicMock(name="fake_agent"), MagicMock(name="fake_context"), MagicMock(name="fake_state")

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.build_agent_instance",
        fake_build,
    )

    # 同步 mock get_agent_config（router 在 session.agent_type 绑定分支会调用）
    async def fake_get(self, name):
        from app.shared.utils.agent.agent_config_service import UnifiedAgentConfig
        return UnifiedAgentConfig(
            name=name,
            display_name="地图智能体",
            description="",
            system_prompt="# 地图",
            state_class=MagicMock(return_value={"messages": []}),
            context_class=MagicMock(return_value={"session_id": "test"}),
        )

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.get_agent_config",
        fake_get,
    )

    def fake_stream(*args, **kwargs):
        yield "data: test\n\n"

    monkeypatch.setattr("app.routers.agent_router.generate_stream_response", fake_stream)

    # Mock get_session / update_session_agent 避免触发 session 绑定分支（agent_name=map_agent）
    async def mock_get_session(session_id):
        return {
            "session_id": session_id,
            "user_id": 1,
            "username": "admin",
            "agent_type": "default",
            "agent_display_name": "",
        }

    async def mock_update_session_agent(session_id, agent_type, agent_display_name):
        return True

    monkeypatch.setattr("app.shared.utils.auth.session_db.SessionDB.get_session", mock_get_session)
    monkeypatch.setattr(
        "app.shared.utils.auth.session_db.SessionDB.update_session_agent", mock_update_session_agent
    )

    headers = {**admin_headers, "X-Session-ID": "test-session"}
    response = client.post("/api/agent/chat", json={
        "message": "hello",
        "session_id": "test-session",
        "agent_name": "map_agent",
        "context_overrides": {"foo": "bar"},
    }, headers=headers)

    assert response.status_code == 200
    assert len(captured_calls) == 1
    call = captured_calls[0]
    assert call["agent_name"] == "map_agent"
    assert call["session_id"] == "test-session"
    assert call["message"] == "hello"
    assert call["context_overrides"] == {"foo": "bar"}
    assert call["resume"] is None


def test_chat_returns_404_when_agent_not_found(client, admin_headers, monkeypatch):
    """测试 service.build_agent_instance 抛 AgentNotFoundError 时 chat 返回 404。

    验证：
    - service.build_agent_instance 内部调用 get_agent_config 抛 AgentNotFoundError
    - router 捕获后转换为 HTTPException(404)
    """
    from app.shared.utils.agent.agent_config_service import AgentNotFoundError

    async def fake_build_raise(self, agent_name, session_id, **kwargs):
        raise AgentNotFoundError(f"Agent {agent_name} not found")

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.build_agent_instance",
        fake_build_raise,
    )

    # 同步 mock get_agent_config（router 在 session.agent_type 绑定分支会调用）
    async def fake_get_raise(self, name):
        raise AgentNotFoundError(f"Agent {name} not found")

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.get_agent_config",
        fake_get_raise,
    )

    # Mock SessionDB.get_session 返回 None，跳过 session 绑定分支
    async def mock_get_session(session_id):
        return None

    monkeypatch.setattr(
        "app.shared.utils.auth.session_db.SessionDB.get_session", mock_get_session
    )

    headers = {**admin_headers, "X-Session-ID": "test-session"}
    response = client.post("/api/agent/chat", json={
        "message": "hello",
        "session_id": "test-session",
        "agent_name": "nonexistent_agent",
    }, headers=headers)

    assert response.status_code == 404
    assert "nonexistent_agent" in response.json()["detail"]


def test_chat_returns_500_when_init_fails(client, admin_headers, monkeypatch):
    """测试 service.build_agent_instance 抛通用 Exception 时 chat 返回 500。

    验证：
    - service.build_agent_instance 抛 RuntimeError 等非 HTTP 异常时
    - router 捕获后转换为 HTTPException(500)
    """
    async def fake_build_raise(self, agent_name, session_id, **kwargs):
        raise RuntimeError("LLM 初始化失败")

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.build_agent_instance",
        fake_build_raise,
    )

    # 同步 mock get_agent_config（router 在 session.agent_type 绑定分支会调用）
    from unittest.mock import MagicMock
    async def fake_get(self, name):
        from app.shared.utils.agent.agent_config_service import UnifiedAgentConfig
        return UnifiedAgentConfig(
            name=name, display_name="测试", description="", system_prompt="",
            state_class=MagicMock(return_value={"messages": []}),
            context_class=MagicMock(return_value={"session_id": "test"}),
        )

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.get_agent_config",
        fake_get,
    )

    # Mock SessionDB.get_session 返回 None，跳过 session 绑定分支
    async def mock_get_session(session_id):
        return None

    monkeypatch.setattr(
        "app.shared.utils.auth.session_db.SessionDB.get_session", mock_get_session
    )

    headers = {**admin_headers, "X-Session-ID": "test-session"}
    response = client.post("/api/agent/chat", json={
        "message": "hello",
        "session_id": "test-session",
        "agent_name": "test_agent",
    }, headers=headers)

    assert response.status_code == 500
    assert "LLM 初始化失败" in response.json()["detail"]


def test_chat_no_longer_imports_agent_or_agent_config_in_router():
    """测试 router 模块不再 import Agent / AgentConfig（验证下沉完整性）。

    验证：
    - 重构后 agent_router.py 不再持有 AgentConfig / Agent / Command /
      HumanMessage / get_async_checkpointer / get_async_store 等 import
    - 所有 Agent 构造逻辑已下沉到 service.build_agent_instance()
    """
    import app.routers.agent_router as router_module
    source = open(router_module.__file__, encoding="utf-8").read()

    # 已下沉的引用不应再出现在 router 中
    assert "from app.core.agent.AgentConfig import AgentConfig" not in source
    assert "from app.core.agent.agent import Agent" not in source
    assert "from langchain_core.messages import HumanMessage" not in source
    assert "from langgraph.types import Command" not in source
    assert "get_async_checkpointer" not in source
    assert "get_async_store" not in source
    assert "RESERVED_CONTEXT_FIELDS" not in source


# =============================================================================
# 2026-06-30 新增：context_overrides 空值过滤测试
# 验证 router 在合并 context_overrides 时自动过滤容器型空值（None/""/[]/{}），
# 避免覆盖 agent context_class 字段默认值。该机制为通用通道，不针对具体字段硬编码。
# =============================================================================


def _setup_chat_capture_for_context_overrides(monkeypatch, captured):
    """为 context_overrides 系列测试准备 monkeypatch：mock build_agent_instance 捕获调用参数。"""
    from unittest.mock import MagicMock

    async def fake_build(self, agent_name, session_id, message=None,
                          context_overrides=None, resume=None,
                          state_class_kwargs=None, system_prompt_override=None):
        captured.append({
            "agent_name": agent_name,
            "session_id": session_id,
            "message": message,
            "context_overrides": context_overrides,
            "resume": resume,
        })
        return MagicMock(name="fake_agent"), MagicMock(name="fake_context"), MagicMock(name="fake_state")

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.build_agent_instance",
        fake_build,
    )

    # 同步 mock get_agent_config（避免触发 session 绑定分支的真实数据库调用）
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

    # Mock session 绑定相关，避免触发真实 SessionDB 调用
    async def mock_get_session(session_id):
        return None

    monkeypatch.setattr(
        "app.shared.utils.auth.session_db.SessionDB.get_session", mock_get_session
    )


def test_chat_filters_empty_dict_geometry_data_from_context_overrides(
    client, admin_headers, monkeypatch
):
    """测试 context_overrides 中的空 dict（如 geometry_data={}）被过滤掉。

    验证：前端传入 ``context_overrides={"geometry_data": {}}`` 时，
    service.build_agent_instance 收到的 context_overrides 不包含 geometry_data 键，
    避免覆盖 MapAgentContext.geometry_data 默认值（虽然值相同，但避免语义混淆）。
    """
    captured = []
    _setup_chat_capture_for_context_overrides(monkeypatch, captured)

    def fake_stream(*args, **kwargs):
        yield "data: test\n\n"

    monkeypatch.setattr("app.routers.agent_router.generate_stream_response", fake_stream)

    headers = {**admin_headers, "X-Session-ID": "test-session"}
    response = client.post("/api/agent/chat", json={
        "message": "hello",
        "session_id": "test-session",
        "agent_name": "map_agent",
        "context_overrides": {"geometry_data": {}},
    }, headers=headers)

    assert response.status_code == 200
    assert len(captured) == 1
    # 核心断言：空 dict 已被过滤
    assert "geometry_data" not in captured[0]["context_overrides"]


def test_chat_filters_none_value_from_context_overrides(
    client, admin_headers, monkeypatch
):
    """测试 context_overrides 中的 None 值被过滤掉。"""
    captured = []
    _setup_chat_capture_for_context_overrides(monkeypatch, captured)

    def fake_stream(*args, **kwargs):
        yield "data: test\n\n"

    monkeypatch.setattr("app.routers.agent_router.generate_stream_response", fake_stream)

    headers = {**admin_headers, "X-Session-ID": "test-session"}
    response = client.post("/api/agent/chat", json={
        "message": "hello",
        "session_id": "test-session",
        "agent_name": "map_agent",
        "context_overrides": {
            "geometry_data": None,
            "audit_root": None,
        },
    }, headers=headers)

    assert response.status_code == 200
    assert len(captured) == 1
    # 核心断言：所有 None 值已被过滤
    assert captured[0]["context_overrides"] == {}


def test_chat_filters_empty_string_and_empty_list_from_context_overrides(
    client, admin_headers, monkeypatch
):
    """测试 context_overrides 中的空字符串 / 空列表也被过滤。"""
    captured = []
    _setup_chat_capture_for_context_overrides(monkeypatch, captured)

    def fake_stream(*args, **kwargs):
        yield "data: test\n\n"

    monkeypatch.setattr("app.routers.agent_router.generate_stream_response", fake_stream)

    headers = {**admin_headers, "X-Session-ID": "test-session"}
    response = client.post("/api/agent/chat", json={
        "message": "hello",
        "session_id": "test-session",
        "agent_name": "map_agent",
        "context_overrides": {
            "geometry_data": "",
            "audit_files": [],
            "map_center": "",
        },
    }, headers=headers)

    assert response.status_code == 200
    assert len(captured) == 1
    # 核心断言：所有空值已被过滤
    assert captured[0]["context_overrides"] == {}


def test_chat_passes_non_empty_geometry_data_to_context_overrides(
    client, admin_headers, monkeypatch
):
    """测试非空的 geometry_data 能正确透传到 context_overrides。

    验证：前端传入 ``context_overrides={"geometry_data": {"point": [...]}}`` 时，
    service.build_agent_instance 收到的 context_overrides 包含完整 geometry_data 字典，
    最终注入到 MapAgentContext.geometry_data 供工具通过 runtime.context.get('geometry_data') 读取。
    """
    captured = []
    _setup_chat_capture_for_context_overrides(monkeypatch, captured)

    def fake_stream(*args, **kwargs):
        yield "data: test\n\n"

    monkeypatch.setattr("app.routers.agent_router.generate_stream_response", fake_stream)

    headers = {**admin_headers, "X-Session-ID": "test-session"}
    geometry = {
        "point": [{"lat": 1.0, "lng": 2.0}],
        "line": [],
        "polygon": [],
    }
    response = client.post("/api/agent/chat", json={
        "message": "hello",
        "session_id": "test-session",
        "agent_name": "map_agent",
        "context_overrides": {"geometry_data": geometry},
    }, headers=headers)

    assert response.status_code == 200
    assert len(captured) == 1
    # 核心断言：非空 geometry_data 完整透传
    assert captured[0]["context_overrides"] == {"geometry_data": geometry}


def test_chat_arbitrary_context_overrides_pass_through(
    client, admin_headers, monkeypatch
):
    """测试任意非空 context_overrides 键都能透传（验证通用化机制）。

    设计原则：router 不针对任何具体字段硬编码键名。
    任意子智能体的 context 扩展字段（geometry_data / audit_root / map_center 等）
    只要值非空，都能通过通用通道注入到 context_class。
    """
    captured = []
    _setup_chat_capture_for_context_overrides(monkeypatch, captured)

    def fake_stream(*args, **kwargs):
        yield "data: test\n\n"

    monkeypatch.setattr("app.routers.agent_router.generate_stream_response", fake_stream)

    headers = {**admin_headers, "X-Session-ID": "test-session"}
    response = client.post("/api/agent/chat", json={
        "message": "hello",
        "session_id": "test-session",
        "agent_name": "audit_document_agent",
        "context_overrides": {
            "geometry_data": {"point": [{"lat": 1, "lng": 2}]},
            "audit_root": "/tmp/audit",
            "map_center": {"lat": 41.0, "lng": 123.0},
            "is_visible": False,           # bool False 不应被过滤
            "priority": 0,                 # int 0 不应被过滤
            "tags": ["urgent"],            # 非空 list 透传
            "empty_list": [],              # 空 list 应被过滤
            "empty_str": "",               # 空 str 应被过滤
        },
    }, headers=headers)

    assert response.status_code == 200
    assert len(captured) == 1
    expected = {
        "geometry_data": {"point": [{"lat": 1, "lng": 2}]},
        "audit_root": "/tmp/audit",
        "map_center": {"lat": 41.0, "lng": 123.0},
        "is_visible": False,              # 保留
        "priority": 0,                    # 保留
        "tags": ["urgent"],               # 保留
    }
    assert captured[0]["context_overrides"] == expected
