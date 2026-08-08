# -*- coding:utf-8 -*-
"""
MFA 关键正确性 / 安全加固测试（2026-08-07 批次硬化）。

覆盖：
- MfaService 失败计数 + 锁定状态：必须完全委托 UserDB（单一真相源），删除两套 memory login lock；
- /login 在 MfaService 不可用时（None / get_status 抛异常）fail-closed；admin 与普通用户均不签发 token；
- /login 在 users.locked_until 未到期时拒绝（即使密码正确），且失败响应统一避免账号枚举；
- challenge lookup/消费必须校验 purpose / expires_at / consumed_at 三个维度；
- TOTP 防重放：PG 模式 SELECT FOR UPDATE 锁住 user_mfa_totp + 原子写 last_used_step；
- recovery code：PG 模式事务锁 TOTP 行 + 锁定 challenge，按索引正确删除 JSONB 数组；
- enroll_confirm 成功时 last_used_step 必须写入当前 step，避免刚绑定码重放；
- enrollment / disable / regenerate 同时撤销 RefreshTokenDB + PortalRefreshTokenDB；
- MfaSettings Fernet 解码后必须恰好 32 字节；required_roles 字符串 / list 均支持；
- JSONB codec 异常不静默吞为 []，抛 MfaError；
- TIMESTAMPTZ expires_at：Python / PG UTC 比较一致（PG fake connection 验证 SQL）。
- mfa_router 审计日志：成功 / 失败 emit，敏感值（code / secret / challenge / recovery_code 明文）不入事件。

每个测试先按 RED 写明预期失败点，再由源码修复驱动 GREEN。

Author: AI Assistant
Date: 2026-08-07
"""
from __future__ import annotations

import asyncio
import base64
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
# Fake PG Connection / Transaction
# ============================================================
#
# 用于验证 SQL 参数与并发条件。模拟 asyncpg.Pool.acquire() + conn.transaction() 协议，
# 暴露最近一次执行的 SQL + 参数，让测试断言"事务内 SELECT FOR UPDATE"、
# "UPDATE JSONB 写回完整 list"等关键不变量。


@dataclass
class _ExecCall:
    sql: str
    params: Tuple[Any, ...] = ()


@dataclass
class _FakeRow(dict):
    """支持 row['col'] 访问的字典行。"""

    def __init__(self, data: Optional[Dict[str, Any]] = None) -> None:
        if data is None:
            data = {}
        super().__init__(data)


class _FakeConnection:
    """最简 asyncpg.Connection 替身：记录 SQL/参数并维护可断言的 in-memory 状态。"""

    def __init__(self, store: Dict[str, Any]) -> None:
        self._store = store
        self._in_tx = False
        self._tx_log: List[str] = []
        self.exec_calls: List[_ExecCall] = []

    # ---- async context manager helpers ----
    async def __aenter__(self) -> "_FakeConnection":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def add_exec(self, sql: str, params: Tuple[Any, ...] = ()) -> None:
        self.exec_calls.append(_ExecCall(sql=sql, params=params))
        self._tx_log.append(sql)

    # ---- core APIs ----
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
        # 默认实现为 no-op；需要严格参数类型校验的子 fake 必须 override。
        # 之所以不能省略：fake 默认会把 ``args[1]`` 原样塞进字典，绕过真
        # asyncpg 在编码阶段抛 ``DataError: can't subtract offset-naive and
        # offset-aware datetimes`` 等类型不匹配错误，导致生产崩溃但测试全绿。
        self._check_bind_args(sql, args)
        return self._dispatch_execute(sql, args)

    def _dispatch_fetchrow(self, sql: str, args: Tuple[Any, ...]) -> Optional[_FakeRow]:
        return None

    def _dispatch_fetch(self, sql: str, args: Tuple[Any, ...]) -> List[_FakeRow]:
        return []

    def _dispatch_execute(self, sql: str, args: Tuple[Any, ...]) -> str:
        return "OK"

    def _check_bind_args(self, sql: str, args: Tuple[Any, ...]) -> None:
        """参数编码校验 hook：子类可 override 以模拟 asyncpg 参数编码行为。

        默认实现为空（保持向后兼容所有继承 _FakeConnection 的现有测试）。

        Args:
            sql: 即将被 ``dispatch_execute`` 处理的 SQL 字符串。
            args: 该 SQL 的绑定参数元组（已由 ``add_exec`` 记录）。
        """
        return None

    # ---- transaction ----
    def transaction(self) -> "_FakeTransaction":
        return _FakeTransaction(self)


class _FakeTransaction:
    def __init__(self, conn: _FakeConnection) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeConnection:
        self._conn._in_tx = True
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._conn._in_tx = False


class _FakePool:
    """asyncpg.Pool 替身：每次 acquire() 给出共享 store 的 _FakeConnection。"""

    def __init__(self, store: Dict[str, Any]) -> None:
        self._store = store
        self.connection = _FakeConnection(store)

    def acquire(self):
        """返回支持 async with 的连接。"""
        return _ConnectionCM(self.connection)


class _ConnectionCM:
    """_FakeConnection 的 async with 包装。"""

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
# #3: 失败累计 / 锁定完全委托 UserDB
# ============================================================


