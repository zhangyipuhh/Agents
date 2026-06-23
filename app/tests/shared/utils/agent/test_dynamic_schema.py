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
    RESERVED_STATE_FIELDS,
    RESERVED_CONTEXT_FIELDS,
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
        "knowledge_root": {"type": "str", "default": "data/Knowledge"},
        "geometry_data": {"type": "dict", "default": {}},
    }
    cls = build_agent_context("map_agent", schema)
    assert cls.__name__ == "MapAgentAgentContext"
    annotations = cls.__annotations__
    assert "knowledge_root" in annotations
    assert annotations["knowledge_root"] is str


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
        context_overrides = {"knowledge_root": "custom/path"}

    schema = {"knowledge_root": {"type": "str", "default": "data/Knowledge"}}
    ctx = build_context("map_agent", schema, FakeRequest())
    assert ctx["session_id"] == "sess-001"
    assert ctx["store_id"] == "store-001"
    assert ctx["knowledge_root"] == "custom/path"


def test_reserved_state_fields_contains_messages():
    """测试保留字段集合包含 messages。"""
    assert "messages" in RESERVED_STATE_FIELDS
    assert "error_limit" in RESERVED_STATE_FIELDS


def test_reserved_context_fields_contains_session_id():
    """测试 context 保留字段包含 session_id。"""
    assert "session_id" in RESERVED_CONTEXT_FIELDS
    assert "store_id" in RESERVED_CONTEXT_FIELDS
