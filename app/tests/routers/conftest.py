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

    lifespan 集成（Task 14）尚未完成，此处在测试中手动注入 AgentConfigService 实例。
    测试通过 monkeypatch 替换类方法，因此 db=None 和 loader=None 即可。
    """
    from app.shared.utils.agent.agent_config_service import AgentConfigService
    from app.shared.utils.agent.agents_md_loader import AgentsMdLoader
    app.state.agent_config_service = AgentConfigService(db=None, agents_md_loader=AgentsMdLoader())


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

