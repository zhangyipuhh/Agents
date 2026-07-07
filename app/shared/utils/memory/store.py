#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
LangGraph Store 全局单例模块

本模块提供了与 ``get_async_checkpointer()`` 对齐的全局单例 Store，
确保在 FastAPI 应用中所有 Agent 实例共享同一份长期记忆
（cross-thread / cross-session persistence via LangGraph Store）。

支持的两种模式（按 ``DatabasePool.is_enabled()`` 自动选择）：

- **持久化模式（Postgres 模式）**：
  使用 ``AsyncPostgresStore``（来自 ``langgraph-checkpoint-postgres``），
  数据持久化到 PostgreSQL。首次调用会执行 ``store.setup()`` 创建
  ``store`` / ``store_migrations`` 表（与 ``checkpoints`` 表相互独立）。

- **内存模式（Memory 模式）**：
  使用 ``InMemoryStore``，数据存储在内存中，重启后丢失。
  适合开发 / 测试环境。

调用方式::

    from app.shared.utils.memory import get_async_store
    store = await get_async_store()
    await store.aput(namespace, key, value)

退出方式（lifespan 关闭时调用）::

    from app.shared.utils.memory import close_global_store
    await close_global_store()

设计决策（2026-06-26）：

- 与 checkpointer **各自维护 psycopg 连接池**，避免交叉依赖与并发
  死锁（两者需要独立锁定连接）。双倍连接数 ~max_size=20 是可接受的。
- 不在 lifespan 阶段预创建，遵循"懒加载 + 启动失败不阻塞"原则，
  与 ``get_async_checkpointer`` 行为一致。

Date: 2026-06-26
Author: AI Assistant
"""
from typing import Optional

from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore


# 全局单例 store
_global_store: Optional[BaseStore] = None

# 全局 psypg 连接池（Postgres 模式专属，Memory 模式下为 None）
_global_pg_connection: Optional[object] = None


async def get_async_store() -> BaseStore:
    """获取全局单例异步 Store（懒加载）。

    根据 ``DatabasePool.is_enabled()`` 选择实现：

    - **Postgres 模式**：创建 ``AsyncPostgresStore`` 实例并执行 ``setup()``
      创建表结构。失败时降级到 ``InMemoryStore``。
    - **Memory 模式**：直接创建 ``InMemoryStore``。

    Returns:
        BaseStore: 全局单例 Store 实例

    Note:
        与 ``get_async_checkpointer`` 的差异：Store 复用自己的 psycopg
        连接池（不共享 checkpointer 的 pool），避免两边相互锁定造成
        死锁；代价是连接数翻倍（可接受）。

    Example:
        ```python
        store = await get_async_store()
        await store.aput(("audit_documents",), "session_001", {"foo": "bar"})
        item = await store.aget(("audit_documents",), "session_001")
        ```
    """
    global _global_store, _global_pg_connection

    if _global_store is not None:
        print(
            f"[Store] get_async_store() 返回已存在的单例: "
            f"{type(_global_store).__name__}"
        )
        return _global_store

    from app.core.database import DatabasePool
    is_enabled = DatabasePool.is_enabled()
    dsn = DatabasePool.get_dsn()
    print(f"[Store] DatabasePool.is_enabled()={is_enabled}, dsn={dsn}")

    if is_enabled:
        # PostgreSQL 持久化模式
        try:
            # 优先从 langgraph.store.postgres.aio 导入（langgraph 主包 1.x）
            # 回退到 langgraph.checkpoint.postgres.aio（早期版本曾放在此）
            try:
                from langgraph.store.postgres.aio import AsyncPostgresStore
            except ImportError:
                from langgraph.checkpoint.postgres.aio import AsyncPostgresStore  # type: ignore[no-redef]

            from psycopg_pool import AsyncConnectionPool
            from psycopg.rows import dict_row

            dsn = DatabasePool.get_dsn()
            # 创建独立的 psycopg 连接池（不复用 checkpointer 的 pool，避免死锁）
            # 不使用 async with，保持连接池长期有效
            _global_pg_connection = AsyncConnectionPool(
                conninfo=dsn,
                max_size=20,
                open=False,  # 阻止构造函数自动打开连接池，避免废弃警告
                kwargs={
                    "autocommit": True,        # 必需：确保 setup() 能提交 DDL
                    "prepare_threshold": 0,
                    "row_factory": dict_row,   # 必需：store 内部按列名访问行数据
                },
            )
            # 预热连接池
            await _global_pg_connection.open()
            # 创建 AsyncPostgresStore 实例，传入 psycopg 连接池
            store = AsyncPostgresStore(conn=_global_pg_connection)
            # 初始化数据库表结构（创建 store / store_migrations 表）
            await store.setup()
            _global_store = store
            print(f"[Store] 使用 PostgreSQL 持久化模式（AsyncPostgresStore）")
        except ImportError:
            print(
                "[Store] 警告：langgraph-checkpoint-postgres 未安装或 "
                "AsyncPostgresStore 不可用，回退到内存模式"
            )
            _global_store = InMemoryStore()
            print(f"[Store] 使用内存模式（InMemoryStore）")
        except Exception as e:
            print(
                f"[Store] 警告：PostgreSQL 初始化失败 "
                f"({type(e).__name__}: {e})，回退到内存模式"
            )
            # 关闭可能部分初始化的连接池
            if _global_pg_connection is not None:
                try:
                    await _global_pg_connection.close()
                except Exception:
                    pass
                _global_pg_connection = None
            _global_store = InMemoryStore()
            print(f"[Store] 使用内存模式（InMemoryStore）")
    else:
        # 内存模式
        _global_store = InMemoryStore()
        print(f"[Store] 使用内存模式（InMemoryStore）")

    return _global_store


async def close_global_store():
    """关闭全局 Store 和数据库连接池。

    用于应用关闭时（lifespan 退出阶段）清理资源。

    注意：仅在 store 自建的 psycopg 连接池上调用 close；
    若未来改成共享 checkpointer 的 pool，应跳过关闭（由 checkpointer 负责）。
    """
    global _global_store, _global_pg_connection

    if _global_pg_connection is not None:
        try:
            await _global_pg_connection.close()
            print("[Store] PostgreSQL 连接池已关闭")
        except Exception as e:
            print(f"[Store] 关闭 PostgreSQL 连接池时出错: {e}")
        _global_pg_connection = None

    _global_store = None
    print("[Store] 全局 store 已重置")


def reset_global_store():
    """重置全局单例 Store（不关闭连接池，仅清空引用）。

    用于测试场景或需要重新初始化的场景。
    """
    global _global_store
    _global_store = None
    print("[Store] 全局 store 单例已重置（连接池未关闭）")
