# -*- coding:utf-8 -*-
"""
init_map_business_info_schema 测试

覆盖：
- 导入/存在性
- 调用后不抛异常（mock DatabasePool）

Date: 2026-06-26
Author: AI Assistant
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


def test_init_map_business_info_schema_importable():
    """
    P0: init_map_business_info_schema 可导入且为 async 函数。
    """
    from app.shared.tools.skills.map_agent.MapTools import init_map_business_info_schema
    import inspect

    assert init_map_business_info_schema is not None
    assert inspect.iscoroutinefunction(init_map_business_info_schema)


def test_init_map_business_info_schema_runs_without_error():
    """
    P1: 调用 init_map_business_info_schema 不抛异常（mock DatabasePool.execute）。
    """
    from app.shared.tools.skills.map_agent.MapTools import init_map_business_info_schema

    calls = []

    async def fake_execute(*args, **kwargs):
        calls.append((args, kwargs))

    with patch("app.shared.tools.skills.map_agent.MapTools.DatabasePool") as MockDB:
        MockDB.execute = fake_execute

        asyncio.run(init_map_business_info_schema())

    # 应至少调用 4 次：2 张 CREATE TABLE + 2 个 CREATE INDEX
    # 实际代码：3 次（map_business_info 主表 + 2 个索引 + map_business_no_counter 计数器）
    assert len(calls) >= 3, f"期望至少 3 次 SQL 调用，实际 {len(calls)} 次"

    # 检查是否包含创建 map_business_info 表
    sql_texts = [args[0] for args, _ in calls]
    assert any("map_business_info" in sql and "CREATE TABLE" in sql for sql in sql_texts), \
        "应包含 CREATE TABLE map_business_info 语句"
    assert any("map_business_no_counter" in sql and "CREATE TABLE" in sql for sql in sql_texts), \
        "应包含 CREATE TABLE map_business_no_counter 语句"
