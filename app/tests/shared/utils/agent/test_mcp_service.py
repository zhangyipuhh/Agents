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


def test_load_yaml_seed_passes_path_to_loader(tmp_path, monkeypatch):
    """测试 _load_yaml_seed 把 str 路径转 Path 再传给 load_mcp_config。

    回归测试：修复前 _load_yaml_seed 直接把 str 传给 load_mcp_config，
    后者调用 config_path.exists() 抛 AttributeError，导致 lifespan
    启动种子失败、MCP 表一直为空。
    """
    from pathlib import Path

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "mcp_servers:\n"
        "  test_server:\n"
        "    type: sse\n"
        "    url: http://test/sse\n",
        encoding="utf-8",
    )

    service = McpConfigService(MagicMock())

    # 用 mock 替换 settings 链：避免依赖真实配置模块
    fake_settings = MagicMock()
    fake_settings.mcp.mcp_config_path = str(config_file)
    monkeypatch.setattr(
        "app.core.config.config.settings",
        fake_settings,
    )

    # 捕获传给 load_mcp_config 的实参，验证类型为 Path
    captured = {}

    def fake_loader(path):
        captured["path"] = path
        return {"test_server": {"type": "sse", "url": "http://test/sse"}}

    monkeypatch.setattr(
        "mcpClient.shared.config_loader.load_mcp_config",
        fake_loader,
    )

    result = service._load_yaml_seed()

    assert result == {"test_server": {"type": "sse", "url": "http://test/sse"}}
    # 关键断言：传入的必须是 Path 实例（修复前是 str 会抛 AttributeError）
    assert isinstance(captured["path"], Path)
    assert captured["path"] == config_file


def test_load_yaml_seed_returns_empty_on_missing_file(tmp_path, monkeypatch):
    """测试 YAML 文件不存在时返回空 dict 并记录 warning。"""
    service = McpConfigService(MagicMock())

    fake_settings = MagicMock()
    fake_settings.mcp.mcp_config_path = str(tmp_path / "nonexistent.yaml")
    monkeypatch.setattr("app.core.config.config.settings", fake_settings)

    result = service._load_yaml_seed()
    assert result == {}


# ============== _decode_jsonb / _decode_row 防御性反序列化测试 ==============

def test_decode_jsonb_none_returns_default():
    """测试 _decode_jsonb：None 入参应返回 default。"""
    assert McpConfigService._decode_jsonb(None, []) == []
    assert McpConfigService._decode_jsonb(None, {"enabled": False}) == {"enabled": False}


def test_decode_jsonb_str_parses_json():
    """测试 _decode_jsonb：str 入参应被 json.loads 解析。"""
    assert McpConfigService._decode_jsonb('["map","geo"]', []) == ["map", "geo"]
    assert McpConfigService._decode_jsonb(
        '{"enabled": true}', {"enabled": False}
    ) == {"enabled": True}


def test_decode_jsonb_dict_list_passthrough():
    """测试 _decode_jsonb：dict/list 入参应原样返回（兼容 codec 已注册场景）。"""
    value = {"enabled": True}
    assert McpConfigService._decode_jsonb(value, {"enabled": False}) is value
    assert McpConfigService._decode_jsonb(["a"], []) == ["a"]


def test_decode_row_decodes_all_jsonb_fields():
    """测试 _decode_row：DB row 中所有 JSONB 字段都被反序列化。"""
    row = {
        "name": "amap",
        "tags": '["map", "geo"]',
        "progress_reporting": '{"enabled": true}',
        "tool_config": '{"enable_injection": true, "default_param_keys": ["session_id"]}',
        "sampling": '{"enabled": false}',
        "command": '["python", "server.py"]',
        "enabled": True,
    }
    result = McpConfigService._decode_row(row)
    assert result["tags"] == ["map", "geo"]
    assert result["progress_reporting"] == {"enabled": True}
    assert result["tool_config"]["enable_injection"] is True
    assert result["tool_config"]["default_param_keys"] == ["session_id"]
    assert result["sampling"] == {"enabled": False}
    assert result["command"] == ["python", "server.py"]
    # 非 JSONB 字段保持原样
    assert result["enabled"] is True


def test_decode_row_handles_none_jsonb():
    """测试 _decode_row：JSONB 字段为 None 时使用合理默认值。"""
    row = {
        "name": "stdio_server",
        "tags": None,
        "progress_reporting": None,
        "tool_config": None,
        "sampling": None,
        "command": None,
    }
    result = McpConfigService._decode_row(row)
    assert result["tags"] == []
    assert result["progress_reporting"] == {"enabled": False}
    assert result["tool_config"] == {"enabled": False}
    assert result["sampling"] == {"enabled": False}
    assert result["command"] is None


def test_list_servers_decodes_str_jsonb():
    """测试 list_servers：DB 返回 str JSONB 也能正确反序列化。"""
    db = MagicMock()
    db.fetch = AsyncMock(return_value=[
        {
            "name": "amap",
            "tags": '["map"]',
            "progress_reporting": '{"enabled": false}',
            "tool_config": '{"enable_injection": false}',
            "sampling": '{"enabled": false}',
            "command": None,
        },
    ])

    service = McpConfigService(db)
    result = asyncio.run(service.list_servers())

    assert len(result) == 1
    # 关键：JSONB 字段已从 str 反序列化为 list / dict
    assert result[0]["tags"] == ["map"]
    assert result[0]["progress_reporting"] == {"enabled": False}
    assert result[0]["tool_config"] == {"enable_injection": False}
