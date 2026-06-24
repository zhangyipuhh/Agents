# -*- coding:utf-8 -*-
"""
seed_mcp_servers 数据库种子脚本测试模块

验证 seed_mcp_servers 脚本能从 YAML 加载 MCP server 配置并写入
mcp_server_configs 表，且表非空时跳过。
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock


def test_seed_mcp_servers_importable():
    """测试 seed_mcp_servers 模块可导入。"""
    from app.migrations import seed_mcp_servers
    assert hasattr(seed_mcp_servers, "seed_mcp_servers")
    assert callable(seed_mcp_servers.seed_mcp_servers)


def test_seed_mcp_servers_skips_when_table_non_empty():
    """测试表非空时跳过导入并返回 0。

    返回值：
        None

    异常：
        AssertionError: 断言失败时抛出
    """
    from app.migrations import seed_mcp_servers

    db = MagicMock()
    # 第一次 fetch 已有 2 条记录
    db.fetch = AsyncMock(return_value=[
        {"name": "existing_a"},
        {"name": "existing_b"},
    ])

    inserted = asyncio.run(seed_mcp_servers.seed_mcp_servers(db))

    assert inserted == 0
    # 不应再调用 fetch 第二次（即不应触发 seed_from_yaml_if_empty 内的 fetch）
    assert db.fetch.await_count == 1


def test_seed_mcp_servers_inserts_from_yaml(monkeypatch):
    """测试表为空时通过 McpConfigService 从 YAML 导入。

    返回值：
        None

    异常：
        AssertionError: 断言失败时抛出
    """
    from app.migrations import seed_mcp_servers
    from app.shared.utils.agent import mcp_service

    # FakeDB：第一次 fetch 返回空列表，create_server 内调 get_server 的
    # fetchrow 也返回 None（表示 name 不存在），然后 INSERT 的 fetchrow
    # 返回模拟的新行；最后一次 fetch 用于计算 inserted。
    inserted_rows: list = []

    class FakeDB:
        """模拟 asyncpg.Connection，支持 seed 流程的所有调用。"""

        def __init__(self) -> None:
            self.fetch_calls = 0
            self.fetchrow_calls = 0

        async def fetch(self, sql, *args):
            """模拟 fetch。

            调用顺序：
            1. seed_mcp_servers.seed_mcp_servers(db) 内的 rows_before → 返回 []
            2. service.seed_from_yaml_if_empty() 内的检查 → 返回 []（表仍空）
            3. seed_mcp_servers.seed_mcp_servers(db) 内的 rows_after → 返回 2 条（已写入）
            """
            self.fetch_calls += 1
            if "SELECT name FROM mcp_server_configs" in sql:
                if self.fetch_calls <= 2:
                    return []  # 第一次和第二次：表为空
                return [{"name": "server_a"}, {"name": "server_b"}]  # 第三次：已写入 2 条
            return []

        async def fetchrow(self, sql, *args):
            """模拟 fetchrow：name 存在性检查返回 None（可创建），INSERT 返回模拟行。"""
            self.fetchrow_calls += 1
            if "SELECT * FROM mcp_server_configs WHERE name" in sql:
                return None  # 不存在，可创建
            if "INSERT INTO mcp_server_configs" in sql:
                row = {
                    "name": args[0], "display_name": args[1], "type": args[2],
                    "url": args[3], "command": args[4], "timeout": args[5],
                    "read_timeout": args[6], "tags": args[7], "enabled": args[8],
                    "progress_reporting": args[9], "tool_config": args[10],
                    "sampling": args[11],
                }
                inserted_rows.append(args)
                return row
            return None

    # monkeypatch _load_yaml_seed 返回固定配置（避免依赖真实 YAML 文件）
    def fake_load_yaml_seed(self):
        return {
            "server_a": {
                "type": "sse",
                "url": "http://example.com/sse_a",
                "tags": ["map"],
                "progress_reporting": {"enabled": False},
                "tool_config": {
                    "enable_injection": True,
                    "default_param_keys": [],
                    "hidden_param_keys": [],
                    "unwrap_result": False,
                },
                "sampling": {"enabled": False},
            },
            "server_b": {
                "type": "sse",
                "url": "http://example.com/sse_b",
                "tags": ["map", "geo"],
                "progress_reporting": {"enabled": True},
                "tool_config": {
                    "enable_injection": False,
                    "default_param_keys": ["session_id"],
                    "hidden_param_keys": [],
                    "unwrap_result": True,
                },
                "sampling": {"enabled": False},
            },
        }

    monkeypatch.setattr(
        mcp_service.McpConfigService,
        "_load_yaml_seed",
        fake_load_yaml_seed,
    )

    db = FakeDB()
    inserted = asyncio.run(seed_mcp_servers.seed_mcp_servers(db))

    # 应写入 2 条
    assert inserted == 2
    assert len(inserted_rows) == 2
    # 验证 server_a 写入时 JSONB 字段已序列化为字符串
    first = inserted_rows[0]
    assert first[0] == "server_a"
    assert isinstance(first[7], str), "tags 应为 JSON 字符串"
    assert isinstance(first[9], str), "progress_reporting 应为 JSON 字符串"
    assert isinstance(first[10], str), "tool_config 应为 JSON 字符串"
    assert isinstance(first[11], str), "sampling 应为 JSON 字符串"
    assert len(inserted_rows) == 2
    # 验证 server_a 写入时 JSONB 字段已序列化为字符串
    first = inserted_rows[0]
    assert first[0] == "server_a"
    assert isinstance(first[7], str), "tags 应为 JSON 字符串"
    assert isinstance(first[9], str), "progress_reporting 应为 JSON 字符串"
    assert isinstance(first[10], str), "tool_config 应为 JSON 字符串"
    assert isinstance(first[11], str), "sampling 应为 JSON 字符串"


def test_seed_mcp_servers_handles_empty_yaml(monkeypatch):
    """测试 YAML 为空时返回 0，不抛异常。

    返回值：
        None

    异常：
        AssertionError: 断言失败时抛出
    """
    from app.migrations import seed_mcp_servers
    from app.shared.utils.agent import mcp_service

    class FakeDB:
        """模拟 DB：表空 + YAML 加载为空。"""

        async def fetch(self, sql, *args):
            return []

        async def fetchrow(self, sql, *args):
            return None

    monkeypatch.setattr(
        mcp_service.McpConfigService,
        "_load_yaml_seed",
        lambda self: {},
    )

    db = FakeDB()
    inserted = asyncio.run(seed_mcp_servers.seed_mcp_servers(db))
    assert inserted == 0
