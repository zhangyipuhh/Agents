# -*- coding:utf-8 -*-
"""
子智能体工具集中注册表测试（2026-06-16 新增）

覆盖：
    - SUBAGENT_TOOL_NAMES 集合包含当前已注册的 sandbox / explore
    - is_subagent_tool 对注册表内工具返回 True
    - is_subagent_tool 对普通工具（如 generate_report）返回 False（防回归）
    - is_subagent_tool 大小写不敏感
    - is_subagent_tool 对空值/None/非字符串类型返回 False（防御性）
"""
import pytest

from app.core.tools.subagent_registry import SUBAGENT_TOOL_NAMES, is_subagent_tool


# ===== SUBAGENT_TOOL_NAMES 注册内容校验 =====

def test_subagent_tool_names_contains_sandbox():
    """SUBAGENT_TOOL_NAMES 应包含 'sandbox'（来自 SandboxTools.py）"""
    assert "sandbox" in SUBAGENT_TOOL_NAMES


def test_subagent_tool_names_contains_explore():
    """SUBAGENT_TOOL_NAMES 应包含 'explore'（来自 FilesystemReadTools.py）"""
    assert "explore" in SUBAGENT_TOOL_NAMES


# ===== is_subagent_tool 正例 =====

def test_is_subagent_tool_positive():
    """对注册表内工具名应返回 True"""
    assert is_subagent_tool("sandbox") is True
    assert is_subagent_tool("explore") is True


# ===== is_subagent_tool 反例（防回归） =====

def test_is_subagent_tool_negative_for_generate_report():
    """对普通工具 generate_report 应返回 False（用户报告的核心 bug 防回归）"""
    assert is_subagent_tool("generate_report") is False


def test_is_subagent_tool_negative_for_common_tools():
    """对常见的普通工具名应全部返回 False"""
    assert is_subagent_tool("get_current_time") is False
    assert is_subagent_tool("ask_user_question") is False
    assert is_subagent_tool("upload_file") is False
    assert is_subagent_tool("") is False


# ===== is_subagent_tool 大小写不敏感 =====

def test_is_subagent_tool_case_insensitive():
    """工具名不区分大小写（沙箱、子智能体 等可能的大小写变体都应识别）"""
    assert is_subagent_tool("SANDBOX") is True
    assert is_subagent_tool("Sandbox") is True
    assert is_subagent_tool("EXPLORE") is True
    assert is_subagent_tool("Explore") is True
    # 普通工具大小写混写也应识别为非子智能体
    assert is_subagent_tool("Generate_Report") is False


# ===== is_subagent_tool 输入防御 =====

def test_is_subagent_tool_defensive_inputs():
    """对 None / 非字符串 / 数字等异常输入应安全返回 False 而不抛错"""
    assert is_subagent_tool(None) is False
    assert is_subagent_tool("") is False
    assert is_subagent_tool(123) is False
    assert is_subagent_tool(["sandbox"]) is False
    assert is_subagent_tool({"name": "sandbox"}) is False


# ===== SUBAGENT_TOOL_NAMES 不可变性 =====

def test_subagent_tool_names_is_frozenset():
    """SUBAGENT_TOOL_NAMES 应为 frozenset，防止运行期误改"""
    from typing import FrozenSet
    assert isinstance(SUBAGENT_TOOL_NAMES, frozenset)
    # frozenset 没有 .add() 方法（会抛 AttributeError），验证不可变
    with pytest.raises(AttributeError):
        SUBAGENT_TOOL_NAMES.add("new_tool")  # type: ignore[attr-defined]