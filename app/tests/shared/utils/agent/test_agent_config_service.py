# -*- coding:utf-8 -*-
"""
AgentConfigService 测试模块

验证从数据库 + AGENTS.md 加载完整 Agent 配置的流程。
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.shared.utils.agent.agent_config_service import (
    AgentConfigService,
    AgentNotFoundError,
)


def test_service_importable():
    """测试 agent_config_service 模块可导入。"""
    from app.shared.utils.agent import agent_config_service
    assert hasattr(agent_config_service, "AgentConfigService")
    assert hasattr(agent_config_service, "AgentNotFoundError")


def test_get_agent_config_loads_from_db_and_md():
    """测试 get_agent_config 从数据库和 AGENTS.md 加载配置。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "map_agent",
        "display_name": "地图智能体",
        "description": "地图控制",
        "agents_md_path": "agents/map_agent/AGENTS.md",
        "state_schema": {"map_center": {"type": "dict", "default": {"lat": 0}}},
        "context_schema": {"knowledge_root": {"type": "str", "default": "data/Knowledge"}},
        "mcp_tags": ["map"],
        "enabled": True,
    })
    db.fetch = AsyncMock(return_value=[
        {"tool_name": "explore", "is_enabled": True},
        {"tool_name": "query_knowledge", "is_enabled": True},
        {"tool_name": "disabled_tool", "is_enabled": False},
    ])

    loader = MagicMock()
    loader.load = MagicMock(return_value="# 地图智能体\n\n## 身份")

    service = AgentConfigService(db, loader)
    config = asyncio.run(service.get_agent_config("map_agent"))

    assert config.name == "map_agent"
    assert "# 地图智能体" in config.system_prompt
    assert "explore" in config.enabled_tool_names
    assert "query_knowledge" in config.enabled_tool_names
    assert "disabled_tool" not in config.enabled_tool_names
    assert config.mcp_tags == ["map"]


def test_get_agent_config_raises_on_not_found():
    """测试 agent 不存在时抛出 AgentNotFoundError。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value=None)

    loader = MagicMock()
    service = AgentConfigService(db, loader)

    with pytest.raises(AgentNotFoundError, match="map_agent"):
        asyncio.run(service.get_agent_config("map_agent"))


def test_get_agent_config_raises_on_disabled():
    """测试 agent 被禁用时抛出 AgentNotFoundError。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "map_agent",
        "agents_md_path": "x",
        "state_schema": {},
        "context_schema": {},
        "mcp_tags": [],
        "enabled": False,
    })

    loader = MagicMock()
    service = AgentConfigService(db, loader)

    with pytest.raises(AgentNotFoundError):
        asyncio.run(service.get_agent_config("map_agent"))


def test_list_agents_returns_enabled_only():
    """测试 list_agents 只返回启用的智能体。"""
    db = MagicMock()
    db.fetch = AsyncMock(return_value=[
        {"name": "map_agent", "display_name": "地图", "description": "地图控制"},
    ])

    loader = MagicMock()
    service = AgentConfigService(db, loader)
    result = asyncio.run(service.list_agents())
    assert len(result) == 1
    assert result[0]["name"] == "map_agent"


