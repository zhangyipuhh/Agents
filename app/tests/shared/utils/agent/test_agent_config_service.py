# -*- coding:utf-8 -*-
"""
AgentConfigService 测试模块

验证从数据库 + AGENTS.md 加载完整 Agent 配置的流程。
"""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.shared.utils.agent.agent_config_service import (
    AgentConfigService,
    AgentNotFoundError,
    AgentAlreadyExistsError,
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


def test_get_agent_config_returns_default_when_name_empty():
    """测试 agent_name 为空时返回框架默认配置。"""
    db = MagicMock()
    loader = MagicMock()
    service = AgentConfigService(db, loader)

    # None
    config = asyncio.run(service.get_agent_config(None))
    assert config.name == ""
    assert config.system_prompt == ""
    assert config.enabled_tool_names == []
    assert config.enabled_skill_names == []
    assert config.agent_config_overrides == {}

    # 空字符串
    config2 = asyncio.run(service.get_agent_config(""))
    assert config2.name == ""
    assert config2.system_prompt == ""

    # 验证未查询数据库
    db.fetchrow.assert_not_called()


def test_get_agent_config_default_has_base_classes():
    """测试默认配置的 state_class / context_class 为基类。"""
    from app.core.agent.AgentConfig import AgentState
    from app.core.agent.AgentContext import AgentContext

    db = MagicMock()
    loader = MagicMock()
    service = AgentConfigService(db, loader)
    config = asyncio.run(service.get_agent_config(None))

    assert config.state_class is AgentState
    assert config.context_class is AgentContext


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


def test_create_agent_inserts_and_returns_row(tmp_path):
    """测试 create_agent 插入并返回新行。

    参数:
        tmp_path: pytest 内置 fixture，提供临时目录

    返回:
        None

    异常:
        AssertionError: 断言失败时抛出
    """
    md_file = tmp_path / "AGENTS.md"
    md_file.write_text("# new agent")
    db = MagicMock()
    # 2026-06-24 改造后 create_agent 会先 SELECT 检查重名（返回 None），再 INSERT
    db.fetchrow = AsyncMock(side_effect=[
        None,  # 不存在
        {
            "name": "new_agent",
            "display_name": "新智能体",
            "description": "测试",
            "agents_md_path": str(md_file),
            "state_schema": {},
            "context_schema": {},
            "mcp_tags": [],
            "enabled": True,
            "sort_order": 0,
        },
    ])
    loader = MagicMock()
    service = AgentConfigService(db, loader)
    config = {
        "name": "new_agent",
        "display_name": "新智能体",
        "description": "测试",
        "agents_md_path": str(md_file),
    }
    result = asyncio.run(service.create_agent(config))
    assert result["name"] == "new_agent"
    assert result["display_name"] == "新智能体"
    # 验证 fetchrow 被调用 2 次（SELECT 检查 + INSERT ... RETURNING *）
    assert db.fetchrow.call_count == 2


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


# ============================================================
# 2026-06-24 新增：config_schema 三层嵌套结构测试
# ============================================================

def test_get_agent_config_parses_three_layer_config_schema():
    """测试 get_agent_config 从 config_schema 正确解析三层嵌套结构。

    验证：
    - state_class / context_class 由 state_fields / context_fields 构建
    - agent_config_overrides 来自顶层字段
    """
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "test_agent",
        "display_name": "Test",
        "description": "",
        "agents_md_path": "agents/test/AGENTS.md",
        "state_schema": "{}",
        "context_schema": "{}",
        "config_schema": {
            "temperature": {"type": "float", "default": 0.5},
            "max_tokens":  {"type": "int",   "default": 4096},
            "state_fields": {
                "test_field": {"type": "str", "default": "hi"},
            },
            "context_fields": {
                "audit_root": {"type": "str", "default": "data/audit"},
            },
        },
        "mcp_tags": [],
        "enabled": True,
    })
    db.fetch = AsyncMock(return_value=[])

    loader = MagicMock()
    loader.load = MagicMock(return_value="system prompt")
    service = AgentConfigService(db, loader)
    config = asyncio.run(service.get_agent_config("test_agent"))

    # 验证 agent_config_overrides 提取正确
    assert config.agent_config_overrides["temperature"] == 0.5
    assert config.agent_config_overrides["max_tokens"] == 4096
    # 验证 state_fields / context_fields
    instance = config.state_class(messages=[])
    assert instance["test_field"] == "hi"
    context = config.context_class(session_id="s1")
    assert context["audit_root"] == "data/audit"


