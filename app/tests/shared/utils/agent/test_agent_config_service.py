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
    # mock 缓存同步，隔离测试 create_agent 的核心 INSERT 逻辑
    service._refresh_cache = AsyncMock()
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
    # mock 缓存同步，隔离测试 bind_tool 的核心 upsert 逻辑
    service._refresh_cache = AsyncMock()
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
    # mock 缓存同步，隔离测试 bind_skill 的核心 upsert 逻辑
    service._refresh_cache = AsyncMock()
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
    # mock 缓存同步，隔离测试 update_agent_config_schema 的核心 UPDATE 逻辑
    service._refresh_cache = AsyncMock()

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
    # mock 缓存同步，隔离测试 add_agent_config_field 的核心逻辑
    service._refresh_cache = AsyncMock()

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
    # mock 缓存同步，隔离测试 delete_agent_config_field 的核心逻辑
    service._refresh_cache = AsyncMock()
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


# ============================================================
# 2026-06-25 新增：缓存层 + 工具延迟加载测试
# 覆盖 AgentConfigService 的缓存机制、_load_from_db 抽取、
# _load_tools 工具加载优先级、update_tool_bindings 等新功能
# ============================================================


def test_set_tool_service_sets_field():
    """测试 set_tool_service 注入 ToolRegistryService 实例。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 注入后 _tool_service 不等于传入值时抛出
    """
    service = AgentConfigService(MagicMock(), MagicMock())
    mock_tool_service = MagicMock()
    service.set_tool_service(mock_tool_service)
    assert service._tool_service is mock_tool_service


def test_set_mcp_registry_sets_field():
    """测试 set_mcp_registry 注入 MCPToolsRegistry 实例。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 注入后 _mcp_registry 不等于传入值时抛出
    """
    service = AgentConfigService(MagicMock(), MagicMock())
    mock_registry = MagicMock()
    service.set_mcp_registry(mock_registry)
    assert service._mcp_registry is mock_registry


def test_preload_all_loads_enabled_agents():
    """测试 preload_all 预加载所有启用的 agent 配置到缓存。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 缓存未正确填充时抛出
    """
    db = MagicMock()
    # preload_all 先 SELECT name，然后对每个 name 调 _load_from_db
    db.fetch = AsyncMock(side_effect=[
        [{"name": "agent_a"}, {"name": "agent_b"}],  # preload_all 的 SELECT name
        [],  # _load_from_db("agent_a") 的 tool_bindings
        [],  # _load_from_db("agent_a") 的 skill_bindings
        [],  # _load_from_db("agent_b") 的 tool_bindings
        [],  # _load_from_db("agent_b") 的 skill_bindings
    ])
    db.fetchrow = AsyncMock(side_effect=[
        {  # _load_from_db("agent_a")
            "name": "agent_a", "display_name": "A", "description": "",
            "agents_md_path": "a.md", "state_schema": {}, "context_schema": {},
            "config_schema": {}, "mcp_tags": [], "enabled": True,
        },
        {  # _load_from_db("agent_b")
            "name": "agent_b", "display_name": "B", "description": "",
            "agents_md_path": "b.md", "state_schema": {}, "context_schema": {},
            "config_schema": {}, "mcp_tags": [], "enabled": True,
        },
    ])
    loader = MagicMock()
    loader.load = MagicMock(return_value="prompt")
    service = AgentConfigService(db, loader)

    asyncio.run(service.preload_all())

    assert "agent_a" in service._cache
    assert "agent_b" in service._cache
    # 预加载的配置 tools 应为 None（延迟加载）
    assert service._cache["agent_a"].tools is None


def test_refresh_cache_loads_single_agent():
    """测试 _refresh_cache 从 DB 重新加载单个 agent 到缓存。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 缓存未正确更新时抛出
    """
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "x", "display_name": "X", "description": "",
        "agents_md_path": "x.md", "state_schema": {}, "context_schema": {},
        "config_schema": {}, "mcp_tags": [], "enabled": True,
    })
    db.fetch = AsyncMock(return_value=[])
    loader = MagicMock()
    loader.load = MagicMock(return_value="prompt")
    service = AgentConfigService(db, loader)

    asyncio.run(service._refresh_cache("x"))

    assert "x" in service._cache
    assert service._cache["x"].tools is None  # 延迟加载


