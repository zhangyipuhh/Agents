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

    创建用户表（如果不存在，含 role 字段）和会话表，包含会话ID、用户ID（外键）、用户名和创建时间。
    同时创建对话记录表和附件表，并添加必要的索引。
    """
    # 先创建 users 表（如果尚未创建）
    await DatabasePool.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(20) DEFAULT 'user',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # 再创建 sessions 表
    await DatabasePool.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id VARCHAR(100) PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            username VARCHAR(100) NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # sessions 表新增字段（向后兼容）
    await DatabasePool.execute("""
        ALTER TABLE sessions ADD COLUMN IF NOT EXISTS title VARCHAR(200) DEFAULT '新对话'
    """)
    await DatabasePool.execute("""
        ALTER TABLE sessions ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMP DEFAULT NOW()
    """)
    await DatabasePool.execute("""
        ALTER TABLE sessions ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'active'
    """)
    await DatabasePool.execute("""
        ALTER TABLE sessions ADD COLUMN IF NOT EXISTS agent_type VARCHAR(50) DEFAULT 'default'
    """)
    await DatabasePool.execute("""
        ALTER TABLE sessions ADD COLUMN IF NOT EXISTS agent_display_name VARCHAR(200) DEFAULT ''
    """)

    # sessions 表索引
    await DatabasePool.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)
    """)
    await DatabasePool.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_last_active_at ON sessions(last_active_at)
    """)
    await DatabasePool.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status)
    """)
    await DatabasePool.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_user_id_last_active ON sessions(user_id, last_active_at DESC)
    """)

    # 创建对话记录表
    await DatabasePool.execute("""
        CREATE TABLE IF NOT EXISTS conversation_records (
            id SERIAL PRIMARY KEY,
            session_id VARCHAR(100) NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
            role VARCHAR(20) NOT NULL,
            content TEXT,
            tool_calls JSONB,
            tool_call_id VARCHAR(100),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # conversation_records 表索引
    await DatabasePool.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversation_records_session_id ON conversation_records(session_id)
    """)
    await DatabasePool.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversation_records_session_created ON conversation_records(session_id, created_at)
    """)

    # 创建附件表
    await DatabasePool.execute("""
        CREATE TABLE IF NOT EXISTS attachments (
            id SERIAL PRIMARY KEY,
            session_id VARCHAR(100) NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
            file_name VARCHAR(500) NOT NULL,
            stored_path VARCHAR(1000) NOT NULL,
            file_type VARCHAR(20) NOT NULL,
            file_size BIGINT DEFAULT 0,
            mime_type VARCHAR(100),
            file_id VARCHAR(100),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # attachments 表索引
    await DatabasePool.execute("""
        CREATE INDEX IF NOT EXISTS idx_attachments_session_id ON attachments(session_id)
    """)
    await DatabasePool.execute("""
        CREATE INDEX IF NOT EXISTS idx_attachments_session_created ON attachments(session_id, created_at)
    """)

    # Refresh Tokens 表
    await DatabasePool.execute("""
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id SERIAL PRIMARY KEY,
            token_hash VARCHAR(255) UNIQUE NOT NULL,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    await DatabasePool.execute("""
        CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id)
    """)
    await DatabasePool.execute("""
        CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires_at ON refresh_tokens(expires_at)
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

        rows = await DatabasePool.fetch(
            "SELECT session_id, user_id, username, created_at, title, last_active_at, status, agent_type, agent_display_name FROM sessions"
        )
        with cls._lock:
            for row in rows:
                cls._memory_cache[row['session_id']] = {
                    'user_id': row['user_id'],
                    'username': row['username'],
                    'created_at': row['created_at'],
                    'title': row.get('title', '新对话'),
                    'last_active_at': row.get('last_active_at', row['created_at']),
                    'status': row.get('status', 'active'),
                    'agent_type': row.get('agent_type', 'default'),
                    'agent_display_name': row.get('agent_display_name', ''),
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
        now = datetime.now()
        print(f"[诊断-SessionDB] add_session: session_id={session_id}, user_id={user_id}, username={username}")

        # 写入内存
        with cls._lock:
            cls._memory_cache[session_id] = {
                'user_id': user_id,
                'username': username,
                'created_at': now,
                'title': '新对话',
                'last_active_at': now,
                'status': 'active',
                'agent_type': 'default',
                'agent_display_name': '',
            }
            #print(f"[诊断-SessionDB] 已写入内存, _memory_cache keys={list(cls._memory_cache.keys())}")

        # 写入数据库
        if cls.is_enabled():
            await DatabasePool.execute(
                """
                INSERT INTO sessions (session_id, user_id, username, created_at, title, last_active_at, status, agent_type, agent_display_name)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (session_id) DO NOTHING
                """,
                session_id,
                user_id,
                username,
                now,
                '新对话',
                now,
                'active',
                'default',
                ''
            )

    @classmethod
    async def get_session(cls, session_id: str) -> Optional[dict]:
        """
        获取 Session（先内存，后数据库）

        Args:
            session_id: 会话 ID

        Returns:
            Optional[dict]: Session 信息，包含 title、last_active_at、status、agent_type
        """
        print(f"[诊断-SessionDB] get_session: session_id={session_id}")
        # 先查内存
        with cls._lock:
            #print(f"[诊断-SessionDB] 内存缓存 keys={list(cls._memory_cache.keys())}")
            session = cls._memory_cache.get(session_id)
            print(f"[诊断-SessionDB] 内存查询结果: {session}")
            if session:
                return session.copy()

        # 内存未命中，查数据库
        if cls.is_enabled():
            row = await DatabasePool.fetchrow(
                "SELECT session_id, user_id, username, created_at, title, last_active_at, status, agent_type, agent_display_name FROM sessions WHERE session_id = $1",
                session_id
            )
            if row:
                session_data = {
                    'user_id': row['user_id'],
                    'username': row['username'],
                    'created_at': row['created_at'],
                    'title': row.get('title', '新对话'),
                    'last_active_at': row.get('last_active_at', row['created_at']),
                    'status': row.get('status', 'active'),
                    'agent_type': row.get('agent_type', 'default'),
                    'agent_display_name': row.get('agent_display_name', ''),
                }
                # 回填内存
                with cls._lock:
                    cls._memory_cache[session_id] = session_data
                return session_data

        return None

    @classmethod
    async def verify_session(cls, session_id: str, username: str) -> bool:
        """
        验证 Session 是否属于指定用户

        Args:
            session_id: 会话 ID
            username: 用户名

        Returns:
            bool: Session 属于该用户且状态为 active 返回 True
        """
        print(f"[诊断-SessionDB] verify_session: session_id={session_id}, username={username}")
        session = await cls.get_session(session_id)
        print(f"[诊断-SessionDB] get_session result: {session}")
        if not session:
            print(f"[诊断-SessionDB] session not found")
            return False
        if session.get('status', 'active') != 'active':
            print(f"[诊断-SessionDB] session status={session.get('status')}, 拒绝访问")
            return False
        result = session['username'] == username
        print(f"[诊断-SessionDB] verify result: {result}, session_username={session.get('username')}")
        return result

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
        if not cls.is_enabled():
            # Memory 模式：只删除内存中的 session
            session_ids = []
            with cls._lock:
                for session_id, session in list(cls._memory_cache.items()):
                    if session.get('user_id') == user_id:
                        session_ids.append(session_id)
                        del cls._memory_cache[session_id]
            return len(session_ids)

        # Postgres 模式：从数据库查询并删除
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
        await DatabasePool.execute(
            "DELETE FROM sessions WHERE user_id = $1",
            user_id
        )
        return len(session_ids)

    @classmethod
    async def kick_user_sessions(cls, user_id: int) -> int:
        """
        强制下线用户的所有 Session

        将用户所有 Session 的 status 更新为 'kicked'，使其不再计入在线列表，
        同时保留会话记录供 admin 会话查询查看历史数据。

        Args:
            user_id: 用户 ID

        Returns:
            int: 被标记为 kicked 的 session 数量
        """
        # 更新内存缓存
        kicked_count = 0
        with cls._lock:
            for sid, s in list(cls._memory_cache.items()):
                if s.get('user_id') == user_id:
                    cls._memory_cache[sid]['status'] = 'kicked'
                    kicked_count += 1

        # 更新数据库
        if cls.is_enabled():
            await DatabasePool.execute(
                "UPDATE sessions SET status = 'kicked' WHERE user_id = $1 AND status = 'active'",
                user_id
            )

        return kicked_count

    @classmethod
    async def update_session_title(cls, session_id: str, title: str) -> bool:
        """
        更新会话标题

        Args:
            session_id: 会话 ID
            title: 新标题

        Returns:
            bool: 更新成功返回 True
        """
        # 更新内存
        with cls._lock:
            if session_id in cls._memory_cache:
                cls._memory_cache[session_id]['title'] = title

        # 更新数据库
        if cls.is_enabled():
            await DatabasePool.execute(
                "UPDATE sessions SET title = $1 WHERE session_id = $2",
                title,
                session_id
            )
        return True

    @classmethod
    async def update_last_active(cls, session_id: str) -> bool:
        """
        更新会话最后活跃时间

        Args:
            session_id: 会话 ID

        Returns:
            bool: 更新成功返回 True
        """
        now = datetime.now()

        # 更新内存
        with cls._lock:
            if session_id in cls._memory_cache:
                cls._memory_cache[session_id]['last_active_at'] = now

        # 更新数据库
        if cls.is_enabled():
            await DatabasePool.execute(
                "UPDATE sessions SET last_active_at = $1 WHERE session_id = $2",
                now,
                session_id
            )
        return True

    @classmethod
    async def update_session_agent(cls, session_id: str, agent_type: str, agent_display_name: str) -> bool:
        """
        更新会话绑定的智能体（同步更新内存 + 数据库）

        Args:
            session_id: 会话 ID
            agent_type: 智能体标识名称
            agent_display_name: 智能体展示名称（中文）

        Returns:
            bool: 更新成功返回 True
        """
        # 更新内存
        with cls._lock:
            if session_id in cls._memory_cache:
                cls._memory_cache[session_id]['agent_type'] = agent_type
                cls._memory_cache[session_id]['agent_display_name'] = agent_display_name

        # 更新数据库
        if cls.is_enabled():
            await DatabasePool.execute(
                "UPDATE sessions SET agent_type = $1, agent_display_name = $2 WHERE session_id = $3",
                agent_type,
                agent_display_name,
                session_id,
            )
        return True

    @classmethod
    async def get_user_sessions(cls, user_id: int) -> list:
        """
        获取用户的所有会话列表（按最后活跃时间倒序）

        Args:
            user_id: 用户 ID

        Returns:
            list: 会话列表，每项包含 session_id、title、last_active_at、status、agent_type、agent_display_name、created_at
        """
        if cls.is_enabled():
            rows = await DatabasePool.fetch(
                """
                SELECT session_id, title, last_active_at, status, agent_type, agent_display_name, created_at
                FROM sessions
                WHERE user_id = $1
                ORDER BY last_active_at DESC
                """,
                user_id
            )
            return [dict(row) for row in rows]

        # Memory 模式：从内存缓存中筛选
        with cls._lock:
            sessions = []
            for sid, s in cls._memory_cache.items():
                if s.get('user_id') == user_id:
                    sessions.append({
                        'session_id': sid,
                        'title': s.get('title', '新对话'),
                        'last_active_at': s.get('last_active_at', s.get('created_at')),
                        'status': s.get('status', 'active'),
                        'agent_type': s.get('agent_type', 'default'),
                        'agent_display_name': s.get('agent_display_name', ''),
                        'created_at': s.get('created_at'),
                    })
            sessions.sort(key=lambda x: x.get('last_active_at') or datetime.min, reverse=True)
            return sessions

    @classmethod
    async def get_all_active_sessions(cls, minutes: int = 30) -> list:
        """
        获取所有活跃会话（用于 admin 在线监控）

        基于最后活跃时间判断在线状态，按用户聚合返回在线用户列表。

        Args:
            minutes: 活跃时间阈值（分钟），默认 30 分钟

        Returns:
            list: 在线用户列表，每项包含 user_id、username、session_count、last_active_at
        """
        from datetime import timedelta
        threshold = datetime.now() - timedelta(minutes=minutes)

        if cls.is_enabled():
            rows = await DatabasePool.fetch(
                """
                SELECT s.user_id, s.username, COUNT(*) as session_count, MAX(s.last_active_at) as last_active_at
                FROM sessions s
                WHERE s.last_active_at >= $1 AND s.status = 'active'
                GROUP BY s.user_id, s.username
                ORDER BY last_active_at DESC
                """,
                threshold
            )
            return [dict(row) for row in rows]

        # Memory 模式：从内存缓存中筛选
        with cls._lock:
            user_map = {}
            for sid, s in cls._memory_cache.items():
                if s.get('status', 'active') != 'active':
                    continue
                last_active = s.get('last_active_at', s.get('created_at'))
                if last_active and last_active >= threshold:
                    user_id = s.get('user_id')
                    username = s.get('username')
                    if user_id not in user_map:
                        user_map[user_id] = {
                            'user_id': user_id,
                            'username': username,
                            'session_count': 0,
                            'last_active_at': last_active
                        }
                    user_map[user_id]['session_count'] += 1
                    if last_active > user_map[user_id]['last_active_at']:
                        user_map[user_id]['last_active_at'] = last_active
            return sorted(user_map.values(), key=lambda x: x['last_active_at'], reverse=True)

    @classmethod
    async def search_sessions_by_username(cls, username: str) -> list:
        """
        按用户名搜索会话（admin 专用）

        支持模糊匹配用户名，返回匹配的会话列表。

        Args:
            username: 用户名关键字

        Returns:
            list: 会话列表，每项包含 session_id、username、title、last_active_at、status、agent_type、created_at
        """
        if cls.is_enabled():
            rows = await DatabasePool.fetch(
                """
                SELECT s.session_id, s.username, s.title, s.last_active_at, s.status, s.agent_type, s.agent_display_name, s.created_at
                FROM sessions s
                JOIN users u ON s.user_id = u.id
                WHERE u.username ILIKE $1
                ORDER BY s.last_active_at DESC
                """,
                f"%{username}%"
            )
            return [dict(row) for row in rows]

        # Memory 模式：需要从 UserDB 获取用户列表进行匹配
        from app.shared.utils.auth.user_db import UserDB
        users = await UserDB.list_users(limit=1000)
        matched_usernames = {u['username'] for u in users if username.lower() in u['username'].lower()}

        with cls._lock:
            sessions = []
            for sid, s in cls._memory_cache.items():
                if s.get('username') in matched_usernames:
                    sessions.append({
                        'session_id': sid,
                        'username': s.get('username'),
                        'title': s.get('title', '新对话'),
                        'last_active_at': s.get('last_active_at', s.get('created_at')),
                        'status': s.get('status', 'active'),
                        'agent_type': s.get('agent_type', 'default'),
                        'agent_display_name': s.get('agent_display_name', ''),
                        'created_at': s.get('created_at'),
                    })
            sessions.sort(key=lambda x: x.get('last_active_at') or datetime.min, reverse=True)
            return sessions

    @classmethod
    async def get_session_detail(cls, session_id: str) -> Optional[dict]:
        """
        获取会话详情（含附件列表）

        Args:
            session_id: 会话 ID

        Returns:
            Optional[dict]: 会话详情，包含基本信息和附件列表
        """
        session = await cls.get_session(session_id)
        if not session:
            return None

        detail = {
            **session,
            'session_id': session_id,
            'attachments': [],
        }

        # 查询附件列表
        if cls.is_enabled():
            rows = await DatabasePool.fetch(
                """
                SELECT id, file_name, stored_path, file_type, file_size, mime_type, file_id, created_at
                FROM attachments
                WHERE session_id = $1
                ORDER BY created_at
                """,
                session_id
            )
            detail['attachments'] = [dict(row) for row in rows]

        return detail