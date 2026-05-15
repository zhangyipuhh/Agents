"""
全局数据库连接池模块

提供 PostgreSQL 异步连接池，支持单例模式。
通过环境变量 AUTH_STORAGE_MODE 控制是否启用数据库。

各业务模块可通过 @register_schema 装饰器注册表结构初始化函数，
启动时统一调用。

Date: 2026/5/15
"""
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
        return os.getenv("AUTH_STORAGE_MODE", "memory") == "postgres"

    @classmethod
    async def initialize(cls, min_size: int = 5, max_size: int = 20):
        """
        初始化连接池

        Args:
            min_size: 最小连接数
            max_size: 最大连接数
        """
        if cls._initialized:
            return

        if not cls.is_enabled():
            cls._initialized = True
            return

        cls._pool = await asyncpg.create_pool(
            dsn=cls.get_dsn(),
            min_size=min_size,
            max_size=max_size,
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
        """
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
        """
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
        """
        async with cls._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    @classmethod
    async def register_schemas(cls):
        """
        初始化所有已注册的表结构
        """
        for schema_func in _registered_schemas:
            await schema_func()