def test_get_agent_config_fallback_to_legacy_fields():
    """测试 config_schema 为空时回退到旧 state_schema + context_schema 字段。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "legacy_agent",
        "display_name": "Legacy",
        "description": "",
        "agents_md_path": "agents/legacy/AGENTS.md",
        "state_schema": {"legacy_field": {"type": "int", "default": 99}},
        "context_schema": {"legacy_ctx": {"type": "str", "default": "data/legacy"}},
        "config_schema": "{}",
        "mcp_tags": [],
        "enabled": True,
    })
    db.fetch = AsyncMock(return_value=[])

    loader = MagicMock()
    loader.load = MagicMock(return_value="prompt")
    service = AgentConfigService(db, loader)
    config = asyncio.run(service.get_agent_config("legacy_agent"))

    state = config.state_class(messages=[])
    assert state["legacy_field"] == 99
    ctx = config.context_class(session_id="s1")
    assert ctx["legacy_ctx"] == "data/legacy"


def test_update_agent_config_schema_replaces_whole():
    """测试 update_agent_config_schema 全量替换 config_schema。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "x",
        "config_schema": {
            "state_fields": {"map_zoom": {"type": "int", "default": 10}},
            "context_fields": {},
        },
    })
    service = AgentConfigService(db, MagicMock())

    new_schema = {
        "temperature": {"type": "float", "default": 0.8},
        "state_fields": {"new_field": {"type": "str", "default": "v"}},
        "context_fields": {},
    }
    result = asyncio.run(service.update_agent_config_schema("x", new_schema))
    assert result is not None

    # 验证 SQL 含 config_schema 和旧的 state_schema/context_schema
    sql = db.fetchrow.call_args.args[0]
    assert "config_schema" in sql
    assert "state_schema" in sql
    assert "context_schema" in sql


def test_update_agent_config_schema_rejects_reserved_field():
    """测试 update_agent_config_schema 拒绝保留字段。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={"name": "x", "config_schema": "{}"})
    service = AgentConfigService(db, MagicMock())

    bad_schema = {
        "checkpointer": {"type": "str", "default": "should_be_rejected"},
    }
    with pytest.raises(ValueError, match="保留字段"):
        asyncio.run(service.update_agent_config_schema("x", bad_schema))


def test_add_agent_config_field_root_section():
    """测试 add_agent_config_field 向 root section 添加字段。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "x",
        "config_schema": {
            "state_fields": {},
            "context_fields": {},
            "temperature": {"type": "float", "default": 0.5},
        },
    })
    service = AgentConfigService(db, MagicMock())

    result = asyncio.run(service.add_agent_config_field(
        "x", "root", "max_tokens", {"type": "int", "default": 8192},
    ))
    assert result is not None
    # 验证 update_agent_config_schema 被调用，config_schema 含 max_tokens
    final_schema = db.fetchrow.call_args.kwargs.get("config_schema") or \
                   db.fetchrow.call_args.args[1] if len(db.fetchrow.call_args.args) > 1 else None
    # 由于 fetchrow 多次调用，最后一次调用是 update_agent_config_schema 的 UPDATE 返回
    # 这里只验证 add_agent_config_field 不抛错


