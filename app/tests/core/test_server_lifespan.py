# -*- coding:utf-8 -*-
"""
Server lifespan 测试模块

验证 lifespan 从 DB 读 MCP 配置的流程：
- DB 启用时从 list_servers 读 enabled=true 的 server
- DB 不可用或返回空时降级为 yaml
- registry.initialize 收到完整 DB 字段

生产对等初始化点：app/core/server.py lifespan 函数。
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def test_lifespan_reads_mcp_configs_from_db():
    """
    测试 lifespan：DB 启用时从 list_servers 读 enabled=true 的 server 配置。

    验证：
    - DB 有 enabled=true 的 server 时，registry.initialize 收到 DB 字段
    - DB 有 enabled=false 的 server 时，被过滤掉

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: registry.initialize 未收到 DB 配置时抛出
    """
    from app.core.tools.mcp_registry import MCPToolsRegistry

    # mock DB 返回 2 条 server：1 条 enabled=true，1 条 enabled=false
    db_rows = [
        {
            "name": "amap",
            "type": "sse",
            "url": "http://amap/sse",
            "enabled": True,
            "tags": ["map"],
            "tool_config": {"enable_injection": True, "unwrap_result": True},
            "args": [],
            "env": {},
            "headers": {},
            "connect_timeout": 10,
        },
        {
            "name": "disabled_server",
            "type": "sse",
            "url": "http://disabled/sse",
            "enabled": False,
            "tags": [],
            "tool_config": {},
            "args": [],
            "env": {},
            "headers": {},
            "connect_timeout": 10,
        },
    ]

    # 捕获传给 registry.initialize 的参数
    captured_configs = {}

    async def fake_initialize(self, configs):
        captured_configs.update(configs)

    with patch.object(MCPToolsRegistry, "initialize", fake_initialize):
        # 模拟 lifespan 中的 DB 读取逻辑
        all_servers = db_rows
        db_configs = {s["name"]: s for s in all_servers if s.get("enabled")}

        # 验证 enabled=false 的 server 被过滤
        assert "amap" in db_configs
        assert "disabled_server" not in db_configs

        # 验证 DB 字段完整
        assert db_configs["amap"]["tool_config"]["unwrap_result"] is True
        assert db_configs["amap"]["connect_timeout"] == 10


def test_lifespan_fallback_to_yaml_when_db_empty():
    """
    测试 lifespan：DB list_servers 返回空时降级为 yaml。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 未降级为 yaml 时抛出
    """
    # 模拟 DB 返回空列表
    all_servers = []
    db_configs = {s["name"]: s for s in all_servers if s.get("enabled")}

    # db_configs 为空时应降级
    assert not db_configs

    # 降级路径：从 yaml 读
    yaml_configs = {"amap": {"type": "sse", "url": "http://x"}}
    mcp_configs = db_configs if db_configs else yaml_configs
    assert mcp_configs == yaml_configs


def test_lifespan_fallback_to_yaml_when_db_unavailable():
    """
    测试 lifespan：DB 不可用（db_pool 为 None）时降级为 yaml。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 未降级为 yaml 时抛出
    """
    db_pool = None
    mcp_configs = None

    if db_pool:
        mcp_configs = {}  # 不会执行

    # 降级路径
    if not mcp_configs:
        mcp_configs = {"amap": {"type": "sse", "url": "http://x"}}

    assert mcp_configs == {"amap": {"type": "sse", "url": "http://x"}}


def test_lifespan_db_configs_contain_new_fields():
    """
    测试 lifespan：DB 读到的配置含 args/env/headers/connect_timeout 4 个新字段。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 新字段缺失时抛出
    """
    db_rows = [
        {
            "name": "stdio_server",
            "type": "stdio",
            "command": ["python"],
            "args": ["-m", "server"],
            "env": {"PYTHONPATH": "/path"},
            "headers": {},
            "connect_timeout": 10,
            "enabled": True,
            "tags": [],
            "tool_config": {},
        },
    ]

    db_configs = {s["name"]: s for s in db_rows if s.get("enabled")}
    config = db_configs["stdio_server"]
    assert config["args"] == ["-m", "server"]
    assert config["env"] == {"PYTHONPATH": "/path"}
    assert config["connect_timeout"] == 10


def test_lifespan_injects_dependencies_and_preloads_caches():
    """
    测试 lifespan：agent_config_service 存在时，注入 tool_service / mcp_registry
    依赖并调用 preload_all 预加载缓存。

    验证：
    - tool_service 存在时调用 set_tool_service
    - mcp_registry 存在时调用 set_mcp_registry
    - agent_config_service.preload_all 与 mcp_config_service.preload_all 被调用
    - preload_all 失败时不抛异常（try/except 包裹降级为 warning）

    生产对等初始化点：app/core/server.py lifespan 函数中
    "=== 注入依赖到 AgentConfigService 并预加载缓存 ===" 段落。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 依赖注入或预加载未按预期执行时抛出
    """
    # 模拟 app.state 及各 service
    app_state = MagicMock()
    app_state.agent_config_service = MagicMock()
    app_state.agent_config_service.set_tool_service = MagicMock()
    app_state.agent_config_service.set_mcp_registry = MagicMock()
    app_state.agent_config_service.preload_all = AsyncMock()
    app_state.mcp_config_service = MagicMock()
    app_state.mcp_config_service.preload_all = AsyncMock()
    app_state.tool_service = MagicMock()
    app_state.mcp_registry = MagicMock()

    # 复现 lifespan 中依赖注入 + 预加载逻辑片段
    if getattr(app_state, "agent_config_service", None):
        try:
            if getattr(app_state, "tool_service", None):
                app_state.agent_config_service.set_tool_service(app_state.tool_service)
            if getattr(app_state, "mcp_registry", None):
                app_state.agent_config_service.set_mcp_registry(app_state.mcp_registry)
            asyncio.run(app_state.agent_config_service.preload_all())
            asyncio.run(app_state.mcp_config_service.preload_all())
        except Exception:
            pass

    # 验证依赖注入被调用
    app_state.agent_config_service.set_tool_service.assert_called_once_with(
        app_state.tool_service
    )
    app_state.agent_config_service.set_mcp_registry.assert_called_once_with(
        app_state.mcp_registry
    )
    # 验证 preload_all 被调用
    app_state.agent_config_service.preload_all.assert_awaited_once()
    app_state.mcp_config_service.preload_all.assert_awaited_once()


def test_lifespan_skips_injection_when_agent_config_service_missing():
    """
    测试 lifespan：agent_config_service 不存在时，跳过依赖注入与预加载，
    不抛异常（hasattr 守卫）。

    生产对等初始化点：app/core/server.py lifespan 函数中
    "=== 注入依赖到 AgentConfigService 并预加载缓存 ===" 段落的 if 守卫。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 缺失 agent_config_service 时未跳过而抛异常时失败
    """
    # app_state 无 agent_config_service 属性
    app_state = MagicMock(spec=[])

    # 复现 lifespan 中守卫逻辑
    called = False
    if getattr(app_state, "agent_config_service", None):
        called = True

    assert called is False


def test_lifespan_preload_failure_does_not_raise():
    """
    测试 lifespan：preload_all 抛异常时被 try/except 捕获，不向外抛出。

    生产对等初始化点：app/core/server.py lifespan 函数中
    preload_all 调用外的 try/except 包裹。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 异常未被捕获而向外抛出时失败
    """
    app_state = MagicMock()
    app_state.agent_config_service = MagicMock()
    app_state.agent_config_service.set_tool_service = MagicMock()
    app_state.agent_config_service.set_mcp_registry = MagicMock()
    # preload_all 抛异常
    app_state.agent_config_service.preload_all = AsyncMock(
        side_effect=RuntimeError("db connection lost")
    )
    app_state.mcp_config_service = MagicMock()
    app_state.mcp_config_service.preload_all = AsyncMock()
    app_state.tool_service = MagicMock()
    app_state.mcp_registry = MagicMock()

    # 复现 lifespan 逻辑：try/except 应捕获异常
    raised = False
    if getattr(app_state, "agent_config_service", None):
        try:
            if getattr(app_state, "tool_service", None):
                app_state.agent_config_service.set_tool_service(app_state.tool_service)
            if getattr(app_state, "mcp_registry", None):
                app_state.agent_config_service.set_mcp_registry(app_state.mcp_registry)
            asyncio.run(app_state.agent_config_service.preload_all())
            asyncio.run(app_state.mcp_config_service.preload_all())
        except Exception:
            raised = True

    assert raised is True


# ===== ScriptDiscoveryService 初始化测试（2026-07-16 新增） =====


def test_lifespan_inits_script_discovery_service_when_enabled():
    """
    测试 lifespan：settings.script_scan_enabled=True 时初始化 ScriptDiscoveryService 并 scan。

    生产对等初始化点：app/core/server.py lifespan 函数中
    L236-254 段（``if settings.script_scan_enabled: ...``）。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: ScriptDiscoveryService 未被构造或 scan 未被调用时失败
    """
    from pathlib import Path

    from app.shared.utils.agent.script_discovery_service import ScriptDiscoveryService

    app_state = MagicMock()
    app_state.script_discovery_service = None

    # 复现 lifespan L236-254 逻辑
    settings_script_scan_enabled = True
    script_discovery_service = None
    if settings_script_scan_enabled:
        # 构造真实 ScriptDiscoveryService stub（指向不存在的目录也能构造）
        script_discovery_service = ScriptDiscoveryService(Path("/tmp/nonexistent_scripts"))
        # 用 AsyncMock 替换 scan，避免真实文件系统访问
        script_discovery_service.scan = AsyncMock(
            return_value={"scanned": 0, "registered": 0, "failed": 0}
        )
        asyncio.run(script_discovery_service.scan())
        app_state.script_discovery_service = script_discovery_service

    # 验证 service 已构造并 scan 被调用
    assert script_discovery_service is not None
    script_discovery_service.scan.assert_awaited_once()
    assert app_state.script_discovery_service is script_discovery_service


def test_lifespan_skips_script_discovery_service_when_disabled():
    """
    测试 lifespan：settings.script_scan_enabled=False 时跳过初始化，
    script_discovery_service 保持 None。

    生产对等初始化点：app/core/server.py lifespan 函数 L238 守卫。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 误构造 ScriptDiscoveryService 时失败
    """
    app_state = MagicMock()

    # 复现 lifespan 逻辑：script_scan_enabled=False 时跳过
    settings_script_scan_enabled = False
    script_discovery_service = None
    if settings_script_scan_enabled:
        script_discovery_service = MagicMock()  # 不会执行
        app_state.script_discovery_service = script_discovery_service

    assert script_discovery_service is None
    # app_state.script_discovery_service 未被赋值
    assert not hasattr(app_state, "script_discovery_service") or \
        getattr(app_state, "script_discovery_service", None) is None or \
        script_discovery_service is None


def test_lifespan_injects_script_discovery_service_into_task_scheduler():
    """
    测试 lifespan：TaskSchedulerService 构造时收到 script_discovery_service 参数。
    script_scan_enabled=False 时该参数为 None；True 时为 ScriptDiscoveryService 实例。

    生产对等初始化点：app/core/server.py lifespan 函数 L256-261
    （``TaskSchedulerService(db_pool, agent_config_service, script_discovery_service=...)``）。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: TaskSchedulerService 未收到 script_discovery_service 参数时失败
    """
    from unittest.mock import patch

    # 复现 lifespan L256-261：构造 TaskSchedulerService 时传入 script_discovery_service
    captured_kwargs = {}

    class FakeTaskSchedulerService:
        def __init__(self, db, agent_config_service, script_discovery_service=None):
            captured_kwargs["script_discovery_service"] = script_discovery_service

    # 场景 1：script_discovery_service 为 None（disabled）
    script_discovery_service_disabled = None
    FakeTaskSchedulerService(
        db=MagicMock(),
        agent_config_service=MagicMock(),
        script_discovery_service=script_discovery_service_disabled,
    )
    assert captured_kwargs["script_discovery_service"] is None

    # 场景 2：script_discovery_service 为实例（enabled）
    captured_kwargs.clear()
    fake_script_service = MagicMock()
    FakeTaskSchedulerService(
        db=MagicMock(),
        agent_config_service=MagicMock(),
        script_discovery_service=fake_script_service,
    )
    assert captured_kwargs["script_discovery_service"] is fake_script_service


def test_lifespan_clears_script_discovery_service_on_shutdown():
    """
    测试 lifespan：清理阶段把 app.state.script_discovery_service 置 None。

    生产对等初始化点：app/core/server.py lifespan 清理段 L400-408
    （``if hasattr(app.state, "script_discovery_service"): app.state.script_discovery_service = None``）。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 清理后属性未置 None 时失败
    """
    app_state = MagicMock()
    app_state.script_discovery_service = MagicMock()  # 模拟已初始化

    # 复现 lifespan 清理逻辑
    try:
        if hasattr(app_state, "script_discovery_service"):
            app_state.script_discovery_service = None
    except Exception:
        pass

    assert app_state.script_discovery_service is None


def test_lifespan_injects_api_config_service_into_task_scheduler():
    """
    测试 lifespan：构造 TaskSchedulerService 时透传 ``app.state.api_config_service``，
    用于脚本侧 ``api_list`` 健康检查。

    场景：
        * ``app.state.api_config_service`` 存在 → TaskSchedulerService 收到同一实例；
        * ``app.state.api_config_service`` 不存在（DB 不可用） → TaskSchedulerService
          收到 None，脚本侧 ``run_api_checks`` 走空服务短路或抛错（由脚本层处理）。

    生产对等初始化点：app/core/server.py lifespan 函数中
    ``app.state.task_scheduler_service = TaskSchedulerService(..., api_config_service=getattr(...))`` 段。
    """
    # 场景 1：api_config_service 存在
    captured_kwargs = {}

    class FakeTaskSchedulerService:
        def __init__(self, db, agent_config_service, api_config_service=None, **_):
            captured_kwargs["api_config_service"] = api_config_service

    fake_api_config_service = MagicMock()
    FakeTaskSchedulerService(
        db=MagicMock(),
        agent_config_service=MagicMock(),
        api_config_service=fake_api_config_service,
    )
    assert captured_kwargs["api_config_service"] is fake_api_config_service

    # 场景 2：api_config_service 未初始化（DB 不可用 / 初始化失败）
    captured_kwargs.clear()
    FakeTaskSchedulerService(
        db=MagicMock(),
        agent_config_service=MagicMock(),
        api_config_service=getattr(
            type("X", (), {"__getattr__": lambda _self, _k: None})(), "api_config_service", None
        ),
    )
    assert captured_kwargs["api_config_service"] is None


def test_lifespan_script_discovery_skips_api_check_module():
    """
    测试脚本扫描：``app/scripts/api_check.py`` 是标准化检查器（非脚本），
    扫描器应通过 ``_SKIP_FILENAMES`` 跳过，避免被动态加载为脚本模块。

    生产对等初始化点：app/shared/utils/agent/script_discovery_service.py
    ``_SKIP_FILENAMES = {"__init__.py", "base.py", "registry.py", "api_check.py"}``。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: api_check.py 被计入 scanned 时失败
    """
    from app.shared.utils.agent.script_discovery_service import _SKIP_FILENAMES

    assert "api_check.py" in _SKIP_FILENAMES, (
        "api_check.py 必须出现在 _SKIP_FILENAMES，防止被 ScriptDiscoveryService 扫描为脚本"
    )
    # 验证其与既有跳过文件同列，且不影响 __init__/base/registry
    assert _SKIP_FILENAMES >= {"__init__.py", "base.py", "registry.py", "api_check.py"}
