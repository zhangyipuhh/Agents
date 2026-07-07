# -*- coding:utf-8 -*-
"""
SkillsAwarePrompt 模块。

构造完整 system prompt：base + agent_specific + bootstrap + available_skills，
用于在 AgentBase._llm_call 中统一生成送入 LLM 的系统提示词。
"""

from typing import List, Optional
from langchain_core.runnables import Runnable, RunnableLambda

from .service import SkillsService
from .prompt import render_available_skills_block
from .bootstrap import BootstrapProvider


class SkillsAwarePrompt:
    """构造完整 system prompt：base + agent_specific + bootstrap + available_skills。

    用法（在 AgentBase._llm_call 中）：
        system_prompt = SkillsAwarePrompt(
            base=BASE_SYSTEM_PROMPT,
            agent_specific=(self.system_prompt or "") + ...,
            agent_name="map_agent",           # 触发子智能体覆盖
        ).build()

    拼接顺序（与 opencode session/system.ts 风格一致，但 bootstrap 前置）：
        1. base（BASE_SYSTEM_PROMPT 通用规则）
        2. agent_specific（Agent 专属 + 运行时动态层）
        3. bootstrap（EXTREMELY_IMPORTANT 包裹的工具映射/项目特定提示）
        4. available_skills（已加载 skill 的能力清单）
    """

    def __init__(
        self,
        base: str,
        agent_specific: str = "",
        agent_name: Optional[str] = None,
        project_root=None,
        enabled_skill_names: Optional[List[str]] = None,
    ):
        """
        初始化 SkillsAwarePrompt。

        Args:
            base: 通用基础系统提示词。
            agent_specific: Agent 专属及运行时动态系统提示词，默认为空字符串。
            agent_name: 可选的 Agent 名称，用于定位 agent 专属 bootstrap.md。
            project_root: 项目根目录，用于解析 bootstrap 文件相对路径。
            enabled_skill_names: 启用的 skill 名称列表；为 None 时使用全部已加载 skill，
                                为列表时（即使为空）使用 service.available(name_filter=...)
                                进行过滤。空列表会传给 available()，由 service 层决定
                                返回结果（通常返回空）。
        """
        self.base = base
        self.agent_specific = agent_specific
        self.agent_name = agent_name
        self.enabled_skill_names = enabled_skill_names
        self._service = SkillsService.get_instance(agent_name=agent_name)
        self._bootstrap = BootstrapProvider(project_root=project_root)

    def build(self) -> str:
        """
        拼接并返回完整系统提示词字符串。

        Returns:
            按 base → agent_specific → bootstrap → available_skills 顺序拼接的字符串，
            空部分会被自动过滤。
        """
        if self.enabled_skill_names is None:
            skills = self._service.all()
        else:
            skills = self._service.available(name_filter=self.enabled_skill_names)
        skills_block = render_available_skills_block(skills)
        agent_bootstrap_path = None
        if self.agent_name:
            from pathlib import Path
            agent_bootstrap_path = str(
                Path("app/features") / self.agent_name / "config" / "bootstrap.md"
            )
        # 用户全局 bootstrap 由 settings 提供；MVP 阶段从 SkillsConfig.bootstrap_path 透传
        user_global_path = self._service.config.bootstrap_path
        bootstrap_block = self._bootstrap.render(
            agent_bootstrap_path=agent_bootstrap_path,
            user_global_path=user_global_path,
        )
        parts = [
            self.base,
            self.agent_specific,
            bootstrap_block,
            skills_block,
        ]
        return "\n\n".join(p for p in parts if p)

    def as_runnable(self) -> Runnable:
        """
        返回 langchain Runnable，供 LangGraph 异步包装场景。

        Returns:
            包装 build() 的 RunnableLambda 实例。
        """
        def _fn(_input) -> str:
            return self.build()
        return RunnableLambda(_fn)