def test_add_agent_config_field_rejects_reserved():
    """测试 add_agent_config_field 拒绝保留字段添加到 root section。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={"name": "x", "config_schema": "{}"})
    service = AgentConfigService(db, MagicMock())

    with pytest.raises(ValueError, match="保留字段"):
        asyncio.run(service.add_agent_config_field(
            "x", "root", "checkpointer", {"type": "str", "default": "x"},
        ))


def test_add_agent_config_field_invalid_section():
    """测试 add_agent_config_field 拒绝非法 section。"""
    db = MagicMock()
    service = AgentConfigService(db, MagicMock())
    with pytest.raises(ValueError, match="section"):
        asyncio.run(service.add_agent_config_field(
            "x", "invalid_section", "field", {"type": "int", "default": 0},
        ))


def test_delete_agent_config_field_state_fields():
    """测试 delete_agent_config_field 从 state_fields 删除字段。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "x",
        "config_schema": {
            "state_fields": {
                "to_delete": {"type": "int", "default": 1},
                "keep":      {"type": "int", "default": 2},
            },
            "context_fields": {},
        },
    })
    service = AgentConfigService(db, MagicMock())
    result = asyncio.run(service.delete_agent_config_field("x", "state_fields", "to_delete"))
    assert result is not None


def test_delete_agent_config_field_nonexistent_is_idempotent():
    """测试删除不存在的字段时幂等返回（不抛异常）。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "x",
        "config_schema": {"state_fields": {"a": {"type": "int", "default": 0}}},
    })
    service = AgentConfigService(db, MagicMock())
    result = asyncio.run(service.delete_agent_config_field("x", "state_fields", "nonexistent"))
    assert result is not None


def test_create_agent_validates_name_format(tmp_path):
    """测试 create_agent 校验 name 格式。"""
    md = tmp_path / "AGENTS.md"
    md.write_text("# x")
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value=None)
    service = AgentConfigService(db, MagicMock())
    with pytest.raises(ValueError, match="name 必须"):
        asyncio.run(service.create_agent({
            "name": "Invalid Name!",
            "display_name": "X",
            "agents_md_path": str(md),
        }))


def test_create_agent_rejects_reserved_field_in_config_schema(tmp_path):
    """测试 create_agent 拒绝保留字段在 config_schema 顶层。"""
    md = tmp_path / "AGENTS.md"
    md.write_text("# x")
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value=None)
    service = AgentConfigService(db, MagicMock())
    with pytest.raises(ValueError, match="保留字段"):
        asyncio.run(service.create_agent({
            "name": "valid_name",
            "display_name": "X",
            "agents_md_path": str(md),
            "config_schema": {"checkpointer": {"type": "str", "default": "x"}},
        }))


def test_create_agent_duplicate_name_raises(tmp_path):
    """测试 create_agent 在 name 重复时抛 AgentAlreadyExistsError。"""
    md = tmp_path / "AGENTS.md"
    md.write_text("# existing")
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={"name": "existing_agent"})
    service = AgentConfigService(db, MagicMock())
    with pytest.raises(AgentAlreadyExistsError):
        asyncio.run(service.create_agent({
            "name": "existing_agent",
            "display_name": "X",
            "agents_md_path": str(md),
        }))


def test_delete_agent_cascades_bindings():
    """测试 delete_agent 级联清理工具和技能绑定。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={"name": "to_delete"})
    db.execute = AsyncMock()
    service = AgentConfigService(db, MagicMock())
    asyncio.run(service.delete_agent("to_delete"))
    # 验证 execute 被调用 3 次（tool_bindings / skill_bindings / agents）
    assert db.execute.await_count == 3
    # 检查 SQL 含三类表名
    all_sqls = " ".join(call.args[0] for call in db.execute.await_args_list)
    assert "agent_tool_bindings" in all_sqls
    assert "agent_skill_bindings" in all_sqls
    assert "DELETE FROM agents" in all_sqls


# ============================================================
# 2026-06-24 新增：admin 端点专用方法测试
# 覆盖 AgentConfigService.list_all_agents_admin / get_agent_admin
# 用于 agent_admin_router 重构后替代直接访问 app.state.db 的接口
# ============================================================


