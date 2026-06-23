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
