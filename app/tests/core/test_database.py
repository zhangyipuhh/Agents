# -*- coding:utf-8 -*-
"""
测试 app.core.database 数据库连接池模块

验证 DatabasePool 启用状态判断以及未初始化时的异常抛出行为。
"""

import asyncio
import pytest

from app.core.database import DatabasePool


def test_database_pool_is_enabled_memory_mode(monkeypatch):
    """
    测试 AUTH_STORAGE_MODE=memory 时 is_enabled() 返回 False。

    参数:
        monkeypatch: pytest 内置 fixture，用于临时修改环境变量

    返回值:
        None
    """
    monkeypatch.setenv("AUTH_STORAGE_MODE", "memory")
    assert DatabasePool.is_enabled() is False


def test_database_pool_is_enabled_postgres_mode(monkeypatch):
    """
    测试 AUTH_STORAGE_MODE=postgres 时 is_enabled() 返回 True。

    参数:
        monkeypatch: pytest 内置 fixture，用于临时修改环境变量

    返回值:
        None
    """
    monkeypatch.setenv("AUTH_STORAGE_MODE", "postgres")
    assert DatabasePool.is_enabled() is True


def test_database_pool_execute_without_initialization_raises_runtime_error():
    """
    测试未初始化时调用 execute() 抛出 RuntimeError。

    Returns:
        None

    异常:
        RuntimeError: 预期抛出的异常
    """

    async def _run():
        # 确保连接池未初始化
        DatabasePool._pool = None
        DatabasePool._initialized = False
        with pytest.raises(RuntimeError, match="Database pool not initialized"):
            await DatabasePool.execute("SELECT 1")

    asyncio.run(_run())


def test_database_pool_fetch_without_initialization_raises_runtime_error():
    """
    测试未初始化时调用 fetch() 抛出 RuntimeError。

    Returns:
        None

    异常:
        RuntimeError: 预期抛出的异常
    """

    async def _run():
        DatabasePool._pool = None
        DatabasePool._initialized = False
        with pytest.raises(RuntimeError, match="Database pool not initialized"):
            await DatabasePool.fetch("SELECT 1")

    asyncio.run(_run())


def test_database_pool_fetchrow_without_initialization_raises_runtime_error():
    """
    测试未初始化时调用 fetchrow() 抛出 RuntimeError。

    Returns:
        None

    异常:
        RuntimeError: 预期抛出的异常
    """

    async def _run():
        DatabasePool._pool = None
        DatabasePool._initialized = False
        with pytest.raises(RuntimeError, match="Database pool not initialized"):
            await DatabasePool.fetchrow("SELECT 1")

    asyncio.run(_run())
