"""
Refresh Token 双模式存储模块

支持两种模式：
- postgres 模式：SHA256 哈希存入 PostgreSQL
- memory 模式：SHA256 哈希存入内存字典

设计目的：
- 数据库持久化支持主动撤销（登出、密码修改、管理员踢人）
- 纯 JWT 无状态方案无法主动撤销 Token

Date: 2026/5/27
"""
import hashlib
import threading
from typing import Optional, Dict, List
from datetime import datetime
from app.core.database import DatabasePool


class RefreshTokenDB:
    """
    Refresh Token 数据库操作类

    以 SHA256 哈希存储 Token，支持 postgres 和 memory 双模式。
    """

    _memory_tokens: Dict[str, dict] = {}
    _lock = threading.Lock()

    @classmethod
    def is_enabled(cls) -> bool:
        """检查是否启用数据库模式"""
        return DatabasePool.is_enabled()

    @staticmethod
    def hash_token(token: str) -> str:
        """
        计算 Token 的 SHA256 哈希值

        Args:
            token: Refresh Token 字符串

        Returns:
            str: SHA256 哈希值
        """
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    @classmethod
    async def store_token(cls, token_hash: str, user_id: int, expires_at: datetime) -> bool:
        """
        存储 Refresh Token 哈希

        Args:
            token_hash: Token 的 SHA256 哈希值
            user_id: 用户 ID
            expires_at: 过期时间

        Returns:
            bool: 存储成功返回 True
        """
        if not cls.is_enabled():
            with cls._lock:
                cls._memory_tokens[token_hash] = {
                    'user_id': user_id,
                    'expires_at': expires_at,
                    'created_at': datetime.utcnow()
                }
            return True

        try:
            await DatabasePool.execute(
                """
                INSERT INTO refresh_tokens (token_hash, user_id, expires_at)
                VALUES ($1, $2, $3)
                ON CONFLICT (token_hash) DO NOTHING
                """,
                token_hash, user_id, expires_at
            )
        except Exception as e:
            print(f"[RefreshTokenDB] 存储 Token 失败: {e}")
            return False
        return True

    @classmethod
    async def verify_token(cls, token_hash: str) -> Optional[dict]:
        """
        验证 Refresh Token 是否存在且未过期

        Args:
            token_hash: Token 的 SHA256 哈希值

        Returns:
            Optional[dict]: Token 信息（含 user_id），不存在或已过期返回 None
        """
        if not cls.is_enabled():
            with cls._lock:
                record = cls._memory_tokens.get(token_hash)
                if not record:
                    return None
                if record['expires_at'] < datetime.utcnow():
                    del cls._memory_tokens[token_hash]
                    return None
                return {'user_id': record['user_id']}

        row = await DatabasePool.fetchrow(
            "SELECT user_id, expires_at FROM refresh_tokens WHERE token_hash = $1",
            token_hash
        )
        if not row:
            return None
        if row['expires_at'] < datetime.utcnow():
            await DatabasePool.execute(
                "DELETE FROM refresh_tokens WHERE token_hash = $1",
                token_hash
            )
            return None
        return {'user_id': row['user_id']}

    @classmethod
    async def delete_token(cls, token_hash: str) -> bool:
        """
        删除指定 Refresh Token

        Args:
            token_hash: Token 的 SHA256 哈希值

        Returns:
            bool: 删除成功返回 True
        """
        if not cls.is_enabled():
            with cls._lock:
                if token_hash in cls._memory_tokens:
                    del cls._memory_tokens[token_hash]
                    return True
            return False

        result = await DatabasePool.execute(
            "DELETE FROM refresh_tokens WHERE token_hash = $1",
            token_hash
        )
        parts = result.split()
        deleted = int(parts[1]) if len(parts) > 1 else 0
        return deleted > 0

    @classmethod
    async def delete_user_tokens(cls, user_id: int) -> int:
        """
        删除用户的所有 Refresh Token

        用于密码修改、管理员踢人等场景。

        Args:
            user_id: 用户 ID

        Returns:
            int: 删除的 Token 数量
        """
        if not cls.is_enabled():
            deleted = 0
            with cls._lock:
                for token_hash, record in list(cls._memory_tokens.items()):
                    if record['user_id'] == user_id:
                        del cls._memory_tokens[token_hash]
                        deleted += 1
            return deleted

        result = await DatabasePool.execute(
            "DELETE FROM refresh_tokens WHERE user_id = $1",
            user_id
        )
        parts = result.split()
        return int(parts[1]) if len(parts) > 1 else 0

    @classmethod
    async def cleanup_expired(cls) -> int:
        """
        清理所有已过期的 Refresh Token

        Returns:
            int: 清理的 Token 数量
        """
        if not cls.is_enabled():
            deleted = 0
            now = datetime.utcnow()
            with cls._lock:
                for token_hash, record in list(cls._memory_tokens.items()):
                    if record['expires_at'] < now:
                        del cls._memory_tokens[token_hash]
                        deleted += 1
            return deleted

        result = await DatabasePool.execute(
            "DELETE FROM refresh_tokens WHERE expires_at < NOW()"
        )
        parts = result.split()
        return int(parts[1]) if len(parts) > 1 else 0

    @classmethod
    async def get_users_with_valid_tokens(cls) -> List[dict]:
        """
        获取所有持有有效 Refresh Token 的用户列表

        用于在线用户监控，判断用户是否因持有未过期主 refresh_token 而在线。

        Returns:
            List[dict]: 用户列表，每项包含 user_id
        """
        if not cls.is_enabled():
            now = datetime.utcnow()
            user_ids = set()
            with cls._lock:
                for record in cls._memory_tokens.values():
                    if record['expires_at'] >= now:
                        user_ids.add(record['user_id'])
            return [{'user_id': uid} for uid in user_ids]

        rows = await DatabasePool.fetch(
            "SELECT DISTINCT user_id FROM refresh_tokens WHERE expires_at >= NOW()"
        )
        return [{'user_id': row['user_id']} for row in rows]