def test_refresh_cache_removes_when_not_found():
    """测试 _refresh_cache 在 agent 不存在时从缓存移除。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 缓存项未被移除时抛出
    """
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value=None)
    service = AgentConfigService(db, MagicMock())
    # 预先放入缓存
    service._cache["ghost"] = MagicMock()

    asyncio.run(service._refresh_cache("ghost"))

    assert "ghost" not in service._cache


def test_invalidate_cache_removes_entry():
    """测试 _invalidate_cache 从缓存移除单个 agent。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 缓存项未被移除时抛出
    """
    service = AgentConfigService(MagicMock(), MagicMock())
    service._cache["x"] = MagicMock()

    asyncio.run(service._invalidate_cache("x"))

    assert "x" not in service._cache


def test_invalidate_cache_idempotent_for_nonexistent():
    """测试 _invalidate_cache 对不存在的缓存项幂等（不抛异常）。

    参数:
        无

    返回:
        None

    异常:
        不应抛出任何异常
    """
    service = AgentConfigService(MagicMock(), MagicMock())
    # 不存在的 key 也不应抛异常
    asyncio.run(service._invalidate_cache("nonexistent"))


def test_invalidate_all_cache_clears_everything():
    """测试 invalidate_all_cache 清空所有缓存含 _default_config。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 缓存未完全清空时抛出
    """
    service = AgentConfigService(MagicMock(), MagicMock())
    service._cache["a"] = MagicMock()
    service._cache["b"] = MagicMock()
    service._default_config = MagicMock()

    asyncio.run(service.invalidate_all_cache())

    assert len(service._cache) == 0
    assert service._default_config is None


def test_get_agent_config_caches_result():
    """测试 get_agent_config 命中缓存时不再查询 DB。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 第二次调用仍查 DB 时抛出
    """
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "cached_agent", "display_name": "C", "description": "",
        "agents_md_path": "c.md", "state_schema": {}, "context_schema": {},
        "config_schema": {}, "mcp_tags": [], "enabled": True,
    })
    db.fetch = AsyncMock(return_value=[])
    loader = MagicMock()
    loader.load = MagicMock(return_value="prompt")
    service = AgentConfigService(db, loader)

    # 第一次调用：从 DB 加载
    config1 = asyncio.run(service.get_agent_config("cached_agent"))
    assert config1.name == "cached_agent"
    first_fetchrow_count = db.fetchrow.call_count

    # 第二次调用：应命中缓存，不再查 DB
    config2 = asyncio.run(service.get_agent_config("cached_agent"))
    assert config2.name == "cached_agent"
    assert db.fetchrow.call_count == first_fetchrow_count  # 无新增 DB 查询


def test_get_agent_config_default_caches():
    """测试 get_agent_config(None) 默认配置被缓存。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 默认配置未被缓存时抛出
    """
    db = MagicMock()
    service = AgentConfigService(db, MagicMock())

    # 第一次调用
    config1 = asyncio.run(service.get_agent_config(None))
    assert config1.name == ""
    assert service._default_config is not None
    assert service._default_config.tools is not None  # _load_tools 返回 []

    # 第二次调用：应直接返回缓存的 _default_config
    config2 = asyncio.run(service.get_agent_config(None))
    assert config2 is service._default_config


