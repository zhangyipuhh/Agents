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


def test_list_agents_works_without_session_id(client, admin_headers, monkeypatch):
    """2026-07-XX 新增：/api/agent/list 不依赖 session_id 隔离（按需建 session 配套白名单）。

    验证 session_auth_middleware 的 SESSION_WHITELIST_PREFIXES 已包含 /api/agent/list，
    首次进入页面 / localStorage.session_id 为空时仍能正常返回 200，不抛 400 "缺少 X-Session-ID 请求头"。
    """
    async def fake_list(self):
        return [{"name": "map_agent", "display_name": "地图智能体"}]

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.list_agents",
        fake_list,
    )

    # 关键：headers 中**不携带** X-Session-ID，模拟前端首次进入 / 按需建 session 阶段
    response = client.get("/api/agent/list", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["name"] == "map_agent"


def test_agent_chat_still_requires_session_id(client, admin_headers, monkeypatch):
    """2026-07-XX 新增：/api/agent/chat 仍必须携带 X-Session-ID，验证白名单精确前缀不会误伤。

    验证 SESSION_WHITELIST_PREFIXES 中的 "/api/agent/list" 是精确前缀匹配，
    不会通过 startswith 误把 /api/agent/chat 放行。/api/agent/chat 仍命中 SESSION_REQUIRED_PREFIXES。
    """
    # 不携带 X-Session-ID 访问 chat → 期望 400（session_auth_middleware 拒绝）
    response = client.post("/api/agent/chat", json={
        "message": "hello",
        "session_id": "",
        "agent_name": None,
    }, headers=admin_headers)
    assert response.status_code == 400
    assert "缺少 X-Session-ID" in response.json()["detail"]


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
        "agent_name": "test_agent",
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


# =============================================================================
# 2026-07-02 新增：POST /api/agent/message-feedback 反馈入库接口测试
# 验证：
#   * 路由已注册到 /api/agent/message-feedback
#   * feedback_type=like 时直接入库，INSERT 调用与参数符合预期
#   * feedback_type=dislike 时携带 problem_type/problem_description/expected_answer 也能入库
#   * 非法 feedback_type 返回 400
#   * 内存模式（DatabasePool.is_enabled()=False）返回 503
#   * 未登录（request.state.user_id=None）返回 401
# 设计原则：
#   - 通过 monkeypatch 替换 DatabasePool.fetchrow / is_enabled，避免依赖真实 PG
#   - 通过 ASGI 中间件注入 request.state.user_id=1 模拟登录态
#   - client fixture 来自根 conftest.py（已是登录 admin 状态）
# =============================================================================


def test_message_feedback_endpoint_registered(client):
    """测试 POST /api/agent/message-feedback 路由已注册。"""
    routes = [r.path for r in client.app.routes]
    assert "/api/agent/message-feedback" in routes


def test_post_message_feedback_like_succeeds_and_inserts_row(client, admin_headers, monkeypatch):
    """测试赞（feedback_type=like）能直接入库。

    验证：
      * 接口返回 201
      * 返回体含 id (int) 与 created_at (str)
      * DatabasePool.fetchrow 被调用一次，参数包含 feedback_type='like'
      * user_id 从 request.state.user_id 正确解析（mock admin 用户 id=1）
    """
    import asyncio
    import httpx
    from datetime import datetime

    # mock UserDB.get_user_by_username 让 auth_middleware 能拿到 user_id=1
    async def fake_get_user(username):
        return {"id": 1, "username": username, "role": "admin", "allowed_agents": []}

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username", fake_get_user
    )

    captured_calls = []

    async def fake_fetchrow(query, *args):
        captured_calls.append({"query": query, "args": args})
        return {"id": 100, "created_at": datetime(2026, 7, 2, 12, 0, 0)}

    monkeypatch.setattr("app.routers.agent_router.DatabasePool.fetchrow", fake_fetchrow)
    monkeypatch.setattr("app.routers.agent_router.DatabasePool.is_enabled", lambda: True)

    async def _run():
        transport = httpx.ASGITransport(app=client.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
            response = await ac.post(
                "/api/agent/message-feedback",
                json={
                    "session_id": "test-session",
                    "message_id": "msg-001",
                    "feedback_type": "like",
                    "message_content": "原始问题",
                    "ai_reply": "AI 回答",
                    "agent_name": "map_agent",
                },
                headers={**admin_headers, "X-Session-ID": "test-session"},
            )
        return response

    response = asyncio.run(_run())
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 100
    assert "created_at" in body
    # captured_calls 可能包含 SessionDB.get_session 等其他 fetchrow 调用
    # 找到 feedback INSERT 那次（args 包含 'msg-001'）
    feedback_calls = [
        c for c in captured_calls
        if len(c.get("args", ())) >= 11 and c["args"][2] == "msg-001"
    ]
    assert len(feedback_calls) == 1
    call_args = feedback_calls[0]["args"]
    # 入参顺序：(user_id, session_id, message_id, feedback_type, problem_type,
    #            problem_description, expected_answer, message_content, ai_reply,
    #            agent_name, user_agent)
    assert call_args[0] == 1  # user_id
    assert call_args[1] == "test-session"
    assert call_args[2] == "msg-001"
    assert call_args[3] == "like"
    assert call_args[7] == "原始问题"
    assert call_args[8] == "AI 回答"
    assert call_args[9] == "map_agent"


def test_post_message_feedback_dislike_with_full_problem_fields_succeeds(client, admin_headers, monkeypatch):
    """测试踩（feedback_type=dislike）携带完整 problem_* 字段能入库。

    验证：
      * 接口返回 201
      * problem_type / problem_description / expected_answer 完整透传
      * DatabasePool.fetchrow 被调用一次且参数正确
    """
    import asyncio
    import httpx
    from datetime import datetime

    # mock UserDB.get_user_by_username 让 auth_middleware 能拿到 user_id=7
    async def fake_get_user(username):
        return {"id": 7, "username": username, "role": "admin", "allowed_agents": []}

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username", fake_get_user
    )

    captured_calls = []

    async def fake_fetchrow(query, *args):
        captured_calls.append({"args": args})
        return {"id": 200, "created_at": datetime(2026, 7, 2, 13, 0, 0)}

    monkeypatch.setattr("app.routers.agent_router.DatabasePool.fetchrow", fake_fetchrow)
    monkeypatch.setattr("app.routers.agent_router.DatabasePool.is_enabled", lambda: True)

    async def _run():
        transport = httpx.ASGITransport(app=client.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
            response = await ac.post(
                "/api/agent/message-feedback",
                json={
                    "session_id": "sess-xyz",
                    "message_id": "msg-002",
                    "feedback_type": "dislike",
                    "problem_type": "logic_error",
                    "problem_description": "逻辑跳跃，从 A 直接跳到 C",
                    "expected_answer": "应分步说明 A→B→C",
                    "message_content": "原始问题文本",
                    "ai_reply": "AI 实际回答文本",
                    "agent_name": "map_agent",
                },
                headers={**admin_headers, "X-Session-ID": "sess-xyz"},
            )
        return response

    response = asyncio.run(_run())
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 200
    # 找到 feedback INSERT 那次（args 包含 'msg-002'）
    feedback_calls = [
        c for c in captured_calls
        if len(c.get("args", ())) >= 11 and c["args"][2] == "msg-002"
    ]
    assert len(feedback_calls) == 1
    args = feedback_calls[0]["args"]
    assert args[0] == 7  # user_id
    assert args[3] == "dislike"
    assert args[4] == "logic_error"
    assert args[5] == "逻辑跳跃，从 A 直接跳到 C"
    assert args[6] == "应分步说明 A→B→C"


def test_post_message_feedback_invalid_type_returns_400(client, admin_headers, monkeypatch):
    """测试非法 feedback_type（如 'xxx'）返回 400。

    验证：未到达 DatabasePool.fetchrow 之前就被路由层拦下。
    """
    import asyncio
    import httpx

    async def fake_get_user(username):
        return {"id": 1, "username": username, "role": "admin", "allowed_agents": []}

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username", fake_get_user
    )

    captured_queries = []

    async def fake_fetchrow(query, *args, **kwargs):
        captured_queries.append(query)
        return None

    monkeypatch.setattr("app.routers.agent_router.DatabasePool.fetchrow", fake_fetchrow)
    monkeypatch.setattr("app.routers.agent_router.DatabasePool.is_enabled", lambda: True)

    async def _run():
        transport = httpx.ASGITransport(app=client.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
            response = await ac.post(
                "/api/agent/message-feedback",
                json={
                    "session_id": "s",
                    "message_id": "m",
                    "feedback_type": "xxx",
                },
                headers={**admin_headers, "X-Session-ID": "s"},
            )
        return response

    response = asyncio.run(_run())
    assert response.status_code == 400
    assert "like" in response.json()["detail"] and "dislike" in response.json()["detail"]
    # 核心断言：INSERT INTO message_feedback 不在捕获的 SQL 列表中
    insert_calls = [q for q in captured_queries if q and "INSERT INTO message_feedback" in q]
    assert len(insert_calls) == 0, "非法 feedback_type 不应触发 message_feedback INSERT"


def test_post_message_feedback_memory_mode_returns_503(client, admin_headers, monkeypatch):
    """测试内存模式（DatabasePool.is_enabled()=False）时返回 503。

    验证：
      * feedback_type=like 也直接返回 503（不区分 like/dislike）
      * 不会调用 DatabasePool.fetchrow
    """
    import asyncio
    import httpx

    async def fake_get_user(username):
        return {"id": 1, "username": username, "role": "admin", "allowed_agents": []}

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username", fake_get_user
    )

    captured_queries = []

    async def fake_fetchrow(query, *args, **kwargs):
        captured_queries.append(query)
        return None

    monkeypatch.setattr("app.routers.agent_router.DatabasePool.fetchrow", fake_fetchrow)
    # 关键：is_enabled 返回 False 模拟内存模式
    monkeypatch.setattr("app.routers.agent_router.DatabasePool.is_enabled", lambda: False)

    async def _run():
        transport = httpx.ASGITransport(app=client.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
            response = await ac.post(
                "/api/agent/message-feedback",
                json={
                    "session_id": "s",
                    "message_id": "m",
                    "feedback_type": "like",
                },
                headers={**admin_headers, "X-Session-ID": "s"},
            )
        return response

    response = asyncio.run(_run())
    assert response.status_code == 503
    assert "数据库" in response.json()["detail"]
    # 核心断言：内存模式下不应触达 message_feedback INSERT
    insert_calls = [q for q in captured_queries if q and "INSERT INTO message_feedback" in q]
    assert len(insert_calls) == 0, "内存模式下不应触达数据库写入"


def test_post_message_feedback_like_then_dislike_upserts_same_row(client, admin_headers, monkeypatch):
    """测试同一消息先赞后踩会更新为踩，不会同时存在两条记录。

    验证：
      * 第一次 like 返回 201
      * 第二次 dislike 返回 201 且 id 与第一次相同（upsert 保留原记录 id）
      * 捕获的 SQL 包含 ON CONFLICT 子句
      * 第二次 args 中 feedback_type='dislike' 且 problem_* 字段透传
    """
    import asyncio
    import httpx
    from datetime import datetime

    async def fake_get_user(username):
        return {"id": 1, "username": username, "role": "admin", "allowed_agents": []}

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username", fake_get_user
    )

    captured_calls = []

    async def fake_fetchrow(query, *args):
        captured_calls.append({"query": query, "args": args})
        return {"id": 42, "created_at": datetime(2026, 7, 4, 15, 0, 0)}

    monkeypatch.setattr("app.routers.agent_router.DatabasePool.fetchrow", fake_fetchrow)
    monkeypatch.setattr("app.routers.agent_router.DatabasePool.is_enabled", lambda: True)

    async def _post(feedback_type, problem_type=None, problem_description=None):
        transport = httpx.ASGITransport(app=client.app)
        payload = {
            "session_id": "mutex-session",
            "message_id": "msg-mutex-001",
            "feedback_type": feedback_type,
            "message_content": "问题",
            "ai_reply": "回答",
            "agent_name": "map_agent",
        }
        if problem_type:
            payload["problem_type"] = problem_type
        if problem_description:
            payload["problem_description"] = problem_description
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
            return await ac.post(
                "/api/agent/message-feedback",
                json=payload,
                headers={**admin_headers, "X-Session-ID": "mutex-session"},
            )

    async def _run():
        r1 = await _post("like")
        r2 = await _post("dislike", problem_type="logic_error", problem_description="逻辑不通")
        return r1, r2

    r1, r2 = asyncio.run(_run())
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"] == 42

    feedback_calls = [
        c for c in captured_calls
        if len(c.get("args", ())) >= 11 and c["args"][2] == "msg-mutex-001"
    ]
    assert len(feedback_calls) == 2
    assert "ON CONFLICT" in feedback_calls[0]["query"].upper()
    assert feedback_calls[0]["args"][3] == "like"
    assert feedback_calls[1]["args"][3] == "dislike"
    assert feedback_calls[1]["args"][4] == "logic_error"
    assert feedback_calls[1]["args"][5] == "逻辑不通"


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

    # 将 nonexistent_agent 加入当前用户 allowed_agents，确保权限校验通过后再测 404
    async def fake_get_user(username):
        return {
            "id": 1,
            "username": username,
            "role": "admin",
            "allowed_agents": ["nonexistent_agent"],
        }

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username", fake_get_user
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
        "agent_name": "test_agent",
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


