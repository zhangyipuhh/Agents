"""
用户数据库操作模块

提供用户的注册、验证、查询等数据库操作。
使用 bcrypt 进行密码加密。

通过 @register_schema 装饰器自动注册用户表结构。

Date: 2026/5/15
"""
import bcrypt
from typing import Optional, List
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
    """

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
        import asyncpg
        password_hash = cls.hash_password(password)
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
        result = await DatabasePool.execute(
            "UPDATE users SET password_hash = $1, updated_at = NOW() WHERE id = $2",
            password_hash,
            user_id
        )
        return "UPDATE 1" in result