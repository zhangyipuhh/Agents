# -*- coding:utf-8 -*-
"""
动态 State/Context 构建器测试模块

验证 build_agent_state / build_agent_context 能根据数据库 JSON schema 动态生成子类，
保留基类字段，跳过保留字段，支持子类重写默认值。
"""
import asyncio
import pytest
from app.shared.utils.agent.dynamic_schema import (
    build_agent_state,
    build_agent_context,
    build_context,
    parse_config_schema,
    build_agent_config_overrides,
    get_agent_config_field_schema,
    get_agent_config_field_templates,
    get_agent_state_field_templates,
    get_agent_context_field_templates,
    _get_type_str,
    RESERVED_STATE_FIELDS,
    RESERVED_CONTEXT_FIELDS,
    RESERVED_CONFIG_FIELDS,
)


def test_build_agent_state_importable():
    """测试 dynamic_schema 模块可导入。"""
    from app.shared.utils.agent import dynamic_schema
    assert hasattr(dynamic_schema, "build_agent_state")


def test_build_agent_state_creates_subclass_with_extra_fields():
    """测试动态生成的 state 子类包含 schema 中定义的额外字段。"""
    schema = {
        "map_center": {"type": "dict", "default": {"latitude": 0, "longitude": 0}},
        "map_zoom": {"type": "int", "default": 10},
    }
    cls = build_agent_state("map_agent", schema)
    assert cls.__name__ == "MapAgentAgentState"
    annotations = cls.__annotations__
    assert "map_center" in annotations
    assert "map_zoom" in annotations
    assert annotations["map_center"] is dict
    assert annotations["map_zoom"] is int


def test_build_agent_state_preserves_base_fields():
    """测试基类 AgentState 的保留字段仍然存在。"""
    schema = {"custom_field": {"type": "str", "default": "hello"}}
    cls = build_agent_state("test", schema)
    annotations = cls.__annotations__
    assert "error_limit" in annotations


def test_build_agent_state_skips_reserved_fields():
    """测试 schema 中尝试覆盖保留字段时被跳过。"""
    schema = {
        "messages": {"type": "list", "default": []},
        "custom": {"type": "str", "default": "ok"},
    }
    cls = build_agent_state("test", schema)
    annotations = cls.__annotations__
    assert "custom" in annotations


def test_build_agent_state_overrides_base_default():
    """测试 schema 中同名字段覆盖基类默认值。"""
    schema = {"error_limit": {"type": "int", "default": 99}}
    cls = build_agent_state("test", schema)
    instance = cls(messages=[])
    assert instance["error_limit"] == 99


def test_build_agent_context_creates_subclass():
    """测试动态生成 context 子类。"""
    schema = {
        "custom_kb_dir": {"type": "str", "default": "data/Knowledge"},
        "geometry_data": {"type": "dict", "default": {}},
    }
    cls = build_agent_context("map_agent", schema)
    assert cls.__name__ == "MapAgentAgentContext"
    annotations = cls.__annotations__
    assert "custom_kb_dir" in annotations
    assert annotations["custom_kb_dir"] is str


def test_build_agent_context_preserves_base_fields():
    """测试基类 AgentContext 的保留字段仍然存在。"""
    schema = {"custom": {"type": "str", "default": "x"}}
    cls = build_agent_context("test", schema)
    annotations = cls.__annotations__
    assert "session_id" in annotations
    assert "store_id" in annotations


def test_build_context_runtime_instance():
    """测试运行时构造 context 实例。"""
    class FakeRequest:
        session_id = "sess-001"
        store_id = "store-001"
        context_overrides = {"custom_kb_dir": "custom/path"}

    schema = {"custom_kb_dir": {"type": "str", "default": "data/Knowledge"}}
    ctx = build_context("map_agent", schema, FakeRequest())
    assert ctx["session_id"] == "sess-001"
    assert ctx["store_id"] == "store-001"
    assert ctx["custom_kb_dir"] == "custom/path"


