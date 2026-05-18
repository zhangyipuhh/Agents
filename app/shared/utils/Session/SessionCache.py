#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
会话缓存模块

本模块提供会话缓存功能，支持两种模式：
- memory 模式：仅使用内存缓存
- postgres 模式：使用两级缓存（内存 + 数据库）

Date: 2026/2/6
Author: 张镒谱
"""
from datetime import datetime, timedelta
from typing import Dict, Optional
import threading

from app.shared.utils.auth.session_db import SessionDB
from app.shared.utils.Session.SessionCacheOriginal import session_cache_original


class SessionCache:
    """
    会话缓存类

    兼容层，将原有接口适配到新的 SessionDB 实现。
    当 AUTH_STORAGE_MODE=postgres 时，使用两级缓存。
    """

    def __init__(self):
        """
        初始化会话缓存

        使用字典存储 session_id 与用户名的映射。
        使用锁确保线程安全。
        """
        self._db = SessionDB()

    def add_session(self, session_id: str, username: str, user_id: int = 0):
        #print(f"[诊断-SessionCache] add_session: SessionDB.is_enabled()={SessionDB.is_enabled()}, session_id={session_id}, username={username}")
        if SessionDB.is_enabled():
            #print(f"[诊断-SessionCache] add_session: 使用数据库路径")
            import asyncio
            loop = asyncio.get_event_loop()
            loop.run_until_complete(
                self._db.add_session(session_id, user_id, username)
            )
        else:
            #print(f"[诊断-SessionCache] add_session: 使用内存路径")
            session_cache_original.add_session(session_id, username)

    def get_session(self, session_id: str) -> Optional[dict]:
        """
        获取会话信息

        Args:
            session_id (str): 会话ID

        Returns:
            Optional[dict]: 会话信息，如果不存在返回None
        """
        if SessionDB.is_enabled():
            import asyncio
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self._db.get_session(session_id))
        else:
            return session_cache_original.get_session(session_id)

    def verify_session(self, session_id: str, username: str) -> bool:
        #print(f"[诊断-SessionCache] verify_session: SessionDB.is_enabled()={SessionDB.is_enabled()}, session_id={session_id}, username={username}")
        if SessionDB.is_enabled():
            #print(f"[诊断-SessionCache] verify_session: 使用数据库路径")
            import asyncio
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self._db.verify_session(session_id, username))
        else:
            #print(f"[诊断-SessionCache] verify_session: 使用内存路径")
            return session_cache_original.verify_session(session_id, username)

    def delete_session(self, session_id: str) -> bool:
        """
        删除会话

        Args:
            session_id (str): 会话ID

        Returns:
            bool: 删除成功返回True，不存在返回False
        """
        if SessionDB.is_enabled():
            import asyncio
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self._db.delete_session(session_id))
        else:
            return session_cache_original.delete_session(session_id)

    def delete_user_sessions(self, user_id: int) -> int:
        """
        删除用户的所有 Session

        Args:
            user_id (int): 用户ID

        Returns:
            int: 删除的 session 数量
        """
        if SessionDB.is_enabled():
            import asyncio
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self._db.delete_user_sessions(user_id))
        return 0

    def clear_expired_sessions(self, hours: int = 24):
        """
        清除过期的会话

        Args:
            hours (int): 过期时间（小时），默认24小时
        """
        if not SessionDB.is_enabled():
            session_cache_original.clear_expired_sessions(hours)


# 创建全局会话缓存实例
session_cache = SessionCache()