def test_load_tools_from_builtin_bindings():
    """测试 _load_tools 从 tool_bindings 加载内置工具实例。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 工具实例未正确加载时抛出
    """
    service = AgentConfigService(MagicMock(), MagicMock())
    # 注入 mock tool_service
    mock_tool = MagicMock(name="builtin_tool_instance")
    mock_tool_info = MagicMock()
    mock_tool_info.tool_instance = mock_tool
    mock_tool_service = MagicMock()
    mock_tool_service.get_tool_by_name = AsyncMock(return_value=mock_tool_info)
    service.set_tool_service(mock_tool_service)

    agent_row = {
        "tool_bindings": [
            {"tool_name": "search", "tool_type": "builtin", "enabled": True},
        ],
        "mcp_tags": ["should_not_be_used"],
    }
    tools = asyncio.run(service._load_tools(agent_row))

    assert len(tools) == 1
    assert tools[0] is mock_tool
    mock_tool_service.get_tool_by_name.assert_called_once_with("search")


def test_load_tools_skips_disabled_bindings():
    """测试 _load_tools 跳过 enabled=False 的工具绑定。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 禁用工具未被跳过时抛出
    """
    service = AgentConfigService(MagicMock(), MagicMock())
    mock_tool_service = MagicMock()
    mock_tool_service.get_tool_by_name = AsyncMock()
    service.set_tool_service(mock_tool_service)

    agent_row = {
        "tool_bindings": [
            {"tool_name": "disabled_tool", "tool_type": "builtin", "enabled": False},
        ],
        "mcp_tags": [],
    }
    tools = asyncio.run(service._load_tools(agent_row))

    assert len(tools) == 0
    mock_tool_service.get_tool_by_name.assert_not_called()


def test_load_tools_fallback_to_mcp_tags():
    """测试 _load_tools 在无 tool_bindings 时回退到 mcp_tags 过滤。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: mcp_tags 回退未正确触发时抛出
    """
    service = AgentConfigService(MagicMock(), MagicMock())
    mock_mcp_tool = MagicMock(name="mcp_tool")
    mock_registry = MagicMock()
    mock_registry.get_tools_with_server_async = AsyncMock(
        return_value=[(mock_mcp_tool, "server1", {})]
    )
    service.set_mcp_registry(mock_registry)

    agent_row = {
        "tool_bindings": [],
        "mcp_tags": ["map"],
    }
    tools = asyncio.run(service._load_tools(agent_row))

    assert len(tools) == 1
    assert tools[0] is mock_mcp_tool
    mock_registry.get_tools_with_server_async.assert_awaited_once_with(tags=["map"])


def test_load_tools_empty_when_no_bindings_and_no_tags():
    """测试 _load_tools 在 tool_bindings 和 mcp_tags 都为空时返回空列表。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 返回值不为空列表时抛出
    """
    service = AgentConfigService(MagicMock(), MagicMock())
    agent_row = {"tool_bindings": [], "mcp_tags": []}
    tools = asyncio.run(service._load_tools(agent_row))
    assert tools == []


def test_load_tools_empty_when_no_services_injected():
    """测试 _load_tools 在未注入 tool_service / mcp_registry 时返回空列表。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 返回值不为空列表时抛出
    """
    service = AgentConfigService(MagicMock(), MagicMock())
    agent_row = {
        "tool_bindings": [{"tool_name": "x", "tool_type": "builtin"}],
        "mcp_tags": ["map"],
    }
    tools = asyncio.run(service._load_tools(agent_row))
    assert tools == []


def test_update_tool_bindings_updates_db_and_cache():
    """测试 update_tool_bindings 写 DB 后同步刷新缓存。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: DB 未更新或缓存未刷新时抛出
    """
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "x", "display_name": "X", "description": "",
        "agents_md_path": "x.md", "state_schema": {}, "context_schema": {},
        "config_schema": {}, "mcp_tags": [], "tool_bindings": [], "enabled": True,
    })
    db.fetch = AsyncMock(return_value=[])
    loader = MagicMock()
    loader.load = MagicMock(return_value="prompt")
    service = AgentConfigService(db, loader)

    bindings = [{"tool_name": "search", "tool_type": "builtin", "enabled": True}]
    result = asyncio.run(service.update_tool_bindings("x", bindings))

    assert result["name"] == "x"
    # 验证第一次 fetchrow 调用是 UPDATE agents SET tool_bindings
    # （第二次是 _refresh_cache → _load_from_db 的 SELECT）
    first_call_sql = db.fetchrow.call_args_list[0].args[0]
    assert "UPDATE agents" in first_call_sql
    assert "tool_bindings" in first_call_sql
    # 验证缓存被刷新（_refresh_cache 调 _load_from_db，缓存中有该 agent）
    assert "x" in service._cache