def test_reserved_state_fields_contains_messages():
    """测试保留字段集合包含 messages。"""
    assert "messages" in RESERVED_STATE_FIELDS
    assert "error_limit" in RESERVED_STATE_FIELDS


def test_reserved_context_fields_contains_session_id():
    """测试 context 保留字段包含 session_id。"""
    assert "session_id" in RESERVED_CONTEXT_FIELDS
    assert "store_id" in RESERVED_CONTEXT_FIELDS


def test_build_agent_state_mutable_defaults_not_shared():
    """测试可变默认值（dict/list）在不同实例间不共享。

    验证 _TypedDictWithDefaults.__call__ 对 dict / list 类型默认值
    使用 copy.deepcopy，避免多个实例共享同一对象引用导致跨实例污染。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    schema = {
        "map_center": {"type": "dict", "default": {"latitude": 0, "longitude": 0}},
        "map_markers": {"type": "list", "default": []},
    }
    cls = build_agent_state("test_mutable", schema)
    instance_a = cls(messages=[])
    instance_b = cls(messages=[])

    # 修改 instance_a 的可变默认值
    instance_a["map_center"]["latitude"] = 999
    instance_a["map_markers"].append("marker1")

    # instance_b 不应受影响
    assert instance_b["map_center"]["latitude"] == 0
    assert len(instance_b["map_markers"]) == 0


def test_build_context_filters_reserved_keywords_in_overrides():
    """测试 context_overrides 中的保留字段被过滤，避免关键字冲突。

    验证当 request.context_overrides 包含 session_id / store_id 等
    保留字段时，build_context 不会抛出 "got multiple values for keyword
    argument" 错误，且显式传入的 session_id / store_id 优先。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    class FakeRequest:
        session_id = "sess-explicit"
        store_id = "store-explicit"
        # 故意包含保留字段，模拟冲突场景
        context_overrides = {
            "session_id": "sess-override",
            "store_id": "store-override",
            "custom_kb_dir": "custom/path",
        }

    schema = {"custom_kb_dir": {"type": "str", "default": "data/Knowledge"}}
    ctx = build_context("map_agent", schema, FakeRequest())
    # 显式传入的 session_id / store_id 应优先
    assert ctx["session_id"] == "sess-explicit"
    assert ctx["store_id"] == "store-explicit"
    # 非保留字段的覆盖值应正常生效
    assert ctx["custom_kb_dir"] == "custom/path"


# ============================================================
# 2026-06-24 新增：基类保留字段默认值自动补全
# 修复 Bug A（agent_router.py chat 端点重构后 state 缺基类保留字段）
# 验证 dynamic_schema._BASE_STATE_DEFAULTS / _BASE_CONTEXT_DEFAULTS 兜底逻辑
# ============================================================


