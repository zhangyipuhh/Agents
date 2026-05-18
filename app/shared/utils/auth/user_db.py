"""
用户数据库操作模块

提供用户的注册、验证、查询等数据库操作。
使用 bcrypt 进行密码加密。

通过 @register_schema 装饰器自动注册用户表结构。

支持两种模式：
- postgres 模式：使用 PostgreSQL 数据库
- memory 模式：使用内存字典存储

Date: 2026/5/15
"""
import threading
import bcrypt
from typing import Optional, List, Dict
from datetime import datetime
from app.core.database import DatabasePool, register_schema


@register_schema
async def init_user_schema():
    """
    用户表结构初始化

    创建用户表，包含用户名（唯一）、密码哈希、创建时间和更新时间
    """
    await DatabasePool.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)


class UserDB:
    """
    用户数据库操作类

    提供用户的创建、验证、查询等方法。
    支持两种模式：
    - postgres 模式：使用 PostgreSQL 数据库
    - memory 模式：使用内存字典存储
    """

    # 内存存储（当 AUTH_STORAGE_MODE=memory 时使用）
    _memory_users: Dict[str, dict] = {}
    _memory_id_counter: int = 0
    _lock = threading.Lock()

    @classmethod
    def is_enabled(cls) -> bool:
        """
        检查是否启用数据库模式

        Returns:
            bool: AUTH_STORAGE_MODE=postgres 时返回 True
        """
        return DatabasePool.is_enabled()

    @staticmethod
    def hash_password(password: str) -> str:
        """
        使用 bcrypt 加密密码

        Args:
            password: 明文密码

        Returns:
            str: 加密后的密码哈希
        """
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """
        验证密码

        Args:
            password: 明文密码
            password_hash: 加密后的密码哈希

        Returns:
            bool: 验证通过返回 True
        """
        return bcrypt.checkpw(
            password.encode('utf-8'),
            password_hash.encode('utf-8')
        )

    @classmethod
    async def create_user(cls, username: str, password: str) -> int:
        """
        创建新用户

        Args:
            username: 用户名
            password: 明文密码

        Returns:
            int: 新用户 ID

        Raises:
            ValueError: 用户名已存在
        """
        password_hash = cls.hash_password(password)

        if not cls.is_enabled():
            # Memory 模式：使用内存存储
            with cls._lock:
                if username in cls._memory_users:
                    raise ValueError("用户名已存在")
                cls._memory_id_counter += 1
                user_id = cls._memory_id_counter
                now = datetime.utcnow()
                cls._memory_users[username] = {
                    'id': user_id,
                    'username': username,
                    'password_hash': password_hash,
                    'created_at': now,
                    'updated_at': now
                }
                return user_id

        # Postgres 模式：使用数据库
        import asyncpg
        try:
            row = await DatabasePool.fetchrow(
                """
                INSERT INTO users (username, password_hash)
                VALUES ($1, $2)
                RETURNING id
                """,
                username,
                password_hash
            )
            return row['id']
        except asyncpg.UniqueViolationError:
            raise ValueError("用户名已存在")

    @classmethod
    async def verify_credentials(cls, username: str, password: str) -> bool:
        """
        验证用户凭据

        Args:
            username: 用户名
            password: 明文密码

        Returns:
            bool: 验证通过返回 True
        """
        if not cls.is_enabled():
            # Memory 模式：从内存存储验证
            with cls._lock:
                user = cls._memory_users.get(username)
                if not user:
                    return False
                return cls.verify_password(password, user['password_hash'])

        # Postgres 模式：从数据库验证
        row = await DatabasePool.fetchrow(
            "SELECT password_hash FROM users WHERE username = $1",
            username
        )
        if not row:
            return False
        return cls.verify_password(password, row['password_hash'])

    @classmethod
    async def get_user_by_username(cls, username: str) -> Optional[dict]:
        """
        根据用户名查询用户

        Args:
            username: 用户名

        Returns:
            Optional[dict]: 用户信息，不存在返回 None
        """
        if not cls.is_enabled():
            #print(f"[诊断-UserDB] get_user_by_username('{username}'): 记忆模式, _memory_users keys={list(cls._memory_users.keys())}")
            # Memory 模式：从内存存储查询
            with cls._lock:
                user = cls._memory_users.get(username)
                if not user:
                    #print(f"[诊断-UserDB] get_user_by_username: 用户 '{username}' 不在内存中, 返回 None")
                    return None
                result = {
                    'id': user['id'],
                    'username': user['username'],
                    'created_at': user['created_at'],
                    'updated_at': user['updated_at']
                }
                #print(f"[诊断-UserDB] get_user_by_username: 返回 {result}")
                return result

        #print(f"[诊断-UserDB] get_user_by_username('{username}'): 数据库模式")
        # Postgres 模式：从数据库查询
        return await DatabasePool.fetchrow(
            "SELECT id, username, created_at, updated_at FROM users WHERE username = $1",
            username
        )

    @classmethod
    async def get_user_by_id(cls, user_id: int) -> Optional[dict]:
        """
        根据 ID 查询用户

        Args:
            user_id: 用户 ID

        Returns:
            Optional[dict]: 用户信息，不存在返回 None
        """
        if not cls.is_enabled():
            # Memory 模式：从内存存储查询
            with cls._lock:
                for user in cls._memory_users.values():
                    if user['id'] == user_id:
                        return {
                            'id': user['id'],
                            'username': user['username'],
                            'created_at': user['created_at'],
                            'updated_at': user['updated_at']
                        }
                return None

        # Postgres 模式：从数据库查询
        return await DatabasePool.fetchrow(
            "SELECT id, username, created_at, updated_at FROM users WHERE id = $1",
            user_id
        )

    @classmethod
    async def list_users(cls, limit: int = 100, offset: int = 0) -> List[dict]:
        """
        查询用户列表

        Args:
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            List[dict]: 用户列表
        """
        if not cls.is_enabled():
            # Memory 模式：从内存存储查询
            with cls._lock:
                users = list(cls._memory_users.values())
                sorted_users = sorted(users, key=lambda u: u['id'])
                paginated_users = sorted_users[offset:offset + limit]
                return [
                    {
                        'id': user['id'],
                        'username': user['username'],
                        'created_at': user['created_at'],
                        'updated_at': user['updated_at']
                    }
                    for user in paginated_users
                ]

        # Postgres 模式：从数据库查询
        return await DatabasePool.fetch(
            "SELECT id, username, created_at, updated_at FROM users ORDER BY id LIMIT $1 OFFSET $2",
            limit,
            offset
        )

    @classmethod
    async def delete_user(cls, user_id: int) -> bool:
        """
        删除用户

        Args:
            user_id: 用户 ID

        Returns:
            bool: 删除成功返回 True
        """
        if not cls.is_enabled():
            # Memory 模式：从内存存储删除
            with cls._lock:
                for username, user in list(cls._memory_users.items()):
                    if user['id'] == user_id:
                        del cls._memory_users[username]
                        return True
                return False

        # Postgres 模式：从数据库删除
        result = await DatabasePool.execute(
            "DELETE FROM users WHERE id = $1",
            user_id
        )
        return "DELETE 1" in result

    @classmethod
    async def update_password(cls, user_id: int, new_password: str) -> bool:
        """
        更新用户密码

        Args:
            user_id: 用户 ID
            new_password: 新明文密码

        Returns:
            bool: 更新成功返回 True
        """
        password_hash = cls.hash_password(new_password)

        if not cls.is_enabled():
            # Memory 模式：更新内存存储中的密码
            with cls._lock:
                for user in cls._memory_users.values():
                    if user['id'] == user_id:
                        user['password_hash'] = password_hash
                        user['updated_at'] = datetime.utcnow()
                        return True
                return False

        # Postgres 模式：更新数据库中的密码
        result = await DatabasePool.execute(
            "UPDATE users SET password_hash = $1, updated_at = NOW() WHERE id = $2",
            password_hash,
            user_id
        )
        return "UPDATE 1" in result