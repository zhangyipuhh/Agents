"""
Portal Refresh Token 双模式存储模块

与 RefreshTokenDB 同形，专门用于"门户子 refresh_token"——
父页（门户导航页）通过后端 issue-portal-refresh-token 接口颁发，
再经 postMessage 推送给第三方 iframe；第三方像普通 SPA 一样用它
反复换 access_token。子 token 24 小时有效，独立存储便于独立撤销。

支持两种模式：
- postgres 模式：SHA256 哈希存入 PostgreSQL
- memory 模式：SHA256 哈希存入内存字典

设计目的：
- 与 refresh_tokens 表解耦，登出 / 密码修改 / 管理员踢人时可独立撤销
- 数据库持久化支持主动撤销（revoked 软删除）
- 纯 JWT 无状态方案无法主动撤销 Token

与 refresh_token_db 的差异：
- 独立表（portal_refresh_tokens），不与主 refresh_tokens 互查
- 增加 revoked 软删除字段，便于审计与撤销策略
- 撤销 API 命名为 revoke_* 而非 delete_*，与软删除语义一致

Date: 2026-06-05
"""
import hashlib
import threading
from typing import Optional, Dict
from datetime import datetime
from app.core.database import DatabasePool


class PortalRefreshTokenDB:
    """
    Portal Refresh Token 数据库操作类

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
            token: Portal Refresh Token 字符串

        Returns:
            str: SHA256 哈希值
        """
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    @classmethod
    async def store_token(cls, token_hash: str, user_id: int, username: str, expires_at: datetime) -> bool:
        """
        存储 Portal Refresh Token 哈希

        Args:
            token_hash: Token 的 SHA256 哈希值
            user_id: 用户 ID
            username: 用户名（冗余用于审计）
            expires_at: 过期时间

        Returns:
            bool: 存储成功返回 True
        """
        if not cls.is_enabled():
            with cls._lock:
                cls._memory_tokens[token_hash] = {
                    'user_id': user_id,
                    'username': username,
                    'expires_at': expires_at,
                    'revoked': False,
                    'created_at': datetime.utcnow()
                }
            return True

        try:
            await DatabasePool.execute(
                """
                INSERT INTO portal_refresh_tokens (token_hash, user_id, username, expires_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (token_hash) DO NOTHING
                """,
                token_hash, user_id, username, expires_at
            )
        except Exception as e:
            print(f"[PortalRefreshTokenDB] 存储 Token 失败: {e}")
            return False
        return True

    @classmethod
    async def verify_token(cls, token_hash: str) -> Optional[dict]:
        """
        验证 Portal Refresh Token 是否存在且未过期且未撤销

        Args:
            token_hash: Token 的 SHA256 哈希值

        Returns:
            Optional[dict]: Token 信息（含 user_id、username），不存在或已过期或已撤销返回 None
        """
        if not cls.is_enabled():
            with cls._lock:
                record = cls._memory_tokens.get(token_hash)
                if not record:
                    return None
                if record.get('revoked'):
                    return None
                if record['expires_at'] < datetime.utcnow():
                    cls._memory_tokens.pop(token_hash, None)
                    return None
                return {'user_id': record['user_id'], 'username': record.get('username', '')}

        row = await DatabasePool.fetchrow(
            "SELECT user_id, username, expires_at, revoked FROM portal_refresh_tokens WHERE token_hash = $1",
            token_hash
        )
        if not row:
            return None
        if row.get('revoked'):
            return None
        if row['expires_at'] < datetime.utcnow():
            await DatabasePool.execute(
                "DELETE FROM portal_refresh_tokens WHERE token_hash = $1",
                token_hash
            )
            return None
        return {'user_id': row['user_id'], 'username': row.get('username', '')}

    @classmethod
    async def revoke_token(cls, token_hash: str) -> bool:
        """
        软删除指定的 Portal Refresh Token（置 revoked=TRUE）

        软删除而非物理删除，便于审计追溯。

        Args:
            token_hash: Token 的 SHA256 哈希值

        Returns:
            bool: 撤销成功返回 True
        """
        if not cls.is_enabled():
            with cls._lock:
                if token_hash in cls._memory_tokens:
                    cls._memory_tokens[token_hash]['revoked'] = True
                    return True
            return False

        result = await DatabasePool.execute(
            "UPDATE portal_refresh_tokens SET revoked = TRUE WHERE token_hash = $1",
            token_hash
        )
        # asyncpg 返回 "UPDATE n" 格式
        parts = result.split()
        return len(parts) >= 2 and parts[1] != '0'

    @classmethod
    async def revoke_user_tokens(cls, user_id: int) -> int:
        """
        撤销指定用户的所有 Portal Refresh Token

        用于登出、密码修改、管理员踢人等场景。
        该用户的所有子 refresh_token 立即失效，第三方 iframe
        下次调用 /api/auth/refresh 换 access_token 时将得到 401。

        Args:
            user_id: 用户 ID

        Returns:
            int: 撤销的 Token 数量
        """
        if not cls.is_enabled():
            revoked = 0
            with cls._lock:
                for record in cls._memory_tokens.values():
                    if record['user_id'] == user_id and not record.get('revoked'):
                        record['revoked'] = True
                        revoked += 1
            return revoked

        result = await DatabasePool.execute(
            "UPDATE portal_refresh_tokens SET revoked = TRUE WHERE user_id = $1 AND revoked = FALSE",
            user_id
        )
        parts = result.split()
        return int(parts[1]) if len(parts) > 1 else 0

    @classmethod
    async def cleanup_expired(cls) -> int:
        """
        清理所有已过期的 Portal Refresh Token（物理删除）

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
            "DELETE FROM portal_refresh_tokens WHERE expires_at < NOW()"
        )
        parts = result.split()
        return int(parts[1]) if len(parts) > 1 else 0