def test_get_agent_config_loads_skill_bindings():
    """测试 get_agent_config 加载 skill 绑定。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "map_agent",
        "agents_md_path": "agents/map_agent/AGENTS.md",
        "state_schema": {},
        "context_schema": {},
        "mcp_tags": [],
        "enabled": True,
    })

    db.fetch = AsyncMock(side_effect=[
        [{"tool_name": "explore", "is_enabled": True}],
        [{"skill_name": "data-skill", "is_enabled": True}],
    ])

    loader = MagicMock()
    loader.load = MagicMock(return_value="# test")

    service = AgentConfigService(db, loader)
    config = asyncio.run(service.get_agent_config("map_agent"))

    assert "data-skill" in config.enabled_skill_names


def test_create_agent_inserts_and_returns_row():
    """测试 create_agent 插入并返回新行。

    参数:
        None

    返回:
        None

    异常:
        AssertionError: 断言失败时抛出
    """
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "new_agent",
        "display_name": "新智能体",
        "description": "测试",
        "agents_md_path": "agents/new_agent/AGENTS.md",
        "state_schema": {},
        "context_schema": {},
        "mcp_tags": [],
        "enabled": True,
        "sort_order": 0,
    })
    loader = MagicMock()
    service = AgentConfigService(db, loader)
    config = {
        "name": "new_agent",
        "display_name": "新智能体",
        "description": "测试",
        "agents_md_path": "agents/new_agent/AGENTS.md",
    }
    result = asyncio.run(service.create_agent(config))
    assert result["name"] == "new_agent"
    assert result["display_name"] == "新智能体"
    # 验证 fetchrow 被调用（INSERT ... RETURNING *）
    db.fetchrow.assert_called_once()


def test_bind_tool_upserts_binding():
    """测试 bind_tool 执行 upsert 操作。

    参数:
        None

    返回:
        None

    异常:
        AssertionError: 断言失败时抛出
    """
    db = MagicMock()
    db.execute = AsyncMock()
    loader = MagicMock()
    service = AgentConfigService(db, loader)
    asyncio.run(service.bind_tool("map_agent", "explore", True))
    db.execute.assert_called_once()
    # 验证 SQL 含 ON CONFLICT
    call_args = db.execute.call_args
    sql = call_args.args[0] if call_args.args else call_args[0][0]
    assert "ON CONFLICT" in sql
    assert "agent_tool_bindings" in sql


def test_bind_skill_upserts_binding():
    """测试 bind_skill 执行 upsert 操作。

    参数:
        None

    返回:
        None

    异常:
        AssertionError: 断言失败时抛出
    """
    db = MagicMock()
    db.execute = AsyncMock()
    loader = MagicMock()
    service = AgentConfigService(db, loader)
    asyncio.run(service.bind_skill("map_agent", "data-skill", True))
    db.execute.assert_called_once()
    # 验证 SQL 含 ON CONFLICT
    call_args = db.execute.call_args
    sql = call_args.args[0] if call_args.args else call_args[0][0]
    assert "ON CONFLICT" in sql
    assert "agent_skill_bindings" in sql


# ============== _decode_jsonb 防御性反序列化测试 ==============

def test_decode_jsonb_none_returns_default():
    """测试 _decode_jsonb：None 入参应返回 default。"""
    assert AgentConfigService._decode_jsonb(None, {"k": "v"}) == {"k": "v"}
    assert AgentConfigService._decode_jsonb(None, []) == []


def test_decode_jsonb_str_parses_json():
    """测试 _decode_jsonb：str 入参应被 json.loads 解析为 dict/list。"""
    assert AgentConfigService._decode_jsonb(
        '{"a": 1}', {}
    ) == {"a": 1}
    assert AgentConfigService._decode_jsonb(
        '["map", "gis"]', []
    ) == ["map", "gis"]


def test_decode_jsonb_dict_passthrough():
    """测试 _decode_jsonb：dict 入参应原样返回（兼容 codec 已注册场景）。"""
    value = {"map_center": {"type": "dict", "default": {}}}
    assert AgentConfigService._decode_jsonb(value, {}) is value


def test_decode_jsonb_list_passthrough():
    """测试 _decode_jsonb：list 入参应原样返回（兼容 codec 已注册场景）。"""
    value = ["map", "gis"]
    assert AgentConfigService._decode_jsonb(value, []) is value


def test_decode_jsonb_invalid_str_falls_back_to_default():
    """测试 _decode_jsonb：无效 JSON 字符串应回退到 default 并记录 warning。"""
    result = AgentConfigService._decode_jsonb("not valid json {{", {"fallback": True})
    assert result == {"fallback": True}


def test_get_agent_config_decodes_str_jsonb_fields():
    """测试 get_agent_config：DB 返回 JSONB 字段为 str 时也能正确反序列化。

    模拟 asyncpg 未注册 JSONB codec 的真实场景：
    state_schema / context_schema / mcp_tags 三个字段均为 JSON 字符串，
    验证 get_agent_config 内部自动 json.loads 解析为 dict/list。
    """
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "map_agent",
        "display_name": "地图智能体",
        "description": "地图控制",
        "agents_md_path": "agents/map_agent/AGENTS.md",
        "state_schema": '{"map_zoom": {"type": "int", "default": 10}}',
        "context_schema": '{"knowledge_root": {"type": "str", "default": "data/Knowledge"}}',
        "mcp_tags": '["map"]',
        "enabled": True,
    })
    db.fetch = AsyncMock(side_effect=[
        [{"tool_name": "explore", "is_enabled": True}],
        [{"skill_name": "data-skill", "is_enabled": True}],
    ])

    loader = MagicMock()
    loader.load = MagicMock(return_value="# 地图智能体\n\n## 身份")

    service = AgentConfigService(db, loader)
    config = asyncio.run(service.get_agent_config("map_agent"))

    # state_schema 被解析为 dict，能传入 build_agent_state
    assert config.state_class is not None
    # mcp_tags 被解析为 list
    assert config.mcp_tags == ["map"]

