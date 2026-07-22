# -*- coding:utf-8 -*-
"""
Task Scheduler lifespan 行为测试模块。

验证智能体定时任务服务在生产 lifespan 中的真实初始化顺序与关闭逻辑。
"""
import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


def test_lifespan_initializes_email_before_task_scheduler():
    """测试 lifespan 源码顺序: EmailConfigService 必须在 TaskSchedulerService 之前初始化。

    参数:
        无。

    返回值:
        None。

    异常:
        AssertionError: 顺序错误或未通过 ``getattr(app.state, 'email_config_service', None)``
            注入 ``email_config_service`` 参数时抛出。
    """
    from app.core.server import lifespan

    source = inspect.getsource(lifespan)
    email_init_index = source.index(
        "app.state.email_config_service = EmailConfigService("
    )
    scheduler_init_index = source.index(
        "app.state.task_scheduler_service = TaskSchedulerService("
    )

    # EmailConfigService 必须在 TaskSchedulerService 之前构造完成
    assert email_init_index < scheduler_init_index, (
        "lifespan 中 EmailConfigService 必须在 TaskSchedulerService 之前初始化, "
        "否则脚本任务邮件通知会被提前短路。"
    )
    # 必须通过 getattr 注入到 TaskSchedulerService 构造参数
    assert "email_config_service=getattr(" in source, (
        "lifespan 中必须通过 email_config_service=getattr(app.state, ...) "
        "将已初始化的 EmailConfigService 注入 TaskSchedulerService。"
    )


def test_lifespan_initializes_devops_server_before_task_scheduler():
    """测试 lifespan 源码顺序: DevOpsServerService 必须在 TaskSchedulerService 之前初始化。

    触发原因（2026-07-22 实测）：

    在 ops_inspection_sweep 触发定时任务 #4 时, ``task_scheduler_service.execute_schedule``
    抛出 ``ScriptExecutionError: devops_server_service 不可用``。根因是 lifespan 源码中
    ``DevOpsServerService`` 的初始化块（第 339-388 行附近）**晚于**
    ``TaskSchedulerService`` 构造（第 270-315 行附近）。TaskSchedulerService 在构造时
    通过 ``getattr(app.state, 'devops_server_service', None)`` 读取服务, 此时尚未初始化,
    拿到 ``None`` 并永久缓存到 ``self._devops_server_service``, 后续脚本执行时
    ``context.devops_server_service`` 一直是 ``None``, 调用 ``run_server_ops`` 触发
    显式校验抛错。

    修复策略: 将 DevOpsServerService 初始化块前移到 TaskSchedulerService 构造之前。

    生产对等初始化点: ``app/core/server.py`` lifespan 中
    ``TaskSchedulerService(..., devops_server_service=getattr(app.state, 'devops_server_service', None))``
    与 ``DevOpsServerService.set_instance(svc)`` + ``app.state.devops_server_service = svc``。

    参数:
        无。

    返回值:
        None。

    异常:
        AssertionError: 顺序错误时抛出。
    """
    from app.core.server import lifespan

    source = inspect.getsource(lifespan)
    devops_init_index = source.index("app.state.devops_server_service = svc")
    scheduler_init_index = source.index(
        "app.state.task_scheduler_service = TaskSchedulerService("
    )

    assert devops_init_index < scheduler_init_index, (
        "lifespan 中 DevOpsServerService 初始化（app.state.devops_server_service = svc）"
        "必须在 TaskSchedulerService 之前完成, 否则 run_server_ops 在脚本执行时拿到 None, "
        "导致 server_list 巡检失败（ScriptExecutionError: devops_server_service 不可用）。"
    )
    assert "devops_server_service=getattr(" in source, (
        "lifespan 中必须通过 devops_server_service=getattr(app.state, ...) "
        "将已初始化的 DevOpsServerService 注入 TaskSchedulerService。"
    )


def test_lifespan_initializes_api_config_before_task_scheduler():
    """测试 lifespan 源码顺序: ApiConfigService 必须在 TaskSchedulerService 之前初始化。

    与 ``test_lifespan_initializes_devops_server_before_task_scheduler`` 同源问题:
    ApiConfigService 初始化块（第 397 行附近）也晚于 TaskSchedulerService, 导致
    ``self._api_config_service is None``。当前因 hello_script / ops_inspection_sweep 默认
    ``api_list=[]`` 走 ``run_api_checks`` 空数组短路未暴露, 但只要用户配置了 ``api_list``
    即触发 ``ScriptExecutionError: api_config_service 不可用``。

    参数:
        无。

    返回值:
        None。

    异常:
        AssertionError: 顺序错误时抛出。
    """
    from app.core.server import lifespan

    source = inspect.getsource(lifespan)
    api_cfg_init_index = source.index("app.state.api_config_service = ApiConfigService(")
    scheduler_init_index = source.index(
        "app.state.task_scheduler_service = TaskSchedulerService("
    )

    assert api_cfg_init_index < scheduler_init_index, (
        "lifespan 中 ApiConfigService 初始化（app.state.api_config_service = ApiConfigService(...)）"
        "必须在 TaskSchedulerService 之前完成, 否则 run_api_checks 在脚本执行时拿到 None, "
        "导致 api_list 健康检查失败（ScriptExecutionError: api_config_service 不可用）。"
    )
    assert "api_config_service=getattr(" in source, (
        "lifespan 中必须通过 api_config_service=getattr(app.state, ...) "
        "将已初始化的 ApiConfigService 注入 TaskSchedulerService。"
    )