def test_build_agent_state_fills_base_reserved_defaults():
    """验证 state 实例自动包含基类保留字段的默认值（修复 Bug A）。

    构造最小 schema（只含 map_zoom），实例化时不应抛 KeyError，且应自动包含
    error_limit=5 / limit=25 / file_chunk_read_progress=1 / agent_name=None 等。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    cls = build_agent_state("test", {"map_zoom": {"type": "int", "default": 10}})
    instance = cls(messages=[])
    # 基类保留字段默认值应自动补全
    assert instance["error_limit"] == 5
    assert instance["limit"] == 25
    assert instance["file_chunk_read_progress"] == 1
    assert instance["agent_name"] is None
    assert instance["pending_question"] is None
    assert instance["question_answers"] == []
    assert instance["tool_progress"] == {}
    assert instance["intermediate_results"] == {}
    # schema 中显式提供的扩展字段应保留
    assert instance["map_zoom"] == 10


def test_build_agent_state_empty_schema_creates_valid_state():
    """验证空 schema 也能生成合法 state 实例。

    参数:
        无

    返回:
        无
    """
    cls = build_agent_state("empty_agent", {})
    instance = cls(messages=[])
    # 所有基类保留字段默认值应自动补全
    assert instance["error_limit"] == 5
    assert instance["limit"] == 25
    assert instance["file_chunk_read_progress"] == 1
    assert instance["agent_name"] is None
    assert instance["messages"] == []
    # 至少包含 messages 字段（来自 _MessagesState 基类）
    assert "messages" in instance


# ============================================================
# 2026-06-24 新增：parse_config_schema / build_agent_config_overrides 测试
# ============================================================

def test_parse_config_schema_importable():
    """测试 parse_config_schema 可被导入。"""
    from app.shared.utils.agent import dynamic_schema
    assert hasattr(dynamic_schema, "parse_config_schema")
    assert hasattr(dynamic_schema, "build_agent_config_overrides")
    assert hasattr(dynamic_schema, "RESERVED_CONFIG_FIELDS")


def test_parse_config_schema_three_layer_structure():
    """测试三层嵌套 config_schema 正确拆分。

    验证 agent_config_overrides / state_schema / context_schema / raw_root_fields。
    """
    config_schema = {
        "temperature": {"type": "float", "default": 0.5},
        "max_tokens":  {"type": "int",   "default": 4096},
        "state_fields": {
            "map_zoom": {"type": "int", "default": 10},
        },
        "context_fields": {
            "custom_kb_dir": {"type": "str", "default": "data/Knowledge"},
        },
    }
    result = parse_config_schema(config_schema)
    assert result["agent_config_overrides"]["temperature"] == 0.5
    assert result["agent_config_overrides"]["max_tokens"] == 4096
    assert result["state_schema"]["map_zoom"]["default"] == 10
    assert result["context_schema"]["custom_kb_dir"]["default"] == "data/Knowledge"
    assert "temperature" in result["raw_root_fields"]


def test_parse_config_schema_empty_input():
    """测试空 config_schema / None / 非 dict 输入的兜底行为。"""
    assert parse_config_schema({})["agent_config_overrides"] == {}
    assert parse_config_schema(None)["agent_config_overrides"] == {}
    # 非 dict 类型应回退到空 dict
    result = parse_config_schema("not a dict")  # type: ignore[arg-type]
    assert result["state_schema"] == {}
    assert result["context_schema"] == {}


def test_parse_config_schema_filters_reserved_fields():
    """测试保留字段（state_class / context_class / checkpointer / store）被过滤。"""
    config_schema = {
        "temperature": {"type": "float", "default": 0.5},
        "state_class": {"type": "str", "default": "should_be_ignored"},
        "checkpointer": {"type": "str", "default": "should_be_ignored"},
    }
    result = parse_config_schema(config_schema)
    # 保留字段不会出现在 overrides / raw_root_fields 中
    assert "state_class" not in result["agent_config_overrides"]
    assert "checkpointer" not in result["agent_config_overrides"]
    assert "state_class" not in result["raw_root_fields"]
    assert "checkpointer" not in result["raw_root_fields"]
    # 但 temperature 保留
    assert result["agent_config_overrides"]["temperature"] == 0.5


def test_build_agent_config_overrides_type_conversion():
    """测试 build_agent_config_overrides 把 JSON 值转换为 Python 原生类型。"""
    config_schema = {
        "temperature":     {"type": "float", "default": 0.7},
        "max_tokens":      {"type": "int",   "default": 8192},
        "trim_tool_messages": {"type": "bool", "default": False},
        "mcp_tags":        {"type": "list",  "default": ["a", "b"]},
        "api_key":         {"type": "str",   "default": "sk-xxx"},
    }
    overrides = build_agent_config_overrides(config_schema)
    assert overrides["temperature"] == 0.7
    assert isinstance(overrides["temperature"], float)
    assert overrides["max_tokens"] == 8192
    assert isinstance(overrides["max_tokens"], int)
    assert overrides["trim_tool_messages"] is False
    assert isinstance(overrides["trim_tool_messages"], bool)
    assert overrides["mcp_tags"] == ["a", "b"]
    assert isinstance(overrides["mcp_tags"], list)
    assert overrides["api_key"] == "sk-xxx"


def test_build_agent_config_overrides_skips_no_default():
    """测试缺少 default 键的字段被跳过（仅声明类型无值）。"""
    config_schema = {
        "temperature": {"type": "float"},  # 缺 default
        "max_tokens":  {"type": "int", "default": 4096},
    }
    overrides = build_agent_config_overrides(config_schema)
    assert "temperature" not in overrides
    assert overrides["max_tokens"] == 4096


def test_get_agent_config_field_schema_returns_dict():
    """测试已知字段返回完整 schema。"""
    schema = get_agent_config_field_schema("temperature")
    assert schema is not None
    assert schema["field_name"] == "temperature"
    assert schema["type"] == "float"


def test_get_agent_config_field_schema_unknown_field_returns_none():
    """测试未知字段返回 None。"""
    assert get_agent_config_field_schema("non_existent_field") is None
    # 保留字段也返回 None
    assert get_agent_config_field_schema("state_class") is None
    assert get_agent_config_field_schema("checkpointer") is None


def test_get_agent_config_field_templates_returns_list():
    """测试 AgentConfig 字段模板列表非空。"""
    templates = get_agent_config_field_templates()
    assert isinstance(templates, list)
    assert len(templates) > 0
    # 不包含保留字段
    field_names = [t["field_name"] for t in templates]
    assert "state_class" not in field_names
    assert "checkpointer" not in field_names
    # 包含常用字段
    assert "temperature" in field_names
    assert "max_tokens" in field_names


def test_parse_config_schema_state_fields_preserved_through_pipeline():
    """端到端：parse_config_schema → build_agent_state 应能正确生成 state 子类。"""
    config_schema = {
        "temperature": {"type": "float", "default": 0.5},
        "state_fields": {
            "map_zoom": {"type": "int", "default": 12},
            "map_layer": {"type": "str", "default": "satellite"},
        },
    }
    parsed = parse_config_schema(config_schema)
    cls = build_agent_state("map_agent", parsed["state_schema"])
    annotations = cls.__annotations__
    assert "map_zoom" in annotations
    assert "map_layer" in annotations
    instance = cls(messages=[])
    assert instance["map_zoom"] == 12
    assert instance["map_layer"] == "satellite"


def test_build_agent_context_fills_base_reserved_defaults():
    """验证 context 实例自动包含基类保留字段默认值。

    参数:
        无

    返回:
        无
    """
    cls = build_agent_context("test", {})
    instance = cls(session_id="sess-1")
    # 基类保留字段默认值应自动补全
    assert instance["session_id"] == "sess-1"  # 调用方显式传入
    assert instance["store_id"] == "default"
    assert instance["image_ids"] == []
    assert instance["host_session_id"] is None
    assert instance["process_data"] == {}


def test_caller_kwargs_override_base_defaults():
    """验证调用方 kwargs 优先于基类默认值（最高优先级）。

    knowledge_router.py 已使用此模式（显式传 error_limit=2 / limit=10），
    必须确保这个优先级不被破坏。

    参数:
        无

    返回:
        无
    """
    cls = build_agent_state("test", {})
    instance = cls(messages=[], error_limit=2, limit=10, agent_name="map_agent")
    # 调用方 kwargs 优先
    assert instance["error_limit"] == 2
    assert instance["limit"] == 10
    assert instance["agent_name"] == "map_agent"


def test_map_agent_full_schema_creates_complete_state():
    """端到端验证：模拟 seed_map_agent.py 的完整 schema。

    与 app/migrations/seed_map_agent.py 的 MAP_AGENT_STATE_SCHEMA 保持一致。
    修复后调用方只需传 messages，应自动补全 5 个 map 扩展字段 + 8 个基类保留字段。

    参数:
        无

    返回:
        无
    """
    map_schema = {
        "map_center":   {"type": "dict", "default": {"latitude": 0, "longitude": 0}},
        "map_zoom":     {"type": "int",  "default": 10},
        "map_markers":  {"type": "list", "default": []},
        "map_layer":    {"type": "str",  "default": "standard"},
        "map_polygons": {"type": "list", "default": []},
    }
    cls = build_agent_state("map_agent", map_schema)
    instance = cls(messages=[])
    # 5 个 map 扩展字段
    assert instance["map_center"] == {"latitude": 0, "longitude": 0}
    assert instance["map_zoom"] == 10
    assert instance["map_markers"] == []
    assert instance["map_layer"] == "standard"
    assert instance["map_polygons"] == []
    # 8 个基类保留字段
    assert instance["error_limit"] == 5
    assert instance["limit"] == 25
    assert instance["file_chunk_read_progress"] == 1
    assert instance["agent_name"] is None
    assert instance["pending_question"] is None
    assert instance["question_answers"] == []
    assert instance["tool_progress"] == {}
    assert instance["intermediate_results"] == {}


def test_map_agent_state_reserved_field_override():
    """验证 schema 可重写基类保留字段默认值（次高优先级）。

    例如：map_agent 在 state_schema 中将 error_limit 从 5 改为 2，
    应覆盖 _BASE_STATE_DEFAULTS 的默认值。

    参数:
        无

    返回:
        无
    """
    schema = {"error_limit": {"type": "int", "default": 2}}
    cls = build_agent_state("custom", schema)
    instance = cls(messages=[])
    # schema 重写值优先于基类默认值
    assert instance["error_limit"] == 2


# ============================================================
# 2026-06-24 新增：state / context 字段模板测试
# ============================================================


def test_get_type_str_conversion():
    """验证 _get_type_str 将 Python 类型注解正确转换为字符串键。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    import typing
    assert _get_type_str(str) == "str"
    assert _get_type_str(int) == "int"
    assert _get_type_str(float) == "float"
    assert _get_type_str(bool) == "bool"
    assert _get_type_str(dict) == "dict"
    assert _get_type_str(list) == "list"
    assert _get_type_str(typing.Optional[str]) == "str"
    assert _get_type_str(typing.Optional[int]) == "int"
    assert _get_type_str(typing.Dict[str, dict]) == "dict"
    assert _get_type_str(typing.List[str]) == "list"
    assert _get_type_str(typing.Any) == "str"  # 未知类型回退


