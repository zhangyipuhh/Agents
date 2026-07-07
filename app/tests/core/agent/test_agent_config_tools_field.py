# -*- coding:utf-8 -*-
"""
AgentConfig.tools 字段与 get_tools() 方法测试。

覆盖 Task 7 引入的变更：
    - tools 字段存在性及默认值（None）
    - get_tools() 完全依赖 self.tools，不再有硬编码默认工具
    - tools=None / tools=[] 时返回空工具列表
    - 传入外部工具时返回该工具

设计原则（决策 8）：基础工具不默认加载，所有工具通过绑定实现。
生产 chat 路径（agent_router）必须传入 tools=config.tools。

注意：
    conftest.py 全局 mock 了 langgraph.prebuilt.ToolNode 为 Mock()，
    且 langchain_core.tools.tool 被替换为 _tool_identity（返回原函数）。
    因此本测试不依赖真实的 ToolNode 类型检查与 @tool 装饰器，
    仅验证 get_tools() 的核心契约：返回 (self.tools or [], ToolNode(...))。
"""

from dataclasses import fields
from unittest.mock import Mock

from app.core.agent.AgentConfig import AgentConfig


def _make_config(**overrides):
    """构造测试用 AgentConfig，屏蔽 LLM/工具相关字段的副作用。

    Args:
        **overrides: 覆盖默认值的字段。

    Returns:
        AgentConfig: 测试用配置实例。
    """
    defaults = {
        "name": "test_agent",
        "system_prompt": "test",
    }
    defaults.update(overrides)
    return AgentConfig(**defaults)


def test_tools_field_exists():
    """AgentConfig 应包含 tools 字段。

    Returns:
        None
    """
    config_fields = {f.name: f for f in fields(AgentConfig)}
    assert "tools" in config_fields, "AgentConfig 应包含 tools 字段"


def test_tools_field_default_is_none():
    """tools 字段默认值应为 None。

    Returns:
        None
    """
    config_fields = {f.name: f for f in fields(AgentConfig)}
    assert config_fields["tools"].default is None, "tools 字段默认值应为 None"


def test_get_tools_default_none_returns_empty():
    """tools=None 时 get_tools() 应返回空工具列表。

    Returns:
        None
    """
    config = _make_config()  # 默认 tools=None
    tools, node = config.get_tools()
    assert tools == [], f"默认应返回空列表, 实际: {tools}"
    # conftest mock 了 ToolNode 为 Mock()，node 应为 Mock 调用结果（非 None）
    assert node is not None, "应返回非 None 的工具节点"


def test_get_tools_with_empty_list_returns_empty():
    """tools=[] 时 get_tools() 应返回空工具列表。

    Returns:
        None
    """
    config = _make_config(tools=[])
    tools, node = config.get_tools()
    assert tools == [], f"空列表应返回空列表, 实际: {tools}"
    assert node is not None, "应返回非 None 的工具节点"


def test_get_tools_returns_external_tools():
    """传入外部工具时 get_tools() 应返回该工具。

    使用 Mock 对象模拟工具（conftest 已 mock @tool 装饰器，
    真实 BaseTool 无法在测试环境构造）。

    Returns:
        None
    """
    fake_tool = Mock(name="fake_tool")
    config = _make_config(tools=[fake_tool])
    tools, node = config.get_tools()
    assert len(tools) == 1, f"应返回1个工具, 实际: {len(tools)}"
    assert tools[0] is fake_tool, "应返回传入的工具对象"
    assert node is not None, "应返回非 None 的工具节点"


def test_get_tools_no_hardcoded_defaults():
    """get_tools() 不应硬编码任何默认工具。

    验证决策 8：基础工具不默认加载。默认情况下 agent 无工具可用。

    Returns:
        None
    """
    config = _make_config()
    tools, _ = config.get_tools()
    assert tools == [], "默认不应有任何硬编码工具"


def test_get_tools_returns_same_list_reference():
    """get_tools() 应返回 self.tools 的引用（None 时回退到空列表）。

    Returns:
        None
    """
    custom_tools = [Mock(name="t1"), Mock(name="t2")]
    config = _make_config(tools=custom_tools)
    tools, _ = config.get_tools()
    assert tools is custom_tools, "应直接返回 self.tools 引用（None 回退除外）"


def test_get_tools_passes_tools_to_tool_node():
    """get_tools() 应将工具列表传给 ToolNode 构造器。

    通过检查 ToolNode 被调用时传入的 tools 参数验证。
    conftest 已 mock ToolNode 为 Mock()，可检查 call_args。

    Returns:
        None
    """
    # 重新 import 以获取被 conftest mock 后的 ToolNode
    import app.core.agent.AgentConfig as module

    fake_tool = Mock(name="fake_tool")
    config = _make_config(tools=[fake_tool])
    config.get_tools()

    # ToolNode 被 mock，检查它是否被以 tools 参数调用
    assert module.ToolNode.called, "ToolNode 应被调用"
    call_args, call_kwargs = module.ToolNode.call_args
    # 第一个位置参数应为工具列表
    assert call_args[0] == [fake_tool] or call_kwargs.get("tools") == [fake_tool], (
        "ToolNode 应以工具列表作为首参"
    )


def test_agent_config_no_longer_imports_hardcoded_tools():
    """AgentConfig 模块不应再 import 硬编码工具。

    验证 SubTask 7.3：移除了 BaseTools/SandboxTools/FilesystemReadTools/skills.tool 的 import。

    Returns:
        None
    """
    import app.core.agent.AgentConfig as module

    # 这些硬编码工具不应再作为模块属性存在
    hardcoded_names = [
        "get_current_time",
        "open_file",
        "load_web_page",
        "read_cached_chunk",
        "open_file_by_id",
        "sandbox",
        "explore",
        "load_skill",
        "read_skill_file",
    ]
    for name in hardcoded_names:
        assert not hasattr(module, name), (
            f"AgentConfig 模块不应再导出硬编码工具: {name}"
        )
