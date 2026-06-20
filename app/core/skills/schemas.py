# -*- coding:utf-8 -*-
"""Skill 系统 Pydantic 模型。

定义 skill 元信息（SkillInfo）与运行时配置（SkillsConfig）。
"""

from typing import Optional

from pydantic import BaseModel, Field


class SkillInfo(BaseModel):
    """单个 skill 的元信息。

    Attributes:
        name: skill 名称（来自 SKILL.md frontmatter name 字段，必须全局唯一）
        description: skill 用途描述（来自 frontmatter description 字段，可选）
        location: SKILL.md 文件绝对路径
        content: 去除 frontmatter 后的正文
        base_dir: SKILL.md 所在目录绝对路径（同目录下脚本/参考文档的访问入口）
    """

    name: str
    description: Optional[str] = None
    location: str
    content: str
    base_dir: str


class SkillsConfig(BaseModel):
    """Skill 系统运行时配置。

    Attributes:
        paths: 用户扩展扫描路径，支持绝对路径、~/ 缩写、相对项目根
        bootstrap_path: 用户自定义全局 bootstrap 文件路径（可选）
        enabled: 总开关；False 时不扫描、不注入、不注册工具
    """

    paths: list[str] = Field(default_factory=list)
    bootstrap_path: Optional[str] = None
    enabled: bool = True