def test_get_agent_state_field_templates_returns_list():
    """验证 get_agent_state_field_templates 返回 AgentState 保留字段模板。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    templates = get_agent_state_field_templates()
    assert isinstance(templates, list)
    assert len(templates) > 0

    field_names = [t["field_name"] for t in templates]
    # 应包含基类保留字段
    assert "error_limit" in field_names
    assert "limit" in field_names
    assert "agent_name" in field_names
    # 不应包含运行时必需字段 messages
    assert "messages" not in field_names

    # 验证每项结构
    for t in templates:
        assert "field_name" in t
        assert "type" in t
        assert "default" in t
        assert t["type"] in ("str", "int", "float", "bool", "dict", "list")


def test_get_agent_context_field_templates_returns_list():
    """验证 get_agent_context_field_templates 返回 AgentContext 保留字段模板。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    templates = get_agent_context_field_templates()
    assert isinstance(templates, list)
    assert len(templates) > 0

    field_names = [t["field_name"] for t in templates]
    # 应包含基类保留字段
    assert "session_id" in field_names
    assert "namespace" in field_names
    assert "store_id" in field_names
    assert "image_ids" in field_names

    # 验证每项结构
    for t in templates:
        assert "field_name" in t
        assert "type" in t
        assert "default" in t
        assert t["type"] in ("str", "int", "float", "bool", "dict", "list")
