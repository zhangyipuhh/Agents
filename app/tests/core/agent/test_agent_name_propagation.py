# -*- coding:utf-8 -*-
"""
AgentConfig.name 字段与 Agent.agent_name 透传链路测试。

覆盖：
    - AgentConfig 基类 name 字段默认值
    - 7 个子智能体 *Config 类覆盖 name 为字面量
    - Agent.__init__ 读取 config.name 赋给 self.agent_name
"""

from dataclasses import fields

from app.core.agent.AgentConfig import AgentConfig


def test_agent_config_base_name_default_is_none():
    """
    AgentConfig 基类的 name 字段默认为 None。

    Returns:
        None
    """
    config_fields = {f.name: f for f in fields(AgentConfig)}
    assert "name" in config_fields
    assert config_fields["name"].default is None


def test_all_subagent_configs_have_correct_name_default():
    """
    7 个子智能体 *Config 类的 name 字段默认值应严格匹配 app/features/<dir>/ 目录名。

    Returns:
        None
    """
    from app.features.AI_Coding_Check_agent.config.AICodingCheckConfig import (
        AICodingCheckConfig,
    )
    from app.features.DevOps_agent.config.DevOpsAgentConfig import DevOpsAgentConfig
    from app.features.Tagent.config.TagentConfig import TAgentConfig
    from app.features.contract_approval_agent.config.ApprovalAgentConfig import (
        ApprovalAgentConfig,
    )
    from app.features.contract_document_agent.config.DocAgentConfig import DocAgentConfig
    from app.features.contract_host_agent.config.HtAgentConfig import HtAgentConfig
    from app.features.map_agent.config.MapAgentConfig import MapAgentConfig

    expected = {
        MapAgentConfig: "map_agent",
        HtAgentConfig: "contract_host_agent",
        DocAgentConfig: "contract_document_agent",
        ApprovalAgentConfig: "contract_approval_agent",
        DevOpsAgentConfig: "DevOps_agent",
        AICodingCheckConfig: "AI_Coding_Check_agent",
        TAgentConfig: "Tagent",
    }

    for cls, expected_name in expected.items():
        cls_fields = {f.name: f for f in fields(cls)}
        assert "name" in cls_fields, f"{cls.__name__} missing name field"
        assert cls_fields["name"].default == expected_name, (
            f"{cls.__name__}.name default should be {expected_name!r}, "
            f"got {cls_fields['name'].default!r}"
        )


def test_agent_config_name_can_be_overridden_at_instantiation():
    """
    AgentConfig(name="custom") 显式传参时，name 字段会覆盖子类的默认字面量。

    Returns:
        None
    """
    from app.features.map_agent.config.MapAgentConfig import MapAgentConfig

    config = MapAgentConfig(name="override_name")
    assert config.name == "override_name"


def test_agent_name_attribute_propagates_from_config():
    """
    Agent.__init__ 会从 config.name 读取并赋给 self.agent_name。

    Returns:
        None
    """
    from app.core.agent.agent import Agent
    from app.features.map_agent.config.MapAgentConfig import MapAgentConfig

    config = MapAgentConfig(system_prompt="dummy")
    agent = Agent(config=config)
    assert agent.agent_name == "map_agent"


def test_agent_name_attribute_defaults_to_none_for_base_config():
    """
    使用基类 AgentConfig()（不传 name）时，agent.agent_name 应为 None。

    模拟尚未迁移到子智能体 config 的兜底场景。

    Returns:
        None
    """
    from app.core.agent.agent import Agent

    config = AgentConfig()
    agent = Agent(config=config)
    assert agent.agent_name is None
