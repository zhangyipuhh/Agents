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
    async def store_token(
        cls,
        token_hash: str,
        user_id: int,
        expires_at: datetime,
        username: str = "",
    ) -> bool:
        """
        存储 Refresh Token 哈希

        2026-08-11 强化：增加 ``username`` 入参，写入 refresh_tokens.username 列，
        便于 ``/refresh`` 路径直接基于 token_hash 查到 username，签发新 token。

        Args:
            token_hash: Token 的 SHA256 哈希值
            user_id: 用户 ID
            expires_at: 过期时间
            username: 用户名（冗余用于审计与 ``/refresh`` 重签发；可空）

        Returns:
            bool: 存储成功返回 True
        """
        if not cls.is_enabled():
            with cls._lock:
                cls._memory_tokens[token_hash] = {
                    'user_id': user_id,
                    'username': username,
                    'expires_at': expires_at,
                    'created_at': datetime.utcnow()
                }
            return True

        try:
            await DatabasePool.execute(
                """
                INSERT INTO refresh_tokens (token_hash, user_id, username, expires_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (token_hash) DO NOTHING
                """,
                token_hash, user_id, username, expires_at
            )
        except Exception as e:
            print(f"[RefreshTokenDB] 存储 Token 失败: {e}")
            return False
        return True

    @classmethod
    async def verify_token(cls, token_hash: str) -> Optional[dict]:
        """
        验证 Refresh Token 是否存在且未过期

        2026-08-11 强化：返回结果同时携带 ``username``，便于 ``/refresh`` 路径
        直接签发新 Access Token，无需再次按 username 查询 users 表。

        Args:
            token_hash: Token 的 SHA256 哈希值

        Returns:
            Optional[dict]: Token 信息（含 ``user_id`` 与 ``username``），不存在或已过期返回 None
        """
        if not cls.is_enabled():
            with cls._lock:
                record = cls._memory_tokens.get(token_hash)
                if not record:
                    return None
                if record['expires_at'] < datetime.utcnow():
                    del cls._memory_tokens[token_hash]
                    return None
                return {
                    'user_id': record['user_id'],
                    'username': record.get('username', ''),
                }

        row = await DatabasePool.fetchrow(
            "SELECT user_id, username, expires_at FROM refresh_tokens WHERE token_hash = $1",
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
        return {
            'user_id': row['user_id'],
            'username': row.get('username') or '',
        }

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
    async def count_active_tokens(cls, user_id: int) -> int:
        """
        统计指定用户当前未过期的 Refresh Token 数量。

        2026-08-11 增强（等保三级 §1.7）：用于实现并发会话数量限制。

        Args:
            user_id: 用户 ID。

        Returns:
            int: 未过期 Token 数量（>= 0）。
        """
        if not cls.is_enabled():
            now = datetime.utcnow()
            with cls._lock:
                return sum(
                    1
                    for record in cls._memory_tokens.values()
                    if record['user_id'] == user_id and record['expires_at'] >= now
                )

        row = await DatabasePool.fetchrow(
            "SELECT COUNT(*) AS cnt FROM refresh_tokens "
            "WHERE user_id = $1 AND expires_at >= NOW()",
            user_id,
        )
        return int(row['cnt']) if row else 0

    @classmethod
    async def delete_oldest_tokens(cls, user_id: int, keep_count: int) -> int:
        """
        删除指定用户最旧的 Refresh Token，仅保留 ``keep_count`` 条。

        2026-08-11 增强：并发会话数量限制——新登录前先踢出最旧会话，确保总数量
        不超过 ``max_concurrent_sessions``。

        Args:
            user_id: 用户 ID。
            keep_count: 需要保留的最新 Token 数量；<0 抛 ``ValueError``。

        Returns:
            int: 实际删除的 Token 数量（>= 0）。
        """
        if keep_count < 0:
            raise ValueError("keep_count 必须 >= 0")

        if not cls.is_enabled():
            now = datetime.utcnow()
            deleted = 0
            with cls._lock:
                user_tokens = [
                    (h, r)
                    for h, r in cls._memory_tokens.items()
                    if r['user_id'] == user_id and r['expires_at'] >= now
                ]
                user_tokens.sort(
                    key=lambda item: item[1].get('created_at', datetime.min)
                )
                if keep_count:
                    to_delete = user_tokens[:-keep_count]
                else:
                    to_delete = user_tokens
                for h, _ in to_delete:
                    cls._memory_tokens.pop(h, None)
                    deleted += 1
            return deleted

        result = await DatabasePool.execute(
            """
            WITH ranked AS (
                SELECT token_hash,
                       ROW_NUMBER() OVER (
                           ORDER BY created_at DESC, id DESC
                       ) AS rn
                FROM refresh_tokens
                WHERE user_id = $1 AND expires_at >= NOW()
            )
            DELETE FROM refresh_tokens
            WHERE token_hash IN (
                SELECT token_hash FROM ranked WHERE rn > $2
            )
            """,
            user_id,
            keep_count,
        )
        parts = result.split()
        return int(parts[1]) if len(parts) > 1 else 0

    @classmethod
    async def has_valid_token(cls, user_id: int) -> bool:
        """
        检查指定用户是否持有有效的 Refresh Token

        Args:
            user_id: 用户 ID

        Returns:
            bool: 该用户存在未过期的 Refresh Token 返回 True
        """
        if not cls.is_enabled():
            now = datetime.utcnow()
            with cls._lock:
                for record in cls._memory_tokens.values():
                    if record['user_id'] == user_id and record['expires_at'] >= now:
                        return True
            return False

        row = await DatabasePool.fetchrow(
            "SELECT 1 FROM refresh_tokens WHERE user_id = $1 AND expires_at >= NOW() LIMIT 1",
            user_id
        )
        return row is not None

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
