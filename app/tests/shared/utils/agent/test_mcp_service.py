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
    """测试 create_server 写入数据库并同步缓存。"""
    db = MagicMock()
    new_row = {
        "name": "amap", "display_name": "高德", "type": "sse",
        "url": "http://x", "enabled": True, "tags": [], "command": None,
        "timeout": 5, "read_timeout": 300, "tool_config": {}, "sampling": {},
        "progress_reporting": {}, "methods_synced_at": None,
    }
    # fetchrow 被调用三次：
    # 1. get_server 存在性检查（返回 None 表示不存在）
    # 2. INSERT ... RETURNING *（返回新插入行）
    # 3. _refresh_cache 重新从 DB 加载该 server（返回新插入行）
    db.fetchrow = AsyncMock(side_effect=[None, new_row, new_row])

    service = McpConfigService(db)
    config = McpServerConfig(name="amap", display_name="高德", type="sse", url="http://x")
    result = asyncio.run(service.create_server(config))
    assert result["name"] == "amap"
    db.fetchrow.assert_awaited()
    # 缓存应已同步
    assert "amap" in service._cache


def test_delete_server_removes_row():
    """测试 delete_server 删除数据库行和关联 methods。"""
    db = MagicMock()
    db.execute = AsyncMock(return_value="DELETE 1")

    service = McpConfigService(db)
    asyncio.run(service.delete_server("amap"))
    assert db.execute.await_count >= 2


def test_toggle_server_updates_enabled():
    """测试 toggle_server 更新 enabled 字段并同步缓存。"""
    db = MagicMock()
    db.execute = AsyncMock(return_value="UPDATE 1")
    # _refresh_cache 会调用 fetchrow 重新加载该 server
    db.fetchrow = AsyncMock(return_value={
        "name": "amap", "enabled": False, "tags": [], "command": None,
        "progress_reporting": {}, "tool_config": {}, "sampling": {},
    })

    service = McpConfigService(db)
    asyncio.run(service.toggle_server("amap", enabled=False))
    db.execute.assert_awaited()
    # _refresh_cache 应被调用以同步缓存
    db.fetchrow.assert_awaited()


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
    # fetchrow 被调用三次（每个 create_server）：
    # 1. get_server 存在性检查（返回 None）
    # 2. INSERT ... RETURNING *（返回新插入行）
    # 3. _refresh_cache 重新加载（返回新插入行）
    db.fetchrow = AsyncMock(side_effect=[None, {"name": "amap"}, {"name": "amap"}])

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


# ============== 2026-06-24 新增：args/env/headers/connect_timeout 字段测试 ==============


def test_mcp_server_config_has_new_fields():
    """测试 McpServerConfig dataclass 含 4 个新字段且默认值正确。"""
    config = McpServerConfig(name="test")
    assert config.args == []
    assert config.env == {}
    assert config.headers == {}
    assert config.connect_timeout == 10


def test_decode_row_decodes_new_jsonb_fields():
    """测试 _decode_row：args/env/headers 三个新 JSONB 字段被正确反序列化。"""
    row = {
        "name": "stdio_server",
        "args": '["-y", "server"]',
        "env": '{"KEY": "VAL"}',
        "headers": '{"Authorization": "Bearer token"}',
        "connect_timeout": 30,
        "tags": '[]',
        "progress_reporting": '{"enabled": false}',
        "tool_config": '{"enable_injection": true}',
        "sampling": '{"enabled": false}',
        "command": None,
    }
    result = McpConfigService._decode_row(row)
    assert result["args"] == ["-y", "server"]
    assert result["env"] == {"KEY": "VAL"}
    assert result["headers"] == {"Authorization": "Bearer token"}
    assert result["connect_timeout"] == 30


def test_decode_row_new_fields_none_uses_defaults():
    """测试 _decode_row：args/env/headers 为 None 时使用合理默认值。"""
    row = {
        "name": "amap",
        "args": None,
        "env": None,
        "headers": None,
        "connect_timeout": None,
        "tags": None,
        "progress_reporting": None,
        "tool_config": None,
        "sampling": None,
        "command": None,
    }
    result = McpConfigService._decode_row(row)
    assert result["args"] == []
    assert result["env"] == {}
    assert result["headers"] == {}
    assert result["connect_timeout"] == 10


def test_create_server_includes_new_fields():
    """测试 create_server SQL 包含 4 个新字段占位符。"""
    import inspect
    source = inspect.getsource(McpConfigService.create_server)
    assert "args" in source
    assert "env" in source
    assert "headers" in source
    assert "connect_timeout" in source


