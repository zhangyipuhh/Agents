# -*- coding:utf-8 -*-
"""
BootstrapProvider 模块。

负责按优先级读取 bootstrap.md 内容，并用 <EXTREMELY_IMPORTANT> 标签包裹后注入系统提示词。
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_FALLBACK_TOOL_MAPPING = """**Tool Mapping for This Environment:**
- `TodoWrite` → `todowrite` tool
- `Task` tool with subagents → Use OpenCode's subagent system (@mention)
- `Skill` tool → OpenCode's native `skill` tool
- `Read`, `Write`, `Edit`, `Bash` → Your native tools

Use OpenCode's native `skill` tool to list and load skills."""


class BootstrapProvider:
    """读取 bootstrap.md 内容并用 <EXTREMELY_IMPORTANT>...</EXTREMELY_IMPORTANT> 包裹。

    优先级链（从高到低）：
        1. agent_bootstrap_path（子智能体 config/bootstrap.md）
        2. user_global_path（settings.skills_bootstrap_path）
        3. 系统默认 app/core/skills/bootstrap.md
        4. 代码内置 _FALLBACK_TOOL_MAPPING（5 条英文 Tool Mapping）

    Args:
        project_root: 项目根路径（用于解析相对路径）
    """

    DEFAULT_BOOTSTRAP_PATH = "app/core/skills/bootstrap.md"
    WRAPPER_OPEN = "<EXTREMELY_IMPORTANT>"
    WRAPPER_CLOSE = "</EXTREMELY_IMPORTANT>"

    def __init__(self, project_root: Optional[Path] = None):
        """
        初始化 BootstrapProvider。

        Args:
            project_root: 项目根路径，未提供时使用当前工作目录。
        """
        self.project_root = project_root or Path.cwd()

    def render(
        self,
        agent_bootstrap_path: Optional[str] = None,
        user_global_path: Optional[str] = None,
    ) -> str:
        """按优先级读取 bootstrap 内容并包裹 <EXTREMELY_IMPORTANT>。

        Args:
            agent_bootstrap_path: 子智能体 bootstrap 文件路径（最高优先级）
            user_global_path: 用户自定义全局 bootstrap 文件路径

        Returns:
            包裹 <EXTREMELY_IMPORTANT> 标签的 bootstrap 字符串
        """
        content = self._resolve_content(agent_bootstrap_path, user_global_path)
        return f"{self.WRAPPER_OPEN}\n{content.strip()}\n{self.WRAPPER_CLOSE}"

    def _resolve_content(
        self,
        agent_bootstrap_path: Optional[str],
        user_global_path: Optional[str],
    ) -> str:
        """
        按优先级解析 bootstrap 内容。

        Args:
            agent_bootstrap_path: 子智能体 bootstrap 文件路径。
            user_global_path: 用户自定义全局 bootstrap 文件路径。

        Returns:
            读取到的 bootstrap 文本；若全部路径均不可用则返回内置 fallback。
        """
        for label, raw in (
            ("agent", agent_bootstrap_path),
            ("user_global", user_global_path),
            ("default", self.DEFAULT_BOOTSTRAP_PATH),
        ):
            if raw is None:
                continue
            path = self._resolve(raw)
            if path.is_file():
                try:
                    text = path.read_text(encoding="utf-8")
                    logger.debug("bootstrap loaded from %s path: %s", label, path)
                    return text
                except OSError as e:
                    logger.warning("failed to read bootstrap %s: %s", path, e)
        logger.debug("bootstrap falling back to code-default tool mapping")
        return _FALLBACK_TOOL_MAPPING

    def _resolve(self, raw: str) -> Path:
        """
        将原始路径解析为绝对 Path。

        支持 ~ 展开；相对路径基于 project_root 拼接。

        Args:
            raw: 原始路径字符串。

        Returns:
            解析后的绝对 Path。
        """
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = self.project_root / path
        return path.resolve()