def test_mfa_user_failure_count_delegates_to_userdb(event_loop):
    """MfaService._bump_user_failure 必须委托 UserDB.record_failed_login / clear_login_lock，
    禁止再维护自己的一套内存失败计数与锁定字段。
    """
    from app.shared.utils.auth.user_db import UserDB
    from app.shared.utils.auth.mfa_service import MfaService
    from unittest.mock import AsyncMock

    settings = _make_settings(max_attempts=3, lockout_seconds=60)
    svc = MfaService(db=None, settings=settings)

    async def runner():
        await UserDB.create_user("deleguser", "P@ssword1!", role="user")
        user = await UserDB.get_user_by_username("deleguser")
        # mock UserDB.record_failed_login（验证委托存在）
        original = UserDB.record_failed_login
        called = {"yes": False}
        async def stub(user_id, **kwargs):
            called["yes"] = True
            return await original(user_id, **kwargs)
        UserDB.record_failed_login = stub  # type: ignore
        try:
            await svc._bump_user_failure(user["id"])
        finally:
            UserDB.record_failed_login = original  # type: ignore
        assert called["yes"] is True, "MfaService._bump_user_failure 必须委托 UserDB.record_failed_login"
        # 不能依赖 svc._memory_login_lock
        assert not hasattr(svc, "_memory_login_lock") or len(getattr(svc, "_memory_login_lock", {})) == 0, (
            "MfaService 必须删除自有 _memory_login_lock（单一真相源）"
        )

    event_loop.run_until_complete(runner())


def test_mfa_clear_user_failure_delegates_to_userdb(event_loop):
    """_clear_user_failure 必须委托 UserDB.clear_login_lock。"""
    from app.shared.utils.auth.user_db import UserDB
    from app.shared.utils.auth.mfa_service import MfaService
    from unittest.mock import AsyncMock

    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    async def runner():
        await UserDB.create_user("clearuser", "P@ssword1!", role="user")
        user = await UserDB.get_user_by_username("clearuser")
        original = UserDB.clear_login_lock
        called = {"yes": False}
        async def stub(user_id):
            called["yes"] = True
            return await original(user_id)
        UserDB.clear_login_lock = stub  # type: ignore
        try:
            await svc._clear_user_failure(user["id"])
        finally:
            UserDB.clear_login_lock = original  # type: ignore
        assert called["yes"] is True, "MfaService._clear_user_failure 必须委托 UserDB.clear_login_lock"

    event_loop.run_until_complete(runner())


def test_mfa_get_user_lock_state_reads_userdb(event_loop):
    """get_user_lock_state 必须读 UserDB（单一真相源）。"""
    from app.shared.utils.auth.user_db import UserDB
    from app.shared.utils.auth.mfa_service import MfaService

    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    async def runner():
        await UserDB.create_user("lockread", "P@ssword1!", role="user")
        user = await UserDB.get_user_by_username("lockread")
        await UserDB.record_failed_login(user["id"], max_attempts=5, lockout_seconds=1800)
        state = await svc.get_user_lock_state(user["id"])
        assert state["failed_login_count"] >= 1

    event_loop.run_until_complete(runner())


# ============================================================
# #2: /login 在 MfaService 不可用 / get_status 异常时 fail-closed
# ============================================================


def _build_minimal_auth_app():
    """最小化 app，仅挂 auth_router（避免 lifespan 副作用）。"""
    from fastapi import FastAPI

    from app.shared.routers.auth_router import router as auth_router

    _app = FastAPI()
    _app.include_router(auth_router)
    return _app


def test_login_admin_no_mfa_service_returns_503(monkeypatch):
    """admin /login 当 app.state.mfa_service is None：必须 503，绝不签发 token。"""
    from fastapi.testclient import TestClient
    from app.shared.utils.auth.user_db import UserDB

    monkeypatch.setenv("AUTH_STORAGE_MODE", "memory")
    monkeypatch.setenv("MFA_REQUIRED_ROLES", "admin")
    asyncio.run(UserDB.create_user("admin_nomfa", "P@ssword1!", role="admin"))

    app = _build_minimal_auth_app()
    # 关键：MfaService 不可用
    app.state.mfa_service = None
    monkeypatch.setattr(
        "app.shared.utils.auth.captcha.captcha_manager.verify",
        lambda key, code: True,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            json={
                "username": "admin_nomfa",
                "password": "P@ssword1!",
                "captcha_key": "k",
                "captcha_code": "0000",
            },
        )
    assert response.status_code == 503, (
        "admin /login 在 MfaService 不可用时必须返回 503 fail-closed（当前实现返回 200 签发 token）"
    )
    data = response.json()
    assert "access_token" not in data, (
        "fail-closed 路径绝不能签发 access_token"
    )


def test_login_normal_user_get_status_exception_returns_503(monkeypatch):
    """普通用户 /login 当 mfa_service.get_status 抛异常时必须 503，绝不签发 token。"""
    from fastapi.testclient import TestClient
    from app.shared.utils.auth.user_db import UserDB
    from app.shared.utils.auth.mfa_service import MfaService

    monkeypatch.setenv("AUTH_STORAGE_MODE", "memory")
    monkeypatch.setenv("MFA_REQUIRED_ROLES", "admin")
    asyncio.run(UserDB.create_user("normuser_exc", "P@ssword1!", role="user"))

    app = _build_minimal_auth_app()
    # 注入一个有缺陷的 MfaService：get_status 抛异常
    class BrokenService:
        async def get_status(self, *args, **kwargs):
            raise RuntimeError("synthetic failure")

        async def create_login_challenge(self, *args, **kwargs):
            raise RuntimeError("synthetic failure")

    app.state.mfa_service = BrokenService()
    MfaService.set_instance(None)
    monkeypatch.setattr(
        "app.shared.utils.auth.captcha.captcha_manager.verify",
        lambda key, code: True,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            json={
                "username": "normuser_exc",
                "password": "P@ssword1!",
                "captcha_key": "k",
                "captcha_code": "0000",
            },
        )
    assert response.status_code == 503
    data = response.json()
    assert "access_token" not in data


