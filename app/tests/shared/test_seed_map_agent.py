# -*- coding:utf-8 -*-
"""
map_agent 数据库种子脚本测试模块

验证 seed_map_agent 脚本能向 agents / agent_tool_bindings / agent_skill_bindings
表写入 map_agent 的初始配置，且重复执行幂等。
"""
import asyncio
import pytest


def test_seed_map_agent_importable():
    """测试 seed_map_agent 模块可导入。"""
    from app.migrations import seed_map_agent
    assert hasattr(seed_map_agent, "seed_map_agent")


def test_seed_map_agent_inserts_rows(monkeypatch):
    """测试 seed_map_agent 能向 agents 表插入 map_agent 记录。

    参数：
        monkeypatch: pytest fixture，用于替换运行时依赖

    返回值：
        None

    异常：
        AssertionError: 断言失败时抛出
    """
    from app.migrations import seed_map_agent

    inserted = []
    updated = []

    class FakeDB:
        """模拟 asyncpg.Connection，记录 INSERT/UPDATE 调用。"""

        async def fetchrow(self, sql, *args):
            """模拟 fetchrow：agents 表查询返回 None 表示记录不存在。"""
            if "SELECT" in sql and "agents" in sql:
                return None  # 模拟首次执行，记录不存在
            return None

        async def execute(self, sql, *args):
            """模拟 execute：根据 SQL 类型记录到 inserted/updated 列表。"""
            if "INSERT" in sql and "agents" in sql:
                inserted.append(args)
            elif "UPDATE" in sql:
                updated.append(args)
            return "OK"

        async def fetch(self, sql, *args):
            """模拟 fetch：返回空列表。"""
            return []

    async def run():
        await seed_map_agent.seed_map_agent(FakeDB())

    asyncio.run(run())
    assert len(inserted) == 1
    assert inserted[0][0] == "map_agent"  # name 参数


def test_seed_map_agent_idempotent(monkeypatch):
    """测试 seed_map_agent 重复执行不报错（已存在则 UPDATE）。

    参数：
        monkeypatch: pytest fixture，用于替换运行时依赖

    返回值：
        None

    异常：
        AssertionError: 断言失败时抛出
    """
    from app.migrations import seed_map_agent

    class FakeDB:
        """模拟 asyncpg.Connection，agents 表查询返回已存在记录。"""

        async def fetchrow(self, sql, *args):
            """模拟 fetchrow：agents 表查询返回已存在记录。"""
            if "SELECT" in sql and "agents" in sql:
                return {"name": "map_agent"}  # 模拟已存在
            return None

        async def execute(self, sql, *args):
            """模拟 execute：统一返回 OK。"""
            return "OK"

        async def fetch(self, sql, *args):
            """模拟 fetch：返回空列表。"""
            return []

    async def run():
        await seed_map_agent.seed_map_agent(FakeDB())

    # 不抛异常即通过
    asyncio.run(run())
