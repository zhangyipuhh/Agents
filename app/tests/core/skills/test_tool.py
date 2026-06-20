# -*- coding:utf-8 -*-
"""
load_skill 工具单元测试。

覆盖成功加载返回 XML 块、包含 base_dir URI、文件列表过滤、skill 不存在时返回错误、
文件数量限制为 10 以及 @tool 装饰器注册验证。
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.skills.schemas import SkillInfo
from app.core.skills.service import SkillNotFoundError


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


def test_load_skill_returns_skill_content_block(monkeypatch, tmp_path: Path):
    """
    成功加载时返回包含 <skill_content>、正文与 <skill_files> 的 XML 块。

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

    assert "<skill_content name=\"alpha\">" in result
    assert "This is the alpha skill body." in result
    assert "<skill_files>" in result
    assert "</skill_files>" in result


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

    assert "Base directory for this skill: file:///" in result


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

    assert result.count("<file>") == 2
    assert "script.py" in result
    assert "reference.md" in result
    assert "SKILL.md" not in result.split("<skill_files>")[1].split("</skill_files>")[0]


def test_load_skill_returns_error_for_missing_skill(monkeypatch):
    """
    require 抛出 SkillNotFoundError 时，工具返回 Error: ... 字符串且不传播异常。

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

    assert result.startswith("Error:")
    assert "nope" in result


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

    assert result.count("<file>") == 10


def test_load_skill_tool_is_registered_as_langchain_tool():
    """
    导入的 load_skill 已被 @tool 注册为 LangChain 工具，具备 invoke 方法。

    Returns:
        None
    """
    from app.core.skills.tool import load_skill

    assert hasattr(load_skill, "invoke")
