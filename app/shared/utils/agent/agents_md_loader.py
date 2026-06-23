#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
AGENTS.md 加载器模块

从文件系统读取 agents/<agent_name>/AGENTS.md 纯 markdown 内容，
供 AgentConfigService 作为 system_prompt 注入 LLM。

特性：
- 内存缓存（同一路径只读一次磁盘）
- 文件不存在时抛出 FileNotFoundError
- clear_cache() 方法供 admin 更新 AGENTS.md 后刷新

Date: 2026-06-23
Author: AI Assistant
"""

from pathlib import Path
from typing import Dict


class AgentsMdLoader:
    """AGENTS.md 文件加载器，带内存缓存。

    通过路径读取 markdown 文件内容，相同路径的多次加载只读取一次磁盘。
    提供 clear_cache() 方法在文件更新后刷新缓存。

    Attributes:
        _cache: 路径到文件内容的内存缓存字典
    """

    def __init__(self) -> None:
        """初始化加载器，创建空缓存字典。"""
        self._cache: Dict[str, str] = {}

    def load(self, agents_md_path: str) -> str:
        """加载 AGENTS.md 文件内容。

        首次加载时从磁盘读取并写入缓存，后续相同路径的加载直接返回缓存内容。
        文件不存在时抛出 FileNotFoundError。

        参数:
            agents_md_path: AGENTS.md 文件路径（绝对路径或相对路径）

        返回:
            str: markdown 文件正文内容

        异常:
            FileNotFoundError: 当指定路径的文件不存在时抛出
        """
        if agents_md_path in self._cache:
            return self._cache[agents_md_path]

        path = Path(agents_md_path)
        if not path.is_file():
            raise FileNotFoundError(
                f"AGENTS.md not found at: {agents_md_path}"
            )

        content = path.read_text(encoding="utf-8")
        self._cache[agents_md_path] = content
        return content

    def clear_cache(self) -> None:
        """清空缓存（admin 更新 AGENTS.md 后调用）。

        清空后下次 load() 将重新从磁盘读取最新内容。

        参数:
            None

        返回:
            None
        """
        self._cache.clear()
