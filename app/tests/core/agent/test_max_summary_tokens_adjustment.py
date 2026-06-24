# -*- coding:utf-8 -*-
"""
Agent max_summary_tokens 防御性调整测试

验证 Agent.__init__ 在 max_summary_tokens >= max_tokens 时
自动调整 max_summary_tokens = max_tokens // 2 并记录 warning。
"""
import logging
import pytest

from app.core.agent.AgentConfig import AgentConfig


def _make_config(**overrides):
    """构造测试用 AgentConfig，屏蔽 LLM/工具相关字段的副作用。"""
    defaults = {
        "name": "test_agent",
        "system_prompt": "test",
        "max_tokens": 999999999,
        "max_tokens_before_summary": 999999999,
        "max_summary_tokens": 999999999,
    }
    defaults.update(overrides)
    return AgentConfig(**defaults)


def test_default_values_get_adjusted_to_half():
    """三个默认值都是 999999999 时，max_summary_tokens 应被自动调整为 999999999 // 2。"""
    from app.core.agent.agent import Agent
    from app.core.config.config import LLM_CONFIG

    config = _make_config()  # 全 999999999
    agent = Agent(config)

    assert agent._max_tokens == 999999999
    assert agent._max_summary_tokens == 999999999 // 2  # 499999999
    # 关键断言：严格小于
    assert agent._max_summary_tokens < agent._max_tokens


def test_user_customized_summary_keeps_value():
    """用户显式把 max_summary_tokens 设小（< max_tokens）时不应被调整。"""
    from app.core.agent.agent import Agent

    config = _make_config(max_tokens=8000, max_summary_tokens=2000)
    agent = Agent(config)

    assert agent._max_tokens == 8000
    assert agent._max_summary_tokens == 2000  # 保持原值


def test_user_inverted_values_get_adjusted():
    """用户把 max_summary_tokens 设得 >= max_tokens 时应被自动调整。"""
    from app.core.agent.agent import Agent

    # 模拟用户错误地把 max_summary_tokens 设得比 max_tokens 大
    config = _make_config(max_tokens=8000, max_summary_tokens=16000)
    agent = Agent(config)

    assert agent._max_tokens == 8000
    # 16000 >= 8000，触发调整 → 8000 // 2 = 4000
    assert agent._max_summary_tokens == 4000


def test_adjustment_logs_warning(caplog):
    """调整时应记录 warning 日志。"""
    from app.core.agent.agent import Agent

    config = _make_config()
    with caplog.at_level(logging.WARNING):
        Agent(config)

    # 验证日志包含调整信息
    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("max_summary_tokens" in msg and "已自动调整" in msg for msg in warning_messages)


def test_equal_values_at_smaller_scale():
    """小规模场景：max_tokens == max_summary_tokens == 100 应被调整为 50。"""
    from app.core.agent.agent import Agent

    config = _make_config(max_tokens=100, max_summary_tokens=100)
    agent = Agent(config)

    assert agent._max_summary_tokens == 50