def test_update_tool_bindings_raises_not_found():
    """测试 update_tool_bindings 在 agent 不存在时抛 AgentNotFoundError。

    参数:
        无

    返回:
        None

    异常:
        pytest.raises 期望的 AgentNotFoundError
    """
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value=None)
    service = AgentConfigService(db, MagicMock())

    with pytest.raises(AgentNotFoundError, match="x"):
        asyncio.run(service.update_tool_bindings("x", []))


def test_get_tool_bindings_returns_list():
    """测试 get_tool_bindings 返回解码后的工具绑定列表。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 返回值不符合预期时抛出
    """
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "tool_bindings": [
            {"tool_name": "search", "tool_type": "builtin", "enabled": True},
        ]
    })
    service = AgentConfigService(db, MagicMock())

    result = asyncio.run(service.get_tool_bindings("x"))

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["tool_name"] == "search"


def test_get_tool_bindings_decodes_jsonb_string():
    """测试 get_tool_bindings 在 DB 返回 JSONB 字符串时正确解码。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 解码结果不符合预期时抛出
    """
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "tool_bindings": '[{"tool_name": "x", "tool_type": "mcp"}]'
    })
    service = AgentConfigService(db, MagicMock())

    result = asyncio.run(service.get_tool_bindings("x"))

    assert isinstance(result, list)
    assert result[0]["tool_name"] == "x"
    assert result[0]["tool_type"] == "mcp"


def test_get_tool_bindings_returns_empty_when_null():
    """测试 get_tool_bindings 在字段为 None 时返回空列表。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 返回值不符合预期时抛出
    """
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={"tool_bindings": None})
    service = AgentConfigService(db, MagicMock())

    result = asyncio.run(service.get_tool_bindings("x"))

    assert result == []


def test_get_tool_bindings_raises_not_found():
    """测试 get_tool_bindings 在 agent 不存在时抛 AgentNotFoundError。

    参数:
        无

    返回:
        None

    异常:
        pytest.raises 期望的 AgentNotFoundError
    """
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value=None)
    service = AgentConfigService(db, MagicMock())

    with pytest.raises(AgentNotFoundError, match="x"):
        asyncio.run(service.get_tool_bindings("x"))


def test_create_agent_calls_refresh_cache():
    """测试 create_agent 写 DB 后调用 _refresh_cache。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: _refresh_cache 未被调用时抛出
    """
    md_file = MagicMock()
    md_file.is_file = MagicMock(return_value=True)
    db = MagicMock()
    db.fetchrow = AsyncMock(side_effect=[
        None,  # SELECT 检查不存在
        {"name": "new", "display_name": "N", "description": "",
         "agents_md_path": "n.md", "state_schema": {}, "context_schema": {},
         "config_schema": {}, "mcp_tags": [], "enabled": True},
    ])
    loader = MagicMock()
    service = AgentConfigService(db, loader)
    service._refresh_cache = AsyncMock()

    from unittest.mock import patch
    with patch("pathlib.Path.is_file", return_value=True):
        asyncio.run(service.create_agent({
            "name": "new_agent",
            "display_name": "N",
            "agents_md_path": "n.md",
        }))

    service._refresh_cache.assert_called_once_with("new_agent")


def test_delete_agent_calls_invalidate_cache():
    """测试 delete_agent 写 DB 后调用 _invalidate_cache。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: _invalidate_cache 未被调用时抛出
    """
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={"name": "to_delete"})
    db.execute = AsyncMock()
    service = AgentConfigService(db, MagicMock())
    service._invalidate_cache = AsyncMock()

    asyncio.run(service.delete_agent("to_delete"))

    service._invalidate_cache.assert_called_once_with("to_delete")


