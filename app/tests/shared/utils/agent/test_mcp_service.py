# -*- coding:utf-8 -*-
"""
MCP 配置 CRUD 服务测试模块

验证 McpConfigService 能从数据库加载 server 配置、增删改查、
空表时从 YAML 导入种子数据。
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.shared.utils.agent.mcp_service import McpConfigService, McpServerConfig


def test_service_importable():
    """测试 mcp_service 模块可导入。"""
    from app.shared.utils.agent import mcp_service
    assert hasattr(mcp_service, "McpConfigService")
    assert hasattr(mcp_service, "McpServerConfig")


def test_list_servers_returns_rows():
    """测试 list_servers 返回数据库所有 server 配置。"""
    db = MagicMock()
    db.fetch = AsyncMock(return_value=[
        {"name": "amap", "display_name": "高德地图", "type": "sse", "url": "http://x", "enabled": True},
    ])

    service = McpConfigService(db)
    result = asyncio.run(service.list_servers())
    assert len(result) == 1
    assert result[0]["name"] == "amap"


def test_get_server_returns_config():
    """测试 get_server 返回单个 server 配置。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "amap", "display_name": "高德地图", "type": "sse",
        "url": "http://x", "enabled": True, "tags": ["map"],
    })

    service = McpConfigService(db)
    result = asyncio.run(service.get_server("amap"))
    assert result["name"] == "amap"


def test_create_server_inserts_row():
    """测试 create_server 写入数据库。"""
    db = MagicMock()
    # fetchrow 被调用两次：第一次为 get_server 存在性检查（返回 None 表示不存在），
    # 第二次为 INSERT ... RETURNING *（返回新插入行）
    db.fetchrow = AsyncMock(side_effect=[
        None,
        {
            "name": "amap", "display_name": "高德", "type": "sse",
            "url": "http://x", "enabled": True, "tags": [], "command": None,
            "timeout": 5, "read_timeout": 300, "tool_config": {}, "sampling": {},
            "progress_reporting": {}, "methods_synced_at": None,
        },
    ])

    service = McpConfigService(db)
    config = McpServerConfig(name="amap", display_name="高德", type="sse", url="http://x")
    result = asyncio.run(service.create_server(config))
    assert result["name"] == "amap"
    db.fetchrow.assert_awaited()


def test_delete_server_removes_row():
    """测试 delete_server 删除数据库行和关联 methods。"""
    db = MagicMock()
    db.execute = AsyncMock(return_value="DELETE 1")

    service = McpConfigService(db)
    asyncio.run(service.delete_server("amap"))
    assert db.execute.await_count >= 2


def test_toggle_server_updates_enabled():
    """测试 toggle_server 更新 enabled 字段。"""
    db = MagicMock()
    db.execute = AsyncMock(return_value="UPDATE 1")

    service = McpConfigService(db)
    asyncio.run(service.toggle_server("amap", enabled=False))
    db.execute.assert_awaited()


def test_list_methods_returns_rows():
    """测试 list_methods 返回 server 下所有 method。"""
    db = MagicMock()
    db.fetch = AsyncMock(return_value=[
        {"server_name": "amap", "method_name": "search", "enabled": True},
        {"server_name": "amap", "method_name": "route", "enabled": False},
    ])

    service = McpConfigService(db)
    result = asyncio.run(service.list_methods("amap"))
    assert len(result) == 2
    assert result[0]["method_name"] == "search"


def test_toggle_method_updates_enabled():
    """测试 toggle_method 更新 method 的 enabled 字段。"""
    db = MagicMock()
    db.execute = AsyncMock(return_value="UPDATE 1")

    service = McpConfigService(db)
    asyncio.run(service.toggle_method("amap", "search", enabled=False))
    db.execute.assert_awaited()


def test_seed_from_yaml_when_empty():
    """测试数据库为空时从 YAML 导入种子数据。"""
    db = MagicMock()
    db.fetch = AsyncMock(return_value=[])
    # fetchrow 被调用两次：第一次为 create_server 内 get_server 存在性检查（返回 None），
    # 第二次为 INSERT ... RETURNING *（返回新插入行）
    db.fetchrow = AsyncMock(side_effect=[None, {"name": "amap"}])

    service = McpConfigService(db)
    with patch.object(service, "_load_yaml_seed", return_value={"amap": {"type": "sse", "url": "http://x"}}):
        asyncio.run(service.seed_from_yaml_if_empty())

    db.fetchrow.assert_awaited()
