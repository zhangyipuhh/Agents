# -*- coding:utf-8 -*-
"""
load_skill 工具单元测试。

覆盖成功加载返回 XML 块、包含 base_dir URI、文件列表过滤、skill 不存在时返回错误、
文件数量限制为 10 以及 @tool 装饰器注册验证。
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langgraph.types import Command

from app.core.skills.schemas import SkillInfo
from app.core.skills.service import SkillNotFoundError


class _RealToolMessage:
    """
    真实可断言的 ToolMessage 替身。

    conftest 将 langchain_core.messages.ToolMessage 整体 mock 为 Mock()，
    构造出的对象属性访问仍返回 Mock，无法对 content / tool_call_id 做字符串断言。
    本类提供 content / tool_call_id 两个真实属性，patch 后 tool.py 内的
    ToolMessage(content=..., tool_call_id=...) 调用会生成可断言的实例。
    """

    def __init__(self, content, tool_call_id):
        self.content = content
        self.tool_call_id = tool_call_id


def _make_service_mock(info: SkillInfo | None = None, available: list[str] | None = None) -> MagicMock:
    """
    构造一个用于替换 SkillsService.get_instance() 返回值的 mock 服务。

    Args:
        info: 调用 require 时返回的 SkillInfo；为 None 时抛出 SkillNotFoundError。
        available: skill 不存在时异常中包含的可用 skill 列表。

    Returns:
        配置好的 MagicMock 服务实例。
    """
    service = MagicMock()

    def _require(name: str) -> SkillInfo:
        if info is None:
            raise SkillNotFoundError(name, available or [])
        return info

    service.require.side_effect = _require
    return service


@pytest.fixture(autouse=True)
def _reset_singleton():
    """
    每个用例前后清空 SkillsService 单例缓存，避免状态泄漏。

    Yields:
        None
    """
    from app.core.skills.service import SkillsService

    SkillsService.reset()
    yield
    SkillsService.reset()


@pytest.fixture(autouse=True)
def _patch_tool_message():
    """
    将 tool.py 模块内的 ToolMessage 替换为 _RealToolMessage，使 Command 中的
    ToolMessage 实例具有可断言的真实 content / tool_call_id 属性。

    Yields:
        None
    """
    with patch("app.core.skills.tool.ToolMessage", _RealToolMessage):
        yield


def _unwrap(result):
    """
    从 load_skill 返回的 Command 中解包出 ToolMessage.content 字符串。

    Args:
        result: load_skill.invoke() 的返回值，应为 Command 实例。

    Returns:
        Command.update["messages"][0].content 字符串。

    Raises:
        AssertionError: 当 result 不是 Command 或 messages 数量不为 1 时。
    """
    assert isinstance(result, Command)
    messages = result.update["messages"]
    assert len(messages) == 1
    return messages[0].content


def test_load_skill_returns_skill_content_block(monkeypatch, tmp_path: Path):
    """
    成功加载时返回 Command，content 含 <skill_content>、正文与 <skill_files> 的 XML 块。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    base_dir = tmp_path / "skills" / "alpha"
    base_dir.mkdir(parents=True)
    info = SkillInfo(
        name="alpha",
        description="Alpha skill",
        location=str(base_dir / "SKILL.md"),
        content="This is the alpha skill body.",
        base_dir=str(base_dir),
    )
    service = _make_service_mock(info)
    monkeypatch.setattr(
        "app.core.skills.tool.SkillsService.get_instance", lambda: service
    )

    from app.core.skills.tool import load_skill

    result = load_skill.invoke({"name": "alpha"})

    assert isinstance(result, Command)
    content = _unwrap(result)
    assert "<skill_content name=\"alpha\">" in content
    assert "This is the alpha skill body." in content
    assert "<skill_files>" in content
    assert "</skill_files>" in content
    # 验证 tool_call_id 透传
    assert result.update["messages"][0].tool_call_id == "test-tool-call-id"


