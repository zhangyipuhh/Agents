# -*- coding:utf-8 -*-
"""
子智能体工具集中注册表测试（2026-06-16 新增；2026-06-18 扩展 SUBAGENT_META / get_subagent_meta）

覆盖：
    - SUBAGENT_TOOL_NAMES 集合包含当前已注册的 sandbox / explore / query_knowledge
    - is_subagent_tool 对注册表内工具返回 True
    - is_subagent_tool 对普通工具（如 generate_report）返回 False（防回归）
    - is_subagent_tool 大小写不敏感
    - is_subagent_tool 对空值/None/非字符串类型返回 False（防御性）
    - SUBAGENT_META 覆盖所有已注册工具且包含 icon/label
    - get_subagent_meta 对注册工具返回正确 meta，对未知输入返回兜底
"""
import pytest

from app.core.tools.subagent_registry import SUBAGENT_TOOL_NAMES, is_subagent_tool, get_subagent_meta, SUBAGENT_META


# ===== SUBAGENT_TOOL_NAMES 注册内容校验 =====

def test_subagent_tool_names_contains_sandbox():
    """SUBAGENT_TOOL_NAMES 应包含 'sandbox'（来自 SandboxTools.py）"""
    assert "sandbox" in SUBAGENT_TOOL_NAMES


def test_subagent_tool_names_contains_explore():
    """SUBAGENT_TOOL_NAMES 应包含 'explore'（来自 FilesystemReadTools.py）"""
    assert "explore" in SUBAGENT_TOOL_NAMES


def test_subagent_tool_names_contains_query_knowledge():
    """SUBAGENT_TOOL_NAMES 应包含 'query_knowledge'（来自 MapTools.py）"""
    assert "query_knowledge" in SUBAGENT_TOOL_NAMES


# ===== is_subagent_tool 正例 =====

def test_is_subagent_tool_positive():
    """对注册表内工具名应返回 True"""
    assert is_subagent_tool("sandbox") is True
    assert is_subagent_tool("explore") is True
    assert is_subagent_tool("query_knowledge") is True


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


# ===== SUBAGENT_META 内容校验 =====

def test_subagent_meta_contains_registered_tools():
    """SUBAGENT_META 应覆盖所有已注册的子智能体工具"""
    for tool in SUBAGENT_TOOL_NAMES:
        assert tool in SUBAGENT_META
        meta = SUBAGENT_META[tool]
        assert isinstance(meta, dict)
        assert "icon" in meta and isinstance(meta["icon"], str)
        assert "label" in meta and isinstance(meta["label"], str)


def test_subagent_meta_values():
    """SUBAGENT_META 的 icon/label 值应与当前业务定义一致"""
    assert SUBAGENT_META["sandbox"] == {"icon": "📦", "label": "沙箱执行"}
    assert SUBAGENT_META["explore"] == {"icon": "🔍", "label": "文件探索"}
    assert SUBAGENT_META["query_knowledge"] == {"icon": "📚", "label": "知识库检索"}


# ===== get_subagent_meta 正例 =====

def test_get_subagent_meta_registered_tools():
    """对注册表内工具应返回对应 icon/label"""
    assert get_subagent_meta("sandbox") == {"icon": "📦", "label": "沙箱执行"}
    assert get_subagent_meta("explore") == {"icon": "🔍", "label": "文件探索"}
    assert get_subagent_meta("query_knowledge") == {"icon": "📚", "label": "知识库检索"}


def test_get_subagent_meta_case_insensitive():
    """工具名不区分大小写时应返回对应 meta"""
    assert get_subagent_meta("SANDBOX") == {"icon": "📦", "label": "沙箱执行"}
    assert get_subagent_meta("Sandbox") == {"icon": "📦", "label": "沙箱执行"}


# ===== get_subagent_meta 兜底 =====

def test_get_subagent_meta_fallback_for_unknown_tool():
    """对未知工具应返回兜底 meta，icon 为 🤖，label 为工具名"""
    assert get_subagent_meta("unknown_tool") == {"icon": "🤖", "label": "unknown_tool"}


def test_get_subagent_meta_fallback_for_empty_input():
    """对空值/None/非字符串输入应返回兜底 meta，label 为'子智能体'"""
    assert get_subagent_meta("") == {"icon": "🤖", "label": "子智能体"}
    assert get_subagent_meta(None) == {"icon": "🤖", "label": "子智能体"}  # type: ignore[arg-type]
    assert get_subagent_meta(123) == {"icon": "🤖", "label": "子智能体"}  # type: ignore[arg-type]


# ===== get_subagent_meta 不修改原始常量 =====

def test_get_subagent_meta_returns_copy():
    """get_subagent_meta 应返回副本，避免调用方修改原始 SUBAGENT_META"""
    meta = get_subagent_meta("sandbox")
    meta["icon"] = "changed"
    assert SUBAGENT_META["sandbox"]["icon"] == "📦"
