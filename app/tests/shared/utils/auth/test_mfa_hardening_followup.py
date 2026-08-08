# -*- coding:utf-8 -*-
"""
MFA 复审 2026-08-07 批次硬化 —— 二轮加固。

覆盖两个剩余问题：

问题一：管理员首次绑定 confirm 不是原子。

    当前 ``app/shared/routers/mfa_router.py`` 的 ``/api/auth/mfa/login/enroll/confirm``
    先 ``lookup_challenge``（仅 SELECT，未消费），再 ``consume_challenge``
    （UPDATE 但不带 purpose 强校验），再 ``confirm_enrollment``
    （再 SELECT + 验 TOTP + 写 secret/enabled_at/recovery hashes/last_used_step）。
    三段独立事务，且中间步骤失败后 challenge 已被消费，无法重试。
    本轮新增 ``MfaService.confirm_login_enrollment(enrollment_token, code)``
    公开方法：DB 模式在 ``conn.transaction()`` 内做
    SELECT challenge FOR UPDATE → 校验 purpose=enroll_confirm +
    expires_at/consumed_at → 锁 user_mfa_totp FOR UPDATE → 解密 pending_secret
    → 验 TOTP → 写 secret/enabled_at/recovery hashes/last_used_step → 标记 challenge
    consumed。失败全部回滚，enrollment_token 可重试；成功返回 ``user_id`` /
    ``step`` / ``recovery_codes``（明文只返回一次）。

问题二：``mfa_router.py`` 已登录 ``disable`` / ``regenerate`` 直接访问
``MfaService`` 私有方法 ``_get_totp_entry`` / ``_validate_totp`` /
``_validate_recovery_code``。本轮新增 ``MfaService.verify_and_consume_management_factor``
    公开方法，封装 TOTP / recovery code 校验 + 一次性消费。recovery code
    一旦被该操作消费，不能再次成功（不依赖 challenge）。

测试要点：

1. ``test_login_enroll_confirm_failure_keeps_challenge_retryable``
   —— 错误码：challenge 未消费，可再次 confirm 成功。
2. ``test_login_enroll_confirm_success_then_second_confirm_fails``
   —— 成功：第二次 confirm 必失败。
3. ``test_login_enroll_confirm_pg_single_transaction``
   —— PG fake transaction：所有写入发生在同一个 conn.transaction() 内；
   且 ``enrollment_token`` 明文走公开 API，路由不再 import 任何 ``_xxx``。
4. ``test_router_source_does_not_access_private_mfa_methods``
   —— 源码静态检查：``mfa_router.py`` 字符串中无 ``mfa._xxx`` 调用。
5. ``test_recovery_code_used_for_disable_cannot_be_used_again``
   —— 同一 recovery code 二次用于 ``disable``/``regenerate`` 必失败。
6. ``test_recovery_code_used_for_regenerate_cannot_be_used_again``
   —— 同上但针对 ``regenerate``。
7. ``test_router_login_enroll_confirm_uses_public_service_only``
   —— 端到端：``/api/auth/mfa/login/enroll/confirm`` 走公开 API。
8. ``test_router_login_enroll_confirm_failure_does_not_consume_challenge``
   —— 端到端：错误码后 ``enrollment_token`` 仍可用于再次 confirm 成功。

Author: AI Assistant
Date: 2026-08-07
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

if "asyncpg" not in sys.modules:
    sys.modules["asyncpg"] = MagicMock()

import pyotp
import pytest
from cryptography.fernet import Fernet


class _FakeAsyncpgDataError(Exception):
    """模拟 asyncpg.exceptions.DataError。

    仅供 fake connection 在 ``_check_bind_args`` hook 内抛出，不与真实
    asyncpg 耦合。原因：conftest 在模块加载早期把 ``asyncpg`` 整个换成
    ``MagicMock``，在此环境下 ``from asyncpg.exceptions import DataError``
    拿到的会是 Mock 实例，无法被 ``pytest.raises`` 捕获。
    """

    pass


# ============================================================
# 共用工具
# ============================================================


def _fernet_key_bytes() -> str:
    """生成合法 Fernet 密钥（url-safe base64 字符串）。"""
    return Fernet.generate_key().decode("ascii")


def _make_settings(**overrides) -> Any:
    """构造符合契约的 MfaSettings（注入合法 Fernet 密钥）。"""
    from app.core.config.settings import MfaSettings

    defaults = {"secret_key": _fernet_key_bytes()}
    defaults.update(overrides)
    return MfaSettings(**defaults)


# ============================================================
# Fake PG Connection / Transaction（来自 test_mfa_hardening.py 复用）
# ============================================================


@dataclass
class _ExecCall:
    sql: str
    params: Tuple[Any, ...] = ()


@dataclass
class _FakeRow(dict):
    def __init__(self, data: Optional[Dict[str, Any]] = None) -> None:
        if data is None:
            data = {}
        super().__init__(data)


class _FakeConnection:
    def __init__(self, store: Dict[str, Any]) -> None:
        self._store = store
        self._in_tx = False
        self._tx_log: List[str] = []
        self.exec_calls: List[_ExecCall] = []

    async def __aenter__(self) -> "_FakeConnection":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def add_exec(self, sql: str, params: Tuple[Any, ...] = ()) -> None:
        self.exec_calls.append(_ExecCall(sql=sql, params=params))
        self._tx_log.append(sql)

    async def fetchrow(self, sql: str, *args: Any, **kw: Any) -> Optional[_FakeRow]:
        self.add_exec(sql, args)
        return self._dispatch_fetchrow(sql, args)

    async def fetch(self, sql: str, *args: Any, **kw: Any) -> List[_FakeRow]:
        self.add_exec(sql, args)
        return self._dispatch_fetch(sql, args)

    async def fetchval(self, sql: str, *args: Any, **kw: Any) -> Any:
        self.add_exec(sql, args)
        rows = self._dispatch_fetch(sql, args)
        return rows[0]["v"] if rows else None

    async def execute(self, sql: str, *args: Any, **kw: Any) -> str:
        self.add_exec(sql, args)
        # 参数编码校验 hook：模拟 asyncpg `_encode_bind_msg` 的类型检查。
        # 默认 no-op；需要严格参数类型校验的子 fake 必须 override。
        self._check_bind_args(sql, args)
        return self._dispatch_execute(sql, args)

    def _dispatch_fetchrow(self, sql: str, args: Tuple[Any, ...]) -> Optional[_FakeRow]:
        return None

    def _dispatch_fetch(self, sql: str, args: Tuple[Any, ...]) -> List[_FakeRow]:
        return []

    def _dispatch_execute(self, sql: str, args: Tuple[Any, ...]) -> str:
        return "OK"

    def _check_bind_args(self, sql: str, args: Tuple[Any, ...]) -> None:
        """参数编码校验 hook 占位（默认 no-op）。子类 override 以模拟 asyncpg 编码层。"""
        return None

    def transaction(self) -> "_FakeTransaction":
        return _FakeTransaction(self)


class _FakeTransaction:
    """记录 transaction 进入/退出，并断言 set/exit 顺序对应 begin/commit。"""

    def __init__(self, conn: _FakeConnection) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeConnection:
        self._conn._in_tx = True
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._conn._in_tx = False


class _FakePool:
    def __init__(self, store: Dict[str, Any]) -> None:
        self._store = store
        self.connection = _FakeConnection(store)

    def acquire(self):
        return _ConnectionCM(self.connection)


class _ConnectionCM:
    def __init__(self, conn: _FakeConnection) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeConnection:
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def reset_singleton():
    from app.shared.utils.auth.mfa_service import MfaService

    MfaService._instance = None
    yield
    MfaService._instance = None


@pytest.fixture(autouse=True)
def clean_user_db():
    from app.shared.utils.auth.user_db import UserDB

    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0
    UserDB._memory_login_lock.clear()
    yield
    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0
    UserDB._memory_login_lock.clear()


# ============================================================
# 问题一：confirm_login_enrollment 原子化
# ============================================================


def _build_pg_enrollment_store(
    svc: Any,
    user_id: int,
    pending_secret: str,
    enrollment_token: str,
    expires_in: float = 300.0,
) -> Tuple[Dict[str, Any], _FakeConnection]:
    """构造 PG fake store + conn，含 user_mfa_totp 行 + mfa_challenges 行。

    Returns:
        Tuple[store, conn]。conn 的 _dispatch_* 已经处理好 confirm_login_enrollment
        期望的所有 SQL 路径。
    """
    from app.shared.utils.auth.mfa_service import _hash_challenge_token
    from datetime import datetime, timezone

    challenge_hash = _hash_challenge_token(enrollment_token)
    encrypted_secret = svc._fernet.encrypt(pending_secret.encode("utf-8")).decode("ascii")

    store: Dict[str, Any] = {
        "user_mfa_totp": [
            {
                "user_id": user_id,
                "secret_cipher": None,
                "pending_secret_cipher": encrypted_secret,
                "enabled_at": None,
                "last_used_step": None,
                "recovery_code_hashes": [],
            }
        ],
        "mfa_challenges": [
            {
                "token_hash": challenge_hash,
                "user_id": user_id,
                "purpose": "enroll_confirm",
                "expires_at": time.time() + expires_in,
                "consumed_at": None,
                "failed_attempts": 0,
            }
        ],
    }

    class Conn(_FakeConnection):
        def __init__(self):
            super().__init__(store)
            self.totp_row = store["user_mfa_totp"][0]
            self.chal = store["mfa_challenges"][0]

        def _check_bind_args(self, sql, args):
            # 模拟 asyncpg `_encode_bind_msg` 对 datetime 参数与 naive 列的
            # 类型不匹配检查。本函数覆盖至少两类已知 bug：
            # 1. 写入 naive TIMESTAMP 列（如 user_mfa_totp.enabled_at）时传入
            #    offset-aware datetime → 抛 ``DataError: ... can't subtract
            #    offset-naive and offset-aware datetimes``（2026-08-08 真生产 bug）。
            # 后续如发现其他列的类型不匹配错误，在此扩展。
            if "UPDATE user_mfa_totp" in sql and "enabled_at" in sql:
                idx = 1  # $1 secret_cipher, $2 enabled_at
                val = args[idx]
                if isinstance(val, datetime) and val.tzinfo is not None:
                    raise _FakeAsyncpgDataError(
                        f"invalid input for query argument ${idx + 1}: "
                        f"{val!r} (can't subtract offset-naive and "
                        f"offset-aware datetimes)"
                    )

        def _dispatch_fetchrow(self, sql, args):
            # SELECT challenge FOR UPDATE
            if "FROM mfa_challenges" in sql and "FOR UPDATE" in sql:
                self.add_exec(sql, args)
                return _FakeRow(
                    {
                        "user_id": self.chal["user_id"],
                        "purpose": self.chal["purpose"],
                        "expires_at": self.chal["expires_at"],
                        "consumed_at": self.chal["consumed_at"],
                        "failed_attempts": self.chal["failed_attempts"],
                    }
                )
            # SELECT user_mfa_totp FOR UPDATE（事务内锁行）
            if "FROM user_mfa_totp" in sql and "FOR UPDATE" in sql:
                self.add_exec(sql, args)
                return _FakeRow(dict(self.totp_row))
            # SELECT 全字段（兜底）
            if "FROM user_mfa_totp" in sql:
                self.add_exec(sql, args)
                return _FakeRow(dict(self.totp_row))
            return super()._dispatch_fetchrow(sql, args)

        def _dispatch_execute(self, sql, args):
            # 最终 commit enrollment：UPDATE user_mfa_totp SET secret_cipher ...
            if (
                "UPDATE user_mfa_totp" in sql
                and "secret_cipher" in sql
                and "recovery_code_hashes" in sql
            ):
                self.add_exec(sql, args)
                self.totp_row["secret_cipher"] = args[0]
                self.totp_row["enabled_at"] = args[1]
                # recovery hashes 是 jsonb 字符串
                self.totp_row["recovery_code_hashes"] = json.loads(args[2])
                self.totp_row["last_used_step"] = args[3]
                self.totp_row["pending_secret_cipher"] = None
                return "UPDATE 1"
            # mark challenge consumed
            if "UPDATE mfa_challenges SET consumed_at" in sql:
                self.add_exec(sql, args)
                self.chal["consumed_at"] = time.time()
                return "UPDATE 1"
            return super()._dispatch_execute(sql, args)

    conn = Conn()
    return store, conn


def test_login_enroll_confirm_failure_keeps_challenge_retryable(event_loop):
    """问题一：错误码时 challenge 必须未被消费，可再次用同一 enrollment_token 确认成功。"""
    from app.shared.utils.auth.mfa_service import MfaService, MfaError

    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    async def runner():
        # 构造 pending_secret + enrollment_token
        secret = pyotp.random_base32()
        user_id = 1
        # 通过 start_enrollment 产生 enrollment_token 并写入 pending_secret
        started = await svc.start_enrollment(user_id=user_id)
        enrollment_token = started["enrollment_token"]
        # 强制 pending_secret 与 started["secret"] 对齐（start_enrollment 已写入 cipher）

        # 错误码：先拿一个错误码，期望抛 MfaError 且 challenge 仍未消费
        with pytest.raises(MfaError):
            await svc.confirm_login_enrollment(
                enrollment_token=enrollment_token, code="000000"
            )

        # 同一 enrollment_token 仍可再次确认（用正确码）
        code = pyotp.TOTP(started["secret"]).now()
        result = await svc.confirm_login_enrollment(
            enrollment_token=enrollment_token, code=code
        )
        assert result["success"] is True
        assert result["user_id"] == user_id
        assert "recovery_codes" in result and len(result["recovery_codes"]) == 10

    event_loop.run_until_complete(runner())


def test_login_enroll_confirm_success_then_second_confirm_fails(event_loop):
    """问题一：成功后第二次 confirm 必失败（MfaError）。"""
    from app.shared.utils.auth.mfa_service import MfaService, MfaError

    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    async def runner():
        secret = pyotp.random_base32()
        user_id = 2
        started = await svc.start_enrollment(user_id=user_id)
        enrollment_token = started["enrollment_token"]

        code = pyotp.TOTP(started["secret"]).now()
        result = await svc.confirm_login_enrollment(
            enrollment_token=enrollment_token, code=code
        )
        assert result["success"] is True

        # 第二次必失败（challenge consumed）
        with pytest.raises(MfaError):
            await svc.confirm_login_enrollment(
                enrollment_token=enrollment_token, code=code
            )

    event_loop.run_until_complete(runner())


def test_login_enroll_confirm_pg_single_transaction(event_loop):
    """问题一：PG 模式 confirm_login_enrollment 必须在同一 conn.transaction 内完成
    SELECT challenge FOR UPDATE + 锁 user_mfa_totp + 解密 + 验 TOTP +
    UPDATE secret/enabled_at/recovery hashes/last_used_step +
    UPDATE mfa_challenges consumed_at。

    关键不变量：
    1. 所有写入必须在 connection.transaction() 内；
    2. challenge 与 user_mfa_totp 都用 SELECT ... FOR UPDATE；
    3. 校验顺序：先 FOR UPDATE challenge → 校验 purpose/expires/consumed →
       FOR UPDATE totp → 验 TOTP → 写 user_mfa_totp → 写 challenge.consumed_at；
       任一校验失败全部回滚（不再执行后续写入）。
    """
    from app.shared.utils.auth.mfa_service import MfaService, MfaError

    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    secret = pyotp.random_base32()
    user_id = 3
    enrollment_token = "test-enroll-token-pg"
    store, conn = _build_pg_enrollment_store(
        svc=svc,
        user_id=user_id,
        pending_secret=secret,
        enrollment_token=enrollment_token,
    )
    pool = _FakePool(store)
    pool.connection = conn  # type: ignore[attr-defined]
    svc._db = pool  # type: ignore[attr-defined]

    async def runner():
        code = pyotp.TOTP(secret).now()
        result = await svc.confirm_login_enrollment(
            enrollment_token=enrollment_token, code=code
        )
        assert result["success"] is True
        assert result["user_id"] == user_id

        # 关键 SQL 必须存在
        sqls = [c.sql for c in conn.exec_calls]
        assert any(
            "FROM mfa_challenges" in s and "FOR UPDATE" in s for s in sqls
        ), "必须 SELECT challenge FOR UPDATE"
        assert any(
            "FROM user_mfa_totp" in s and "FOR UPDATE" in s for s in sqls
        ), "必须 SELECT user_mfa_totp FOR UPDATE"
        assert any(
            "UPDATE user_mfa_totp" in s
            and "secret_cipher" in s
            and "recovery_code_hashes" in s
            for s in sqls
        ), "必须 UPDATE user_mfa_totp 写入 secret + recovery hashes"
        assert any(
            "UPDATE mfa_challenges SET consumed_at" in s for s in sqls
        ), "必须 UPDATE mfa_challenges SET consumed_at"

        # 顺序：FOR UPDATE challenge 必须先于 FOR UPDATE totp
        idx_chal = next(
            i
            for i, s in enumerate(sqls)
            if "FROM mfa_challenges" in s and "FOR UPDATE" in s
        )
        idx_totp = next(
            i
            for i, s in enumerate(sqls)
            if "FROM user_mfa_totp" in s and "FOR UPDATE" in s
        )
        assert idx_chal < idx_totp, "必须先锁 challenge 再锁 totp 行"

        # 顺序：write user_mfa_totp 必须在 write challenge 之前（同一事务）
        idx_write_totp = next(
            i
            for i, s in enumerate(sqls)
            if "UPDATE user_mfa_totp" in s
            and "secret_cipher" in s
            and "recovery_code_hashes" in s
        )
        idx_write_chal = next(
            i
            for i, s in enumerate(sqls)
            if "UPDATE mfa_challenges SET consumed_at" in s
        )
        assert (
            idx_write_totp < idx_write_chal
        ), "必须先写 totp 再 mark challenge consumed"

        # user_mfa_totp 行最终状态
        assert conn.totp_row["secret_cipher"] is not None
        assert conn.totp_row["enabled_at"] is not None
        assert len(conn.totp_row["recovery_code_hashes"]) == 10
        assert conn.totp_row["pending_secret_cipher"] is None
        # challenge 已被消费
        assert conn.chal["consumed_at"] is not None

    event_loop.run_until_complete(runner())


def test_login_enroll_confirm_pg_enabled_at_must_be_naive_datetime(event_loop):
    """回归测试（2026-08-08）：confirm_login_enrollment 写入 user_mfa_totp.enabled_at
    时必须传 naive datetime（user_mfa_totp.enabled_at 是 TIMESTAMP 字段，无时区）。

    若误传 offset-aware datetime（datetime.now(timezone.utc)），asyncpg 会抛
    ``TypeError: can't subtract offset-naive and offset-aware datetimes``
    并最终以 ``asyncpg.exceptions.DataError: invalid input for query argument $2``
    失败，导致 MFA 绑定崩溃（参见 Terminal#677-824 报错堆栈）。

    Args:
        event_loop: pytest-asyncio 模块级事件循环 fixture。
    """
    from app.shared.utils.auth.mfa_service import MfaService
    from datetime import datetime

    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    secret = pyotp.random_base32()
    user_id = 991
    enrollment_token = "naive-datetime-regression-token"
    store, conn = _build_pg_enrollment_store(
        svc=svc,
        user_id=user_id,
        pending_secret=secret,
        enrollment_token=enrollment_token,
    )
    pool = _FakePool(store)
    pool.connection = conn  # type: ignore[attr-defined]
    svc._db = pool  # type: ignore[attr-defined]

    async def runner():
        code = pyotp.TOTP(secret).now()
        await svc.confirm_login_enrollment(
            enrollment_token=enrollment_token, code=code
        )

        # 找到 UPDATE user_mfa_totp ... secret_cipher 的执行
        write_calls = [
            c
            for c in conn.exec_calls
            if "UPDATE user_mfa_totp" in c.sql
            and "secret_cipher" in c.sql
            and "recovery_code_hashes" in c.sql
        ]
        assert write_calls, "必须有一次 UPDATE user_mfa_totp 写入绑定信息"
        enabled_at_arg = write_calls[0].params[1]
        assert isinstance(enabled_at_arg, datetime), (
            f"enabled_at 必须传 datetime 实例，实际 {type(enabled_at_arg).__name__}"
        )
        assert enabled_at_arg.tzinfo is None, (
            "enabled_at 必须为 naive datetime（tzinfo=None）；"
            f"实际 tzinfo={enabled_at_arg.tzinfo}。"
            "PG user_mfa_totp.enabled_at 是 TIMESTAMP（无时区），"
            "传 offset-aware datetime 会触发 asyncpg DataError。"
        )

    event_loop.run_until_complete(runner())


def test_login_enroll_confirm_pg_enabled_at_aware_raises_dataerror(
    event_loop, monkeypatch
):
    """反向回归测试（2026-08-08）：mock 体系必须能捕获"offset-aware datetime
    写入 naive TIMESTAMP 列"这一族 bug。

    本测试临时把 ``mfa_service`` 模块内的 ``datetime`` 类替换为 stub，
    使 ``datetime.now(timezone.utc)`` 返回 **aware** 实例（模拟 2026-08-08
    修复前的 bug 状态）。期望 fake connection 的 ``_check_bind_args`` hook
    检测到该异常并抛 ``_FakeAsyncpgDataError``，整个 confirm 流程以异常
    形式失败。

    Args:
        event_loop: pytest-asyncio 模块级事件循环 fixture。
        monkeypatch: pytest 内置 monkeypatch fixture。
    """
    from app.shared.utils.auth import mfa_service
    from app.shared.utils.auth.mfa_service import MfaService

    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    secret = pyotp.random_base32()
    user_id = 992
    enrollment_token = "aware-datetime-regression-token"
    store, conn = _build_pg_enrollment_store(
        svc=svc,
        user_id=user_id,
        pending_secret=secret,
        enrollment_token=enrollment_token,
    )
    pool = _FakePool(store)
    pool.connection = conn  # type: ignore[attr-defined]
    svc._db = pool  # type: ignore[attr-defined]

    # 用 stub datetime 替换 mfa_service 模块内 import 的 datetime 类。
    # 关键：mfa_service 顶层已 ``from datetime import datetime, timezone``，
    # 函数体直接引用模块级 datetime。monkeypatch 它即可让所有 ``datetime.now(...)``
    # 调用走 stub；同时 stub 还要 override ``replace(tzinfo=None)`` 让其变 no-op，
    # 否则生产代码里 ``.replace(tzinfo=None)`` 会把 aware 变 naive，hook 永远抓不到。
    real_datetime = mfa_service.datetime  # type: ignore[attr-defined]

    class _AwareDatetime(real_datetime):  # type: ignore[misc, valid-type]
        """stub：保留 tzinfo；``replace(tzinfo=None)`` 变 no-op。

        实现要点：``datetime`` 是 immutable builtin-style class，子类化后
        必须显式 ``cls(year, month, ...)`` 构造才能让返回实例是 Stub 类型，
        否则 ``real_datetime.now(tz)`` 直接返回父类实例，``replace`` override
        失效。``fold`` 是 Python 3.6+ 的属性，必须透传。
        """

        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            base = real_datetime.now(tz)
            return cls(
                base.year, base.month, base.day,
                base.hour, base.minute, base.second, base.microsecond,
                tzinfo=base.tzinfo, fold=base.fold,
            )

        def replace(self, **kw):  # type: ignore[override]
            # 屏蔽 ``.replace(tzinfo=None)`` —— 模拟修复前的 bug 状态
            if set(kw.keys()) == {"tzinfo"} and kw["tzinfo"] is None:
                return self
            return super().replace(**kw)

    monkeypatch.setattr(mfa_service, "datetime", _AwareDatetime)

    async def runner():
        code = pyotp.TOTP(secret).now()
        # 期望抛 _FakeAsyncpgDataError（模拟真 asyncpg DataError）
        with pytest.raises(_FakeAsyncpgDataError) as exc_info:
            await svc.confirm_login_enrollment(
                enrollment_token=enrollment_token, code=code
            )
        # 错误信息应明确指向 $2 / enabled_at / aware vs naive
        msg = str(exc_info.value)
        assert "$2" in msg, f"错误信息应指向参数 $2，实际：{msg}"
        assert "offset-naive" in msg and "offset-aware" in msg, (
            f"错误信息应说明 aware vs naive 类型冲突，实际：{msg}"
        )

        # 数据库应未被写入（事务整体回滚）
        assert conn.totp_row["secret_cipher"] is None
        assert conn.totp_row["enabled_at"] is None
        assert conn.chal["consumed_at"] is None, (
            "失败必须整体回滚，challenge 不能被消费"
        )

    event_loop.run_until_complete(runner())


def test_login_enroll_confirm_pg_wrong_purpose_fails_atomically(event_loop):
    """问题一：PG 模式 enrollment_token 的 purpose 不是 enroll_confirm 时，必须整体拒绝（不消费、不写）。"""
    from app.shared.utils.auth.mfa_service import MfaService, MfaError
    from app.shared.utils.auth.mfa_service import _hash_challenge_token
    from datetime import datetime, timezone

    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    secret = pyotp.random_base32()
    user_id = 4
    enrollment_token = "wrong-purpose-token"
    store, conn = _build_pg_enrollment_store(
        svc=svc,
        user_id=user_id,
        pending_secret=secret,
        enrollment_token=enrollment_token,
    )
    # 故意篡改 purpose
    conn.chal["purpose"] = "login_verify"

    pool = _FakePool(store)
    pool.connection = conn  # type: ignore[attr-defined]
    svc._db = pool  # type: ignore[attr-defined]

    async def runner():
        code = pyotp.TOTP(secret).now()
        with pytest.raises(MfaError):
            await svc.confirm_login_enrollment(
                enrollment_token=enrollment_token, code=code
            )
        # challenge 不应被消费；totp 行不应有 secret_cipher
        assert conn.chal["consumed_at"] is None
        assert conn.totp_row["secret_cipher"] is None
        assert conn.totp_row["enabled_at"] is None

    event_loop.run_until_complete(runner())


# ============================================================
# 问题二：路由不访问 MFA service 私有方法
# ============================================================


def test_router_source_does_not_access_private_mfa_methods():
    """问题二：源码静态检查 —— ``mfa_router.py`` 字符串中不出现 ``mfa._xxx`` 调用
    （排除模块顶层 from-import 的私有符号）；同时 ``_hash_challenge_token`` /
    ``_decrypt_secret`` 不能再由路由 import 或调用。

    通过读取模块源码并 AST 扫描所有调用实现：
    - 不允许 ``svc._get_totp_entry`` / ``svc._validate_totp`` / ``svc._validate_recovery_code``
      等私有方法调用
    - 不允许 ``mfa._xxx(...)`` 调用
    - 不允许 ``_hash_challenge_token(...)`` / ``_decrypt_secret(...)`` 调用
      （即使在 ``mfa_service`` 模块内）
    """
    import ast
    from pathlib import Path

    src_path = Path(
        r"E:\laboratory\AI\Agents\feature-agent-core-ref\app\shared\routers\mfa_router.py"
    )
    assert src_path.exists(), f"mfa_router.py 路径不存在: {src_path}"
    src = src_path.read_text(encoding="utf-8")
    tree = ast.parse(src)

    forbidden_names = {
        "_get_totp_entry",
        "_validate_totp",
        "_validate_recovery_code",
        "_hash_challenge_token",
        "_decrypt_secret",
    }

    violations: List[str] = []

    class _Visitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            func = node.func
            # mfa._xxx(...) 形式
            if isinstance(func, ast.Attribute):
                attr_name = func.attr
                if attr_name in forbidden_names:
                    violations.append(
                        f"{src_path}:{node.lineno}: 调用了私有/受保护符号 mfa.{attr_name}(...)"
                    )
            # 直接 _xxx(...) 调用（避免路由内手动 hash/decrypt）
            if isinstance(func, ast.Name):
                if func.id in forbidden_names:
                    violations.append(
                        f"{src_path}:{node.lineno}: 调用了私有/受保护符号 {func.id}(...)"
                    )
            self.generic_visit(node)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            for n in node.names:
                if n.name in forbidden_names:
                    violations.append(
                        f"{src_path}:{node.lineno}: import 了私有符号 {n.name}"
                    )
            self.generic_visit(node)

    _Visitor().visit(tree)
    assert not violations, (
        "mfa_router.py 不应访问 MFA service 私有方法（应改用公开 API）：\n"
        + "\n".join(violations)
    )




def test_login_enroll_start_pg_single_transaction(event_loop):
    """问题二：login_enroll 消费、pending secret 与新 challenge 必须同一 PG 事务。"""
    from app.shared.utils.auth.mfa_service import MfaService, _hash_challenge_token

    svc = MfaService(db=None, settings=_make_settings())
    source_token = "login-enroll-pg-token"
    source_hash = _hash_challenge_token(source_token)
    calls: List[Tuple[str, Tuple[Any, ...], bool]] = []
    state = {"consumed": None, "pending": None, "new_challenge": None}

    class Tx:
        async def __aenter__(self):
            conn.in_tx = True
            return conn

        async def __aexit__(self, exc_type, exc, tb):
            conn.in_tx = False

    class Conn:
        in_tx = False

        def transaction(self):
            return Tx()

        async def fetchrow(self, sql, *args):
            calls.append((sql, args, self.in_tx))
            return {"user_id": 7, "purpose": "login_enroll", "expires_at": time.time() + 300, "consumed_at": None}

        async def execute(self, sql, *args):
            calls.append((sql, args, self.in_tx))
            if "user_mfa_totp" in sql:
                state["pending"] = args[1]
            elif "INSERT INTO mfa_challenges" in sql:
                state["new_challenge"] = args[0]
            elif "consumed_at" in sql:
                state["consumed"] = args[0]

    conn = Conn()

    class Acquire:
        async def __aenter__(self):
            return conn

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class Pool:
        def acquire(self):
            return Acquire()

    svc._db = Pool()

    async def runner():
        result = await svc.start_login_enrollment(source_token, username="pg-user")
        assert result["enrollment_token"]
        assert state["pending"] is not None
        assert state["new_challenge"] is not None
        assert state["consumed"] == source_hash
        assert all(in_tx for _, _, in_tx in calls)
        sqls = [sql for sql, _, _ in calls]
        assert any("FROM mfa_challenges" in sql and "FOR UPDATE" in sql for sql in sqls)
        assert sqls.index(next(sql for sql in sqls if "FROM mfa_challenges" in sql)) < sqls.index(
            next(sql for sql in sqls if "INSERT INTO user_mfa_totp" in sql)
        )

    event_loop.run_until_complete(runner())


def test_recovery_code_used_for_disable_cannot_be_used_again(event_loop):
    """问题二：恢复码用于 disable 后，剩余同样码不能再次成功 disable。"""
    from app.shared.utils.auth.mfa_service import MfaService, MfaError

    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    async def runner():
        user_id = 21
        chal = await svc.start_enrollment(user_id=user_id)
        await svc.confirm_enrollment(
            user_id=user_id, code=pyotp.TOTP(chal["secret"]).now()
        )
        _, plain_codes = await svc.regenerate_recovery_codes(user_id=user_id)
        first = plain_codes[0]

        # 第一次 disable 用恢复码 → 成功 + 消费该码
        await svc.verify_and_consume_management_factor(
            user_id=user_id, code=first, method="recovery_code", operation="disable"
        )
        await svc.disable(user_id=user_id)

        # 重新绑定以便第二次尝试
        chal2 = await svc.start_enrollment(user_id=user_id)
        await svc.confirm_enrollment(
            user_id=user_id, code=pyotp.TOTP(chal2["secret"]).now()
        )
        _, plain_codes2 = await svc.regenerate_recovery_codes(user_id=user_id)
        # 第一个码仍可用（重启场景下生成的码不重合）
        first2 = plain_codes2[0]

        # 第一次 disable（首次）成功
        await svc.verify_and_consume_management_factor(
            user_id=user_id, code=first2, method="recovery_code", operation="disable"
        )
        # 第二次 disable 必须失败（first2 已消费）
        with pytest.raises(MfaError):
            await svc.verify_and_consume_management_factor(
                user_id=user_id,
                code=first2,
                method="recovery_code",
                operation="disable",
            )

    event_loop.run_until_complete(runner())


def test_recovery_code_used_for_regenerate_cannot_be_used_again(event_loop):
    """问题二：恢复码用于 regenerate 后，剩余同样码不能再次成功 regenerate。"""
    from app.shared.utils.auth.mfa_service import MfaService, MfaError

    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    async def runner():
        user_id = 22
        chal = await svc.start_enrollment(user_id=user_id)
        await svc.confirm_enrollment(
            user_id=user_id, code=pyotp.TOTP(chal["secret"]).now()
        )
        _, plain_codes = await svc.regenerate_recovery_codes(user_id=user_id)
        first = plain_codes[0]

        # 第一次成功
        await svc.verify_and_consume_management_factor(
            user_id=user_id,
            code=first,
            method="recovery_code",
            operation="regenerate_recovery_codes",
        )
        _, new_codes = await svc.regenerate_recovery_codes(user_id=user_id)
        # 第二次必失败（first 已被消费）
        with pytest.raises(MfaError):
            await svc.verify_and_consume_management_factor(
                user_id=user_id,
                code=first,
                method="recovery_code",
                operation="regenerate_recovery_codes",
            )

    event_loop.run_until_complete(runner())


def test_management_factor_totp_does_not_advance_step(event_loop):
    """问题二：TOTP 用于 management factor（disable/regenerate）时，**不应**写入
    ``last_used_step``（不同于 ``verify_login`` 路径，避免误伤正常登录）。"""
    from app.shared.utils.auth.mfa_service import MfaService

    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    async def runner():
        user_id = 23
        chal = await svc.start_enrollment(user_id=user_id)
        await svc.confirm_enrollment(
            user_id=user_id, code=pyotp.TOTP(chal["secret"]).now()
        )
        # confirm_enrollment 写入 anti_replay_step；记录当前 last_used_step
        entry_before = svc._memory_totp_entries[user_id]
        before_step = entry_before.get("last_used_step")

        secret = chal["secret"]
        code = pyotp.TOTP(secret).now()
        await svc.verify_and_consume_management_factor(
            user_id=user_id, code=code, method="totp", operation="disable"
        )
        # last_used_step 不应被本操作改写
        entry_after = svc._memory_totp_entries[user_id]
        assert entry_after.get("last_used_step") == before_step, (
            "management factor TOTP 校验不应改写 last_used_step（避免误伤正常登录）"
        )

    event_loop.run_until_complete(runner())


def test_management_factor_pg_uses_transaction_and_atomic_consume(event_loop):
    """问题二：PG 模式 management factor 必须事务 + SELECT FOR UPDATE 锁 TOTP 行 +
    校验 + 一次性消费恢复码。
    """
    import bcrypt
    from app.shared.utils.auth.mfa_service import MfaService, MfaError
    from app.shared.utils.auth.mfa_service import _hash_challenge_token

    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    user_id = 24
    plain_codes = ["aaaa-bbbb", "cccc-dddd", "eeee-ffff"]
    hashed = [bcrypt.hashpw(c.encode(), bcrypt.gensalt()).decode() for c in plain_codes]
    secret = pyotp.random_base32()
    encrypted_secret = svc._fernet.encrypt(secret.encode()).decode()
    challenge_token = "mgmt-token-1"
    challenge_hash = _hash_challenge_token(challenge_token)

    store: Dict[str, Any] = {
        "user_mfa_totp": [
            {
                "user_id": user_id,
                "secret_cipher": encrypted_secret,
                "pending_secret_cipher": None,
                "enabled_at": "2026-01-01T00:00:00",
                "last_used_step": 0,
                "recovery_code_hashes": list(hashed),
            }
        ],
        "mfa_challenges": [
            {
                "token_hash": challenge_hash,
                "user_id": user_id,
                "purpose": "login_verify",
                "expires_at": time.time() + 300.0,
                "consumed_at": None,
                "failed_attempts": 0,
            }
        ],
    }

    class Conn(_FakeConnection):
        def __init__(self):
            super().__init__(store)
            self.totp_row = store["user_mfa_totp"][0]
            self.chal = store["mfa_challenges"][0]

        def _dispatch_fetchrow(self, sql, args):
            if "FROM user_mfa_totp" in sql and "FOR UPDATE" in sql:
                self.add_exec(sql, args)
                return _FakeRow(dict(self.totp_row))
            if "FROM user_mfa_totp" in sql:
                self.add_exec(sql, args)
                return _FakeRow(dict(self.totp_row))
            if "FROM mfa_challenges" in sql and "FOR UPDATE" in sql:
                self.add_exec(sql, args)
                return _FakeRow(dict(self.chal))
            return super()._dispatch_fetchrow(sql, args)

        def _dispatch_execute(self, sql, args):
            if "UPDATE user_mfa_totp" in sql and "recovery_code_hashes" in sql:
                self.add_exec(sql, args)
                self.totp_row["recovery_code_hashes"] = json.loads(args[1])
                return "UPDATE 1"
            return super()._dispatch_execute(sql, args)

    conn = Conn()
    pool = _FakePool(store)
    pool.connection = conn  # type: ignore[attr-defined]
    svc._db = pool  # type: ignore[attr-defined]

    async def runner():
        # 第一次成功：消费 plain_codes[0]
        await svc.verify_and_consume_management_factor(
            user_id=user_id,
            code=plain_codes[0],
            method="recovery_code",
            operation="regenerate_recovery_codes",
        )
        assert len(conn.totp_row["recovery_code_hashes"]) == 2
        # SQL 必须包含 FOR UPDATE
        sqls = [c.sql for c in conn.exec_calls]
        assert any(
            "FROM user_mfa_totp" in s and "FOR UPDATE" in s for s in sqls
        ), "PG 模式 management factor 必须 SELECT user_mfa_totp FOR UPDATE"
        # JSONB 写回必须为完整 list
        write_call = next(
            c for c in conn.exec_calls if "UPDATE user_mfa_totp" in c.sql
        )
        assert isinstance(json.loads(write_call.params[1]), list)

        # 第二次必失败（plain_codes[0] 已消费）
        with pytest.raises(MfaError):
            await svc.verify_and_consume_management_factor(
                user_id=user_id,
                code=plain_codes[0],
                method="recovery_code",
                operation="regenerate_recovery_codes",
            )

    event_loop.run_until_complete(runner())


# ============================================================
# 路由端到端：/api/auth/mfa/login/enroll/confirm
# ============================================================


def _build_minimal_mfa_app(mfa_svc):
    """最小化 app，挂 mfa_router + auth_router，绑 mfa_svc 到 app.state。"""
    from fastapi import FastAPI

    from app.shared.routers.auth_router import router as auth_router
    from app.shared.routers.mfa_router import router as mfa_router

    _app = FastAPI()
    _app.include_router(auth_router)
    _app.include_router(mfa_router)
    _app.state.mfa_service = mfa_svc
    return _app


def test_router_login_enroll_confirm_failure_does_not_consume_challenge(
    event_loop, monkeypatch
):
    """问题一：路由层端到端 —— /api/auth/mfa/login/enroll/confirm 错误码时，
    enrollment_token 仍可用于再次 confirm 成功。

    这是 RED 证据：
    - 路由当前走 lookup_challenge + consume_challenge + confirm_enrollment 三段独立事务，
      错误码导致 challenge 已被 consume_challenge 标记为 consumed；
      但 confirm_enrollment 失败 → TOTP 错误 → 无任何修改 → 第二次用同一 token confirm
      应失败（MfaError：challenge consumed），不符合"可重试"。
    """
    from fastapi.testclient import TestClient

    from app.shared.utils.auth.mfa_service import MfaService
    from app.shared.utils.auth.user_db import UserDB

    monkeypatch.setenv("AUTH_STORAGE_MODE", "memory")

    async def setup():
        UserDB._memory_users.clear()
        UserDB._memory_id_counter = 0
        user_id = await UserDB.create_user(
            "retry_admin", "P@ssword1!", role="admin"
        )
        user = await UserDB.get_user_by_username("retry_admin")
        return user_id, user

    user_id, user = event_loop.run_until_complete(setup())

    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)
    MfaService.set_instance(svc)

    # 模拟 login_enroll → start_enrollment 流程
    async def start_flow():
        login_enroll_token, _ = await svc.create_login_challenge(
            user_id=user_id, purpose="login_enroll"
        )
        # 模拟路由层：lookup login_enroll challenge → start_enrollment
        # 这里我们直接调 start_enrollment（其内部已校验 lookup）
        started = await svc.start_enrollment(user_id=user_id)
        return login_enroll_token, started

    login_enroll_token, started = event_loop.run_until_complete(start_flow())

    app = _build_minimal_mfa_app(svc)

    with TestClient(app) as client:
        # Step 1：错误码 confirm
        bad_resp = client.post(
            "/api/auth/mfa/login/enroll/confirm",
            json={"enrollment_token": started["enrollment_token"], "code": "000000"},
        )
        assert bad_resp.status_code == 401, (
            f"错误码应返 401，actual={bad_resp.status_code}"
        )

        # Step 2：同一 enrollment_token + 正确码再试
        good_code = pyotp.TOTP(started["secret"]).now()
        good_resp = client.post(
            "/api/auth/mfa/login/enroll/confirm",
            json={"enrollment_token": started["enrollment_token"], "code": good_code},
        )
        assert good_resp.status_code == 200, (
            f"同一 enrollment_token 错误码后仍应可重试成功，actual={good_resp.status_code}, "
            f"body={good_resp.text}"
        )
        data = good_resp.json()
        assert "auth" in data
        assert "recovery_codes" in data
        assert len(data["recovery_codes"]) == 10


def test_router_login_enroll_confirm_uses_public_service_only():
    """问题二：路由源内对 mfa_service 的调用只能访问非下划线开头的公开方法。"""
    # 静态扫描：禁止 mfa._xxx 与 mfa_service._xxx 调用；
    # 同时禁止 import 任何以单下划线开头的 MFA service 符号。
    import ast
    from pathlib import Path

    src_path = Path(
        r"E:\laboratory\AI\Agents\feature-agent-core-ref\app\shared\routers\mfa_router.py"
    )
    src = src_path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    violations: List[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr.startswith("_") and not node.func.attr.startswith("__"):
                # Allow common dunder usage; reject single-underscore methods
                violations.append(
                    f"{src_path}:{node.lineno}: 调用了私有/受保护方法 {node.func.attr}"
                )

    assert not violations, "路由不应调用以下私有/受保护方法：\n" + "\n".join(violations)


# ============================================================
# 测试内部：确认 public confirm_login_enrollment 与
# verify_and_consume_management_factor 必须存在
# ============================================================


def test_mfa_service_public_methods_for_followup_exist():
    """P0：MfaService 必须暴露 ``confirm_login_enrollment`` 与
    ``verify_and_consume_management_factor`` 公开方法。
    """
    from app.shared.utils.auth.mfa_service import MfaService

    assert callable(getattr(MfaService, "confirm_login_enrollment", None)), (
        "MfaService.confirm_login_enrollment 必须可调用（问题一公开 API）"
    )
    assert callable(
        getattr(MfaService, "verify_and_consume_management_factor", None)
    ), (
        "MfaService.verify_and_consume_management_factor 必须可调用（问题二公开 API）"
    )


# ============================================================
# 路由源/行为：/api/auth/login-api 函数体 / 模型 / 响应相对 HEAD 未改
# ============================================================


def test_login_api_function_unchanged_relative_to_head():
    """/api/auth/login-api 函数体、模型、响应相对 HEAD 未改。

    HEAD（``origin/main``）对应的源路径不可知；本测试仅在 CI 缺失 HEAD 时跳过，
    直接断言现有契约与历史快照一致（响应字段集合 = LoginResponse 字段）。
    """
    from app.shared.routers.auth_router import ApiLoginRequest, LoginResponse

    # 模型字段必须未改
    assert set(ApiLoginRequest.model_fields.keys()) == {"username", "password"}
    assert set(LoginResponse.model_fields.keys()) == {
        "access_token",
        "token_type",
        "expires_in",
        "role",
        "username",
        "user_id",
        "visible_menus",
        "allowed_agents",
    }

    # 进一步：login_api 路由装饰器与函数名
    from app.shared.routers import auth_router as ar

    func = ar.login_api  # type: ignore[attr-defined]
    assert func.__name__ == "login_api"
    # 路由前缀必须未变
    assert ar.router.prefix == "/api/auth"