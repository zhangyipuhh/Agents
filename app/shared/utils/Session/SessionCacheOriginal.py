"""
原始会话缓存模块

本模块是原有 SessionCache 的实现，保持不变以支持 memory 模式。

Date: 2026/2/6
Author: 张镒谱
"""
from datetime import datetime, timedelta
from typing import Dict, Optional
import threading


class SessionCacheOriginal:
    """会话缓存类"""

    def __init__(self):
        self._cache: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def add_session(self, session_id: str, username: str):
        """
        添加会话到缓存

        Args:
            session_id: 会话ID
            username: 用户名
        """
        with self._lock:
            self._cache[session_id] = {
                "username": username,
                "created_at": datetime.utcnow()
            }

    def get_session(self, session_id: str) -> Optional[dict]:
        """
        获取会话信息

        Args:
            session_id: 会话ID

        Returns:
            Optional[dict]: 会话信息，不存在返回None
        """
        with self._lock:
            return self._cache.get(session_id)

    def verify_session(self, session_id: str, username: str) -> bool:
        """
        验证会话是否属于指定用户

        Args:
            session_id: 会话ID
            username: 用户名

        Returns:
            bool: 如果会话属于该用户返回True，否则返回False
        """
        with self._lock:
            session_info = self._cache.get(session_id)
            if not session_info:
                return False
            return session_info["username"] == username

    def delete_session(self, session_id: str) -> bool:
        """
        删除会话

        Args:
            session_id: 会话ID

        Returns:
            bool: 删除成功返回True，不存在返回False
        """
        with self._lock:
            if session_id in self._cache:
                del self._cache[session_id]
                return True
            return False

    def clear_expired_sessions(self, hours: int = 24):
        """
        清除过期的会话

        Args:
            hours: 过期时间（小时），默认24小时
        """
        with self._lock:
            expired_time = datetime.utcnow() - timedelta(hours=hours)
            expired_sessions = [
                session_id
                for session_id, info in self._cache.items()
                if info["created_at"] < expired_time
            ]
            for session_id in expired_sessions:
                del self._cache[session_id]


session_cache_original = SessionCacheOriginal()