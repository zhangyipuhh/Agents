# -*- coding:utf-8 -*-
"""
BootstrapProvider 单元测试。

覆盖 <EXTREMELY_IMPORTANT> 包裹、默认文件读取、优先级链（agent > user_global >
系统默认 > 代码内置 fallback）以及缺失文件回退场景。
"""

from pathlib import Path

import pytest

from app.core.skills.bootstrap import _FALLBACK_TOOL_MAPPING, BootstrapProvider


@pytest.fixture
def provider(tmp_path: Path) -> BootstrapProvider:
    """
    返回以临时目录为 project_root 的 BootstrapProvider 实例。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        配置好的 BootstrapProvider 实例。
    """
    return BootstrapProvider(project_root=tmp_path)


def test_render_wraps_content_with_extremely_important(provider: BootstrapProvider, tmp_path: Path):
    """
    render() 输出应以 <EXTREMELY_IMPORTANT> 开头并以 </EXTREMELY_IMPORTANT> 结尾。

    Args:
        provider: BootstrapProvider 实例。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    default_path = tmp_path / BootstrapProvider.DEFAULT_BOOTSTRAP_PATH
    default_path.parent.mkdir(parents=True, exist_ok=True)
    default_path.write_text("hello bootstrap", encoding="utf-8")

    result = provider.render()

    assert result.startswith(f"{BootstrapProvider.WRAPPER_OPEN}\n")
    assert result.endswith(f"\n{BootstrapProvider.WRAPPER_CLOSE}")


def test_render_reads_default_bootstrap_md(provider: BootstrapProvider, tmp_path: Path):
    """
    无参数调用时应读取 app/core/skills/bootstrap.md 内容并包裹。

    Args:
        provider: BootstrapProvider 实例。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    default_path = tmp_path / BootstrapProvider.DEFAULT_BOOTSTRAP_PATH
    default_path.parent.mkdir(parents=True, exist_ok=True)
    default_path.write_text("default bootstrap content", encoding="utf-8")

    result = provider.render()

    assert "default bootstrap content" in result
    assert result.startswith(BootstrapProvider.WRAPPER_OPEN)
    assert result.endswith(BootstrapProvider.WRAPPER_CLOSE)


def test_render_returns_fallback_when_no_file_exists(provider: BootstrapProvider):
    """
    默认 bootstrap.md 不存在时应返回包裹的代码内置 Tool Mapping fallback。

    Args:
        provider: BootstrapProvider 实例。

    Returns:
        None
    """
    result = provider.render()

    assert _FALLBACK_TOOL_MAPPING in result
    assert result.startswith(BootstrapProvider.WRAPPER_OPEN)
    assert result.endswith(BootstrapProvider.WRAPPER_CLOSE)


def test_render_agent_bootstrap_overrides_default(provider: BootstrapProvider, tmp_path: Path):
    """
    提供存在的 agent_bootstrap_path 时应优先使用该文件，覆盖系统默认。

    Args:
        provider: BootstrapProvider 实例。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    default_path = tmp_path / BootstrapProvider.DEFAULT_BOOTSTRAP_PATH
    default_path.parent.mkdir(parents=True, exist_ok=True)
    default_path.write_text("default content", encoding="utf-8")

    agent_path = tmp_path / "agent" / "bootstrap.md"
    agent_path.parent.mkdir(parents=True, exist_ok=True)
    agent_path.write_text("agent content", encoding="utf-8")

    result = provider.render(agent_bootstrap_path=str(agent_path.relative_to(tmp_path)))

    assert "agent content" in result
    assert "default content" not in result


def test_render_user_global_overrides_system_default(provider: BootstrapProvider, tmp_path: Path):
    """
    提供存在的 user_global_path 时应优先使用该文件，覆盖系统默认。

    Args:
        provider: BootstrapProvider 实例。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    default_path = tmp_path / BootstrapProvider.DEFAULT_BOOTSTRAP_PATH
    default_path.parent.mkdir(parents=True, exist_ok=True)
    default_path.write_text("default content", encoding="utf-8")

    user_path = tmp_path / "user" / "bootstrap.md"
    user_path.parent.mkdir(parents=True, exist_ok=True)
    user_path.write_text("user global content", encoding="utf-8")

    result = provider.render(user_global_path=str(user_path.relative_to(tmp_path)))

    assert "user global content" in result
    assert "default content" not in result


def test_render_agent_beats_user_global(provider: BootstrapProvider, tmp_path: Path):
    """
    同时提供 agent_bootstrap_path 与 user_global_path 时，agent 优先级更高。

    Args:
        provider: BootstrapProvider 实例。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    agent_path = tmp_path / "agent" / "bootstrap.md"
    agent_path.parent.mkdir(parents=True, exist_ok=True)
    agent_path.write_text("agent content", encoding="utf-8")

    user_path = tmp_path / "user" / "bootstrap.md"
    user_path.parent.mkdir(parents=True, exist_ok=True)
    user_path.write_text("user global content", encoding="utf-8")

    result = provider.render(
        agent_bootstrap_path=str(agent_path.relative_to(tmp_path)),
        user_global_path=str(user_path.relative_to(tmp_path)),
    )

    assert "agent content" in result
    assert "user global content" not in result


def test_render_skips_missing_agent_path_falls_to_default(provider: BootstrapProvider, tmp_path: Path):
    """
    agent_bootstrap_path 指向缺失文件时应回退到系统默认。

    Args:
        provider: BootstrapProvider 实例。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    default_path = tmp_path / BootstrapProvider.DEFAULT_BOOTSTRAP_PATH
    default_path.parent.mkdir(parents=True, exist_ok=True)
    default_path.write_text("default content", encoding="utf-8")

    result = provider.render(agent_bootstrap_path="agent/missing_bootstrap.md")

    assert "default content" in result


def test_render_includes_tool_mapping_keywords(provider: BootstrapProvider):
    """
    代码内置 fallback 应包含项目实际工具映射关键字。

    Args:
        provider: BootstrapProvider 实例。

    Returns:
        None
    """
    result = provider.render()

    assert "sandbox" in result
    assert "explore" in result
    assert "load_skill" in result
    assert "todowrite" in result
    assert "OpenCode" not in result
