# -*- coding:utf-8 -*-
"""
map_agent 数据库种子脚本测试模块

验证 seed_map_agent 脚本能向 agents / agent_tool_bindings / agent_skill_bindings
表写入 map_agent 的初始配置，且重复执行幂等。
"""
import asyncio


def test_seed_map_agent_importable():
    """测试 seed_map_agent 模块可导入且关键常量存在。"""
    from app.migrations import seed_map_agent
    assert hasattr(seed_map_agent, "seed_map_agent")
    assert hasattr(seed_map_agent, "MAP_AGENT_STATE_SCHEMA")
    assert hasattr(seed_map_agent, "MAP_AGENT_TOOLS")
    assert hasattr(seed_map_agent, "MAP_AGENT_SKILLS")
    assert len(seed_map_agent.MAP_AGENT_TOOLS) == 9
    assert len(seed_map_agent.MAP_AGENT_SKILLS) == 1


def test_seed_map_agent_inserts_rows():
    """测试 seed_map_agent 能向 agents 表插入 map_agent 记录。

    返回值：
        None

    异常：
        AssertionError: 断言失败时抛出
    """
    from app.migrations import seed_map_agent

    inserted = []
    updated = []
    tool_bindings_inserted = []
    skill_bindings_inserted = []

    class FakeDB:
        """模拟 asyncpg.Connection，记录 INSERT/UPDATE 调用。"""

        async def fetchrow(self, sql, *args):
            """模拟 fetchrow：agents 表查询返回 None 表示记录不存在。"""
            if "SELECT" in sql and "agents" in sql:
                return None  # 模拟首次执行，记录不存在
            return None

        async def execute(self, sql, *args):
            """模拟 execute：根据 SQL 类型记录到对应列表。"""
            if "INSERT" in sql and "agents" in sql:
                # 验证 JSONB 字段已序列化为字符串
                assert isinstance(args[4], str), "state_schema 应为 JSON 字符串"
                assert isinstance(args[5], str), "context_schema 应为 JSON 字符串"
                assert isinstance(args[6], str), "mcp_tags 应为 JSON 字符串"
                inserted.append(args)
            elif "INSERT" in sql and "agent_tool_bindings" in sql:
                tool_bindings_inserted.append(args)
            elif "INSERT" in sql and "agent_skill_bindings" in sql:
                skill_bindings_inserted.append(args)
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
    assert len(tool_bindings_inserted) == 9  # MAP_AGENT_TOOLS 有 9 个工具
    assert len(skill_bindings_inserted) == 1  # MAP_AGENT_SKILLS 有 1 个 skill


def test_seed_map_agent_idempotent():
    """测试 seed_map_agent 重复执行不报错（已存在则 UPDATE）。

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