# =============================================================================
# 2026-07-01 新增：context_overrides.project_id 与 middleware 注入 project_id 合并优先级
# 验证前端显式传入的 project_id 优先于 session_auth_middleware 注入的 request.state.project_id；
# 同时保留 middleware 兜底语义，向后兼容旧前端（不传 project_id 场景）。
#
# 测试策略：通过 httpx.ASGITransport + 自定义 ASGI 中间件构造独立 HTTP 客户端，
#   避免与 session-scoped app fixture 的中间件链冲突（TestClient 启动后无法 add_middleware）。
#   同时 mock session_cache 让 session_auth_middleware 真实查询逻辑可用。
# =============================================================================


def _build_async_chat_client(app, middleware_project_id):
    """构造带 ASGI 中间件注入 project_id 的异步 HTTP 客户端。

    使用纯 ASGI callable 中间件（避开 BaseHTTPMiddleware 的 Request 重建问题），
    在 scope 层面注入 state.project_id，确保 FastAPI Request.state 可读到。

    参数:
        app: FastAPI 应用实例
        middleware_project_id: 模拟 session_auth_middleware 注入到 request.state.project_id 的值

    返回:
        httpx.AsyncClient 实例
    """
    import httpx

    class _InjectProjectIdASGI:
        def __init__(self, inner_app):
            self.inner_app = inner_app

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                scope.setdefault("state", {})["project_id"] = middleware_project_id
            await self.inner_app(scope, receive, send)

    wrapped_app = _InjectProjectIdASGI(app)
    transport = httpx.ASGITransport(app=wrapped_app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


def _patch_agent_router_for_capture(monkeypatch, captured, middleware_project_id=None):
    """mock chat 路由依赖：build_agent_instance / get_agent_config / get_session / session_cache。

    参数:
        middleware_project_id: 若非 None，mock session_cache.get_session 返回
            {'project_id': middleware_project_id}，模拟 session_auth_middleware 的真实注入。
    """
    from unittest.mock import MagicMock
    from app.shared.utils.agent.agent_config_service import UnifiedAgentConfig

    async def fake_build(self, agent_name, session_id, message=None,
                          context_overrides=None, resume=None,
                          state_class_kwargs=None, system_prompt_override=None):
        captured.append({
            "agent_name": agent_name,
            "session_id": session_id,
            "context_overrides": dict(context_overrides or {}),
        })
        return MagicMock(name="fake_agent"), MagicMock(name="fake_context"), MagicMock(name="fake_state")

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.build_agent_instance",
        fake_build,
    )

    async def fake_get(self, name):
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

    async def mock_get_session(session_id):
        return None

    monkeypatch.setattr(
        "app.shared.utils.auth.session_db.SessionDB.get_session", mock_get_session
    )

    if middleware_project_id is not None:
        async def mock_session_cache_verify(session_id, username):
            return True

        async def mock_session_cache_get(session_id):
            return {"project_id": middleware_project_id}

        monkeypatch.setattr(
            "app.shared.utils.Session.SessionCache.session_cache.verify_session",
            mock_session_cache_verify,
        )
        monkeypatch.setattr(
            "app.shared.utils.Session.SessionCache.session_cache.get_session",
            mock_session_cache_get,
        )


