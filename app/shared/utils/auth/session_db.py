"""
Session 两级缓存模块

提供基于 PostgreSQL 的 Session 存储和两级缓存（内存 + 数据库）。
通过 AUTH_STORAGE_MODE 环境变量控制启用数据库模式。

通过 @register_schema 装饰器自动注册会话表结构。

Date: 2026/5/15
"""
import threading
from typing import Optional, Dict
from datetime import datetime
from app.core.database import DatabasePool, register_schema


@register_schema
async def init_session_schema():
    """
    会话表结构初始化

    创建会话表，包含会话ID、用户ID（外键）、用户名和创建时间
    """
    await DatabasePool.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id VARCHAR(100) PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            username VARCHAR(100) NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)


class SessionDB:
    """
    Session 两级缓存管理器

    当 AUTH_STORAGE_MODE=postgres 时：
    - 写入：双向写（内存 + 数据库）
    - 读取：先内存，miss 时查数据库并回填
    - 启动时：从数据库加载所有 session 到内存
    """

    _memory_cache: Dict[str, dict] = {}
    _lock = threading.Lock()
    _initialized: bool = False

    @classmethod
    def is_enabled(cls) -> bool:
        """
        检查是否启用数据库模式

        Returns:
            bool: AUTH_STORAGE_MODE=postgres 时返回 True
        """
        return DatabasePool.is_enabled()

    @classmethod
    async def initialize(cls):
        """
        启动时从数据库加载所有 session 到内存
        """
        if not cls.is_enabled() or cls._initialized:
            return

        rows = await DatabasePool.fetch("SELECT session_id, user_id, username, created_at FROM sessions")
        with cls._lock:
            for row in rows:
                cls._memory_cache[row['session_id']] = {
                    'user_id': row['user_id'],
                    'username': row['username'],
                    'created_at': row['created_at']
                }
        cls._initialized = True

    @classmethod
    async def add_session(cls, session_id: str, user_id: int, username: str):
        """
        添加 Session（双向写入）

        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            username: 用户名
        """
        now = datetime.utcnow()

        # 写入内存
        with cls._lock:
            cls._memory_cache[session_id] = {
                'user_id': user_id,
                'username': username,
                'created_at': now
            }

        # 写入数据库
        if cls.is_enabled():
            await DatabasePool.execute(
                """
                INSERT INTO sessions (session_id, user_id, username, created_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (session_id) DO NOTHING
                """,
                session_id,
                user_id,
                username,
                now
            )

    @classmethod
    def get_session(cls, session_id: str) -> Optional[dict]:
        """
        获取 Session（先内存，后数据库）

        Args:
            session_id: 会话 ID

        Returns:
            Optional[dict]: Session 信息
        """
        # 先查内存
        with cls._lock:
            session = cls._memory_cache.get(session_id)
            if session:
                return session.copy()

        # 内存未命中，查数据库
        if cls.is_enabled():
            row = DatabasePool.fetchrow(
                "SELECT session_id, user_id, username, created_at FROM sessions WHERE session_id = $1",
                session_id
            )
            if row:
                session_data = {
                    'user_id': row['user_id'],
                    'username': row['username'],
                    'created_at': row['created_at']
                }
                # 回填内存
                with cls._lock:
                    cls._memory_cache[session_id] = session_data
                return session_data

        return None

    @classmethod
    def verify_session(cls, session_id: str, username: str) -> bool:
        """
        验证 Session 是否属于指定用户

        Args:
            session_id: 会话 ID
            username: 用户名

        Returns:
            bool: Session 属于该用户返回 True
        """
        session = cls.get_session(session_id)
        if not session:
            return False
        return session['username'] == username

    @classmethod
    async def delete_session(cls, session_id: str) -> bool:
        """
        删除 Session

        Args:
            session_id: 会话 ID

        Returns:
            bool: 删除成功返回 True
        """
        # 删除内存
        with cls._lock:
            if session_id in cls._memory_cache:
                del cls._memory_cache[session_id]

        # 删除数据库
        if cls.is_enabled():
            await DatabasePool.execute(
                "DELETE FROM sessions WHERE session_id = $1",
                session_id
            )
        return True

    @classmethod
    async def delete_user_sessions(cls, user_id: int) -> int:
        """
        删除用户的所有 Session

        Args:
            user_id: 用户 ID

        Returns:
            int: 删除的 session 数量
        """
        rows = await DatabasePool.fetch(
            "SELECT session_id FROM sessions WHERE user_id = $1",
            user_id
        )
        session_ids = [row['session_id'] for row in rows]

        # 删除内存
        with cls._lock:
            for session_id in session_ids:
                if session_id in cls._memory_cache:
                    del cls._memory_cache[session_id]

        # 删除数据库
        if cls.is_enabled():
            await DatabasePool.execute(
                "DELETE FROM sessions WHERE user_id = $1",
                user_id
            )
            return len(session_ids)

        return 0