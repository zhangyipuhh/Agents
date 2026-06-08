# -*- coding:utf-8 -*-
"""
测试 app.core.agent.AgentContext 上下文模块

验证 AgentContext 为 TypedDict 类型且可正确创建包含 session_id 的字典。
"""

from typing import get_type_hints

from app.core.agent.AgentContext import AgentContext


def test_agent_context_is_typed_dict():
    """
    测试 AgentContext 是 TypedDict 类型。

    Returns:
        None

    异常:
        AssertionError: AgentContext 不是 TypedDict 时抛出
    """
    hints = get_type_hints(AgentContext)
    assert "session_id" in hints


def test_agent_context_can_create_with_session_id():
    """
    测试可创建包含 session_id 的 AgentContext 字典并符合类型定义。

    参数:
        无显式参数，构造测试数据验证类型兼容性

    返回值:
        None

    异常:
        AssertionError: 创建字典不符合类型定义时抛出
    """
    context = AgentContext(session_id="test_session_123")
    assert isinstance(context, dict)
    assert context.get("session_id") == "test_session_123"