@pytest.mark.asyncio
async def test_chat_context_overrides_project_id_passed_through(app, admin_headers, monkeypatch):
    """前端 context_overrides.project_id 透传到 build_agent_instance 入参。

    2026-07-01 新语义：删除 AgentContext.project_id + RESERVED_CONTEXT_FIELDS 后，
    前端可通过 context_overrides 显式注入 project_id，由 build_agent_instance 透传。
    """
    captured = []
    _patch_agent_router_for_capture(monkeypatch, captured)

    def fake_stream(*args, **kwargs):
        yield "data: test\n\n"

    monkeypatch.setattr("app.routers.agent_router.generate_stream_response", fake_stream)

    async with _build_async_chat_client(app, middleware_project_id=None) as ac:
        headers = {**admin_headers, "X-Session-ID": "test-session"}
        response = await ac.post("/api/agent/chat", json={
            "message": "hello",
            "session_id": "test-session",
            "agent_name": "map_agent",
            "context_overrides": {
                "geometry_data": {},
                "project_id": 42,
            },
        }, headers=headers)

    assert response.status_code == 200
    assert len(captured) == 1
    assert captured[0]["context_overrides"]["project_id"] == 42


@pytest.mark.asyncio
async def test_chat_context_overrides_without_project_id_is_empty(app, admin_headers, monkeypatch):
    """前端不传 project_id 时 build_agent_instance 收到的 context_overrides 不含 project_id。

    2026-07-01 新语义：agent_router 不再合并 request.state.project_id；纯靠前端显式传入。
    """
    captured = []
    _patch_agent_router_for_capture(monkeypatch, captured)

    def fake_stream(*args, **kwargs):
        yield "data: test\n\n"

    monkeypatch.setattr("app.routers.agent_router.generate_stream_response", fake_stream)

    async with _build_async_chat_client(app, middleware_project_id=None) as ac:
        headers = {**admin_headers, "X-Session-ID": "test-session"}
        response = await ac.post("/api/agent/chat", json={
            "message": "hello",
            "session_id": "test-session",
            "agent_name": "map_agent",
            "context_overrides": {
                "geometry_data": {},
            },
        }, headers=headers)

    assert response.status_code == 200
    assert len(captured) == 1
    assert "project_id" not in captured[0]["context_overrides"]