def test_update_server_includes_new_fields():
    """测试 update_server SQL 包含 4 个新字段占位符。"""
    import inspect
    source = inspect.getsource(McpConfigService.update_server)
    assert "args" in source
    assert "env" in source
    assert "headers" in source
    assert "connect_timeout" in source


def test_seed_from_yaml_reads_new_fields():
    """测试 seed_from_yaml_if_empty 从 yaml 读 4 个新字段。"""
    import inspect
    source = inspect.getsource(McpConfigService.seed_from_yaml_if_empty)
    assert 'cfg.get("args"' in source
    assert 'cfg.get("env"' in source
    assert 'cfg.get("headers"' in source
    assert 'cfg.get("connect_timeout"' in source


# ============== 2026-06-25 新增：缓存层测试 ==============


def test_init_has_cache_fields():
    """测试 __init__ 初始化 _cache 和 _cache_lock 字段。

    验证目标：
        - _cache 为空 dict
        - _cache_lock 为 asyncio.Lock 实例
    """
    import asyncio as _asyncio

    service = McpConfigService(MagicMock())
    assert service._cache == {}
    assert isinstance(service._cache_lock, _asyncio.Lock)


def test_preload_all_loads_all_servers():
    """测试 preload_all 将所有 server 配置加载到缓存。

    验证目标：
        - DB 返回的行被解码后写入 _cache（key 为 name）
        - 旧缓存被清空
    """
    db = MagicMock()
    db.fetch = AsyncMock(return_value=[
        {"name": "amap", "type": "sse", "url": "http://a", "enabled": True,
         "tags": '["map"]', "progress_reporting": '{"enabled": false}',
         "tool_config": '{"enable_injection": true}', "sampling": '{"enabled": false}',
         "command": None},
        {"name": "weather", "type": "sse", "url": "http://b", "enabled": False,
         "tags": '[]', "progress_reporting": '{"enabled": false}',
         "tool_config": '{"enable_injection": false}', "sampling": '{"enabled": false}',
         "command": None},
    ])

    service = McpConfigService(db)
    # 预置旧缓存，验证 preload_all 会清空
    service._cache["stale"] = {"name": "stale"}

    asyncio.run(service.preload_all())

    assert "stale" not in service._cache
    assert "amap" in service._cache
    assert "weather" in service._cache
    # JSONB 字段应被解码
    assert service._cache["amap"]["tags"] == ["map"]
    assert service._cache["weather"]["enabled"] is False


def test_refresh_cache_loads_single_server():
    """测试 _refresh_cache 从 DB 加载单个 server 到缓存。

    验证目标：
        - DB 返回行时，解码后写入 _cache[name]
        - JSONB 字段被正确解码
    """
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "amap", "enabled": True,
        "tags": '["map"]', "progress_reporting": '{"enabled": false}',
        "tool_config": '{"enable_injection": true}', "sampling": '{"enabled": false}',
        "command": None,
    })

    service = McpConfigService(db)
    asyncio.run(service._refresh_cache("amap"))

    assert "amap" in service._cache
    assert service._cache["amap"]["tags"] == ["map"]
    db.fetchrow.assert_awaited()


def test_refresh_cache_removes_when_not_found():
    """测试 _refresh_cache：DB 中 server 不存在时从缓存移除。

    验证目标：
        - DB 返回 None 时，缓存中对应 name 被移除（保持一致）
    """
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value=None)

    service = McpConfigService(db)
    # 预置缓存项，验证会被移除
    service._cache["amap"] = {"name": "amap", "stale": True}

    asyncio.run(service._refresh_cache("amap"))

    assert "amap" not in service._cache


def test_invalidate_cache_removes_entry():
    """测试 _invalidate_cache 从缓存移除单个 server。

    验证目标：
        - 指定 name 的缓存项被移除
        - 不存在的 name 不报错（幂等）
        - 不访问 DB

    注意：
        两次 _invalidate_cache 调用需在同一 asyncio.run 内执行，
        避免 asyncio.Lock 绑定到已关闭的事件循环。
    """
    db = MagicMock()
    service = McpConfigService(db)
    service._cache["amap"] = {"name": "amap"}
    service._cache["weather"] = {"name": "weather"}

    async def _run():
        # 第一次移除存在的项
        await service._invalidate_cache("amap")
        # 幂等：再次移除不存在的 name 不报错
        await service._invalidate_cache("nonexistent")

    asyncio.run(_run())

    assert "amap" not in service._cache
    assert "weather" in service._cache
    # 不应访问 DB
    db.fetchrow.assert_not_called()
    db.execute.assert_not_called()