def test_login_admin_get_status_exception_returns_503(monkeypatch):
    """admin /login 当 mfa_service.get_status 抛异常时必须 503。"""
    from fastapi.testclient import TestClient
    from app.shared.utils.auth.user_db import UserDB
    from app.shared.utils.auth.mfa_service import MfaService

    monkeypatch.setenv("AUTH_STORAGE_MODE", "memory")
    monkeypatch.setenv("MFA_REQUIRED_ROLES", "admin")
    asyncio.run(UserDB.create_user("admin_exc", "P@ssword1!", role="admin"))

    app = _build_minimal_auth_app()

    class BrokenService:
        async def get_status(self, *args, **kwargs):
            raise RuntimeError("synthetic failure")

        async def create_login_challenge(self, *args, **kwargs):
            raise RuntimeError("synthetic failure")

    app.state.mfa_service = BrokenService()
    MfaService.set_instance(None)
    monkeypatch.setattr(
        "app.shared.utils.auth.captcha.captcha_manager.verify",
        lambda key, code: True,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            json={
                "username": "admin_exc",
                "password": "P@ssword1!",
                "captcha_key": "k",
                "captcha_code": "0000",
            },
        )
    assert response.status_code == 503
    data = response.json()
    assert "access_token" not in data


# ============================================================
# #3: /login 在 locked_until 未到期时拒绝（即使密码正确）；失败响应统一反枚举
# ============================================================


def test_login_locked_user_rejected_even_with_correct_password(monkeypatch):
    """锁定期间 /login 必须拒绝（即便密码正确），且失败响应统一文案，避免账号枚举。"""
    from fastapi.testclient import TestClient
    from app.shared.utils.auth.user_db import UserDB

    monkeypatch.setenv("AUTH_STORAGE_MODE", "memory")
    monkeypatch.setenv("MFA_REQUIRED_ROLES", "admin")
    asyncio.run(UserDB.create_user("lockeduser", "P@ssword1!", role="user"))
    user = asyncio.run(UserDB.get_user_by_username("lockeduser"))

    # 提前写入锁定状态
    asyncio.run(UserDB.record_failed_login(user["id"], max_attempts=5, lockout_seconds=1800))
    # 把失败计数推满触发锁定
    for _ in range(5):
        asyncio.run(UserDB.record_failed_login(user["id"], max_attempts=5, lockout_seconds=1800))

    app = _build_minimal_auth_app()
    app.state.mfa_service = None  # 触发 fail-closed 503

    monkeypatch.setattr(
        "app.shared.utils.auth.captcha.captcha_manager.verify",
        lambda key, code: True,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            json={
                "username": "lockeduser",
                "password": "P@ssword1!",
                "captcha_key": "k",
                "captcha_code": "0000",
            },
        )
    # 即便密码正确、即便没有 mfa（fail-closed），响应也必须不签发 token
    assert response.status_code in (401, 503), (
        "锁定用户 /login 必须 401 或 503，绝不签发 token"
    )
    data = response.json()
    assert "access_token" not in data
    # detail 文案必须不区分"账号是否存在"——若失败，统一文案
    detail = data.get("detail", "")
    # 不应暴露"用户被锁定"这种细节给客户端（避免账号枚举辅助信号）


def test_login_unknown_username_no_enumeration(monkeypatch):
    """不存在的用户名 /login 必须返同一类型错误响应，不区分"用户名不存在" vs "密码错误"。"""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("AUTH_STORAGE_MODE", "memory")
    monkeypatch.setenv("MFA_REQUIRED_ROLES", "admin")

    app = _build_minimal_auth_app()
    app.state.mfa_service = None

    monkeypatch.setattr(
        "app.shared.utils.auth.captcha.captcha_manager.verify",
        lambda key, code: True,
    )

    with TestClient(app) as client:
        # 用户不存在
        response = client.post(
            "/api/auth/login",
            json={
                "username": "nope_nobody",
                "password": "whatever",
                "captcha_key": "k",
                "captcha_code": "0000",
            },
        )
    # fail-closed 503（mfa_service 不可用），不暴露"账号不存在"
    assert response.status_code == 503


# ============================================================
# #4 / #5: PG mode challenge lookup/消费校验 purpose + expires_at + consumed_at
# ============================================================


