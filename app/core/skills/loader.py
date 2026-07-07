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

    @staticmethod
    def _to_relative(path: Path, project_root: Path) -> str:
        """把绝对路径转换为相对 project_root 的 POSIX 字符串。

        路径不在 project_root 下时降级返回原绝对路径的 POSIX 形式
        （常见于用户扩展路径指向项目外、Windows 跨盘符等场景）。

        Args:
            path: 待归一化的绝对路径。
            project_root: 项目根目录。

        Returns:
            POSIX 风格路径字符串（Windows/Linux 通用）。
        """
        try:
            return path.resolve().relative_to(project_root.resolve()).as_posix()
        except ValueError:
            logger.debug(
                "skill path %s not under project_root %s, fallback to absolute",
                path, project_root,
            )
            return path.resolve().as_posix()

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
            SkillInfo.location / base_dir 是相对 project_root 的 POSIX 路径。
        """
        skills: dict[str, SkillInfo] = {}
        for rel in self.DEFAULT_ROOTS:
            self._scan_dir(project_root / rel, project_root, skills)
        for path in extra_paths:
            if not path.exists():
                logger.warning("skill path not found: %s", path)
                continue
            self._scan_dir(path, project_root, skills)
        return skills

    def _scan_dir(
        self, root: Path, project_root: Path, skills: dict[str, SkillInfo]
    ) -> None:
        """
        在单个目录下递归扫描 SKILL.md 文件。

        Args:
            root: 待扫描的目录。
            project_root: 项目根目录，用于将 SKILL.md 路径归一化为相对路径。
            skills: 扫描结果收集字典，会被原地修改。

        Returns:
            None
        """
        if not root.exists() or not root.is_dir():
            return
        for md_path in root.glob(self.SKILL_PATTERN):
            if not md_path.is_file():
                continue
            info = self._parse(md_path, project_root)
            if info is None:
                continue
            if info.name in skills:
                logger.warning(
                    "duplicate skill name '%s': %s overrides %s",
                    info.name, info.location, skills[info.name].location,
                )
            skills[info.name] = info

    def _parse(self, md_path: Path, project_root: Path) -> SkillInfo | None:
        """
        解析单个 SKILL.md 文件。

        location / base_dir 输出相对 project_root 的 POSIX 路径（Windows/Linux 通用），
        消费者通过 SkillRegistryService._to_absolute() 还原为绝对路径再做文件操作。

        Args:
            md_path: SKILL.md 文件路径。
            project_root: 项目根目录，用于相对路径计算。

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
            location=self._to_relative(md_path, project_root),
            content=m.group(2),
            base_dir=self._to_relative(md_path.parent, project_root),
        )