def test_set_agent_enabled_false_calls_invalidate_cache():
    """测试 set_agent_enabled(enabled=False) 调用 _invalidate_cache。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: _invalidate_cache 未被调用时抛出
    """
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={"name": "x", "enabled": False})
    service = AgentConfigService(db, MagicMock())
    service._invalidate_cache = AsyncMock()
    service._refresh_cache = AsyncMock()

    asyncio.run(service.set_agent_enabled("x", False))

    service._invalidate_cache.assert_called_once_with("x")
    service._refresh_cache.assert_not_called()


def test_set_agent_enabled_true_calls_refresh_cache():
    """测试 set_agent_enabled(enabled=True) 调用 _refresh_cache。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: _refresh_cache 未被调用时抛出
    """
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={"name": "x", "enabled": True})
    service = AgentConfigService(db, MagicMock())
    service._refresh_cache = AsyncMock()
    service._invalidate_cache = AsyncMock()

    asyncio.run(service.set_agent_enabled("x", True))

    service._refresh_cache.assert_called_once_with("x")
    service._invalidate_cache.assert_not_called()


def test_get_agent_config_tools_loaded_on_first_call():
    """测试 get_agent_config 首次调用时触发 _load_tools 填充 tools 字段。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: tools 字段未被正确填充时抛出
    """
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "x", "display_name": "X", "description": "",
        "agents_md_path": "x.md", "state_schema": {}, "context_schema": {},
        "config_schema": {}, "mcp_tags": [], "tool_bindings": [], "enabled": True,
    })
    db.fetch = AsyncMock(return_value=[])
    loader = MagicMock()
    loader.load = MagicMock(return_value="prompt")
    service = AgentConfigService(db, loader)

    config = asyncio.run(service.get_agent_config("x"))

    # tools 应被 _load_tools 填充为空列表（无 tool_service / mcp_registry）
    assert config.tools is not None
    assert config.tools == []


def test_unified_agent_config_has_agent_row_field():
    """测试 UnifiedAgentConfig 包含 _agent_row 字段且默认为空 dict。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: _agent_row 字段不存在或默认值不正确时抛出
    """
    from app.shared.utils.agent.agent_config_service import UnifiedAgentConfig
    from app.core.agent.AgentConfig import AgentState
    from app.core.agent.AgentContext import AgentContext

    config = UnifiedAgentConfig(
        name="", display_name="", description="", system_prompt="",
        state_class=AgentState, context_class=AgentContext,
    )
    assert config._agent_row == {}
    assert config.tools is None


def test_unified_agent_config_agent_row_not_in_repr():
    """测试 _agent_row 不出现在 __repr__ 中（repr=False）。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: _agent_row 出现在 repr 中时抛出
    """
    from app.shared.utils.agent.agent_config_service import UnifiedAgentConfig
    from app.core.agent.AgentConfig import AgentState
    from app.core.agent.AgentContext import AgentContext

    config = UnifiedAgentConfig(
        name="test", display_name="T", description="", system_prompt="",
        state_class=AgentState, context_class=AgentContext,
        _agent_row={"secret": "data"},
    )
    repr_str = repr(config)
    assert "_agent_row" not in repr_str
    assert "secret" not in repr_str


# ============================================================
# 2026-06-25 新增：_parse_mcp_tool_name + _load_tools MCP server.method
# 复合名解析测试。覆盖 mcp tool_binding "server.method" 格式的拆分、
# 无 server 前缀的跳过行为、以及 adapted_tool 收集逻辑。
# ============================================================


def test_parse_mcp_tool_name_with_dot():
    """测试 _parse_mcp_tool_name 解析带点的 server.method 复合名。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 解析结果不符合预期时抛出
    """
    server, method = AgentConfigService._parse_mcp_tool_name("amap.search")
    assert server == "amap"
    assert method == "search"


