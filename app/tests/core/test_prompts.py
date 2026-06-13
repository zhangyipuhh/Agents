# -*- coding:utf-8 -*-
"""
测试 app.core.prompts 提示词模块

验证 BASE_SYSTEM_PROMPT 为非空字符串。
"""

from app.core.prompts import BASE_SYSTEM_PROMPT


def test_base_system_prompt_is_non_empty_string():
    """
    测试 BASE_SYSTEM_PROMPT 为非空字符串。

    Returns:
        None

    异常:
        AssertionError: BASE_SYSTEM_PROMPT 为空或不是字符串时抛出
    """
    assert isinstance(BASE_SYSTEM_PROMPT, str)
    assert len(BASE_SYSTEM_PROMPT.strip()) > 0


