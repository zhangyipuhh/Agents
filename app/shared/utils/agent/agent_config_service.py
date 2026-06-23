#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
AgentConfigService 模块

从数据库 agents 表 + AGENTS.md 文件加载完整 Agent 配置，
封装为 UnifiedAgentConfig 实例供 agent_router 使用。

Date: 2026-06-23
Author: AI Assistant
"""

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from app.shared.utils.agent.dynamic_schema import build_agent_state, build_agent_context
from app.shared.utils.agent.agents_md_loader import AgentsMdLoader


logger = logging.getLogger(__name__)


class AgentNotFoundError(Exception):
    """智能体未找到或已禁用时抛出。"""


@dataclass
class UnifiedAgentConfig:
    """统一智能体配置（从数据库 + AGENTS.md 加载）。

    Attributes:
        name: 智能体名称（唯一标识）
        display_name: 展示名称（中文）
        description: 智能体描述
        system_prompt: 从 AGENTS.md 加载的系统提示词
        state_class: 动态生成的 AgentState 子类（可调用包装器）
        context_class: 动态生成的 AgentContext 子类（可调用包装器）
        mcp_tags: MCP 标签列表，用于匹配 MCP server
        enabled_tool_names: 启用的工具名称列表
        enabled_skill_names: 启用的 skill 名称列表
        agents_md_path: AGENTS.md 文件路径
    """
    name: str
    display_name: str
    description: str
    system_prompt: str
    state_class: Callable
    context_class: Callable
    mcp_tags: List[str]
    enabled_tool_names: List[str]
    enabled_skill_names: List[str]
    agents_md_path: str


class AgentConfigService:
    """Agent 配置加载服务。

    参数:
        db: 数据库连接池，需支持 fetch / fetchrow / execute 异步方法
        agents_md_loader: AGENTS.md 加载器
    """

    def __init__(self, db: Any, agents_md_loader: AgentsMdLoader) -> None:
        """初始化服务。

        参数:
            db: 数据库连接池，需支持 fetch / fetchrow / execute 异步方法
            agents_md_loader: AGENTS.md 加载器实例
        """
        self._db = db
        self._loader = agents_md_loader

    async def get_agent_config(self, agent_name: str) -> UnifiedAgentConfig:
        """根据 agent_name 加载完整配置。

        流程：
        1. 从 agents 表查询记录（含 enabled 校验）
        2. 通过 AgentsMdLoader 加载 AGENTS.md 内容作为 system_prompt
        3. 通过 dynamic_schema 构建 state_class / context_class
        4. 从 agent_tool_bindings 加载启用的工具列表
        5. 从 agent_skill_bindings 加载启用的 skill 列表

        参数:
            agent_name: 智能体名称

        返回:
            UnifiedAgentConfig: 完整配置实例

        异常:
            AgentNotFoundError: agent 不存在或已禁用时抛出
        """
        row = await self._db.fetchrow(
            "SELECT * FROM agents WHERE name = $1",
            agent_name,
        )
        if not row or not row.get("enabled", False):
            raise AgentNotFoundError(f"Agent {agent_name} not found or disabled")

        system_prompt = self._loader.load(row["agents_md_path"])
        state_class = build_agent_state(agent_name, row.get("state_schema") or {})
        context_class = build_agent_context(agent_name, row.get("context_schema") or {})

        tool_bindings = await self._db.fetch(
            "SELECT tool_name, is_enabled FROM agent_tool_bindings "
            "WHERE agent_name = $1 ORDER BY sort_order",
            agent_name,
        )
        skill_bindings = await self._db.fetch(
            "SELECT skill_name, is_enabled FROM agent_skill_bindings "
            "WHERE agent_name = $1 ORDER BY sort_order",
            agent_name,
        )

        return UnifiedAgentConfig(
            name=agent_name,
            display_name=row.get("display_name", ""),
            description=row.get("description", ""),
            system_prompt=system_prompt,
            state_class=state_class,
            context_class=context_class,
            mcp_tags=row.get("mcp_tags") or [],
            enabled_tool_names=[
                r["tool_name"] for r in tool_bindings
                if r.get("is_enabled") and "tool_name" in r
            ],
            enabled_skill_names=[
                r["skill_name"] for r in skill_bindings
                if r.get("is_enabled") and "skill_name" in r
            ],
            agents_md_path=row["agents_md_path"],
        )

    async def list_agents(self) -> List[Dict[str, Any]]:
        """列出所有启用的智能体。

        返回:
            List[Dict[str, Any]]: 智能体摘要列表，每项包含
            name / display_name / description 字段
        """
        rows = await self._db.fetch(
            "SELECT name, display_name, description FROM agents "
            "WHERE enabled = TRUE ORDER BY sort_order"
        )
        return [dict(r) for r in rows]

    async def create_agent(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Admin 创建智能体。

        参数:
            config: 智能体配置字典，需包含 name / display_name / agents_md_path
                等字段，可选 description / state_schema / context_schema /
                mcp_tags / enabled / sort_order

        返回:
            Dict[str, Any]: 新插入行的完整数据
        """
        row = await self._db.fetchrow(
            """
            INSERT INTO agents (name, display_name, description, agents_md_path,
                                state_schema, context_schema, mcp_tags, enabled, sort_order)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *
            """,
            config["name"], config["display_name"], config.get("description", ""),
            config["agents_md_path"], config.get("state_schema", {}),
            config.get("context_schema", {}), config.get("mcp_tags", []),
            config.get("enabled", True), config.get("sort_order", 0),
        )
        return dict(row)

    async def bind_tool(self, agent_name: str, tool_name: str, enabled: bool = True) -> None:
        """绑定/解绑工具。

        参数:
            agent_name: 智能体名称
            tool_name: 工具名称
            enabled: True 表示启用，False 表示禁用

        返回:
            None
        """
        await self._db.execute(
            """
            INSERT INTO agent_tool_bindings (agent_name, tool_name, is_enabled)
            VALUES ($1, $2, $3)
            ON CONFLICT (agent_name, tool_name) DO UPDATE SET is_enabled = $3
            """,
            agent_name, tool_name, enabled,
        )

    async def bind_skill(self, agent_name: str, skill_name: str, enabled: bool = True) -> None:
        """绑定/解绑 skill。

        参数:
            agent_name: 智能体名称
            skill_name: skill 名称
            enabled: True 表示启用，False 表示禁用

        返回:
            None
        """
        await self._db.execute(
            """
            INSERT INTO agent_skill_bindings (agent_name, skill_name, is_enabled)
            VALUES ($1, $2, $3)
            ON CONFLICT (agent_name, skill_name) DO UPDATE SET is_enabled = $3
            """,
            agent_name, skill_name, enabled,
        )