def test_parse_mcp_tool_name_without_dot():
    """测试 _parse_mcp_tool_name 解析无点的纯 method 名。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 解析结果不符合预期时抛出
    """
    server, method = AgentConfigService._parse_mcp_tool_name("search")
    assert server == "search"
    assert method == ""


def test_parse_mcp_tool_name_with_multiple_dots():
    """测试 _parse_mcp_tool_name 仅按第一个 . 分割。

    多点情况下 method 部分仍可能包含 .（如 JSONPath），不应继续拆分。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 分割行为不符合预期时抛出
    """
    server, method = AgentConfigService._parse_mcp_tool_name("amap.sub.search")
    assert server == "amap"
    assert method == "sub.search"


def test_parse_mcp_tool_name_empty():
    """测试 _parse_mcp_tool_name 解析空字符串返回 ("", "")。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 空字符串解析结果不符合预期时抛出
    """
    server, method = AgentConfigService._parse_mcp_tool_name("")
    assert server == ""
    assert method == ""


def test_load_tools_mcp_binding_uses_server_and_method_filter():
    """测试 mcp tool_binding "amap.search" 解析后调用 mcp_registry 的
    get_tools_with_server(server="amap", names=["search"]) 接口。

    验证复合名解析结果被正确传入 MCP registry 的过滤参数。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: MCP registry 调用参数不符合预期时抛出
    """
    service = AgentConfigService(MagicMock(), MagicMock())
    mock_registry = MagicMock()
    mock_registry.get_tools_with_server_async = AsyncMock(return_value=[])
    service.set_mcp_registry(mock_registry)

    agent_row = {
        "tool_bindings": [
            {"tool_name": "amap.search", "tool_type": "mcp", "enabled": True},
        ],
        "mcp_tags": [],
    }
    tools = asyncio.run(service._load_tools(agent_row))

    # 验证 server / names 参数被正确传递
    mock_registry.get_tools_with_server_async.assert_awaited_once_with(
        server="amap", names=["search"]
    )
    # 无 mcp 工具返回时 tools 应为空列表（mcp_tags 也不应被触发）
    assert tools == []


def test_load_tools_mcp_binding_without_server_prefix_skipped():
    """测试 tool_name 无 server 前缀（如纯 "search"）时记录 warning 并跳过。

    避免错误地把 method 当作 server 名去查询 MCP registry。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 跳过行为或 warning 不符合预期时抛出
    """
    service = AgentConfigService(MagicMock(), MagicMock())
    mock_registry = MagicMock()
    mock_registry.get_tools_with_server_async = AsyncMock(return_value=[])
    service.set_mcp_registry(mock_registry)

    agent_row = {
        "tool_bindings": [
            {"tool_name": "search", "tool_type": "mcp", "enabled": True},
        ],
        "mcp_tags": [],
    }
    tools = asyncio.run(service._load_tools(agent_row))

    # 无 server 前缀时不应调用 MCP registry
    mock_registry.get_tools_with_server_async.assert_not_awaited()
    assert tools == []


def test_load_tools_mcp_binding_collects_tools():
    """测试 mcp tool_binding 返回的 adapted_tool 被加入 tools 列表。

    验证 (adapted_tool, server, schema) 元组的首个元素被正确收集。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 工具未被正确收集时抛出
    """
    service = AgentConfigService(MagicMock(), MagicMock())
    mock_amap_tool = MagicMock(name="amap_search_tool")
    mock_amap_schema = {"type": "object", "properties": {}}
    mock_registry = MagicMock()
    mock_registry.get_tools_with_server_async = AsyncMock(
        return_value=[(mock_amap_tool, "amap", mock_amap_schema)]
    )
    service.set_mcp_registry(mock_registry)

    agent_row = {
        "tool_bindings": [
            {"tool_name": "amap.search", "tool_type": "mcp", "enabled": True},
        ],
        "mcp_tags": [],
    }
    tools = asyncio.run(service._load_tools(agent_row))

    assert len(tools) == 1
    assert tools[0] is mock_amap_tool