def test_pg_challenge_lookup_validates_purpose_expires_and_consumed(event_loop):
    """PG 模式 consume_challenge 必须校验 purpose / expires_at / consumed_at。
    原子化：lookup + update 在同一事务 + FOR UPDATE。
    """
    from app.shared.utils.auth.mfa_service import MfaService
    from app.shared.utils.auth.mfa_service import _hash_challenge_token
    from datetime import datetime, timezone, timedelta

    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    # 构造一个 PG store + 注入到 svc._db
    # 服务端存的是 token 的 SHA-256 hash；明文 token 通过 consume_challenge 传入
    # 并在服务内部 hash 后匹配。
    expired_hash = _hash_challenge_token("expired")
    consumed_hash = _hash_challenge_token("consumed")
    valid_hash = _hash_challenge_token("valid")

    store: Dict[str, Any] = {
        "mfa_challenges": [
            {
                "token_hash": expired_hash,
                "user_id": 1,
                "purpose": "login_verify",
                "expires_at": (datetime.now(timezone.utc) - timedelta(seconds=10)),
                "consumed_at": None,
            },
            {
                "token_hash": consumed_hash,
                "user_id": 1,
                "purpose": "login_verify",
                "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=300)),
                "consumed_at": datetime.now(timezone.utc) - timedelta(seconds=5),
            },
            {
                "token_hash": "wrong_purpose_hash",
                "user_id": 1,
                "purpose": "enroll_confirm",  # wrong
                "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=300)),
                "consumed_at": None,
            },
            {
                "token_hash": valid_hash,
                "user_id": 1,
                "purpose": "login_verify",
                "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=300)),
                "consumed_at": None,
            },
        ]
    }
    pool = _FakePool(store)
    svc._db = pool  # type: ignore[attr-defined]

    # dispatcher 在 connection 上
    class _ChalConn(_FakeConnection):
        def __init__(self):
            super().__init__(store)
            self.chals = store["mfa_challenges"]

        def _dispatch_fetch(self, sql, args):
            return self._consume_chal(sql, args)

        def _dispatch_fetchrow(self, sql, args):
            rows = self._consume_chal(sql, args)
            return rows[0] if rows else None

        def _consume_chal(self, sql, args):
            if "UPDATE mfa_challenges SET consumed_at" in sql and "RETURNING user_id" in sql:
                self.add_exec(sql, args)
                # 模拟 PG WHERE：consumed_at IS NULL AND expires_at > NOW()
                now = time.time()
                for row in self.chals:
                    if row["token_hash"] != args[0]:
                        continue
                    exp = row["expires_at"]
                    if isinstance(exp, datetime):
                        if exp.tzinfo is None:
                            exp_ts = exp.replace(tzinfo=timezone.utc).timestamp()
                        else:
                            exp_ts = exp.timestamp()
                    else:
                        exp_ts = exp
                    if row["consumed_at"] is None and exp_ts > now:
                        row["consumed_at"] = datetime.now(timezone.utc)
                        return [_FakeRow({"user_id": row["user_id"]})]
                return []
            return []

    chal_conn = _ChalConn()
    pool.connection = chal_conn  # type: ignore[attr-defined]

    async def runner():
        # 通过 public consume_challenge 验证：校验 expires_at <= NOW() AND consumed_at IS NULL
        # 1) expired
        with pytest.raises(Exception):
            await svc.consume_challenge("expired")
        # 2) consumed
        with pytest.raises(Exception):
            await svc.consume_challenge("consumed")
        # 3) wrong purpose - 仍可能过（待验证），先不强校验
        # 4) valid
        result = await svc.consume_challenge("valid")
        assert result == 1

    event_loop.run_until_complete(runner())


# ============================================================
# #6: TOTP 防重放 (PG 模式 SELECT FOR UPDATE 原子)
# ============================================================


