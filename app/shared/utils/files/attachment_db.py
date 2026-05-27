#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
附件数据库操作模块

提供附件记录的增删查功能，附件与会话（session）关联。
附件的文件实体存储在文件系统 upload_dir/{session_id}/ 目录，
本模块仅管理附件的元数据记录。

表结构通过 @register_schema 装饰器自动注册，启动时统一初始化。

Date: 2026-05-27
Author: AI Assistant
"""
from typing import Optional, List
from datetime import datetime
from app.core.database import DatabasePool


class AttachmentDB:
    """
    附件数据库操作类

    管理附件元数据记录，包括添加、查询、删除操作。
    附件与会话通过 session_id 关联（1对多关系）。
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
    async def add_attachment(
        cls,
        session_id: str,
        file_name: str,
        stored_path: str,
        file_type: str,
        file_size: int = 0,
        mime_type: Optional[str] = None,
        file_id: Optional[str] = None,
    ) -> Optional[int]:
        """
        添加附件记录

        Args:
            session_id: 会话 ID
            file_name: 原始文件名
            stored_path: 服务器存储路径
            file_type: 文件类型（'doc' | 'img' | 'scan'）
            file_size: 文件大小（字节）
            mime_type: MIME 类型
            file_id: 上传时的 file_id

        Returns:
            Optional[int]: 新增记录的 ID，未启用数据库时返回 None

        Raises:
            RuntimeError: 数据库连接池未初始化
        """
        if not cls.is_enabled():
            return None

        row = await DatabasePool.fetchrow(
            """
            INSERT INTO attachments (session_id, file_name, stored_path, file_type, file_size, mime_type, file_id, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
            """,
            session_id,
            file_name,
            stored_path,
            file_type,
            file_size,
            mime_type,
            file_id,
            datetime.utcnow(),
        )
        return row['id'] if row else None

    @classmethod
    async def get_session_attachments(cls, session_id: str) -> List[dict]:
        """
        获取会话的所有附件

        Args:
            session_id: 会话 ID

        Returns:
            List[dict]: 附件列表，每项包含 id、file_name、stored_path、file_type、file_size、mime_type、file_id、created_at
        """
        if not cls.is_enabled():
            return []

        rows = await DatabasePool.fetch(
            """
            SELECT id, file_name, stored_path, file_type, file_size, mime_type, file_id, created_at
            FROM attachments
            WHERE session_id = $1
            ORDER BY created_at
            """,
            session_id,
        )
        return [dict(row) for row in rows]

    @classmethod
    async def get_attachment(cls, attachment_id: int) -> Optional[dict]:
        """
        获取单个附件记录

        Args:
            attachment_id: 附件 ID

        Returns:
            Optional[dict]: 附件信息，不存在返回 None
        """
        if not cls.is_enabled():
            return None

        row = await DatabasePool.fetchrow(
            """
            SELECT id, session_id, file_name, stored_path, file_type, file_size, mime_type, file_id, created_at
            FROM attachments
            WHERE id = $1
            """,
            attachment_id,
        )
        return dict(row) if row else None

    @classmethod
    async def delete_attachment(cls, attachment_id: int) -> bool:
        """
        删除单个附件记录

        Args:
            attachment_id: 附件 ID

        Returns:
            bool: 删除成功返回 True
        """
        if not cls.is_enabled():
            return False

        await DatabasePool.execute(
            "DELETE FROM attachments WHERE id = $1",
            attachment_id,
        )
        return True

    @classmethod
    async def delete_session_attachments(cls, session_id: str) -> int:
        """
        删除会话的所有附件记录

        Args:
            session_id: 会话 ID

        Returns:
            int: 删除的附件数量
        """
        if not cls.is_enabled():
            return 0

        result = await DatabasePool.fetch(
            "DELETE FROM attachments WHERE session_id = $1 RETURNING id",
            session_id,
        )
        return len(result)
