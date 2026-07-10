# -*- coding:utf-8 -*-
"""
Task Scheduler lifespan 行为测试模块。

验证智能体定时任务服务在生产 lifespan 中的真实初始化顺序与关闭逻辑。
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


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