def test_load_skill_includes_base_dir_uri(monkeypatch, tmp_path: Path):
    """
    返回结果中包含 skill 所在目录的 file:/// URI。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    base_dir = tmp_path / "skills" / "alpha"
    base_dir.mkdir(parents=True)
    info = SkillInfo(
        name="alpha",
        description="Alpha skill",
        location=str(base_dir / "SKILL.md"),
        content="body",
        base_dir=str(base_dir),
    )
    service = _make_service_mock(info)
    monkeypatch.setattr(
        "app.core.skills.tool.SkillsService.get_instance", lambda: service
    )

    from app.core.skills.tool import load_skill

    result = load_skill.invoke({"name": "alpha"})

    assert isinstance(result, Command)
    content = _unwrap(result)
    assert "Base directory for this skill: file:///" in content


def test_load_skill_includes_file_list(monkeypatch, tmp_path: Path):
    """
    base_dir 包含 SKILL.md 与另外两个文件时，返回结果列出这两个文件。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    base_dir = tmp_path / "skills" / "alpha"
    base_dir.mkdir(parents=True)
    (base_dir / "SKILL.md").write_text("---\nname: alpha\n---\nbody", encoding="utf-8")
    (base_dir / "script.py").write_text("# script", encoding="utf-8")
    (base_dir / "reference.md").write_text("# reference", encoding="utf-8")
    info = SkillInfo(
        name="alpha",
        description="Alpha skill",
        location=str(base_dir / "SKILL.md"),
        content="body",
        base_dir=str(base_dir),
    )
    service = _make_service_mock(info)
    monkeypatch.setattr(
        "app.core.skills.tool.SkillsService.get_instance", lambda: service
    )

    from app.core.skills.tool import load_skill

    result = load_skill.invoke({"name": "alpha"})

    assert isinstance(result, Command)
    content = _unwrap(result)
    assert content.count("<file>") == 2
    assert "script.py" in content
    assert "reference.md" in content
    assert "SKILL.md" not in content.split("<skill_files>")[1].split("</skill_files>")[0]


def test_load_skill_returns_error_for_missing_skill(monkeypatch):
    """
    require 抛出 SkillNotFoundError 时，工具返回 Command，content 以 Error: 开头且不传播异常。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    service = _make_service_mock(None, available=["alpha", "bravo"])
    monkeypatch.setattr(
        "app.core.skills.tool.SkillsService.get_instance", lambda: service
    )

    from app.core.skills.tool import load_skill

    result = load_skill.invoke({"name": "nope"})

    assert isinstance(result, Command)
    content = _unwrap(result)
    assert content.startswith("Error:")
    assert "nope" in content


def test_load_skill_limits_files_to_10(monkeypatch, tmp_path: Path):
    """
    base_dir 包含 15 个非 SKILL.md 文件时，返回结果最多列出 10 个。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    base_dir = tmp_path / "skills" / "alpha"
    base_dir.mkdir(parents=True)
    (base_dir / "SKILL.md").write_text("---\nname: alpha\n---\nbody", encoding="utf-8")
    for i in range(15):
        (base_dir / f"file_{i:02d}.txt").write_text(f"content {i}", encoding="utf-8")
    info = SkillInfo(
        name="alpha",
        description="Alpha skill",
        location=str(base_dir / "SKILL.md"),
        content="body",
        base_dir=str(base_dir),
    )
    service = _make_service_mock(info)
    monkeypatch.setattr(
        "app.core.skills.tool.SkillsService.get_instance", lambda: service
    )

    from app.core.skills.tool import load_skill

    result = load_skill.invoke({"name": "alpha"})

    assert isinstance(result, Command)
    content = _unwrap(result)
    assert content.count("<file>") == 10


def test_load_skill_tool_is_registered_as_langchain_tool():
    """
    导入的 load_skill 已被 @tool 注册为 LangChain 工具，具备 invoke 方法。

    Returns:
        None
    """
    from app.core.skills.tool import load_skill

    assert hasattr(load_skill, "invoke")