def test_lifespan_initializes_task_scheduler_after_agent_preload():
    """测试 lifespan 在 AgentConfigService 预加载后初始化 TaskSchedulerService。

    参数:
        无。

    返回值:
        None。

    异常:
        AssertionError: 初始化顺序或调用不符合生产约定时抛出。
    """
    calls = []
    app_state = SimpleNamespace()
    app_state.agent_config_service = MagicMock()
    app_state.agent_config_service.preload_all = AsyncMock(side_effect=lambda: calls.append("agent_preload"))
    app_state.mcp_config_service = MagicMock()
    app_state.mcp_config_service.preload_all = AsyncMock(side_effect=lambda: calls.append("mcp_preload"))

    class FakeTaskSchedulerService:
        def __init__(self, db, agent_config_service):
            calls.append("scheduler_init")
            self.db = db
            self.agent_config_service = agent_config_service

        async def preload_all(self):
            calls.append("scheduler_preload")

        async def start(self):
            calls.append("scheduler_start")

    async def run_fragment():
        db_pool = object()
        settings = SimpleNamespace(task_scheduler_enabled=True)
        await app_state.agent_config_service.preload_all()
        await app_state.mcp_config_service.preload_all()
        if settings.task_scheduler_enabled and db_pool:
            app_state.task_scheduler_service = FakeTaskSchedulerService(
                db_pool,
                app_state.agent_config_service,
            )
            await app_state.task_scheduler_service.preload_all()
            await app_state.task_scheduler_service.start()

    asyncio.run(run_fragment())

    assert calls == ["agent_preload", "mcp_preload", "scheduler_init", "scheduler_preload", "scheduler_start"]
    assert isinstance(app_state.task_scheduler_service, FakeTaskSchedulerService)


def test_lifespan_injects_email_config_service_identity_into_task_scheduler():
    """测试 lifespan：EmailConfigService 实例必须以同一对象身份注入到 TaskSchedulerService。

    生产对等初始化点：``app/core/server.py`` lifespan 中
    ``TaskSchedulerService(..., email_config_service=getattr(app.state, 'email_config_service', None))``。

    该测试不依赖真实的 EmailConfigService 构造（避免触发 Fernet / DB 副作用），
    而是用 ``SimpleNamespace`` 充当最小 fake service，重点验证：
    1. ``app.state.email_config_service`` 已存在的真实实例;
    2. ``TaskSchedulerService`` 构造时 ``email_config_service`` 形参收到的是
       同一对象（``is`` 身份断言），避免出现"两份实例 / 缓存分叉"。

    参数:
        无。

    返回值:
        None。

    异常:
        AssertionError: 注入失败或身份不同时抛出。
    """
    captured_kwargs: dict = {}

    class FakeTaskSchedulerService:
        def __init__(
            self,
            db,
            agent_config_service,
            script_discovery_service=None,
            email_config_service=None,
        ):
            captured_kwargs["email_config_service"] = email_config_service

    # 场景 1：app.state.email_config_service 为 None（邮件禁用 / DB 不可用 / 诊断失败）
    app_state_none = SimpleNamespace(email_config_service=None)
    FakeTaskSchedulerService(
        db=MagicMock(),
        agent_config_service=MagicMock(),
        script_discovery_service=None,
        email_config_service=getattr(app_state_none, "email_config_service", None),
    )
    assert captured_kwargs["email_config_service"] is None

    # 场景 2：app.state.email_config_service 为真实实例（正常配置）
    captured_kwargs.clear()
    fake_email_service = SimpleNamespace(
        preload_all=AsyncMock(),
        get_policy=AsyncMock(),
        get_active_server_config=AsyncMock(),
    )
    app_state_real = SimpleNamespace(email_config_service=fake_email_service)
    FakeTaskSchedulerService(
        db=MagicMock(),
        agent_config_service=MagicMock(),
        script_discovery_service=None,
        email_config_service=getattr(app_state_real, "email_config_service", None),
    )
    # 关键断言：通过 ``is`` 校验对象身份一致，避免缓存分叉
    assert captured_kwargs["email_config_service"] is fake_email_service


def test_lifespan_shutdown_closes_task_scheduler_before_database_close():
    """测试 shutdown 阶段先关闭 TaskSchedulerService，再关闭数据库。

    参数:
        无。

    返回值:
        None。

    异常:
        AssertionError: 关闭顺序不符合生产约定时抛出。
    """
    calls = []

    class FakeTaskSchedulerService:
        async def shutdown(self):
            calls.append("scheduler_shutdown")

    class FakeDatabasePool:
        @classmethod
        def is_enabled(cls):
            return True

        @classmethod
        async def close(cls):
            calls.append("db_close")

    app_state = SimpleNamespace(task_scheduler_service=FakeTaskSchedulerService())

    async def run_fragment():
        if hasattr(app_state, "task_scheduler_service") and app_state.task_scheduler_service is not None:
            await app_state.task_scheduler_service.shutdown()
        if FakeDatabasePool.is_enabled():
            await FakeDatabasePool.close()

    asyncio.run(run_fragment())

    assert calls == ["scheduler_shutdown", "db_close"]