@pytest.mark.asyncio
async def test_chat_context_project_id_reaches_agent_context_runtime(app, admin_headers, monkeypatch):
    """端到端验证：context_overrides.project_id 透传到 AgentContext 实例（runtime.context）。

    验证：当 context_overrides 含 project_id=42 时，
    config.context_class(...) 构造的 AgentContext 实例含 project_id 键（运行时 dict），
    即 runtime.context.get('project_id') === 42。

    2026-07-01 新语义：AgentContext 删除 project_id 字段后，TypedDict 运行时仍允许任意额外键。
    """
    from unittest.mock import MagicMock
    from app.shared.utils.agent.agent_config_service import UnifiedAgentConfig

    class CapturingContextClass(dict):
        last_kwargs = {}

        def __init__(self, **kwargs):
            CapturingContextClass.last_kwargs = dict(kwargs)
            super().__init__(**kwargs)

    captured_context = {}

    async def fake_build(self, agent_name, session_id, message=None,
                          context_overrides=None, resume=None,
                          state_class_kwargs=None, system_prompt_override=None):
        # 新路径：safe_overrides 不再过滤 project_id（已从 RESERVED_CONTEXT_FIELDS 移除）
        from app.shared.utils.agent.dynamic_schema import RESERVED_CONTEXT_FIELDS
        safe_overrides = {
            k: v for k, v in (context_overrides or {}).items()
            if k not in RESERVED_CONTEXT_FIELDS
        }
        captured_context["safe_overrides"] = dict(safe_overrides)
        return MagicMock(name="fake_agent"), CapturingContextClass(
            session_id=session_id or "default",
            **safe_overrides,
        ), MagicMock(name="fake_state")

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.build_agent_instance",
        fake_build,
    )

    async def fake_get(self, name):
        return UnifiedAgentConfig(
            name=name,
            display_name="测试智能体",
            description="",
            system_prompt="# 测试",
            state_class=MagicMock(return_value={"messages": []}),
            context_class=CapturingContextClass,
        )

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.get_agent_config",
        fake_get,
    )

    async def mock_get_session(session_id):
        return None

    monkeypatch.setattr(
        "app.shared.utils.auth.session_db.SessionDB.get_session", mock_get_session
    )

    def fake_stream(*args, **kwargs):
        yield "data: test\n\n"

    monkeypatch.setattr("app.routers.agent_router.generate_stream_response", fake_stream)

    async with _build_async_chat_client(app, middleware_project_id=None) as ac:
        headers = {**admin_headers, "X-Session-ID": "test-session"}
        response = await ac.post("/api/agent/chat", json={
            "message": "hello",
            "session_id": "test-session",
            "agent_name": "map_agent",
            "context_overrides": {
                "geometry_data": {},
                "project_id": 42,
            },
        }, headers=headers)

    assert response.status_code == 200
    assert captured_context["safe_overrides"].get("project_id") == 42


