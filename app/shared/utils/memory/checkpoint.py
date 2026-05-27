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
    global _global_checkpointer

    if _global_checkpointer is not None:
        return _global_checkpointer

    from app.core.database import DatabasePool

    if DatabasePool.is_enabled():
        # PostgreSQL 持久化模式
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            dsn = DatabasePool.get_dsn()
            checkpointer = AsyncPostgresSaver.from_conn_string(dsn)
            await checkpointer.setup()
            _global_checkpointer = checkpointer
            print(f"[Checkpoint] 使用 PostgreSQL 持久化模式（AsyncPostgresSaver）")
        except ImportError:
            print("[Checkpoint] 警告：langgraph-checkpoint-postgres 未安装，回退到内存模式")
            from langgraph.checkpoint.memory import MemorySaver
            _global_checkpointer = MemorySaver()
            print("[Checkpoint] 使用内存模式（MemorySaver）")
    else:
        # 内存模式
        from langgraph.checkpoint.memory import MemorySaver
        _global_checkpointer = MemorySaver()
        print("[Checkpoint] 使用内存模式（MemorySaver）")

    return _global_checkpointer


def reset_global_checkpointer():
    """重置全局单例 checkpointer

    用于测试或需要重新初始化 checkpointer 的场景。
    """
    global _global_checkpointer
    _global_checkpointer = None
    print("[Checkpoint] 全局 checkpointer 已重置")
