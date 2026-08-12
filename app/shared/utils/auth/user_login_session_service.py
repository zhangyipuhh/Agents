#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
用户登录会话服务（等保三级 §1.5，2026-08-12 新增）

提供"用户登录会话"维度的生命周期管理：
- 登录成功后创建会话记录，签发 session_uuid 写入 HttpOnly Cookie
- 每次成功请求刷新 last_active_at（idle 检测依据）
- 中间件校验 idle 超时，超时返回 401
- 登出/踢出时同步撤销

与既有 SessionDB 的区别：
- SessionDB 承载的是"对话会话"（conversations.session_id），用于聊天记录路由
- 本服务承载"用户登录会话"（user_login_sessions.session_uuid），用于 idle 自动退出

时间约束（2026-08-08 MFA bug 教训）：
- 写入 PG TIMESTAMP 朴素列时**必须**使用 datetime.utcnow()（naive datetime）
- 禁止使用 datetime.now(timezone.utc) 写入 naive 列，否则 asyncpg 抛 DataError
"""

import logging
import secrets
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from fastapi import Request

from app.core.database import DatabasePool

logger = logging.getLogger(__name__)


# ============================================================
# 用户登录会话数据库 / 内存存储
# ============================================================


class UserLoginSessionStore:
    """
    用户登录会话存储层

    - postgres 模式：读写 ``user_login_sessions`` 表（Naive TIMESTAMP）
    - memory 模式：进程内 ``_memory_sessions`` 字典（开发/测试用）

    两种模式均支持 idle 检测、撤销、并发踢出。
    """

    _memory_sessions: Dict[str, Dict[str, Any]] = {}
    _lock = threading.Lock()

    @classmethod
    def is_enabled(cls) -> bool:
        """检查是否启用数据库模式"""
        return DatabasePool.is_enabled()

    # -------- 内存模式辅助方法 --------

    @classmethod
    def _memory_put(cls, record: Dict[str, Any]) -> None:
        """
        写入内存模式会话记录（含默认值字段，便于 fetch 返回完整结构）。

        Args:
            record: 会话记录 dict。
        """
        # 补齐可选字段默认值，避免测试 / 调用方访问 None 字段时报 KeyError
        record.setdefault("ip_address", None)
        record.setdefault("user_agent", None)
        record.setdefault("revoked_at", None)
        record.setdefault("revoke_reason", None)
        with cls._lock:
            cls._memory_sessions[record["session_uuid"]] = record

    @classmethod
    def _memory_get(cls, session_uuid: str) -> Optional[Dict[str, Any]]:
        with cls._lock:
            rec = cls._memory_sessions.get(session_uuid)
            return dict(rec) if rec else None

    @classmethod
    def _memory_touch(cls, session_uuid: str, last_active_at: datetime) -> bool:
        with cls._lock:
            if session_uuid in cls._memory_sessions:
                cls._memory_sessions[session_uuid]["last_active_at"] = last_active_at
                return True
            return False

    @classmethod
    def _memory_revoke(cls, session_uuid: str, reason: str, revoked_at: datetime) -> bool:
        with cls._lock:
            rec = cls._memory_sessions.get(session_uuid)
            if not rec:
                return False
            rec["revoked_at"] = revoked_at
            rec["revoke_reason"] = reason
            return True

    @classmethod
    def _memory_revoke_user_except(
        cls, user_id: int, except_uuid: Optional[str], reason: str, revoked_at: datetime
    ) -> int:
        with cls._lock:
            count = 0
            for uuid, rec in list(cls._memory_sessions.items()):
                if rec.get("user_id") == user_id and uuid != except_uuid and not rec.get("revoked_at"):
                    rec["revoked_at"] = revoked_at
                    rec["revoke_reason"] = reason
                    count += 1
            return count

    # -------- postgres 操作 --------

    @classmethod
    async def insert(cls, record: Dict[str, Any]) -> None:
        """
        插入新会话记录。

        Args:
            record: 包含 ``session_uuid`` / ``user_id`` / ``username`` /
                ``login_at`` / ``last_active_at`` / ``expires_at`` /
                ``ip_address`` / ``user_agent`` 的字典。

        Raises:
            RuntimeError: 数据库写入失败时（fail-loud）。
        """
        if not cls.is_enabled():
            cls._memory_put(record)
            return
        try:
            await DatabasePool.execute(
                """
                INSERT INTO user_login_sessions (
                    session_uuid, user_id, username,
                    login_at, last_active_at, expires_at,
                    ip_address, user_agent
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (session_uuid) DO NOTHING
                """,
                record["session_uuid"],
                record["user_id"],
                record["username"],
                record["login_at"],
                record["last_active_at"],
                record["expires_at"],
                record.get("ip_address"),
                record.get("user_agent"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "[UserLoginSessionStore.insert] 写入失败 session_uuid=%s",
                record.get("session_uuid"),
            )
            raise RuntimeError(f"创建用户登录会话失败: {exc}") from exc

    @classmethod
    async def fetch(cls, session_uuid: str) -> Optional[Dict[str, Any]]:
        """
        查询会话记录。

        Args:
            session_uuid: 会话 UUID。

        Returns:
            Optional[dict]: 会话记录，未找到返回 None。

        Raises:
            RuntimeError: 数据库查询失败时（fail-loud）。
        """
        if not cls.is_enabled():
            return cls._memory_get(session_uuid)
        try:
            row = await DatabasePool.fetchrow(
                """
                SELECT session_uuid, user_id, username,
                       login_at, last_active_at, expires_at,
                       ip_address, user_agent, revoked_at, revoke_reason
                FROM user_login_sessions
                WHERE session_uuid = $1
                """,
                session_uuid,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "[UserLoginSessionStore.fetch] 查询失败 session_uuid=%s",
                session_uuid,
            )
            raise RuntimeError(f"查询用户登录会话失败: {exc}") from exc

        if not row:
            return None
        return dict(row)

    @classmethod
    async def touch(cls, session_uuid: str, last_active_at: datetime) -> bool:
        """
        刷新 ``last_active_at``。

        Args:
            session_uuid: 会话 UUID。
            last_active_at: 新的最后活跃时间（naive datetime）。

        Returns:
            bool: 找到且更新返回 True；未找到或已撤销返回 False。

        Raises:
            RuntimeError: 数据库写入失败时（fail-loud）。
        """
        if not cls.is_enabled():
            return cls._memory_touch(session_uuid, last_active_at)
        try:
            result = await DatabasePool.execute(
                """
                UPDATE user_login_sessions
                SET last_active_at = $2
                WHERE session_uuid = $1
                  AND revoked_at IS NULL
                  AND expires_at > $3
                """,
                session_uuid,
                last_active_at,
                last_active_at,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "[UserLoginSessionStore.touch] 更新失败 session_uuid=%s",
                session_uuid,
            )
            raise RuntimeError(f"刷新 last_active_at 失败: {exc}") from exc

        # asyncpg execute 返回 "UPDATE <n>"
        try:
            updated = int(str(result).split()[-1])
        except (ValueError, IndexError):
            updated = 0
        return updated > 0

    @classmethod
    async def revoke(
        cls, session_uuid: str, reason: str, revoked_at: datetime
    ) -> bool:
        """
        撤销会话。

        Args:
            session_uuid: 会话 UUID。
            reason: 撤销原因（``logout`` / ``idle`` / ``admin_revoke`` / ``replaced``）。
            revoked_at: 撤销时间（naive datetime）。

        Returns:
            bool: 撤销成功返回 True；未找到返回 False。

        Raises:
            RuntimeError: 数据库写入失败时（fail-loud）。
        """
        if not cls.is_enabled():
            return cls._memory_revoke(session_uuid, reason, revoked_at)
        try:
            result = await DatabasePool.execute(
                """
                UPDATE user_login_sessions
                SET revoked_at = $2, revoke_reason = $3
                WHERE session_uuid = $1 AND revoked_at IS NULL
                """,
                session_uuid,
                revoked_at,
                reason,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "[UserLoginSessionStore.revoke] 撤销失败 session_uuid=%s",
                session_uuid,
            )
            raise RuntimeError(f"撤销用户登录会话失败: {exc}") from exc

        try:
            updated = int(str(result).split()[-1])
        except (ValueError, IndexError):
            updated = 0
        return updated > 0

    @classmethod
    async def revoke_user_except(
        cls,
        user_id: int,
        except_uuid: Optional[str],
        reason: str,
        revoked_at: datetime,
    ) -> int:
        """
        撤销某用户的所有会话（排除 except_uuid）。

        Args:
            user_id: 用户 ID。
            except_uuid: 排除的会话 UUID（当前登录会话保留），可为 None。
            reason: 撤销原因。
            revoked_at: 撤销时间。

        Returns:
            int: 撤销的会话数量。

        Raises:
            RuntimeError: 数据库写入失败时（fail-loud）。
        """
        if not cls.is_enabled():
            return cls._memory_revoke_user_except(user_id, except_uuid, reason, revoked_at)
        try:
            if except_uuid:
                result = await DatabasePool.execute(
                    """
                    UPDATE user_login_sessions
                    SET revoked_at = $2, revoke_reason = $3
                    WHERE user_id = $1
                      AND session_uuid <> $4
                      AND revoked_at IS NULL
                    """,
                    user_id,
                    revoked_at,
                    reason,
                    except_uuid,
                )
            else:
                result = await DatabasePool.execute(
                    """
                    UPDATE user_login_sessions
                    SET revoked_at = $2, revoke_reason = $3
                    WHERE user_id = $1
                      AND revoked_at IS NULL
                    """,
                    user_id,
                    revoked_at,
                    reason,
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "[UserLoginSessionStore.revoke_user_except] 批量撤销失败 user_id=%s",
                user_id,
            )
            raise RuntimeError(f"批量撤销用户登录会话失败: {exc}") from exc

        try:
            updated = int(str(result).split()[-1])
        except (ValueError, IndexError):
            updated = 0
        return updated


# ============================================================
# 用户登录会话 Service（业务编排层）
# ============================================================


class UserLoginSessionService:
    """
    用户登录会话业务编排服务。

    职责：
    - create_login_session: 登录成功后创建会话
    - check_idle: 校验 idle 超时
    - touch_last_active: 刷新最后活跃时间（中间件异步调用）
    - revoke_session: 撤销单条会话
    - revoke_user_sessions: 批量撤销（同设备重新登录 / 并发会话限制）

    时间约束（2026-08-08 MFA bug 教训）：
    - 所有写入 PG TIMESTAMP 朴素列的时间必须使用 ``datetime.utcnow()``（naive）
    - 禁止使用 ``datetime.now(timezone.utc)``（aware），否则 asyncpg 抛 DataError
    """

    @staticmethod
    def _generate_session_uuid() -> str:
        """
        生成 64 字符 session_uuid。

        Returns:
            str: url-safe 随机字符串（43 字符 base64 + padding），足够熵。
        """
        return secrets.token_urlsafe(48)

    @staticmethod
    def _client_ip(request: Optional[Request]) -> Optional[str]:
        """从 FastAPI Request 提取客户端 IP。"""
        if not request or not request.client:
            return None
        return request.client.host

    @staticmethod
    def _user_agent(request: Optional[Request]) -> Optional[str]:
        """从 FastAPI Request 提取 User-Agent。"""
        if not request:
            return None
        return request.headers.get("user-agent")

    async def create_login_session(
        self,
        user_id: int,
        username: str,
        refresh_token_ttl_seconds: int,
        request: Optional[Request] = None,
    ) -> str:
        """
        创建用户登录会话。

        Args:
            user_id: 用户 ID。
            username: 用户名。
            refresh_token_ttl_seconds: Refresh Token TTL（秒），同步设置 expires_at。
            request: FastAPI Request，用于提取 IP / UA 审计信息。

        Returns:
            str: 新生成的 session_uuid（写入 HttpOnly Cookie）。

        Raises:
            ValueError: user_id / username 非法时。
            RuntimeError: 数据库写入失败时（fail-loud）。
        """
        if not user_id:
            raise ValueError("user_id 必须为非零整数")
        if not username:
            raise ValueError("username 不能为空")

        now = datetime.utcnow()  # naive datetime，匹配 PG TIMESTAMP 朴素列
        session_uuid = self._generate_session_uuid()
        record = {
            "session_uuid": session_uuid,
            "user_id": int(user_id),
            "username": username,
            "login_at": now,
            "last_active_at": now,
            "expires_at": now + timedelta(seconds=refresh_token_ttl_seconds),
            "ip_address": self._client_ip(request),
            "user_agent": self._user_agent(request),
        }
        await UserLoginSessionStore.insert(record)
        logger.info(
            "[UserLoginSessionService] 创建会话成功 user_id=%s session_uuid=%s",
            user_id,
            session_uuid[:12] + "***",
        )
        return session_uuid

    async def check_idle(
        self, session_uuid: str, idle_timeout_seconds: int
    ) -> Tuple[bool, Optional[datetime]]:
        """
        校验会话是否 idle 超时。

        Args:
            session_uuid: 会话 UUID。
            idle_timeout_seconds: idle 超时阈值（秒）。

        Returns:
            Tuple[is_expired, last_active_at]:
                - (True, last_active_at): 已超时（已撤销 / 已过期 / 超过 idle 阈值）
                - (False, last_active_at): 正常
                - (True, None): 会话不存在（视为过期）
        """
        if not session_uuid:
            return True, None

        record = await UserLoginSessionStore.fetch(session_uuid)
        if not record:
            return True, None

        now = datetime.utcnow()
        # 已撤销 / 已过期 → 视为 idle
        if record.get("revoked_at") is not None:
            return True, record.get("last_active_at")
        if record.get("expires_at") is not None and record["expires_at"] < now:
            return True, record.get("last_active_at")
        # idle 阈值
        last_active = record.get("last_active_at")
        if last_active is not None:
            age_seconds = (now - last_active).total_seconds()
            if age_seconds > idle_timeout_seconds:
                return True, last_active
        return False, last_active

    async def touch_last_active(self, session_uuid: str) -> bool:
        """
        刷新 ``last_active_at`` 为当前时间（naive datetime）。

        Args:
            session_uuid: 会话 UUID。

        Returns:
            bool: 找到且更新返回 True；未找到 / 已撤销 / 已过期返回 False。

        Raises:
            RuntimeError: 数据库写入失败时（fail-loud）。
        """
        if not session_uuid:
            return False
        return await UserLoginSessionStore.touch(
            session_uuid, datetime.utcnow()
        )

    async def revoke_session(self, session_uuid: str, reason: str) -> bool:
        """
        撤销单条会话。

        Args:
            session_uuid: 会话 UUID。
            reason: 撤销原因（``logout`` / ``idle`` / ``admin_revoke`` / ``replaced``）。

        Returns:
            bool: 撤销成功返回 True；未找到返回 False。

        Raises:
            RuntimeError: 数据库写入失败时（fail-loud）。
        """
        if not session_uuid:
            return False
        result = await UserLoginSessionStore.revoke(
            session_uuid, reason, datetime.utcnow()
        )
        if result:
            logger.info(
                "[UserLoginSessionService] 撤销会话 session_uuid=%s reason=%s",
                session_uuid[:12] + "***",
                reason,
            )
        return result

    async def revoke_user_sessions(
        self,
        user_id: int,
        except_session_uuid: Optional[str] = None,
        reason: str = "replaced",
    ) -> int:
        """
        批量撤销某用户的其他会话（并发会话限制 / 同设备重新登录场景）。

        Args:
            user_id: 用户 ID。
            except_session_uuid: 排除的会话 UUID（保留当前会话），可为 None。
            reason: 撤销原因。

        Returns:
            int: 撤销的会话数量。

        Raises:
            RuntimeError: 数据库写入失败时（fail-loud）。
        """
        if not user_id:
            return 0
        count = await UserLoginSessionStore.revoke_user_except(
            int(user_id),
            except_session_uuid,
            reason,
            datetime.utcnow(),
        )
        if count > 0:
            logger.info(
                "[UserLoginSessionService] 批量撤销会话 user_id=%s except=%s count=%s reason=%s",
                user_id,
                (except_session_uuid[:12] + "***") if except_session_uuid else None,
                count,
                reason,
            )
        return count


# 单例
user_login_session_service = UserLoginSessionService()