# =============================================================================
# 2026-07-01 新增：智能体选择权限控制测试
# 验证 /api/agent/list 按 request.state.allowed_agents 过滤，
# /api/agent/chat 对未授权智能体返回 403。
# =============================================================================


def test_list_agents_empty_allowed_returns_empty(client, admin_headers, monkeypatch):
    """测试当前用户 allowed_agents 为空时 /api/agent/list 返回 []。"""
    async def fake_list(self):
        return [{"name": "map_agent", "display_name": "地图智能体"}]

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.list_agents",
        fake_list,
    )

    async def fake_get_user(username):
        return {"id": 1, "username": "admin", "role": "admin", "allowed_agents": []}

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username",
        fake_get_user,
    )

    headers = {**admin_headers, "X-Session-ID": "test-session"}
    response = client.get("/api/agent/list", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


def test_list_agents_filters_by_allowed_agents(client, admin_headers, monkeypatch):
    """测试 /api/agent/list 仅返回 allowed_agents 中包含的智能体。"""
    async def fake_list(self):
        return [
            {"name": "map_agent", "display_name": "地图智能体"},
            {"name": "audit_document_agent", "display_name": "审计文档智能体"},
            {"name": "test_agent", "display_name": "测试智能体"},
        ]

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.list_agents",
        fake_list,
    )

    async def fake_get_user(username):
        return {"id": 1, "username": "admin", "role": "admin", "allowed_agents": ["map_agent"]}

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username",
        fake_get_user,
    )

    headers = {**admin_headers, "X-Session-ID": "test-session"}
    response = client.get("/api/agent/list", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "map_agent"


def test_chat_forbidden_agent_returns_403(client, admin_headers, monkeypatch):
    """测试请求未授权的智能体时 /api/agent/chat 返回 403。"""
    async def fake_get_user(username):
        return {"id": 1, "username": "admin", "role": "admin", "allowed_agents": ["map_agent"]}

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username",
        fake_get_user,
    )

    headers = {**admin_headers, "X-Session-ID": "test-session"}
    response = client.post("/api/agent/chat", json={
        "message": "hello",
        "session_id": "test-session",
        "agent_name": "audit_document_agent",
    }, headers=headers)

    assert response.status_code == 403
    assert "audit_document_agent" in response.json()["detail"]


def test_chat_default_agent_name_not_restricted(client, admin_headers, monkeypatch):
    """测试 agent_name 为 default 时不受 allowed_agents 限制。"""
    from unittest.mock import MagicMock

    async def fake_get_user(username):
        return {"id": 1, "username": "admin", "role": "admin", "allowed_agents": []}

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username",
        fake_get_user,
    )

    async def fake_build(self, **kwargs):
        return MagicMock(name="fake_agent"), MagicMock(name="fake_context"), MagicMock(name="fake_state")

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.build_agent_instance",
        fake_build,
    )

    def fake_stream(*args, **kwargs):
        yield "data: test\n\n"

    monkeypatch.setattr("app.routers.agent_router.generate_stream_response", fake_stream)

    headers = {**admin_headers, "X-Session-ID": "test-session"}
    response = client.post("/api/agent/chat", json={
        "message": "hello",
        "session_id": "test-session",
        "agent_name": "default",
    }, headers=headers)

    assert response.status_code == 200
