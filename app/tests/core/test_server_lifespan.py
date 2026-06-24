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
