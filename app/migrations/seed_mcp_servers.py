#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
mcp_server_configs 数据库种子脚本

从 app/shared/tools/mcp/config.yaml 加载 MCP server 配置，
向 mcp_server_configs 表写入初始记录。幂等：表已存在数据时跳过。

执行方式：
    python -m app.migrations.seed_mcp_servers

异常：
    Exception: 数据库连接或 SQL 执行失败时抛出
"""
import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


async def seed_mcp_servers(db: Any) -> int:
    """
    从 YAML 种子文件导入 MCP server 配置（幂等：表非空时跳过）。

    参数：
        db: asyncpg 连接或兼容的数据库连接对象（需支持 fetch/execute）

    返回值：
        int: 本次实际写入的记录条数（0 表示已存在或 YAML 为空）

    异常：
        Exception: SQL 执行失败时抛出
    """
    # 在函数内部导入，避免测试环境 conftest.py mock 失败
    from app.shared.utils.agent.mcp_service import McpConfigService

    service = McpConfigService(db)
    rows_before = await db.fetch("SELECT name FROM mcp_server_configs")
    if rows_before:
        logger.info(
            "mcp_server_configs 已有 %d 条记录，跳过 YAML 导入", len(rows_before)
        )
        return 0

    # 复用 lifespan 中已有的种子逻辑（包含 _load_yaml_seed 失败容错）
    await service.seed_from_yaml_if_empty()
    rows_after = await db.fetch("SELECT name FROM mcp_server_configs")
    inserted = len(rows_after) - len(rows_before)
    logger.info("mcp_server_configs 写入 %d 条", inserted)
    return inserted


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
        await seed_mcp_servers(conn)
    finally:
        await conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
