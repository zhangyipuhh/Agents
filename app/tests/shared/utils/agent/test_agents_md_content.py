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


def test_agents_md_contains_task_rules_section():
    """测试 AGENTS.md 包含 Task Rules 章节。

    返回:
        None

    异常:
        AssertionError: 当内容中不包含"Task Rules"时断言失败
    """
    content = (_project_root() / "agents" / "map_agent" / "AGENTS.md").read_text(encoding="utf-8")
    assert "Task Rules" in content


def test_agents_md_contains_tool_description_section():
    """测试 AGENTS.md 包含 TOOL DESCRIPTION 章节。

    返回:
        None

    异常:
        AssertionError: 当内容中不包含"TOOL DESCRIPTION"或 explore 工具说明时断言失败
    """
    content = (_project_root() / "agents" / "map_agent" / "AGENTS.md").read_text(encoding="utf-8")
    assert "TOOL DESCRIPTION" in content
    assert "explore" in content


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