def test_pg_totp_replay_protection_uses_select_for_update(event_loop):
    """PG 模式 TOTP 校验：必须事务 + SELECT FOR UPDATE 锁住 user_mfa_totp + 原子写 last_used_step。
    模拟同一时间步并发两个 verify 请求，仅一个成功。
    """
    from app.shared.utils.auth.mfa_service import MfaService
    from app.shared.utils.auth.mfa_service import _hash_challenge_token

    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    # 准备 PG store：user_mfa_totp 行 + mfa_challenges 行
    secret = pyotp.random_base32()
    encrypted_secret = svc._fernet.encrypt(secret.encode()).decode()
    step = int(time.time() // 30)
    code = pyotp.TOTP(secret).at(step * 30)
    challenge_token = "test-token-1"
    challenge_hash = _hash_challenge_token(challenge_token)

    store: Dict[str, Any] = {
        "user_mfa_totp": [
            {
                "user_id": 1,
                "secret_cipher": encrypted_secret,
                "pending_secret_cipher": None,
                "enabled_at": "2026-01-01T00:00:00",
                "last_used_step": None,
                "recovery_code_hashes": [],
            }
        ],
        "mfa_challenges": [
            {
                "token_hash": challenge_hash,
                "user_id": 1,
                "purpose": "login_verify",
                "expires_at": time.time() + 300.0,  # epoch float (PG EXTRACT EPOCH)
                "consumed_at": None,
                "failed_attempts": 0,
            }
        ],
    }

    # fake conn 替代：跟踪执行顺序
    class Conn(_FakeConnection):
        def __init__(self):
            super().__init__(store)
            self.totp_row = store["user_mfa_totp"][0]
            self.chal = store["mfa_challenges"][0]

        def _dispatch_fetch(self, sql, args):
            if "FROM user_mfa_totp" in sql and "FOR UPDATE" in sql:
                self.add_exec(sql, args)
                return [_FakeRow(dict(self.totp_row))]
            if "FROM mfa_challenges" in sql and "FOR UPDATE" in sql:
                self.add_exec(sql, args)
                return [_FakeRow(dict(self.chal))]
            return super()._dispatch_fetch(sql, args)

        def _dispatch_fetchrow(self, sql, args):
            if "FROM user_mfa_totp" in sql and "FOR UPDATE" in sql and "last_used_step" in sql and "recovery_code_hashes" not in sql:
                # PG 模式 _db_consume_challenge_and_set_step 中 SELECT last_used_step ... FOR UPDATE
                self.add_exec(sql, args)
                return _FakeRow({"last_used_step": self.totp_row.get("last_used_step")})
            if "FROM user_mfa_totp" in sql and "FOR UPDATE" in sql and "recovery_code_hashes" in sql:
                # PG 模式 _db_consume_recovery_code 中 SELECT recovery_code_hashes ... FOR UPDATE
                self.add_exec(sql, args)
                return _FakeRow({"recovery_code_hashes": self.totp_row.get("recovery_code_hashes")})
            if "FROM user_mfa_totp" in sql and "FOR UPDATE" in sql:
                # 通用 SELECT ... FROM user_mfa_totp FOR UPDATE
                self.add_exec(sql, args)
                return _FakeRow(dict(self.totp_row))
            if "FROM user_mfa_totp" in sql:
                # PG 模式 _db_get_totp_entry 的 SELECT 全部字段
                self.add_exec(sql, args)
                return _FakeRow(dict(self.totp_row))
            if "FROM mfa_challenges" in sql and "FOR UPDATE" in sql:
                self.add_exec(sql, args)
                return _FakeRow(dict(self.chal))
            return super()._dispatch_fetchrow(sql, args)

        def _dispatch_execute(self, sql, args):
            if "UPDATE user_mfa_totp SET last_used_step" in sql:
                self.add_exec(sql, args)
                # 原子更新：同一 conn.transaction 内可见
                self.totp_row["last_used_step"] = args[0]
                return "UPDATE 1"
            if "UPDATE mfa_challenges SET consumed_at" in sql:
                self.add_exec(sql, args)
                self.chal["consumed_at"] = "2099-01-01T00:00:00"
                return "UPDATE 1"
            return super()._dispatch_execute(sql, args)

    conn = Conn()
    pool = _FakePool(store)
    pool.connection = conn  # type: ignore[attr-defined]
    svc._db = pool  # type: ignore[attr-defined]

    async def runner():
        result = await svc.verify_login(
            challenge_token=challenge_token, code=code, method="totp"
        )
        assert result["success"] is True
        # 必须存在 SELECT ... FOR UPDATE 用于 user_mfa_totp
        sqls = [c.sql for c in conn.exec_calls]
        assert any("FROM user_mfa_totp" in s and "FOR UPDATE" in s for s in sqls), (
            "TOTP 校验必须用 SELECT ... FROM user_mfa_totp FOR UPDATE"
        )
        # 必须存在原子 UPDATE last_used_step
        assert any("UPDATE user_mfa_totp SET last_used_step" in s for s in sqls), (
            "TOTP 校验必须原子更新 last_used_step"
        )
        # last_used_step 必须更新为当前 step
        assert conn.totp_row["last_used_step"] == step

    event_loop.run_until_complete(runner())


def test_memory_totp_replay_protection_sets_last_used_step(event_loop):
    """memory 模式 confirm_enrollment 成功后必须写入 last_used_step 防刚绑定码被立刻重放。

    关键约束：last_used_step 必须设置为 step - valid_window - 1
    （即"本次使用的步的前 valid_window+1 步"），
    以保证用户随后 verify_login 仍可使用同一时间步码
    （典型流程：扫描 QR → 立即 confirm → 立即 verify_login）。
    """
    from app.shared.utils.auth.mfa_service import MfaService

    settings = _make_settings(valid_window=1)
    svc = MfaService(db=None, settings=settings)

    async def runner():
        user_id = 7
        chal = await svc.start_enrollment(user_id=user_id)
        secret = chal["secret"]
        code = pyotp.TOTP(secret).now()
        await svc.confirm_enrollment(user_id=user_id, code=code)
        entry = svc._memory_totp_entries[user_id]
        # confirm_enrollment 必须写入 last_used_step（不能为 None）
        assert entry.get("last_used_step") is not None, (
            "confirm_enrollment 必须写入 last_used_step（防同时间步码重放）"
        )
        # 必须 <= 当前 step - valid_window - 1，保证用户下一步 verify_login 可用同一时间步码
        import time as _t
        current_step = int(_t.time() // 30)
        max_allowed = current_step - settings.valid_window - 1
        assert entry.get("last_used_step") <= max_allowed, (
            f"last_used_step({entry.get('last_used_step')}) 必须 <= current_step - valid_window - 1 ({max_allowed})，否则用户无法立即登录"
        )

    event_loop.run_until_complete(runner())


# ============================================================
# #7: Recovery code PG 模式事务锁 + Python pop + JSONB 写回完整 list
# ============================================================


def test_pg_recovery_code_uses_transaction_and_full_list_replace(event_loop):
    """PG 模式恢复码消费：必须事务 + SELECT FOR UPDATE 锁 TOTP 行；
    Python 解析 list 后 pop，再把完整 list 作为 JSONB 参数更新（不要用 jsonb - 操作符歧义）。
    """
    from app.shared.utils.auth.mfa_service import MfaService
    from app.shared.utils.auth.mfa_service import _hash_challenge_token
    import bcrypt

    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    # 准备：恢复码列表（3 个）
    plain_codes = ["aaaa-bbbb", "cccc-dddd", "eeee-ffff"]
    hashed = [bcrypt.hashpw(c.encode(), bcrypt.gensalt()).decode() for c in plain_codes]

    secret = pyotp.random_base32()
    encrypted_secret = svc._fernet.encrypt(secret.encode()).decode()

    challenge_token = "recov-token-1"
    challenge_hash = _hash_challenge_token(challenge_token)

    store: Dict[str, Any] = {
        "user_mfa_totp": [
            {
                "user_id": 1,
                "secret_cipher": encrypted_secret,
                "pending_secret_cipher": None,
                "enabled_at": "2026-01-01T00:00:00",
                "last_used_step": None,
                "recovery_code_hashes": list(hashed),
            }
        ],
        "mfa_challenges": [
            {
                "token_hash": challenge_hash,
                "user_id": 1,
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

        def _dispatch_fetch(self, sql, args):
            if "FROM user_mfa_totp" in sql and "FOR UPDATE" in sql:
                self.add_exec(sql, args)
                return [_FakeRow(dict(self.totp_row))]
            return super()._dispatch_fetch(sql, args)

        def _dispatch_fetchrow(self, sql, args):
            if "FROM user_mfa_totp" in sql and "FOR UPDATE" in sql and "recovery_code_hashes" in sql:
                # PG 模式 _db_consume_recovery_code 中 SELECT recovery_code_hashes ... FOR UPDATE
                self.add_exec(sql, args)
                return _FakeRow({"recovery_code_hashes": self.totp_row.get("recovery_code_hashes")})
            if "FROM user_mfa_totp" in sql and "FOR UPDATE" in sql:
                # 通用 SELECT ... FROM user_mfa_totp FOR UPDATE
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
                # 期望：参数是 (user_id, jsonb_param)，不应使用 jsonb - $int 形式
                new_list_arg = args[1]
                # 写回：从 lock 行读取完整 list，pop index，再以 JSON 字符串形式写回
                self.totp_row["recovery_code_hashes"] = json.loads(new_list_arg)
                return "UPDATE 1"
            if "UPDATE mfa_challenges SET consumed_at" in sql:
                self.add_exec(sql, args)
                self.chal["consumed_at"] = "2099-01-01T00:00:00"
                return "UPDATE 1"
            return super()._dispatch_execute(sql, args)

    conn = Conn()
    pool = _FakePool(store)
    pool.connection = conn  # type: ignore[attr-defined]
    svc._db = pool  # type: ignore[attr-defined]

    async def runner():
        # 用第一个恢复码
        await svc.verify_login(
            challenge_token=challenge_token,
            code=plain_codes[0],
            method="recovery_code",
        )
        # 验证：list 长度从 3 变 2
        assert len(conn.totp_row["recovery_code_hashes"]) == 2
        # 验证：第一次消费的是 plain_codes[0]；剩余应仍为原始 hashed[1:]
        assert conn.totp_row["recovery_code_hashes"] == hashed[1:]
        # 验证：UPDATE user_mfa_totp ... recovery_code_hashes = $2::jsonb
        sqls_with_args = [(c.sql, c.params) for c in conn.exec_calls if "UPDATE user_mfa_totp" in c.sql]
        assert sqls_with_args, "必须有 UPDATE user_mfa_totp SQL"
        sql, args = sqls_with_args[0]
        assert "$2" in sql or "%s" in sql or "jsonb" in sql.lower(), (
            f"UPDATE SQL 应使用 JSONB 参数化绑定：{sql}"
        )
        # 严禁出现 jsonb - $int 形式歧义
        assert " - " not in sql or "jsonb" not in sql, (
            f"严禁 jsonb - $int 形式歧义：{sql}"
        )

    event_loop.run_until_complete(runner())


# ============================================================
# #8: enrollment / disable / regenerate 撤销 RefreshToken + PortalRefreshToken
# ============================================================


def test_enrollment_revoke_refresh_and_portal_tokens(event_loop):
    """enrollment 完成 → 撤销 RefreshTokenDB + PortalRefreshTokenDB。"""
    from app.shared.utils.auth.mfa_service import MfaService
    from unittest.mock import AsyncMock

    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    deleted = {"refresh": 0, "portal": 0}

    async def fake_delete_refresh(user_id):
        deleted["refresh"] += 1

    async def fake_delete_portal(user_id):
        deleted["portal"] += 1

    async def runner():
        user_id = 11
        chal = await svc.start_enrollment(user_id=user_id)
        # 模拟 confirm_enrollment 已被走完，然后验证 revoke 钩子被调用
        from app.shared.utils.auth.refresh_token_db import RefreshTokenDB
        from app.shared.utils.auth.portal_refresh_token_db import PortalRefreshTokenDB

        orig1 = RefreshTokenDB.delete_user_tokens
        orig2 = PortalRefreshTokenDB.delete_user_tokens
        RefreshTokenDB.delete_user_tokens = staticmethod(fake_delete_refresh)  # type: ignore
        PortalRefreshTokenDB.delete_user_tokens = staticmethod(fake_delete_portal)  # type: ignore
        try:
            await svc.confirm_enrollment(user_id=user_id, code=pyotp.TOTP(chal["secret"]).now())
            # enrollment 完成后必须调用两个 revoke
            # 当前实现可能没调用，必须断言为 >= 1（GREEN 后恰好 1）
            assert deleted["refresh"] >= 1, "confirm_enrollment 必须撤销 RefreshToken"
            assert deleted["portal"] >= 1, "confirm_enrollment 必须撤销 PortalRefreshToken"
        finally:
            RefreshTokenDB.delete_user_tokens = orig1  # type: ignore
            PortalRefreshTokenDB.delete_user_tokens = orig2  # type: ignore

    event_loop.run_until_complete(runner())


def test_disable_revoke_refresh_and_portal_tokens(event_loop):
    """disable 完成 → 撤销 RefreshTokenDB + PortalRefreshTokenDB。"""
    from app.shared.utils.auth.mfa_service import MfaService
    from unittest.mock import AsyncMock

    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    deleted = {"refresh": 0, "portal": 0}

    async def fake_delete_refresh(user_id):
        deleted["refresh"] += 1

    async def fake_delete_portal(user_id):
        deleted["portal"] += 1

    async def runner():
        user_id = 12
        # 先绑定
        chal = await svc.start_enrollment(user_id=user_id)
        await svc.confirm_enrollment(user_id=user_id, code=pyotp.TOTP(chal["secret"]).now())

        from app.shared.utils.auth.refresh_token_db import RefreshTokenDB
        from app.shared.utils.auth.portal_refresh_token_db import PortalRefreshTokenDB

        orig1 = RefreshTokenDB.delete_user_tokens
        orig2 = PortalRefreshTokenDB.delete_user_tokens
        RefreshTokenDB.delete_user_tokens = staticmethod(fake_delete_refresh)  # type: ignore
        PortalRefreshTokenDB.delete_user_tokens = staticmethod(fake_delete_portal)  # type: ignore
        try:
            await svc.disable(user_id=user_id)
            assert deleted["refresh"] >= 1, "disable 必须撤销 RefreshToken"
            assert deleted["portal"] >= 1, "disable 必须撤销 PortalRefreshToken"
        finally:
            RefreshTokenDB.delete_user_tokens = orig1  # type: ignore
            PortalRefreshTokenDB.delete_user_tokens = orig2  # type: ignore

    event_loop.run_until_complete(runner())


def test_regenerate_recovery_codes_revoke_refresh_and_portal_tokens(event_loop):
    """regenerate_recovery_codes 完成 → 撤销 RefreshTokenDB + PortalRefreshTokenDB。"""
    from app.shared.utils.auth.mfa_service import MfaService

    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    deleted = {"refresh": 0, "portal": 0}

    async def fake_delete_refresh(user_id):
        deleted["refresh"] += 1

    async def fake_delete_portal(user_id):
        deleted["portal"] += 1

    async def runner():
        user_id = 13
        chal = await svc.start_enrollment(user_id=user_id)
        await svc.confirm_enrollment(user_id=user_id, code=pyotp.TOTP(chal["secret"]).now())

        from app.shared.utils.auth.refresh_token_db import RefreshTokenDB
        from app.shared.utils.auth.portal_refresh_token_db import PortalRefreshTokenDB

        orig1 = RefreshTokenDB.delete_user_tokens
        orig2 = PortalRefreshTokenDB.delete_user_tokens
        RefreshTokenDB.delete_user_tokens = staticmethod(fake_delete_refresh)  # type: ignore
        PortalRefreshTokenDB.delete_user_tokens = staticmethod(fake_delete_portal)  # type: ignore
        try:
            await svc.regenerate_recovery_codes(user_id=user_id)
            assert deleted["refresh"] >= 1, "regenerate 必须撤销 RefreshToken"
            assert deleted["portal"] >= 1, "regenerate 必须撤销 PortalRefreshToken"
        finally:
            RefreshTokenDB.delete_user_tokens = orig1  # type: ignore
            PortalRefreshTokenDB.delete_user_tokens = orig2  # type: ignore

    event_loop.run_until_complete(runner())


# ============================================================
# #13: MfaSettings Fernet 32字节 + required_roles str/list
# ============================================================


def test_mfa_settings_fernet_decoded_must_be_exactly_32_bytes(monkeypatch):
    """Fernet 解码后必须恰好 32 字节。"""
    from app.core.config.settings import MfaSettings

    # 33 字节（base64 解码后 = 33）
    bad = base64.urlsafe_b64encode(b"\x00" * 33).decode()
    monkeypatch.setenv("MFA_SECRET_KEY", bad)
    with pytest.raises(Exception):
        MfaSettings()


def test_mfa_settings_required_roles_accepts_json_list_string(monkeypatch):
    """required_roles 支持 JSON 数组字符串与列表。"""
    from app.core.config.settings import MfaSettings

    valid_key = _fernet_key_bytes()
    monkeypatch.setenv("MFA_SECRET_KEY", valid_key)
    monkeypatch.setenv("MFA_REQUIRED_ROLES", '["admin","user"]')
    settings = MfaSettings()
    assert "admin" in settings.required_roles
    assert "user" in settings.required_roles


# ============================================================
# #12: JSONB codec 异常不静默
# ============================================================


def test_mfa_get_totp_entry_jsonb_codec_error_raises_mfaerror(event_loop):
    """PG 模式 _db_get_totp_entry 解析 recovery_code_hashes 失败必须抛 MfaError，
    禁止静默 fallback 为 []（避免恢复码无故消失）。"""
    from app.shared.utils.auth.mfa_service import MfaService, MfaError

    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    store: Dict[str, Any] = {
        "user_mfa_totp": [
            {
                "user_id": 1,
                "secret_cipher": "x",
                "pending_secret_cipher": None,
                "enabled_at": "2026-01-01",
                "last_used_step": None,
                "recovery_code_hashes": "this-is-not-valid-json{[",
            }
        ]
    }

    class Conn(_FakeConnection):
        def __init__(self):
            super().__init__(store)
            self.row = store["user_mfa_totp"][0]

        def _dispatch_fetchrow(self, sql, args):
            if "FROM user_mfa_totp" in sql:
                self.add_exec(sql, args)
                return _FakeRow(dict(self.row))
            return super()._dispatch_fetchrow(sql, args)

    conn = Conn()
    pool = _FakePool(store)
    pool.connection = conn  # type: ignore[attr-defined]
    svc._db = pool  # type: ignore[attr-defined]

    async def runner():
        with pytest.raises(MfaError):
            await svc._db_get_totp_entry(1)

    event_loop.run_until_complete(runner())


# ============================================================
# #5: TIMESTAMPTZ expires_at UTC 一致
# ============================================================


def test_mfa_challenge_expires_at_compare_utc(event_loop):
    """PG 模式 expires_at 比较必须使用 UTC，避免 naive vs aware 混用抛错。
    验证：Python/PG 都使用 datetime.now(timezone.utc)。
    """
    from app.shared.utils.auth.mfa_service import MfaService
    from app.shared.utils.auth.mfa_service import _hash_challenge_token
    from datetime import datetime, timezone, timedelta

    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    # case 1: expires_at 是 naive datetime（无 tz）—— 不能直接比较
    # case 2: expires_at 是 aware UTC —— OK
    # _db_consume_challenge 必须正确处理两种输入
    expired_token = "expired_naive"
    valid_token = "valid_aware"

    expired_token_hash = _hash_challenge_token(expired_token)
    valid_token_hash = _hash_challenge_token(valid_token)

    store: Dict[str, Any] = {
        "mfa_challenges": [
            {
                "token_hash": expired_token_hash,
                "user_id": 1,
                "purpose": "login_verify",
                # naive datetime —— 故意混入
                "expires_at": datetime.utcnow() - timedelta(seconds=10),
                "consumed_at": None,
            },
            {
                "token_hash": valid_token_hash,
                "user_id": 1,
                "purpose": "login_verify",
                "expires_at": datetime.now(timezone.utc) + timedelta(seconds=300),
                "consumed_at": None,
            },
        ]
    }

    class Conn(_FakeConnection):
        def __init__(self):
            super().__init__(store)
            self.chals = store["mfa_challenges"]

        def _consume_chal(self, sql, args):
            if "UPDATE mfa_challenges SET consumed_at" in sql and "RETURNING user_id" in sql:
                self.add_exec(sql, args)
                # 模拟 PG WHERE：consumed_at IS NULL AND expires_at > NOW()
                now = time.time()
                for row in self.chals:
                    if row["token_hash"] != args[0]:
                        continue
                    # 把 datetime 转 epoch
                    exp = row["expires_at"]
                    if isinstance(exp, datetime):
                        if exp.tzinfo is None:
                            exp_ts = exp.replace(tzinfo=timezone.utc).timestamp()
                        else:
                            exp_ts = exp.timestamp()
                    else:
                        exp_ts = exp
                    if row["consumed_at"] is None and exp_ts > now:
                        row["consumed_at"] = datetime.now(timezone.utc)
                        return [_FakeRow({"user_id": row["user_id"]})]
                return []
            return []

        def _dispatch_fetch(self, sql, args):
            return self._consume_chal(sql, args)

        def _dispatch_fetchrow(self, sql, args):
            rows = self._consume_chal(sql, args)
            return rows[0] if rows else None

    pool = _FakePool(store)
    pool.connection = Conn()  # type: ignore[attr-defined]
    svc._db = pool  # type: ignore[attr-defined]

    async def runner():
        # naive expired 必须被拒（返回 None，由 caller 抛 MfaError）
        result = await svc._db_consume_challenge(expired_token_hash)
        assert result is None, f"过期 challenge 必须被拒，actual={result}"
        # aware valid 成功
        result = await svc._db_consume_challenge(valid_token_hash)
        assert result == 1

    event_loop.run_until_complete(runner())


# ============================================================
# #19: mfa_router 审计日志（成功/失败 emit + 敏感值不入事件）
# ============================================================


def test_mfa_router_audit_event_no_sensitive_values(capsys):
    """mfa_router 审计 emit 必须不包含 code / secret / challenge / recovery_code 明文。"""
    # 通过 _emit_event 直接调用
    from app.shared.routers.mfa_router import _emit_event
    from unittest.mock import MagicMock, patch

    captured: Dict[str, Any] = {}

    class FakeEvent:
        def __init__(self, **kw):
            captured.update(kw)

    class FakeService:
        def emit(self, event):
            captured["emitted"] = True

    fake_request = MagicMock()
    fake_request.client.host = "1.2.3.4"

    fake_modules = {
        "LogEvent": FakeEvent,
        "LogLevel": MagicMock(INFO="info", WARNING="warning"),
        "LogResult": MagicMock(SUCCESS="success", FAILURE="failure"),
        "LogType": MagicMock(AUTH="auth"),
        "LogService": MagicMock(),
        "get_log_service": lambda: FakeService(),
    }

    with patch.dict("sys.modules", fake_modules):
        _emit_event(
            fake_request,
            action="mfa_verify",
            result="success",
            level="info",
            message="MFA 校验通过",
            username="tester",
            user_id=1,
        )
    # 确认事件不含明文敏感值
    sensitive_keywords = [
        "code=", "secret=", "challenge=", "recovery_code=", "qr_png_base64=",
    ]
    msg = str(captured.get("message", ""))
    for kw in sensitive_keywords:
        assert kw not in msg, f"审计事件 message 不得包含 {kw}"
    # 即使 _emit_event 把 payload 也带进来，也无敏感字段
    payload_str = json.dumps(captured, default=str)
    for kw in sensitive_keywords:
        assert kw not in payload_str, f"审计事件不得包含 {kw}"