# -*- coding:utf-8 -*-
"""Skill 扫描与 frontmatter 解析模块。

SkillDiscovery 负责在项目默认根（app/skills、.agents/skills）以及用户扩展路径中
递归查找 SKILL.md，解析 YAML frontmatter 并构建 SkillInfo 注册表。
"""

import logging
import re
from pathlib import Path

import yaml

from .schemas import SkillInfo

logger = logging.getLogger(__name__)

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


class SkillDiscovery:
    """Skill 文件发现器。

    Attributes:
        DEFAULT_ROOTS: 默认扫描根，相对于 project_root。
        SKILL_PATTERN: glob 模式，用于匹配 SKILL.md 文件。
    """

    DEFAULT_ROOTS = ("app/skills", ".agents/skills")
    SKILL_PATTERN = "**/SKILL.md"

    def scan(self, project_root: Path, extra_paths: list[Path]) -> dict[str, SkillInfo]:
        """
        扫描默认根与用户扩展路径，返回 skill 名称到 SkillInfo 的映射。

        扫描顺序决定覆盖关系：默认根按 DEFAULT_ROOTS 顺序扫描，extra_paths 最后扫描，
        后扫描的同名 skill 会覆盖前者。

        路径解析（~/ 展开、绝对路径识别、相对 project_root 拼接）由调用方（如
        ``SkillsService._resolve``）完成；本方法只负责扫描与 frontmatter 解析。

        Args:
            project_root: 项目根目录，默认根相对它解析。
            extra_paths: 已解析为绝对路径的用户扩展扫描路径列表。

        Returns:
            以 skill 名称为键、SkillInfo 为值的字典。
        """
        skills: dict[str, SkillInfo] = {}
        for rel in self.DEFAULT_ROOTS:
            self._scan_dir(project_root / rel, skills)
        for path in extra_paths:
            if not path.exists():
                logger.warning("skill path not found: %s", path)
                continue
            self._scan_dir(path, skills)
        return skills

    def _scan_dir(self, root: Path, skills: dict[str, SkillInfo]) -> None:
        """
        在单个目录下递归扫描 SKILL.md 文件。

        Args:
            root: 待扫描的目录。
            skills: 扫描结果收集字典，会被原地修改。

        Returns:
            None
        """
        if not root.exists() or not root.is_dir():
            return
        for md_path in root.glob(self.SKILL_PATTERN):
            if not md_path.is_file():
                continue
            info = self._parse(md_path)
            if info is None:
                continue
            if info.name in skills:
                logger.warning(
                    "duplicate skill name '%s': %s overrides %s",
                    info.name, md_path, skills[info.name].location,
                )
            skills[info.name] = info

    def _parse(self, md_path: Path) -> SkillInfo | None:
        """
        解析单个 SKILL.md 文件。

        Args:
            md_path: SKILL.md 文件路径。

        Returns:
            解析成功返回 SkillInfo；失败（读取失败、frontmatter 缺失、YAML 非法、
            name 缺失或为空）返回 None，并记录 warning 日志。

        Raises:
            本方法不抛出异常；所有错误均被捕获并记录日志。
        """
        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("failed to read %s: %s", md_path, e)
            return None
        m = FRONTMATTER_RE.match(text)
        if not m:
            logger.warning("SKILL.md %s missing frontmatter", md_path)
            return None
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError as e:
            logger.warning("SKILL.md %s invalid YAML: %s", md_path, e)
            return None
        if not isinstance(fm, dict) or "name" not in fm:
            logger.warning("SKILL.md %s missing 'name' in frontmatter", md_path)
            return None
        name = str(fm["name"]).strip()
        if not name:
            logger.warning("SKILL.md %s empty 'name'", md_path)
            return None
        description = fm.get("description")
        if description is not None:
            description = str(description).strip()
        return SkillInfo(
            name=name,
            description=description,
            location=str(md_path.resolve()),
            content=m.group(2),
            base_dir=str(md_path.resolve().parent),
        )
