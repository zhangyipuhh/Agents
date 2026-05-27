#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
对话记录数据库操作模块

提供对话记录的增删查功能，对话记录与会话（session）关联。
对话记录作为 LangGraph checkpoint 的冗余备份，支持快速查询和降级恢复。

表结构通过 @register_schema 装饰器自动注册（在 session_db.py 的 init_session_schema 中），
启动时统一初始化。

Date: 2026-05-27
Author: AI Assistant
"""
import json
from typing import Optional, List
from datetime import datetime
from app.core.database import DatabasePool


class ConversationDB:
    """
    对话记录数据库操作类

    管理对话记录的增删查操作，对话记录与会话通过 session_id 关联（1对多关系）。
    作为 LangGraph checkpoint 的冗余备份，支持快速查询和降级恢复。
    """

    @classmethod
    def is_enabled(cls) -> bool:
        """
        检查是否启用数据库模式

        Returns:
            bool: AUTH_STORAGE_MODE=postgres 时返回 True
        """
        return DatabasePool.is_enabled()

    @classmethod
    async def add_record(
        cls,
        session_id: str,
        role: str,
        content: Optional[str] = None,
        tool_calls: Optional[list] = None,
        tool_call_id: Optional[str] = None,
    ) -> Optional[int]:
        """
        添加对话记录

        Args:
            session_id: 会话 ID
            role: 消息角色（'user' | 'assistant' | 'system' | 'tool'）
            content: 消息内容
            tool_calls: 工具调用信息列表（将序列化为 JSONB）
            tool_call_id: 工具调用 ID

        Returns:
            Optional[int]: 新增记录的 ID，未启用数据库时返回 None

        Raises:
            RuntimeError: 数据库连接池未初始化
        """
        if not cls.is_enabled():
            return None

        tool_calls_json = json.dumps(tool_calls) if tool_calls else None

        row = await DatabasePool.fetchrow(
            """
            INSERT INTO conversation_records (session_id, role, content, tool_calls, tool_call_id, created_at)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6)
            RETURNING id
            """,
            session_id,
            role,
            content,
            tool_calls_json,
            tool_call_id,
            datetime.utcnow(),
        )
        return row['id'] if row else None

    @classmethod
    async def add_records_batch(cls, session_id: str, records: List[dict]) -> int:
        """
        批量添加对话记录

        Args:
            session_id: 会话 ID
            records: 对话记录列表，每项包含 role、content、tool_calls、tool_call_id

        Returns:
            int: 成功插入的记录数
        """
        if not cls.is_enabled() or not records:
            return 0

        count = 0
        for record in records:
            tool_calls_json = json.dumps(record.get('tool_calls')) if record.get('tool_calls') else None
            await DatabasePool.execute(
                """
                INSERT INTO conversation_records (session_id, role, content, tool_calls, tool_call_id, created_at)
                VALUES ($1, $2, $3, $4::jsonb, $5, $6)
                """,
                session_id,
                record.get('role'),
                record.get('content'),
                tool_calls_json,
                record.get('tool_call_id'),
                record.get('created_at', datetime.utcnow()),
            )
            count += 1
        return count

    @classmethod
    async def get_session_records(cls, session_id: str) -> List[dict]:
        """
        获取会话的所有对话记录

        Args:
            session_id: 会话 ID

        Returns:
            List[dict]: 对话记录列表，按创建时间排序，每项包含 id、role、content、tool_calls、tool_call_id、created_at
        """
        if not cls.is_enabled():
            return []

        rows = await DatabasePool.fetch(
            """
            SELECT id, role, content, tool_calls, tool_call_id, created_at
            FROM conversation_records
            WHERE session_id = $1
            ORDER BY created_at
            """,
            session_id,
        )
        result = []
        for row in rows:
            record = dict(row)
            # 将 JSONB 转为 Python 对象
            if record.get('tool_calls') and isinstance(record['tool_calls'], str):
                record['tool_calls'] = json.loads(record['tool_calls'])
            result.append(record)
        return result

    @classmethod
    async def delete_session_records(cls, session_id: str) -> int:
        """
        删除会话的所有对话记录

        Args:
            session_id: 会话 ID

        Returns:
            int: 删除的记录数量
        """
        if not cls.is_enabled():
            return 0

        result = await DatabasePool.fetch(
            "DELETE FROM conversation_records WHERE session_id = $1 RETURNING id",
            session_id,
        )
        return len(result)

    @classmethod
    async def get_first_user_message(cls, session_id: str) -> Optional[str]:
        """
        获取会话中第一条用户消息内容（用于自动生成标题）

        Args:
            session_id: 会话 ID

        Returns:
            Optional[str]: 第一条用户消息内容，不存在返回 None
        """
        if not cls.is_enabled():
            return None

        row = await DatabasePool.fetchrow(
            """
            SELECT content
            FROM conversation_records
            WHERE session_id = $1 AND role = 'user'
            ORDER BY created_at
            LIMIT 1
            """,
            session_id,
        )
        return row['content'] if row else None