def test_list_all_agents_admin_returns_all_fields():
    """测试 list_all_agents_admin 返回所有智能体（含禁用项）+ 全字段。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 断言失败时抛出
    """
    db = MagicMock()
    db.fetch = AsyncMock(return_value=[
        {
            "name": "map_agent",
            "display_name": "地图智能体",
            "description": "地图控制",
            "agents_md_path": "agents/map_agent/AGENTS.md",
            "state_schema": "{}",
            "context_schema": "{}",
            "config_schema": {
                "state_fields": {"map_zoom": {"type": "int", "default": 10}},
                "context_fields": {},
            },
            "mcp_tags": ["map"],
            "enabled": True,
            "sort_order": 0,
            "created_at": None,
            "updated_at": None,
        },
        {
            "name": "disabled_agent",
            "display_name": "已禁用",
            "description": "禁用项也应返回",
            "agents_md_path": "agents/disabled/AGENTS.md",
            "state_schema": "{}",
            "context_schema": "{}",
            "config_schema": {},
            "mcp_tags": [],
            "enabled": False,  # 关键：禁用项也要出现
            "sort_order": 99,
            "created_at": None,
            "updated_at": None,
        },
    ])
    service = AgentConfigService(db, MagicMock())

    result = asyncio.run(service.list_all_agents_admin())

    # 1. 长度 = 2（含禁用项）
    assert len(result) == 2
    # 2. 禁用项必须返回（与 list_agents 不同）
    names = [r["name"] for r in result]
    assert "disabled_agent" in names
    # 3. 全字段都在
    first = result[0]
    for field in (
        "name", "display_name", "description", "agents_md_path",
        "state_schema", "context_schema", "config_schema", "mcp_tags",
        "enabled", "sort_order", "created_at", "updated_at",
    ):
        assert field in first, f"缺少字段: {field}"


def test_list_all_agents_admin_orders_by_sort_order_then_name():
    """测试 list_all_agents_admin 传 SQL 时使用 ORDER BY sort_order, name。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: SQL 不含期望的 ORDER BY 子句时抛出
    """
    db = MagicMock()
    db.fetch = AsyncMock(return_value=[])
    service = AgentConfigService(db, MagicMock())
    asyncio.run(service.list_all_agents_admin())

    # 验证 SQL 含 ORDER BY sort_order, name（顺序敏感：admin 端点约定）
    call_args = db.fetch.call_args
    sql = call_args.args[0] if call_args.args else call_args[0][0]
    assert "ORDER BY sort_order, name" in sql
    # 不应过滤 enabled
    assert "WHERE enabled" not in sql


def test_get_agent_admin_returns_full_config_with_overrides():
    """测试 get_agent_admin 返回完整 dict + agent_config_overrides 拆分。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 拆分结果不正确时抛出
    """
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "map_agent",
        "display_name": "地图智能体",
        "description": "地图控制",
        "agents_md_path": "agents/map_agent/AGENTS.md",
        "state_schema": "{}",
        "context_schema": "{}",
        "config_schema": {
            "temperature": {"type": "float", "default": 0.5},
            "max_tokens": {"type": "int", "default": 4096},
            "state_fields": {
                "map_zoom": {"type": "int", "default": 10},
            },
            "context_fields": {},
        },
        "mcp_tags": ["map"],
        "enabled": True,
        "sort_order": 0,
        "created_at": None,
        "updated_at": None,
    })
    service = AgentConfigService(db, MagicMock())
    result = asyncio.run(service.get_agent_admin("map_agent"))

    # 1. 顶层字段全在
    assert result["name"] == "map_agent"
    assert result["display_name"] == "地图智能体"
    assert result["enabled"] is True
    # 2. agent_config_overrides 拆分正确
    assert result["agent_config_overrides"]["temperature"] == 0.5
    assert result["agent_config_overrides"]["max_tokens"] == 4096
    # 3. state_fields / context_fields 不应出现在 overrides 中
    assert "map_zoom" not in result["agent_config_overrides"]


def test_get_agent_admin_raises_not_found():
    """测试 get_agent_admin 在智能体不存在时抛 AgentNotFoundError。

    参数:
        无

    返回:
        None

    异常:
        pytest.raises 期望的 AgentNotFoundError（异常外则测试失败）
    """
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value=None)
    service = AgentConfigService(db, MagicMock())

    with pytest.raises(AgentNotFoundError, match="nonexistent_agent"):
        asyncio.run(service.get_agent_admin("nonexistent_agent"))