def test_clear_cache_empties_all():
    """测试 _clear_cache 清空所有缓存。

    验证目标：
        - 所有缓存项被移除
        - _cache 变为空 dict
    """
    service = McpConfigService(MagicMock())
    service._cache["amap"] = {"name": "amap"}
    service._cache["weather"] = {"name": "weather"}

    asyncio.run(service._clear_cache())

    assert service._cache == {}


def test_list_servers_reads_from_cache():
    """测试 list_servers 缓存命中时直接返回缓存值。

    验证目标：
        - 缓存非空时，不访问 DB
        - 返回缓存值的浅拷贝列表（外部修改不影响缓存）
    """
    db = MagicMock()
    db.fetch = AsyncMock(return_value=[{"name": "should_not_be_used"}])

    service = McpConfigService(db)
    service._cache["amap"] = {"name": "amap", "enabled": True}
    service._cache["weather"] = {"name": "weather", "enabled": False}

    result = asyncio.run(service.list_servers())

    assert len(result) == 2
    names = {r["name"] for r in result}
    assert names == {"amap", "weather"}
    # 不应访问 DB
    db.fetch.assert_not_called()
    # 返回浅拷贝：修改返回值不影响缓存
    result[0]["enabled"] = "modified"
    assert service._cache["amap"]["enabled"] is True


def test_list_servers_falls_back_to_db_and_backfills_cache():
    """测试 list_servers 缓存为空时从 DB 加载并回填缓存。

    验证目标：
        - 缓存为空时访问 DB
        - DB 返回行被解码并写入缓存
        - 返回值与 DB 行一致
    """
    db = MagicMock()
    db.fetch = AsyncMock(return_value=[
        {"name": "amap", "type": "sse", "enabled": True,
         "tags": '["map"]', "progress_reporting": '{"enabled": false}',
         "tool_config": '{"enable_injection": true}', "sampling": '{"enabled": false}',
         "command": None},
    ])

    service = McpConfigService(db)
    result = asyncio.run(service.list_servers())

    assert len(result) == 1
    assert result[0]["name"] == "amap"
    assert result[0]["tags"] == ["map"]
    # 缓存应已回填
    assert "amap" in service._cache
    db.fetch.assert_awaited()


def test_get_server_reads_from_cache():
    """测试 get_server 缓存命中时直接返回缓存值。

    验证目标：
        - 缓存命中时不访问 DB
        - 返回缓存值的浅拷贝（外部修改不影响缓存）
    """
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={"name": "should_not_be_used"})

    service = McpConfigService(db)
    service._cache["amap"] = {"name": "amap", "enabled": True}

    result = asyncio.run(service.get_server("amap"))

    assert result["name"] == "amap"
    assert result["enabled"] is True
    # 不应访问 DB
    db.fetchrow.assert_not_called()
    # 返回浅拷贝
    result["enabled"] = "modified"
    assert service._cache["amap"]["enabled"] is True


def test_get_server_falls_back_to_db_and_backfills_cache():
    """测试 get_server 缓存未命中时从 DB 加载并写入缓存。

    验证目标：
        - 缓存未命中时访问 DB
        - DB 返回行时解码并写入缓存
        - 返回浅拷贝
    """
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "amap", "enabled": True,
        "tags": '["map"]', "progress_reporting": '{"enabled": false}',
        "tool_config": '{"enable_injection": true}', "sampling": '{"enabled": false}',
        "command": None,
    })

    service = McpConfigService(db)
    result = asyncio.run(service.get_server("amap"))

    assert result["name"] == "amap"
    assert result["tags"] == ["map"]
    # 缓存应已回填
    assert "amap" in service._cache
    db.fetchrow.assert_awaited()


def test_get_server_returns_none_when_not_found():
    """测试 get_server：DB 中不存在时返回 None 且不写入缓存。

    验证目标：
        - DB 返回 None 时，get_server 返回 None
        - 缓存中不写入任何项
    """
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value=None)

    service = McpConfigService(db)
    result = asyncio.run(service.get_server("nonexistent"))

    assert result is None
    assert "nonexistent" not in service._cache


def test_delete_server_invalidates_cache():
    """测试 delete_server 写 DB 后使缓存失效。

    验证目标：
        - delete_server 执行后，对应 name 从缓存移除
    """
    db = MagicMock()
    db.execute = AsyncMock(return_value="DELETE 1")

    service = McpConfigService(db)
    service._cache["amap"] = {"name": "amap"}

    asyncio.run(service.delete_server("amap"))

    assert "amap" not in service._cache
    # 应执行两次 DELETE（methods + config）
    assert db.execute.await_count >= 2
