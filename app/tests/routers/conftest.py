# -*- coding:utf-8 -*-
"""
routers 测试目录的本地 conftest

在 app.main 导入前 mock filesystem_encoding_fix 模块，避免 apply_fix()
在测试环境中因 Mock 属性缺失（如 _python_search）而失败。

全局 conftest.py 已 mock 大量外部依赖，但 filesystem_encoding_fix.apply_fix()
会在 app.main 模块加载时被调用，其内部访问 EncodingSafeFileSearchMiddleware._python_search
等属性在纯 Mock 环境下不存在，导致 AttributeError。此处将 apply_fix 替换为 no-op。

同时为 mcp_admin_router 提供 McpConfigService 实例（lifespan 集成在 Task 14 完成）。
"""
import sys
import types
from typing import Any

from typing_extensions import TypedDict

# 覆盖根 conftest 中 MessagesState 的 Mock，确保 AgentState 继承真实 TypedDict。
# 必须在 app.main 首次导入前执行，否则 AgentConfig.py 中的 AgentState 会成为 Mock 对象。
class _MessagesState(TypedDict):
    messages: list[Any]

_lg_graph = sys.modules.get("langgraph.graph")
if _lg_graph is not None:
    _lg_graph.MessagesState = _MessagesState
else:
    _lg_graph = types.ModuleType("langgraph.graph")
    _lg_graph.MessagesState = _MessagesState
    sys.modules["langgraph.graph"] = _lg_graph

for _mod in [
    "app.core.agent.AgentConfig",
    "app.core.agent.AgentContext",
    "app.shared.utils.agent.dynamic_schema",
]:
    sys.modules.pop(_mod, None)

import pytest

# Mock filesystem_encoding_fix 模块，使 apply_fix 成为 no-op
# 必须在 app.main 被导入前执行（app fixture 首次导入 app.main 时生效）
_fs_fix = types.ModuleType("app.shared.tools.middleware.filesystem_encoding_fix")
_fs_fix.apply_fix = lambda: None
sys.modules["app.shared.tools.middleware.filesystem_encoding_fix"] = _fs_fix


@pytest.fixture(autouse=True)
def _init_mcp_config_service(app):
    """初始化 app.state.mcp_config_service 供 mcp_admin_router 使用。

    lifespan 集成（Task 14）尚未完成，此处在测试中手动注入 McpConfigService 实例。
    测试通过 monkeypatch 替换类方法，因此 db=None 即可。
    """
    from app.shared.utils.agent.mcp_service import McpConfigService
    app.state.mcp_config_service = McpConfigService(db=None)


@pytest.fixture(autouse=True)
def _init_agent_config_service(app):
    """初始化 app.state.agent_config_service 供 agent_router 使用。

    生产对应初始化点：``app/core/server.py::lifespan`` 第 113-128 行
    （db_pool 存在时构造 AgentConfigService 并挂到 ``app.state.agent_config_service``）。

    lifespan 在测试环境中不会自动触发，因此 autouse fixture 在测试启动时
    注入与生产同构的 service 实例（db=None 是合法 stub，因为路由层只调
    service 的方法，不直接读 service._db；具体方法需要 db 时通过
    ``monkeypatch`` 或 ``service._db = MagicMock()`` 按需注入）。

    反模式防御：禁止用 ``app.state.db = MagicMock()`` 注入生产 lifespan
    根本不存在的对象（违反 AGENTS.md「禁止在测试中虚构生产不存在的依赖」
    硬约束，会掩盖路由层错读 ``app.state.db`` 的 bug）。
    """
    from app.shared.utils.agent.agent_config_service import AgentConfigService
    from app.shared.utils.agent.agents_md_loader import AgentsMdLoader
    app.state.agent_config_service = AgentConfigService(db=None, agents_md_loader=AgentsMdLoader())


@pytest.fixture(autouse=True)
def _mock_user_db_for_admin_auth(monkeypatch):
    """Mock UserDB.get_user_by_username 根据 username 返回对应 role 用户。

    真实 auth_middleware 通过查询 UserDB 获取 role。测试环境下 DB 已 mock，
    get_user_by_username 返回 None 导致 role='user'，require_admin 拒绝。
    此处 patch 后：
    - username='admin' 返回 role='admin'
    - username='testuser' 返回 role='user'
    - 其他返回 None
    """
    from unittest.mock import AsyncMock
    async def fake_get_user_by_username(username):
        if username == "admin":
            return {"id": 1, "username": "admin", "role": "admin"}
        if username == "testuser":
            return {"id": 2, "username": "testuser", "role": "user"}
        return None
    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username",
        fake_get_user_by_username,
    )


@pytest.fixture(autouse=True)
def _mock_session_cache_for_agent(monkeypatch):
    """Mock session_cache.verify_session 以绕过 /api/agent/ 路径的 Session 校验。

    /api/agent/ 前缀在 SESSION_REQUIRED_PREFIXES 中，需 X-Session-ID 头并通过
    session_cache.verify_session 校验。agent_router 的 list / agents-md 属于
    管理端点，测试中直接放行。
    """
    from unittest.mock import AsyncMock
    monkeypatch.setattr(
        "app.shared.utils.Session.SessionCache.session_cache.verify_session",
        AsyncMock(return_value=True),
    )

