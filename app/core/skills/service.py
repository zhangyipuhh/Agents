# -*- coding:utf-8 -*-
"""
SkillsService 实现。

提供 SkillInfo 注册中心，支持全局单例与按 agent 维度隔离的 skill 扫描策略。
"""

import logging
from pathlib import Path
from typing import Optional

from .loader import SkillDiscovery
from .schemas import SkillInfo, SkillsConfig

logger = logging.getLogger(__name__)


class SkillNotFoundError(LookupError):
    """Skill 名称未找到。message 字段含 available 列表，便于工具直接返回给 LLM。"""

    def __init__(self, name: str, available: list[str]):
        """
        初始化异常。

        Args:
            name: 未找到的 skill 名称。
            available: 当前可用的 skill 名称列表。
        """
        self.name = name
        self.available = available
        super().__init__(
            f'Skill "{name}" not found. Available skills: '
            f'{", ".join(sorted(available)) or "none"}'
        )


class SkillsService:
    """Skill 注册中心。

    - 无 agent_name 调用：返回全局单例（默认根扫描）
    - 带 agent_name 调用：返回 agent 维度的实例（agent skills/ 覆盖默认根）
    测试可通过 reset() 重置全局单例；agent 维度的实例用 reset(agent_name=...)。
    """

    _instances: dict[Optional[str], "SkillsService"] = {}

    def __init__(
        self,
        config: SkillsConfig,
        agent_name: Optional[str] = None,
        project_root: Optional[Path] = None,
    ):
        """
        初始化服务并扫描 skill。

        Args:
            config: skill 系统运行时配置。
            agent_name: 可选的 agent 名称，用于选择 agent 专属 skill 目录。
            project_root: 项目根目录；默认使用当前工作目录。
        """
        self.config = config
        self.agent_name = agent_name
        self.project_root = project_root or Path.cwd()
        self._skills: dict[str, SkillInfo] = {}
        if config.enabled:
            self._skills = self._scan()
            logger.info(
                "SkillsService loaded %d skills (agent=%s)",
                len(self._skills), agent_name or "<default>",
            )

    def _scan(self) -> dict[str, SkillInfo]:
        """
        根据 agent_name 选择扫描根。

        - agent_name 提供且 app/features/<agent>/skills/ 存在 → 仅扫描该目录
        - 否则 → 扫描默认根 + 用户扩展

        Returns:
            skill 名称到 SkillInfo 的映射。
        """
        if self.agent_name:
            agent_skills_dir = (
                self.project_root / "app" / "features" / self.agent_name / "skills"
            )
            if agent_skills_dir.exists() and agent_skills_dir.is_dir():
                extra = [self._resolve(p) for p in self.config.paths]
                # agent skills 完全覆盖默认根（仅扫描 agent_dir，不追加 DEFAULT_ROOTS）
                discovery = SkillDiscovery()
                skills: dict[str, SkillInfo] = {}
                discovery._scan_dir(agent_skills_dir, skills)
                for p in extra:
                    if p.exists():
                        discovery._scan_dir(p, skills)
                return skills
        extra = [self._resolve(p) for p in self.config.paths]
        return SkillDiscovery().scan(self.project_root, extra)

    def _resolve(self, p: str) -> Path:
        """
        解析用户扩展路径：~ 展开、绝对路径直接用、否则相对 project_root。

        Args:
            p: 用户配置的扩展路径字符串。

        Returns:
            解析后的绝对路径。
        """
        path = Path(p).expanduser()
        if not path.is_absolute():
            path = self.project_root / path
        return path.resolve()

    @classmethod
    def get_instance(
        cls,
        config: Optional[SkillsConfig] = None,
        agent_name: Optional[str] = None,
    ) -> "SkillsService":
        """
        获取单例实例。

        Args:
            config: skill 系统运行时配置；首次创建实例时使用，默认启用空配置。
            agent_name: 可选的 agent 名称；不同 agent 对应不同实例。

        Returns:
            SkillsService 实例（全局单例或 agent 维度单例）。
        """
        key = agent_name
        if key not in cls._instances:
            if config is None:
                config = SkillsConfig()
            cls._instances[key] = cls(config, agent_name=agent_name)
        return cls._instances[key]

    @classmethod
    def reset(cls, agent_name: Optional[str] = None) -> None:
        """
        重置单例缓存。

        Args:
            agent_name: 指定 agent 名称时仅移除该 agent 的实例；
                        为 None 时清空所有实例。

        Returns:
            None
        """
        if agent_name is None:
            cls._instances.clear()
        else:
            cls._instances.pop(agent_name, None)

    def get(self, name: str) -> Optional[SkillInfo]:
        """
        按名称获取 skill。

        Args:
            name: skill 名称。

        Returns:
            SkillInfo 或 None（不存在时）。
        """
        return self._skills.get(name)

    def require(self, name: str) -> SkillInfo:
        """
        按名称获取 skill，不存在时抛出 SkillNotFoundError。

        Args:
            name: skill 名称。

        Returns:
            SkillInfo。

        Raises:
            SkillNotFoundError: skill 不存在时抛出。
        """
        info = self._skills.get(name)
        if info is None:
            raise SkillNotFoundError(name, list(self._skills.keys()))
        return info

    def all(self) -> list[SkillInfo]:
        """
        返回所有已加载的 skill。

        Returns:
            SkillInfo 列表。
        """
        return list(self._skills.values())

    def available(self, name_filter: Optional[list[str]] = None) -> list[SkillInfo]:
        """
        返回满足名称过滤条件的 skill 列表。

        Args:
            name_filter: skill 名称过滤列表；为 None 时返回全部。

        Returns:
            匹配的 SkillInfo 列表，顺序与 name_filter 一致。
        """
        if name_filter is None:
            return self.all()
        return [self._skills[n] for n in name_filter if n in self._skills]
