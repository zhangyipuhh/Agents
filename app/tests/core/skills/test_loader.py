# -*- coding:utf-8 -*-
"""
SkillDiscovery 单元测试。

覆盖默认根扫描、额外路径解析（绝对 / 相对 / ~ 展开）、frontmatter 容错、
同名 skill 后扫描覆盖等场景。
"""

import logging
from pathlib import Path

from app.core.skills.loader import SkillDiscovery


def _write_skill(path: Path, name: str, description: str | None = None, body: str = "skill body\n") -> Path:
    """
    在指定目录写入 SKILL.md 文件。

    Args:
        path: SKILL.md 所在的目录。
        name: frontmatter 中的 name 字段。
        description: frontmatter 中的 description 字段（可选）。
        body: 去除 frontmatter 后的正文。

    Returns:
        写入的 SKILL.md 文件路径。
    """
    path.mkdir(parents=True, exist_ok=True)
    md = path / "SKILL.md"
    fm = f"name: {name}\n"
    if description is not None:
        fm += f"description: {description}\n"
    md.write_text(f"---\n{fm}---\n{body}", encoding="utf-8")
    return md


def test_scan_finds_skill_md_files(tmp_path: Path):
    """
    默认扫描能发现 app/skills/<name>/SKILL.md 并返回正确的 SkillInfo。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    _write_skill(tmp_path / "app" / "skills" / "a", "a", "first skill")

    discovery = SkillDiscovery()
    skills = discovery.scan(tmp_path, [])

    assert "a" in skills
    info = skills["a"]
    assert info.name == "a"
    assert info.description == "first skill"
    # location / base_dir 应为相对 project_root 的 POSIX 路径（Windows/Linux 通用）
    assert info.location == "app/skills/a/SKILL.md"
    assert info.base_dir == "app/skills/a"
    assert info.content == "skill body\n"


def test_scan_finds_multiple_roots(tmp_path: Path):
    """
    同时扫描 app/skills 与 .agents/skills 两个默认根。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    _write_skill(tmp_path / "app" / "skills" / "a", "a")
    _write_skill(tmp_path / ".agents" / "skills" / "b", "b")

    discovery = SkillDiscovery()
    skills = discovery.scan(tmp_path, [])

    assert set(skills.keys()) == {"a", "b"}


def test_scan_skips_missing_name_frontmatter(tmp_path: Path, caplog):
    """
    frontmatter 缺少 name 字段时跳过并记录警告。

    Args:
        tmp_path: pytest 提供的临时目录。
        caplog: pytest 日志捕获 fixture。

    Returns:
        None
    """
    skill_dir = tmp_path / "app" / "skills" / "bad"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\ndescription: no name\n---\nbody\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        skills = SkillDiscovery().scan(tmp_path, [])

    assert skills == {}
    assert any("missing 'name'" in record.message for record in caplog.records)


def test_scan_skips_invalid_yaml(tmp_path: Path, caplog):
    """
    frontmatter YAML 解析失败时跳过并记录警告。

    Args:
        tmp_path: pytest 提供的临时目录。
        caplog: pytest 日志捕获 fixture。

    Returns:
        None
    """
    skill_dir = tmp_path / "app" / "skills" / "bad_yaml"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: [unclosed\n---\nbody\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        skills = SkillDiscovery().scan(tmp_path, [])

    assert skills == {}
    assert any("invalid YAML" in record.message for record in caplog.records)


def test_scan_later_overrides_earlier(tmp_path: Path, caplog):
    """
    app/skills 与 .agents/skills 出现同名 skill 时，后扫描的 .agents 版本覆盖前者。

    Args:
        tmp_path: pytest 提供的临时目录。
        caplog: pytest 日志捕获 fixture。

    Returns:
        None
    """
    _write_skill(tmp_path / "app" / "skills" / "a", "a", description="first", body="first body\n")
    _write_skill(
        tmp_path / ".agents" / "skills" / "a",
        "a",
        description="second",
        body="second body\n",
    )

    with caplog.at_level(logging.WARNING):
        skills = SkillDiscovery().scan(tmp_path, [])

    assert skills["a"].description == "second"
    assert skills["a"].content == "second body\n"
    # 后扫描的 .agents/skills 版本覆盖前者，location 是相对路径
    assert skills["a"].location == ".agents/skills/a/SKILL.md"
    assert any("duplicate skill name 'a'" in record.message for record in caplog.records)


def test_scan_skips_nonexistent_extra_path(tmp_path: Path, caplog):
    """
    extra_paths 中包含不存在的路径时记录警告并跳过。

    Args:
        tmp_path: pytest 提供的临时目录。
        caplog: pytest 日志捕获 fixture。

    Returns:
        None
    """
    with caplog.at_level(logging.WARNING):
        skills = SkillDiscovery().scan(tmp_path, [tmp_path / "no_dir"])

    assert skills == {}
    assert any("skill path not found" in record.message for record in caplog.records)


def test_scan_extra_path_absolute(tmp_path: Path):
    """
    extra_paths 使用绝对路径时直接扫描该目录。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    abs_dir = tmp_path / "absolute" / "skills"
    _write_skill(abs_dir / "abs_skill", "abs_skill", "absolute path")

    skills = SkillDiscovery().scan(tmp_path, [abs_dir])

    assert "abs_skill" in skills
    assert skills["abs_skill"].description == "absolute path"


def test_scan_returns_empty_for_no_skills(tmp_path: Path):
    """
    没有任何 SKILL.md 时返回空字典。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    skills = SkillDiscovery().scan(tmp_path, [])

    assert skills == {}


def test_to_relative_under_project_root(tmp_path: Path):
    """
    _to_relative：路径在 project_root 下时返回 POSIX 形式相对路径。

    Args:
        tmp_path: pytest 提供的临时目录，作为 project_root。

    Returns:
        None
    """
    _write_skill(tmp_path / "app" / "skills" / "x", "x")
    target = (tmp_path / "app" / "skills" / "x" / "SKILL.md").resolve()

    rel = SkillDiscovery._to_relative(target, tmp_path)

    # 跨平台统一为 POSIX 形式（正斜杠）
    assert rel == "app/skills/x/SKILL.md"
    assert "\\" not in rel


def test_to_relative_fallback_outside_project_root(tmp_path: Path):
    """
    _to_relative：路径不在 project_root 下时降级返回原绝对路径的 POSIX 形式。

    构造一个兄弟目录的路径（与 tmp_path 共享父目录），保证目标路径不在
    project_root 子树下。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    # sibling 目录：与 tmp_path 同级，路径不在 tmp_path 子树下
    sibling = tmp_path.parent / "sibling_dir_for_fallback_test"
    sibling.mkdir(exist_ok=True)
    target = sibling / "SKILL.md"

    rel = SkillDiscovery._to_relative(target, tmp_path)

    assert rel == target.resolve().as_posix()
    # 验证返回的是绝对路径（POSIX 形式含盘符）
    assert ":\\" in str(target) or rel.startswith("/")
