# -*- coding:utf-8 -*-
"""
ToolRegistry 测试模块

验证 @register_tool 装饰器能注册工具，并能按 agent_name + enabled_tool_names 过滤返回。
"""
import pytest
from app.shared.tools.registry import ToolRegistry, register_tool


def test_registry_importable():
    """测试 registry 模块可导入。"""
    from app.shared.tools import registry
    assert hasattr(registry, "ToolRegistry")
    assert hasattr(registry, "register_tool")


def test_register_tool_decorator_registers_function():
    """测试 @register_tool 装饰器将函数注册到 registry。"""
    ToolRegistry._tools.pop("test_tool_unique_001", None)

    @register_tool(name="test_tool_unique_001", agent="test_agent", description="测试工具")
    def my_tool(arg: str) -> str:
        """测试工具函数。"""
        return arg

    assert "test_tool_unique_001" in ToolRegistry._tools
    info = ToolRegistry._tools["test_tool_unique_001"]
    assert info["agent"] == "test_agent"
    assert info["description"] == "测试工具"
    assert info["func"] is my_tool
    ToolRegistry._tools.pop("test_tool_unique_001", None)


def test_get_tools_for_agent_returns_all_when_no_filter():
    """测试不带 enabled_tool_names 时返回该 agent 所有工具。"""
    ToolRegistry._tools.pop("t_a_001", None)
    ToolRegistry._tools.pop("t_a_002", None)
    ToolRegistry._tools.pop("t_a_003", None)

    @register_tool(name="t_a_001", agent="agent_x", description="x1")
    def f1(): return 1

    @register_tool(name="t_a_002", agent="agent_x", description="x2")
    def f2(): return 2

    @register_tool(name="t_a_003", agent="agent_y", description="y1")
    def f3(): return 3

    tools = ToolRegistry.get_tools_for_agent("agent_x")
    assert f1 in tools
    assert f2 in tools
    assert f3 not in tools

    for k in ["t_a_001", "t_a_002", "t_a_003"]:
        ToolRegistry._tools.pop(k, None)


def test_get_tools_for_agent_filters_by_enabled_names():
    """测试 enabled_tool_names 过滤只返回启用的工具。"""
    ToolRegistry._tools.pop("t_b_001", None)
    ToolRegistry._tools.pop("t_b_002", None)

    @register_tool(name="t_b_001", agent="agent_z", description="z1")
    def g1(): return 1

    @register_tool(name="t_b_002", agent="agent_z", description="z2")
    def g2(): return 2

    tools = ToolRegistry.get_tools_for_agent("agent_z", enabled_tool_names=["t_b_001"])
    assert g1 in tools
    assert g2 not in tools

    for k in ["t_b_001", "t_b_002"]:
        ToolRegistry._tools.pop(k, None)


def test_get_tools_for_agent_ignores_other_agent_tools():
    """测试 enabled_tool_names 中包含其他 agent 的工具时被忽略。"""
    ToolRegistry._tools.pop("t_c_001", None)
    ToolRegistry._tools.pop("t_c_002", None)

    @register_tool(name="t_c_001", agent="agent_a", description="a1")
    def h1(): return 1

    @register_tool(name="t_c_002", agent="agent_b", description="b1")
    def h2(): return 2

    tools = ToolRegistry.get_tools_for_agent("agent_a", enabled_tool_names=["t_c_001", "t_c_002"])
    assert h1 in tools
    assert h2 not in tools

    for k in ["t_c_001", "t_c_002"]:
        ToolRegistry._tools.pop(k, None)


def test_get_tools_for_agent_unknown_name_returns_empty():
    """测试未知 agent_name 返回空列表。"""
    tools = ToolRegistry.get_tools_for_agent("non_existent_agent_xyz")
    assert tools == []
