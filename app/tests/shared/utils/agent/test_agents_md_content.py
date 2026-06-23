# -*- coding:utf-8 -*-
"""
AGENTS.md 内容测试模块

验证 agents/map_agent/AGENTS.md 文件存在且包含必要的章节，
同时确保不包含运行时配置字段（纯 markdown 原则）。
"""
from pathlib import Path
import pytest


def _project_root() -> Path:
    """返回项目根目录。

    返回:
        Path: 指向项目根目录的 Path 对象（测试文件向上回溯 6 层父目录，
              从 app/tests/shared/utils/agent/ 回到项目根 feature-agent-core-ref/）
    """
    return Path(__file__).parent.parent.parent.parent.parent.parent


def test_agents_md_file_exists():
    """测试 agents/map_agent/AGENTS.md 文件存在。

    返回:
        None

    异常:
        AssertionError: 当 AGENTS.md 文件不存在时断言失败
    """
    md_path = _project_root() / "agents" / "map_agent" / "AGENTS.md"
    assert md_path.is_file(), f"AGENTS.md not found at {md_path}"


def test_agents_md_contains_identity_section():
    """测试 AGENTS.md 包含身份与职责章节。

    返回:
        None

    异常:
        AssertionError: 当内容中既不包含"身份"也不包含"职责"时断言失败
    """
    content = (_project_root() / "agents" / "map_agent" / "AGENTS.md").read_text(encoding="utf-8")
    assert "身份" in content or "职责" in content


def test_agents_md_contains_tools_section():
    """测试 AGENTS.md 包含可用工具章节。

    返回:
        None

    异常:
        AssertionError: 当内容中不包含"工具"关键字时断言失败
    """
    content = (_project_root() / "agents" / "map_agent" / "AGENTS.md").read_text(encoding="utf-8")
    assert "工具" in content


def test_agents_md_contains_behavior_section():
    """测试 AGENTS.md 包含行为规范章节。

    返回:
        None

    异常:
        AssertionError: 当内容中既不包含"行为"也不包含"规范"时断言失败
    """
    content = (_project_root() / "agents" / "map_agent" / "AGENTS.md").read_text(encoding="utf-8")
    assert "行为" in content or "规范" in content


def test_agents_md_does_not_contain_state_fields():
    """测试 AGENTS.md 不包含 state 字段定义（纯 markdown 原则）。

    返回:
        None

    异常:
        AssertionError: 当内容中包含 state_schema、context_schema 或 TypedDict 时断言失败
    """
    content = (_project_root() / "agents" / "map_agent" / "AGENTS.md").read_text(encoding="utf-8")
    assert "state_schema" not in content
    assert "context_schema" not in content
    assert "TypedDict" not in content
