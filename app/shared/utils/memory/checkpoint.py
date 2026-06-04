#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
LangGraph Checkpoint 全局单例模块

本模块提供了全局单例的 checkpointer，确保在 FastAPI 应用中
多个 Agent 实例共享同一份短期记忆（thread-level persistence）。

支持两种模式：
- 内存模式（MemorySaver）：开发/测试环境，重启后数据丢失
- 持久化模式（AsyncPostgresSaver）：生产环境，数据持久化到 PostgreSQL

Date: 2026-03-05
Author: AI Assistant
"""
from typing import Optional
from langgraph.checkpoint.base import BaseCheckpointSaver

# 全局单例 checkpointer
_global_checkpointer: Optional[BaseCheckpointSaver] = None

# 全局 PostgreSQL 连接池（psycopg AsyncConnectionPool，用于 AsyncPostgresSaver）
_global_pg_connection: Optional[object] = None


def get_global_checkpointer(db_path: str = ":memory:") -> BaseCheckpointSaver:
    """获取全局单例 checkpointer（同步版本，仅支持内存模式）

    使用单例模式确保在 FastAPI 应用中，所有 Agent 实例共享同一份记忆。

    Args:
        db_path: 数据库路径
            - ":memory:" : 内存数据库（重启后丢失，适合开发测试）
            - 其他值 : 已废弃，请使用 get_async_checkpointer()

    Returns:
        BaseCheckpointSaver: 全局单例 checkpointer 实例（仅内存模式）

    Note:
        生产环境请使用 get_async_checkpointer() 获取 PostgreSQL 持久化 checkpointer
    """
    global _global_checkpointer

    if _global_checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver
        _global_checkpointer = MemorySaver()
        print("[Checkpoint] 使用内存模式（MemorySaver）")

    return _global_checkpointer


async def get_async_checkpointer() -> BaseCheckpointSaver:
    """获取全局单例异步 checkpointer

    根据环境变量 AUTH_STORAGE_MODE 选择合适的 checkpointer：
    - postgres 模式：使用 AsyncPostgresSaver，数据持久化到 PostgreSQL
    - memory 模式：使用 MemorySaver，数据存储在内存中

    Returns:
        BaseCheckpointSaver: 全局单例 checkpointer 实例

    Example:
        ```python
        checkpointer = await get_async_checkpointer()
        graph = builder.compile(checkpointer=checkpointer)
        ```
    """
    global _global_checkpointer, _global_pg_connection

    if _global_checkpointer is not None:
        return _global_checkpointer

    from app.core.database import DatabasePool

    if DatabasePool.is_enabled():
        # PostgreSQL 持久化模式
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            from psycopg_pool import AsyncConnectionPool
            from psycopg.rows import dict_row

            dsn = DatabasePool.get_dsn()
            # 使用 psycopg AsyncConnectionPool（AsyncPostgresSaver 依赖 psycopg，而非 asyncpg）
            # 注意：不使用 async with，保持连接池长期有效
            _global_pg_connection = AsyncConnectionPool(
                conninfo=dsn,
                max_size=20,
                open=False,  # 阻止构造函数自动打开连接池，避免废弃警告
                kwargs={
                    "autocommit": True,          # 必需：确保 setup() 能提交 DDL
                    "prepare_threshold": 0,
                    "row_factory": dict_row,     # 必需：checkpointer 内部按列名访问行数据
                },
            )
            # 预热连接池
            await _global_pg_connection.open()
            # 创建 AsyncPostgresSaver 实例，传入 psycopg 连接池
            checkpointer = AsyncPostgresSaver(_global_pg_connection)
            # 初始化数据库表结构
            await checkpointer.setup()
            _global_checkpointer = checkpointer
            print(f"[Checkpoint] 使用 PostgreSQL 持久化模式（AsyncPostgresSaver）")
        except ImportError:
            print("[Checkpoint] 警告：langgraph-checkpoint-postgres 未安装，回退到内存模式")
            from langgraph.checkpoint.memory import MemorySaver
            _global_checkpointer = MemorySaver()
            print("[Checkpoint] 使用内存模式（MemorySaver）")
        except Exception as e:
            print(f"[Checkpoint] 警告：PostgreSQL 初始化失败 ({type(e).__name__}: {e})，回退到内存模式")
            from langgraph.checkpoint.memory import MemorySaver
            _global_checkpointer = MemorySaver()
            print("[Checkpoint] 使用内存模式（MemorySaver）")
    else:
        # 内存模式
        from langgraph.checkpoint.memory import MemorySaver
        _global_checkpointer = MemorySaver()
        print("[Checkpoint] 使用内存模式（MemorySaver）")

    return _global_checkpointer


async def close_global_checkpointer():
    """关闭全局 checkpointer 和数据库连接

    用于应用关闭时清理资源，确保数据库连接正确关闭。
    """
    global _global_checkpointer, _global_pg_connection

    if _global_pg_connection is not None:
        try:
            await _global_pg_connection.close()
            print("[Checkpoint] PostgreSQL 连接池已关闭")
        except Exception as e:
            print(f"[Checkpoint] 关闭 PostgreSQL 连接池时出错: {e}")
        _global_pg_connection = None

    _global_checkpointer = None
    print("[Checkpoint] 全局 checkpointer 已重置")


def reset_global_checkpointer():
    """重置全局单例 checkpointer

    用于测试或需要重新初始化 checkpointer 的场景。
    注意：此函数不会关闭数据库连接，仅重置单例引用。
    """
    global _global_checkpointer
    _global_checkpointer = None
    print("[Checkpoint] 全局 checkpointer 已重置")
