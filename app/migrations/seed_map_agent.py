#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
map_agent 数据库种子脚本

向 agents / agent_tool_bindings / agent_skill_bindings 表写入 map_agent 的初始配置。
幂等：重复执行会 UPDATE 已存在的记录。

执行方式：
    python -m app.migrations.seed_map_agent

异常：
    Exception: 数据库连接或 SQL 执行失败时抛出
"""
import asyncio
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


# map_agent 的 state_schema
# 2026-06-24 修复：补全原 MapAgentState 全部 5 个扩展字段（map_center / map_zoom /
# map_markers / map_layer / map_polygons），与原 MapAgentConfig.py 保持一致。
# 重构前 seed 脚本只存了 map_zoom 一个字段，导致 map_tools 工具运行时 state 中
# 缺失 map_center / map_markers / map_layer / map_polygons 四个字段。
# 基类保留字段（error_limit / limit / agent_name 等）由
# app/shared/utils/agent/dynamic_schema._BASE_STATE_DEFAULTS 兜底，
# 无需在此重复声明。
MAP_AGENT_STATE_SCHEMA = {
    "map_center":   {"type": "dict", "default": {"latitude": 0, "longitude": 0}},
    "map_zoom":     {"type": "int",  "default": 10},
    "map_markers":  {"type": "list", "default": []},
    "map_layer":    {"type": "str",  "default": "standard"},
    "map_polygons": {"type": "list", "default": []},
}

# map_agent 的 context_schema
# 原 MapAgentContext 无新增字段；基类保留字段（session_id / store_id /
# image_ids / host_session_id / process_data）由
# app/shared/utils/agent/dynamic_schema._BASE_CONTEXT_DEFAULTS 兜底。
MAP_AGENT_CONTEXT_SCHEMA = {}

# map_agent 绑定的工具（与 MapAgentConfig.get_tools() 当前启用的工具一致）
MAP_AGENT_TOOLS = [
    "explore",
    "query_knowledge",
    "get_current_time",
    "generate_report",
    "save_business_info",
    "ask_user_question",
    "sandbox",
    "load_skill",
    "read_skill_file",
]

# map_agent 绑定的 skill
MAP_AGENT_SKILLS = [
    "data-skill",
]


async def seed_map_agent(db: Any) -> None:
    """
    向数据库写入 map_agent 初始配置（幂等）。

    参数：
        db: asyncpg.Connection 或兼容的数据库连接对象（需支持 fetchrow/execute/fetch）

    返回值：
        None

    异常：
        Exception: SQL 执行失败时抛出
    """
    # 1. 检查 agents 表是否已有 map_agent
    existing = await db.fetchrow(
        "SELECT name FROM agents WHERE name = $1",
        "map_agent",
    )

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
                mcp_tags = $7,
                enabled = TRUE,
                updated_at = CURRENT_TIMESTAMP
            WHERE name = $1
            """,
            "map_agent",
            "地图智能体",
            "基于地图的智能体，支持地图操作、知识查询、报告生成",
            "agents/map_agent/AGENTS.md",
            json.dumps(MAP_AGENT_STATE_SCHEMA, ensure_ascii=False),
            json.dumps(MAP_AGENT_CONTEXT_SCHEMA, ensure_ascii=False),
            json.dumps(["map"], ensure_ascii=False),
        )
        logger.info("map_agent 记录已更新")
    else:
        # 不存在：INSERT
        await db.execute(
            """
            INSERT INTO agents (name, display_name, description, agents_md_path,
                              state_schema, context_schema, mcp_tags, enabled, sort_order)
            VALUES ($1, $2, $3, $4, $5, $6, $7, TRUE, 0)
            """,
            "map_agent",
            "地图智能体",
            "基于地图的智能体，支持地图操作、知识查询、报告生成",
            "agents/map_agent/AGENTS.md",
            json.dumps(MAP_AGENT_STATE_SCHEMA, ensure_ascii=False),
            json.dumps(MAP_AGENT_CONTEXT_SCHEMA, ensure_ascii=False),
            json.dumps(["map"], ensure_ascii=False),
        )
        logger.info("map_agent 记录已插入")

    # 2. 写入工具绑定（幂等：ON CONFLICT DO UPDATE）
    for idx, tool_name in enumerate(MAP_AGENT_TOOLS):
        await db.execute(
            """
            INSERT INTO agent_tool_bindings (agent_name, tool_name, is_enabled, sort_order)
            VALUES ($1, $2, TRUE, $3)
            ON CONFLICT (agent_name, tool_name) DO UPDATE SET is_enabled = TRUE, sort_order = $3
            """,
            "map_agent",
            tool_name,
            idx,
        )
    logger.info("map_agent 工具绑定已写入 %d 条", len(MAP_AGENT_TOOLS))

    # 3. 写入 skill 绑定（幂等）
    for idx, skill_name in enumerate(MAP_AGENT_SKILLS):
        await db.execute(
            """
            INSERT INTO agent_skill_bindings (agent_name, skill_name, is_enabled, sort_order)
            VALUES ($1, $2, TRUE, $3)
            ON CONFLICT (agent_name, skill_name) DO UPDATE SET is_enabled = TRUE, sort_order = $3
            """,
            "map_agent",
            skill_name,
            idx,
        )
    logger.info("map_agent skill 绑定已写入 %d 条", len(MAP_AGENT_SKILLS))


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
        await seed_map_agent(conn)
    finally:
        await conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
