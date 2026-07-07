#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
project 智能体数据库种子脚本

向 agents / agent_tool_bindings 表写入 project 智能体的初始配置。
幂等：重复执行会 UPDATE 已存在的记录。

执行方式：
    python -m app.migrations.seed_project_agent

异常：
    Exception: 数据库连接或 SQL 执行失败时抛出
"""
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from app.core.skills.loader import SkillDiscovery
from app.core.skills.schemas import SkillInfo

logger = logging.getLogger(__name__)


# project 智能体的 state_schema
# 当前无特殊扩展字段，使用空对象；基类保留字段由 dynamic_schema._BASE_STATE_DEFAULTS 兜底。
PROJECT_AGENT_STATE_SCHEMA = {}

# project 智能体的 context_schema
# 当前无特殊扩展字段，使用空对象；基类保留字段由 dynamic_schema._BASE_CONTEXT_DEFAULTS 兜底。
PROJECT_AGENT_CONTEXT_SCHEMA = {}

# 2026-06-24 重构：合并为三层嵌套 config_schema
# 结构：{
#   <AgentConfig 字段>: { type, default },    -- 可选：覆盖 model_type / temperature 等
#   state_fields:   { <字段>: { type, default } },
#   context_fields: { <字段>: { type, default } }
# }
# 兼容：state_schema / context_schema 旧列仍写入相同数据，作为兜底
PROJECT_AGENT_CONFIG_SCHEMA = {
    "state_fields":   PROJECT_AGENT_STATE_SCHEMA,
    "context_fields": PROJECT_AGENT_CONTEXT_SCHEMA,
}

# project 智能体绑定的工具列表
PROJECT_AGENT_TOOLS = [
    "intent_clarification",
    "project_doc_query",
    "project_doc_outline",
    "project_doc_write",
    "project_doc_workflow",
    "manage_project_log",
    "append_change_log",
    "generate_project_docx",
]

# project 智能体绑定的 skill 列表
PROJECT_AGENT_SKILLS = [
    "project-doc-overview",
    "project-doc-hub",
    "project-doc-query",
    "project-doc-outline",
    "project-doc-write",
    "project-doc-workflow",
    "intent-clarification",
]

# 扫描 project 相关 skill 时只保留这些名称
_PROJECT_SKILL_NAMES = set(PROJECT_AGENT_SKILLS)


def _discover_project_skills() -> Dict[str, SkillInfo]:
    """扫描 app/skills/ 下 project 智能体需要的 SKILL.md。

    参数：
        无

    返回值：
        Dict[str, SkillInfo]: skill 名称到 SkillInfo 的映射
    """
    project_root = Path(__file__).resolve().parents[2]
    discovery = SkillDiscovery()
    all_skills = discovery.scan(project_root, [])
    return {
        name: info
        for name, info in all_skills.items()
        if name in _PROJECT_SKILL_NAMES
    }


async def seed_project_skills(db: Any) -> None:
    """将 project 智能体依赖的 skills 写入/更新数据库（幂等）。

    参数：
        db: asyncpg.Connection 或兼容的数据库连接对象

    返回值：
        None

    异常：
        Exception: SQL 执行失败时抛出
    """
    skills = _discover_project_skills()
    if not skills:
        logger.warning("未扫描到任何 project 相关 skill，跳过 skills 表写入")
        return

    for idx, name in enumerate(PROJECT_AGENT_SKILLS):
        info = skills.get(name)
        if info is None:
            logger.warning("skill %s 未在 app/skills/ 下找到，跳过", name)
            continue

        await db.execute(
            """
            INSERT INTO skills (name, display_name, category, description,
                                location, base_dir, content,
                                enabled, sort_order)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (name) DO UPDATE
            SET display_name = EXCLUDED.display_name,
                category = EXCLUDED.category,
                description = EXCLUDED.description,
                location = EXCLUDED.location,
                base_dir = EXCLUDED.base_dir,
                content = EXCLUDED.content,
                enabled = EXCLUDED.enabled,
                sort_order = EXCLUDED.sort_order,
                updated_at = CURRENT_TIMESTAMP
            """,
            info.name,
            "",
            "",
            info.description or "",
            info.location,
            info.base_dir,
            info.content,
            True,
            idx,
        )
        logger.info("skill 已写入/更新: %s", name)

    logger.info("project skills 已同步 %d 条", len(skills))


async def seed_project_agent(db: Any) -> None:
    """
    向数据库写入 project 智能体初始配置（幂等）。

    参数：
        db: asyncpg.Connection 或兼容的数据库连接对象（需支持 fetchrow/execute/fetch）

    返回值：
        None

    异常：
        Exception: SQL 执行失败时抛出
    """
    # 1. 检查 agents 表是否已有 project 记录
    existing = await db.fetchrow(
        "SELECT name FROM agents WHERE name = $1",
        "project",
    )

    # agents.tool_bindings / skill_bindings JSONB 快照格式
    # tool_bindings 供 _load_tools 直接加载工具实例使用
    tool_bindings = [
        {"tool_name": name, "tool_type": "builtin", "enabled": True, "sort_order": idx}
        for idx, name in enumerate(PROJECT_AGENT_TOOLS)
    ]
    # skill_bindings 供 enabled_skill_names 提取使用
    skill_bindings = [
        {"skill_name": name, "enabled": True, "sort_order": idx}
        for idx, name in enumerate(PROJECT_AGENT_SKILLS)
    ]

    if existing:
        # 已存在：UPDATE
        await db.execute(
            """
            UPDATE agents SET
                display_name = $2,
                description = $3,
                agents_md_path = $4,
                state_schema = $5,
                context_schema = $6,
                config_schema = $7,
                mcp_tags = $8,
                tool_bindings = $9,
                skill_bindings = $10,
                enabled = TRUE,
                updated_at = CURRENT_TIMESTAMP
            WHERE name = $1
            """,
            "project",
            "项目文档智能体",
            "负责软件工程项目文档的查询、生成、更新与管理",
            "agents/project/AGENTS.md",
            json.dumps(PROJECT_AGENT_STATE_SCHEMA, ensure_ascii=False),
            json.dumps(PROJECT_AGENT_CONTEXT_SCHEMA, ensure_ascii=False),
            json.dumps(PROJECT_AGENT_CONFIG_SCHEMA, ensure_ascii=False),
            json.dumps([], ensure_ascii=False),
            json.dumps(tool_bindings, ensure_ascii=False),
            json.dumps(skill_bindings, ensure_ascii=False),
        )
        logger.info("project 记录已更新")
    else:
        # 不存在：INSERT
        await db.execute(
            """
            INSERT INTO agents (name, display_name, description, agents_md_path,
                              state_schema, context_schema, config_schema,
                              mcp_tags, tool_bindings, skill_bindings, enabled, sort_order)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, TRUE, 0)
            """,
            "project",
            "项目文档智能体",
            "负责软件工程项目文档的查询、生成、更新与管理",
            "agents/project/AGENTS.md",
            json.dumps(PROJECT_AGENT_STATE_SCHEMA, ensure_ascii=False),
            json.dumps(PROJECT_AGENT_CONTEXT_SCHEMA, ensure_ascii=False),
            json.dumps(PROJECT_AGENT_CONFIG_SCHEMA, ensure_ascii=False),
            json.dumps([], ensure_ascii=False),
            json.dumps(tool_bindings, ensure_ascii=False),
            json.dumps(skill_bindings, ensure_ascii=False),
        )
        logger.info("project 记录已插入")

    # 2. 写入工具绑定（幂等：ON CONFLICT DO UPDATE）
    for idx, tool_name in enumerate(PROJECT_AGENT_TOOLS):
        await db.execute(
            """
            INSERT INTO agent_tool_bindings (agent_name, tool_name, is_enabled, sort_order, tool_type)
            VALUES ($1, $2, TRUE, $3, 'builtin')
            ON CONFLICT (agent_name, tool_name) DO UPDATE
            SET is_enabled = TRUE, sort_order = $3, tool_type = 'builtin'
            """,
            "project",
            tool_name,
            idx,
        )
    logger.info("project 工具绑定已写入 %d 条", len(PROJECT_AGENT_TOOLS))

    # 3. 写入/更新 skills 表（project 智能体依赖的 skill）
    await seed_project_skills(db)


async def main() -> None:
    """
    脚本入口：从 DATABASE_URL 环境变量读取连接并执行种子。

    参数：
        无

    返回值：
        None

    异常：
        Exception: 数据库连接或 SQL 执行失败时抛出
    """
    # 在函数内部导入 asyncpg，避免测试环境（conftest.py 已 mock asyncpg）导入失败
    import asyncpg

    dsn = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/feature_agent",
    )
    conn = await asyncpg.connect(dsn=dsn)
    try:
        await seed_project_agent(conn)
    finally:
        await conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
