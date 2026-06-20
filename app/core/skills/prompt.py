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
    described = [s for s in skills if s.description]
    if not described:
        return "No skills are currently available."
    lines = ["<available_skills>"]
    for s in sorted(described, key=lambda x: x.name):
        lines += [
            "  <skill>",
            f"    <name>{escape(s.name)}</name>",
            f"    <description>{escape(s.description or '')}</description>",
            f"    <location>{escape(Path(s.location).as_uri())}</location>",
            "  </skill>",
        ]
    lines.append("</available_skills>")
    return "\n".join(lines)
