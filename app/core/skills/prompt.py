# -*- coding:utf-8 -*-
"""Skill 系统提示词渲染工具。

提供将已加载 skill 列表渲染为 XML 块的能力，供系统提示词注入使用。
"""

from pathlib import Path
from xml.sax.saxutils import escape

from .schemas import SkillInfo


def render_available_skills_block(skills: list[SkillInfo]) -> str:
    """渲染 <available_skills> XML 块，与 opencode Skill.fmt(list, {verbose:true}) 一致。

    Args:
        skills: 全部已加载的 skill 列表

    Returns:
        若无非空描述的 skill，返回 "No skills are currently available."
        否则返回 XML 块字符串
    """
    from app.shared.utils.agent.skill_service import SkillRegistryService
    from app.core.config.paths import _PROJECT_ROOT  # noqa: F401  留作可读性占位

    described = [s for s in skills if s.description]
    if not described:
        return "No skills are currently available."
    lines = ["<available_skills>"]
    for s in sorted(described, key=lambda x: x.name):
        # 2026-06-30 修复：s.location 可能是相对路径（来自 _to_relative），
        # 直接 Path(s.location).as_uri() 会抛 "relative path can't be expressed as a file URI"。
        # 通过 SkillRegistryService._to_absolute 还原为绝对路径后再构造 URI。
        project_root = Path(__file__).parent.parent.parent.parent
        abs_location = SkillRegistryService._to_absolute(s.location, project_root)
        location_uri = abs_location.as_uri()
        lines += [
            "  <skill>",
            f"    <name>{escape(s.name)}</name>",
            f"    <description>{escape(s.description or '')}</description>",
            f"    <location>{escape(location_uri)}</location>",
            "  </skill>",
        ]
    lines.append("</available_skills>")
    return "\n".join(lines)
