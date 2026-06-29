# -*- coding:utf-8 -*-
"""
测试 app.core.prompts 提示词模块

验证 BASE_SYSTEM_PROMPT 为非空字符串。
"""

from app.core.prompts import BASE_SYSTEM_PROMPT


def test_base_system_prompt_contains_time_handling():
    """
    测试 BASE_SYSTEM_PROMPT 包含时间处理策略说明。

    Returns:
        None

    异常:
        AssertionError: 未包含 # Time Handling 或 get_current_time 指令时抛出
    """
    assert "# Time Handling" in BASE_SYSTEM_PROMPT
    assert "get_current_time" in BASE_SYSTEM_PROMPT
    assert "今天" in BASE_SYSTEM_PROMPT

    """
    测试 BASE_SYSTEM_PROMPT 为非空字符串。

    Returns:
        None

    异常:
        AssertionError: BASE_SYSTEM_PROMPT 为空或不是字符串时抛出
    """
    assert isinstance(BASE_SYSTEM_PROMPT, str)
    assert len(BASE_SYSTEM_PROMPT.strip()) > 0