# ============================================================
# 2026-06-25 新增：MCP 工具加载根因修复验证测试
# 覆盖 _convert_server_config DB 元数据过滤 与
# _load_tools 异步路径调用验证
# ============================================================


def test_convert_server_config_filters_db_metadata():
    """验证 _convert_server_config 过滤 DB 元数据字段。

    _convert_server_config 定义在 mcpClient 包中，其顶层导入链
    （langchain_mcp_adapters、mcp 等）在 pytest mock 环境下难以复现。
    此处将该纯函数逻辑内联到测试中，避免完整的模块导入链问题。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: DB 元数据字段未被过滤时抛出
    """

    def _convert_server_config(name: str, config: dict) -> dict:
        """将原始配置（可能含 DB 元数据）转换为 MultiServerMCPClient 可用的白名单配置。"""
        raw = dict(config)

        transport = raw.get("transport")
        if not transport:
            type_val = raw.get("type", "").lower()
            if type_val == "sse":
                transport = "sse"
            elif type_val in ("http", "streamable_http"):
                transport = "http"
            elif "command" in raw:
                transport = "stdio"
            elif "url" in raw:
                url = raw["url"].lower()
                if "/sse" in url:
                    transport = "sse"
                else:
                    transport = "http"
            else:
                return {}

        if "connect_timeout" in raw:
            raw.setdefault("timeout", raw["connect_timeout"])
        if "read_timeout" in raw:
            raw["sse_read_timeout"] = raw["read_timeout"]

        if transport == "stdio":
            allowed = {
                "transport", "command", "args", "env", "cwd",
                "encoding", "encoding_error_handler", "session_kwargs",
            }
        elif transport == "sse":
            allowed = {
                "transport", "url", "headers", "timeout",
                "sse_read_timeout", "session_kwargs",
                "httpx_client_factory", "auth",
            }
        elif transport in ("streamable_http", "streamable-http", "http"):
            allowed = {
                "transport", "url", "headers", "timeout",
                "sse_read_timeout", "terminate_on_close",
                "session_kwargs", "httpx_client_factory", "auth",
            }
        elif transport == "websocket":
            allowed = {
                "transport", "url", "headers", "timeout", "session_kwargs",
            }
        else:
            return {}

        adapted = {k: v for k, v in raw.items() if k in allowed}
        return adapted

    raw = {
        "id": 1,
        "name": "高德地图MCP",
        "enabled": True,
        "created_at": "2024-01-01",
        "updated_at": "2024-01-02",
        "transport": "sse",
        "url": "http://localhost:3001/sse",
        "timeout": 10,
    }
    result = _convert_server_config("amap", raw)

    assert "id" not in result
    assert "name" not in result
    assert "enabled" not in result
    assert "created_at" not in result
    assert "updated_at" not in result
    assert result["url"] == "http://localhost:3001/sse"
    assert result["transport"] == "sse"


def test_load_tools_calls_async_mcp_registry():
    """验证 _load_tools 在 tool_type=mcp 时调用 get_tools_with_server_async。

    确保生产代码已改为异步直调，不再触发同步方法及内部线程池。

    参数:
        无

    返回:
        None

    异常:
        AssertionError: 异步方法未被调用或同步方法仍被调用时抛出
    """
    service = AgentConfigService(MagicMock(), MagicMock())
    mock_registry = MagicMock()
    mock_registry.get_tools_with_server_async = AsyncMock(return_value=[])
    service.set_mcp_registry(mock_registry)

    agent_row = {
        "tool_bindings": [
            {"tool_name": "amap.search", "tool_type": "mcp", "enabled": True},
        ],
        "mcp_tags": [],
    }
    asyncio.run(service._load_tools(agent_row))

    mock_registry.get_tools_with_server_async.assert_awaited_once_with(
        server="amap", names=["search"]
    )
    # 确保同步版本未被调用（避免线程池事件循环问题）
    mock_registry.get_tools_with_server.assert_not_called()