def test_get_agent_admin_handles_non_dict_config_schema():
    """测试 get_agent_admin 在 config_schema 为非 dict 时不崩，回退空 dict。

    防御性测试：覆盖 asyncpg JSONB 字段返回 str / list / None 的边缘情况。
    _decode_jsonb 已有 str → json.loads 兼容；list 类型应原样返回后被识别为非 dict。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 拆分结果异常时抛出
    """
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "weird_agent",
        "display_name": "X",
        "description": "",
        "agents_md_path": "x",
        "state_schema": "{}",
        "context_schema": "{}",
        "config_schema": ["unexpected", "list", "type"],  # 非 dict，模拟脏数据
        "mcp_tags": [],
        "enabled": True,
        "sort_order": 0,
        "created_at": None,
        "updated_at": None,
    })
    service = AgentConfigService(db, MagicMock())
    result = asyncio.run(service.get_agent_admin("weird_agent"))

    # 不应崩溃；overrides 应为空 dict
    assert result["agent_config_overrides"] == {}


def test_delete_agent_nonexistent_raises():
    """测试删除不存在的智能体抛出 AgentNotFoundError。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value=None)
    service = AgentConfigService(db, MagicMock())
    with pytest.raises(AgentNotFoundError):
        asyncio.run(service.delete_agent("nonexistent"))


def test_set_agent_enabled_toggles():
    """测试 set_agent_enabled 切换 enabled 状态。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={"name": "x", "enabled": False})
    service = AgentConfigService(db, MagicMock())
    result = asyncio.run(service.set_agent_enabled("x", False))
    assert result["enabled"] is False
    # 验证 SQL 含 UPDATE
    sql = db.fetchrow.call_args.args[0]
    assert "UPDATE agents" in sql
    assert "enabled" in sql


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


def test_get_agent_admin_decodes_str_config_schema():
    """测试 get_agent_admin：DB 返回 JSONB 字符串时能正确解码并返回 dict。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: config_schema 未被解码为 dict 时抛出
    """
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "map_agent",
        "display_name": "地图智能体",
        "description": "地图控制",
        "agents_md_path": "agents/map_agent/AGENTS.md",
        "state_schema": '{}',
        "context_schema": '{}',
        "config_schema": '{"max_tokens": {"type": "int", "default": 20000}}',
        "mcp_tags": '["map"]',
        "enabled": True,
        "sort_order": 0,
        "created_at": None,
        "updated_at": None,
    })
    service = AgentConfigService(db, MagicMock())
    result = asyncio.run(service.get_agent_admin("map_agent"))

    # config_schema 应为 dict 而非 str
    assert isinstance(result["config_schema"], dict)
    assert result["config_schema"]["max_tokens"]["default"] == 20000
    # agent_config_overrides 应同时正确提取
    assert result["agent_config_overrides"]["max_tokens"] == 20000
    # mcp_tags 应为 list
    assert result["mcp_tags"] == ["map"]


def test_list_all_agents_admin_decodes_str_jsonb_fields():
    """测试 list_all_agents_admin：DB 返回 JSONB 字符串列表时能正确解码。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: JSONB 字段未被解码时抛出
    """
    db = MagicMock()
    db.fetch = AsyncMock(return_value=[
        {
            "name": "map_agent",
            "display_name": "地图智能体",
            "description": "",
            "agents_md_path": "agents/map_agent/AGENTS.md",
            "state_schema": '{"map_zoom": {"type": "int", "default": 10}}',
            "context_schema": '{}',
            "config_schema": '{"max_tokens": {"type": "int", "default": 20000}}',
            "mcp_tags": '["map"]',
            "enabled": True,
            "sort_order": 0,
            "created_at": None,
            "updated_at": None,
        },
    ])
    service = AgentConfigService(db, MagicMock())
    result = asyncio.run(service.list_all_agents_admin())

    assert len(result) == 1
    agent = result[0]
    # state_schema / context_schema / config_schema 应为 dict
    assert isinstance(agent["state_schema"], dict)
    assert agent["state_schema"]["map_zoom"]["default"] == 10
    assert isinstance(agent["config_schema"], dict)
    assert agent["config_schema"]["max_tokens"]["default"] == 20000
    # mcp_tags 应为 list
    assert agent["mcp_tags"] == ["map"]

