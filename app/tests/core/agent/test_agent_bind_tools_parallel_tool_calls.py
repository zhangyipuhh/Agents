# -*- coding:utf-8 -*-
"""
Agent.__init__ 对 AgentConfig.parallel_tool_calls 字段的透传优先级测试。

覆盖 2026-08-20 新增逻辑：
    - AgentConfig 基类新增 ``parallel_tool_calls: Optional[bool]`` 字段
    - Agent.__init__ 通过 ``getattr(config, "parallel_tool_calls", None)`` 保存到
      ``self._parallel_tool_calls``，None 表示走全局 LLM_CONFIG 兜底

用例目标：
    1) AgentConfig.parallel_tool_calls 字段存在，默认 None
    2) Agent 实例字段 self._parallel_tool_calls 跟随 config.parallel_tool_calls
       - None → None（表示走全局兜底）
       - False → False（显式覆盖）
       - True → True（显式覆盖）
    3) getattr 容错：当 config 没有 parallel_tool_calls 字段时（旧版 config / 测试 mock），
       Agent._parallel_tool_calls 应为 None

注意：本测试只测 ``__init__`` 同步逻辑（不调 ``__ainit__``），避免依赖真实 LLM/
ModelFactory；``__ainit__`` 的 bind_kwargs 优先级由合同三 wrapper 间接覆盖
（合同 wrapper 的 _ensure_agent 构造 *Config 时已经把 self.parallel_tool_calls
传给 config；Agent 基类 __init__ 把 config.parallel_tool_calls 存到
self._parallel_tool_calls）。
"""

from dataclasses import fields


def test_agent_config_parallel_tool_calls_field_exists():
    """AgentConfig 应包含 parallel_tool_calls 字段（2026-08-20 新增）。"""
    from app.core.agent.AgentConfig import AgentConfig
    config_fields = {f.name: f for f in fields(AgentConfig)}
    assert "parallel_tool_calls" in config_fields, (
        "AgentConfig 应包含 parallel_tool_calls 字段（2026-08-20 新增）"
    )


def test_agent_config_parallel_tool_calls_default_is_none():
    """parallel_tool_calls 字段默认值应为 None（向后兼容，走全局 LLM_CONFIG 兜底）。"""
    from app.core.agent.AgentConfig import AgentConfig
    config_fields = {f.name: f for f in fields(AgentConfig)}
    assert config_fields["parallel_tool_calls"].default is None, (
        "parallel_tool_calls 字段默认值应为 None，走全局 LLM_CONFIG 兜底"
    )


def test_agent_init_reads_parallel_tool_calls_from_config():
    """Agent.__init__ 应从 config.parallel_tool_calls 读取并保存到 self._parallel_tool_calls。"""
    from app.core.agent.AgentConfig import AgentConfig
    from app.core.agent.agent import Agent

    def _make_config(**overrides):
        defaults = {"name": "test_agent", "system_prompt": "test"}
        defaults.update(overrides)
        return AgentConfig(**defaults)

    # 场景 1：默认 None
    config = _make_config()
    agent = Agent(config=config)
    assert agent._parallel_tool_calls is None, (
        "config.parallel_tool_calls=None 时 agent._parallel_tool_calls 应为 None"
    )

    # 场景 2：显式 False
    config = _make_config(parallel_tool_calls=False)
    agent = Agent(config=config)
    assert agent._parallel_tool_calls is False, (
        "config.parallel_tool_calls=False 时 agent._parallel_tool_calls 应为 False"
    )

    # 场景 3：显式 True
    config = _make_config(parallel_tool_calls=True)
    agent = Agent(config=config)
    assert agent._parallel_tool_calls is True, (
        "config.parallel_tool_calls=True 时 agent._parallel_tool_calls 应为 True"
    )


def test_agent_init_getattr_fallback_when_field_missing():
    """Agent.__init__ 用 getattr 容错：config 没 parallel_tool_calls 字段时（旧 mock/老 config）应得 None。"""
    import dataclasses
    from app.core.agent.AgentConfig import AgentConfig
    from app.core.agent.agent import Agent

    # 用 dataclasses 构造完整 AgentConfig 但手动删除 parallel_tool_calls 字段
    # 模拟「老版本 AgentConfig 没有该字段」的向后兼容场景
    config_full = AgentConfig(name="legacy", system_prompt="x")
    legacy_config = dataclasses.make_dataclass(
        "LegacyConfig",
        [(f.name, f.type, dataclasses.field(default=f.default))
         for f in dataclasses.fields(config_full)
         if f.name != "parallel_tool_calls"],
    )()

    agent = Agent(config=legacy_config)
    assert agent._parallel_tool_calls is None, (
        "config 没有 parallel_tool_calls 字段时，getattr fallback 应为 None（向后兼容）"
    )
