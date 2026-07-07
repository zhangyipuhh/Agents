# -*- coding:utf-8 -*-
"""Skill 系统顶层包。

导出 Skill 系统对外暴露的核心类与函数：
    - SkillsService: skill 注册中心（全局单例 + agent 维度多实例）
    - BootstrapProvider: 按优先级读取 bootstrap.md 并包裹 <EXTREMELY_IMPORTANT>
    - load_skill: LangChain @tool 装饰的 skill 加载工具
    - SkillsAwarePrompt: 构造含 bootstrap + available_skills 的系统提示词
    - render_available_skills_block: 渲染 <available_skills> XML 块
"""

# 各子模块按任务进度逐步落地；在模块尚未实现时跳过导入，避免破坏已完成模块的测试与使用。
__all__ = [
    "BootstrapProvider",
    "SkillsAwarePrompt",
    "SkillsService",
    "load_skill",
    "read_skill_file",
    "render_available_skills_block",
]

try:
    from .bootstrap import BootstrapProvider
except (ImportError, ModuleNotFoundError):
    BootstrapProvider = None  # type: ignore[misc, assignment]

try:
    from .message_transformer import SkillsAwarePrompt
except (ImportError, ModuleNotFoundError):
    SkillsAwarePrompt = None  # type: ignore[misc, assignment]

try:
    from .prompt import render_available_skills_block
except (ImportError, ModuleNotFoundError):
    render_available_skills_block = None  # type: ignore[misc, assignment]

try:
    from .service import SkillsService
except (ImportError, ModuleNotFoundError):
    SkillsService = None  # type: ignore[misc, assignment]

try:
    from app.core.tools.SkillTools import load_skill, read_skill_file
except (ImportError, ModuleNotFoundError):
    load_skill = None  # type: ignore[misc, assignment]
    read_skill_file = None  # type: ignore[misc, assignment]
