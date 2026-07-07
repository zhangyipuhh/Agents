# -*- coding:utf-8 -*-
"""
render_available_skills_block 单元测试。

覆盖空列表、单 skill XML 渲染、无描述过滤、按名称排序、XML 特殊字符转义等场景。
"""

from pathlib import Path

from app.core.skills.prompt import render_available_skills_block
from app.core.skills.schemas import SkillInfo


def _skill(
    tmp_path: Path,
    name: str,
    description: str | None,
    location: str | None = None,
) -> SkillInfo:
    """
    构造测试用的 SkillInfo 实例。

    Args:
        tmp_path: pytest 提供的临时目录，用于生成绝对路径。
        name: skill 名称。
        description: skill 描述（None 表示无描述）。
        location: SKILL.md 文件路径；为 None 时使用 tmp_path 下的默认路径。

    Returns:
        SkillInfo 实例。
    """
    if location is None:
        location = str(tmp_path / "SKILL.md")
    return SkillInfo(
        name=name,
        description=description,
        location=location,
        content="skill body\n",
        base_dir=str(Path(location).parent),
    )


def test_empty_list_returns_no_skills_message():
    """
    空 skill 列表返回固定提示文本。

    Returns:
        None
    """
    result = render_available_skills_block([])

    assert result == "No skills are currently available."


def test_non_empty_returns_xml_block(tmp_path: Path):
    """
    单个 skill 返回包含必要标签的 XML 块。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    location = str(tmp_path / "skills" / "alpha" / "SKILL.md")
    skills = [_skill(tmp_path, "alpha", "Alpha skill", location)]

    result = render_available_skills_block(skills)

    expected = (
        "<available_skills>\n"
        "  <skill>\n"
        "    <name>alpha</name>\n"
        "    <description>Alpha skill</description>\n"
        f"    <location>{Path(location).as_uri()}</location>\n"
        "  </skill>\n"
        "</available_skills>"
    )
    assert result == expected


def test_filters_skills_without_description(tmp_path: Path):
    """
    无描述的 skill 被过滤，仅保留有描述的 skill。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    skills = [
        _skill(tmp_path, "with_desc", "I have a description"),
        _skill(tmp_path, "no_desc", None),
    ]

    result = render_available_skills_block(skills)

    assert "<name>with_desc</name>" in result
    assert "<name>no_desc</name>" not in result
    assert "I have a description" in result


def test_sorts_by_name(tmp_path: Path):
    """
    输出按 skill 名称升序排列。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    skills = [
        _skill(tmp_path, "charlie", "Charlie skill"),
        _skill(tmp_path, "alpha", "Alpha skill"),
        _skill(tmp_path, "bravo", "Bravo skill"),
    ]

    result = render_available_skills_block(skills)

    alpha_pos = result.index("<name>alpha</name>")
    bravo_pos = result.index("<name>bravo</name>")
    charlie_pos = result.index("<name>charlie</name>")
    assert alpha_pos < bravo_pos < charlie_pos


def test_xml_special_chars_escaped(tmp_path: Path):
    """
    描述中的 XML 特殊字符被正确转义。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    skills = [_skill(tmp_path, "escape", "Use <tag> & more \"text\"")]

    result = render_available_skills_block(skills)

    assert "<description>Use &lt;tag&gt; &amp; more \"text\"</description>" in result
    assert "<tag>" not in result
    assert "&amp;" in result


def test_relative_location_is_resolved_to_absolute_uri(tmp_path: Path, monkeypatch):
    """2026-06-30 修复：s.location 为相对路径时不应抛 ValueError。

    场景复现：实际生产中 SkillInfo.location 是 project_root 相对路径（POSIX 风格），
    直接 Path(s.location).as_uri() 会抛 "relative path can't be expressed as a file URI"。
    修复后应通过 SkillRegistryService._to_absolute 还原为绝对路径再构造 URI。

    Args:
        tmp_path: pytest 提供的临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    # 模拟项目根：把 tmp_path 当作项目根
    # 注意 prompt.py 用 Path(__file__).parent.parent.parent.parent 取项目根，
    # 测试时已是项目根目录（tests 在 app/tests 下），无法 monkeypatch 路径计算。
    # 改为直接构造相对路径格式的 location，让 _to_absolute 通过 POSIX 相对路径逻辑处理。
    relative_location = "app/skills/test_skill/SKILL.md"
    skills = [
        SkillInfo(
            name="relative_skill",
            description="Skill with relative location",
            location=relative_location,
            content="body",
            base_dir="app/skills/test_skill",
        )
    ]

    result = render_available_skills_block(skills)

    # 不应抛 ValueError，输出应包含 file:// URI
    assert "<location>file:///" in result
    assert "<name>relative_skill</name>" in result
