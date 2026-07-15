"""
全局数据库连接池模块

提供 PostgreSQL 异步连接池，支持单例模式。
通过环境变量 AUTH_STORAGE_MODE 控制是否启用数据库。

各业务模块可通过 @register_schema 装饰器注册表结构初始化函数，
启动时统一调用。

Date: 2026/5/15
"""
import json
import os
import asyncpg
from typing import Optional, Callable, List

_registered_schemas: List[Callable] = []


def register_schema(func: Callable) -> Callable:
    """
    装饰器：注册数据库表结构初始化函数

    使用方式：
        @register_schema
        async def init_my_schema():
            await DatabasePool.execute("CREATE TABLE ...")

    Args:
        func: 异步初始化函数

    Returns:
        原函数
    """
    _registered_schemas.append(func)
    return func


class DatabasePool:
    """
    PostgreSQL 异步连接池管理器

    Attributes:
        _pool: asyncpg 连接池实例
        _initialized: 是否已初始化
    """
    _pool: Optional[asyncpg.Pool] = None
    _initialized: bool = False

    @classmethod
    def get_dsn(cls) -> str:
        """
        从环境变量构建数据库连接字符串

        Returns:
            str: PostgreSQL DSN 格式连接字符串
        """
        return os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/feature_agent"
        )

    @classmethod
    def is_enabled(cls) -> bool:
        """
        检查是否启用数据库模式

        Returns:
            bool: AUTH_STORAGE_MODE=postgres 时返回 True
        """
        mode = os.getenv("AUTH_STORAGE_MODE", "memory")
        result = mode == "postgres"
        #print(f"[诊断-DatabasePool] is_enabled(): AUTH_STORAGE_MODE='{mode}', result={result}")
        return result

    @classmethod
    async def _init_connection(cls, conn):
        """
        asyncpg 连接初始化回调：注册 JSONB / JSON 类型 codec。

        使 JSONB / JSON 列自动反序列化为 Python 对象（list / dict），
        避免业务层拿到 JSON 字符串导致 Pydantic 校验失败。

        注意：必须显式 ``format='text'``，asyncpg 默认 binary 协议无法被
        ``json.loads`` 解码。某些 asyncpg 版本即便指定 ``format='text'``
        也可能仍返回 JSON 字符串，业务层须做防御性还原
        （见 ``app/shared/utils/devops_server_service.py::_ensure_list``）。

        Args:
            conn: asyncpg 连接实例
        """
        await conn.set_type_codec(
            'jsonb',
            encoder=json.dumps,
            decoder=json.loads,
            schema='pg_catalog',
            format='text',
        )
        await conn.set_type_codec(
            'json',
            encoder=json.dumps,
            decoder=json.loads,
            schema='pg_catalog',
            format='text',
        )

    @classmethod
    async def initialize(cls, min_size: int = 5, max_size: int = 20):
        """
        初始化连接池

        Args:
            min_size: 最小连接数
            max_size: 最大连接数
        """
        #print(f"[诊断-DatabasePool] initialize() 被调用, _initialized={cls._initialized}, _pool={'已存在' if cls._pool else 'None'}")
        if cls._initialized:
            return

        if not cls.is_enabled():
            #print(f"[诊断-DatabasePool] initialize() 跳过数据库连接（记忆模式）")
            cls._initialized = True
            return

        #print(f"[诊断-DatabasePool] initialize() 正在创建连接池...")
        cls._pool = await asyncpg.create_pool(
            dsn=cls.get_dsn(),
            min_size=min_size,
            max_size=max_size,
            init=cls._init_connection,
        )
        cls._initialized = True

    @classmethod
    async def close(cls):
        """
        关闭连接池
        """
        if cls._pool:
            await cls._pool.close()
            cls._pool = None
            cls._initialized = False

    @classmethod
    async def execute(cls, query: str, *args):
        """
        执行 SQL 查询

        Args:
            query: SQL 查询字符串
            *args: 查询参数

        Returns:
            查询结果

        Raises:
            RuntimeError: 连接池未初始化
        """
        if not cls._pool:
            current_mode = os.getenv("AUTH_STORAGE_MODE", "memory")
            raise RuntimeError(
                f"Database pool not initialized. "
                f"Current AUTH_STORAGE_MODE='{current_mode}'. "
                f"Call initialize() first or set AUTH_STORAGE_MODE=memory"
            )
        async with cls._pool.acquire() as conn:
            return await conn.execute(query, *args)

    @classmethod
    async def fetch(cls, query: str, *args):
        """
        执行 SQL 查询并返回所有结果

        Args:
            query: SQL 查询字符串
            *args: 查询参数

        Returns:
            List[asyncpg.Record]: 查询结果列表

        Raises:
            RuntimeError: 连接池未初始化
        """
        if not cls._pool:
            current_mode = os.getenv("AUTH_STORAGE_MODE", "memory")
            raise RuntimeError(
                f"Database pool not initialized. "
                f"Current AUTH_STORAGE_MODE='{current_mode}'. "
                f"Call initialize() first or set AUTH_STORAGE_MODE=memory"
            )
        async with cls._pool.acquire() as conn:
            return await conn.fetch(query, *args)

    @classmethod
    async def fetchrow(cls, query: str, *args):
        """
        执行 SQL 查询并返回单条结果

        Args:
            query: SQL 查询字符串
            *args: 查询参数

        Returns:
            asyncpg.Record: 查询结果

        Raises:
            RuntimeError: 连接池未初始化
        """
        if not cls._pool:
            current_mode = os.getenv("AUTH_STORAGE_MODE", "memory")
            raise RuntimeError(
                f"Database pool not initialized. "
                f"Current AUTH_STORAGE_MODE='{current_mode}'. "
                f"Call initialize() first or set AUTH_STORAGE_MODE=memory"
            )
        async with cls._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    @classmethod
    async def register_schemas(cls):
        """
        初始化所有已注册的表结构
        """
        for schema_func in _registered_schemas:
            await schema_func()