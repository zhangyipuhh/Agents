"""
审计日志模块

记录用户登录、登出、Session 创建/销毁等操作日志。
支持 postgres 和 memory 两种存储模式。

Date: 2026/5/26
"""
import threading
from typing import Optional, List, Dict
from datetime import datetime
from app.core.database import DatabasePool, register_schema


@register_schema
async def init_audit_log_schema():
    """
    审计日志表结构初始化

    创建审计日志表，包含用户ID、用户名、操作类型、详情、IP地址和创建时间。
    """
    await DatabasePool.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            username VARCHAR(100),
            action VARCHAR(50) NOT NULL,
            detail TEXT,
            ip_address VARCHAR(50),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)


class AuditLog:
    """
    审计日志操作类

    提供审计日志的写入和查询方法。
    支持两种模式：
    - postgres 模式：使用 PostgreSQL 数据库
    - memory 模式：使用内存列表存储
    """

    _memory_logs: List[dict] = []
    _lock = threading.Lock()

    @classmethod
    def is_enabled(cls) -> bool:
        """
        检查是否启用数据库模式

        Returns:
            bool: AUTH_STORAGE_MODE=postgres 时返回 True
        """
        return DatabasePool.is_enabled()

    @classmethod
    async def write_log(
        cls,
        action: str,
        username: str = None,
        user_id: int = None,
        detail: str = None,
        ip_address: str = None
    ):
        """
        写入审计日志

        Args:
            action: 操作类型（如 login_success, login_failure, logout, session_create, session_delete）
            username: 用户名
            user_id: 用户 ID
            detail: 操作详情
            ip_address: 请求 IP 地址
        """
        if not cls.is_enabled():
            with cls._lock:
                cls._memory_logs.append({
                    'user_id': user_id,
                    'username': username,
                    'action': action,
                    'detail': detail,
                    'ip_address': ip_address,
                    'created_at': datetime.utcnow()
                })
            return

        await DatabasePool.execute(
            """
            INSERT INTO audit_logs (user_id, username, action, detail, ip_address)
            VALUES ($1, $2, $3, $4, $5)
            """,
            user_id,
            username,
            action,
            detail,
            ip_address
        )

    @classmethod
    async def query_logs(
        cls,
        username: str = None,
        action: str = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[dict]:
        """
        查询审计日志

        Args:
            username: 按用户名过滤
            action: 按操作类型过滤
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            List[dict]: 日志列表
        """
        if not cls.is_enabled():
            with cls._lock:
                logs = cls._memory_logs[:]
                if username:
                    logs = [l for l in logs if l.get('username') == username]
                if action:
                    logs = [l for l in logs if l.get('action') == action]
                logs.sort(key=lambda x: x['created_at'], reverse=True)
                return logs[offset:offset + limit]

        conditions = []
        params = []
        idx = 1

        if username:
            conditions.append(f"username = ${idx}")
            params.append(username)
            idx += 1
        if action:
            conditions.append(f"action = ${idx}")
            params.append(action)
            idx += 1

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        params.extend([limit, offset])

        return await DatabasePool.fetch(
            f"SELECT id, user_id, username, action, detail, ip_address, created_at "
            f"FROM audit_logs{where_clause} "
            f"ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}",
            *params
        )
