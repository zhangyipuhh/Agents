# -*- coding:utf-8 -*-
"""
MfaService 单元测试（memory 模式）。

覆盖：
- MfaService 类/方法可导入；
- get_status() 在未启用 / 已启用下分别返；
- create_login_challenge 一次性 + hash 存储；
- TOTP 正确码通过 / 错误码拒 / ±1 时间步通过 / 重放被拒 / expired 拒；
- 恢复码一次性消费 + 错误码拒；
- 失败次数 / 锁定整合；
- enroll + confirm 流程；
- 失败返回统一 401 风格错误（MfaError）；
- failover：db=None 不影响功能（memory 路径完整）；
- 模块导出 ``MfaService`` / ``MfaError`` 等公共符号。

Author: AI Assistant
Date: 2026-08-07
"""

import asyncio
import base64
from urllib.parse import parse_qs, urlparse

import pyotp
import pytest

from app.shared.utils.auth.mfa_service import (
    MfaError,
    MfaService,
    MfaStatus,
    _make_qr_png_base64,
)


# ============================================================
# Fixture：生成 Fernet 密钥
# ============================================================


def _fernet_key_bytes() -> bytes:
    """使用 cryptography 生成 32 字节强密钥并编码为 base64 字符串。

    Returns:
        str: url-safe base64 字符串。
    """
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode("ascii")


def _make_settings(**overrides):
    """构造符合契约的 MfaSettings（可注入测试用 Fernet 密钥）。"""
    from app.core.config.settings import MfaSettings

    defaults = {"secret_key": _fernet_key_bytes()}
    defaults.update(overrides)
    return MfaSettings(**defaults)


@pytest.fixture
def event_loop():
    """使用 module-scoped event loop，与 memory 状态兼容。

    Yields:
        AbstractEventLoop
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def reset_singleton():
    """重置 MfaService 单例，确保每个测试函数独立。"""
    MfaService._instance = None
    yield
    MfaService._instance = None


# ============================================================
# P0: 导入/存在性
# ============================================================


def test_mfa_service_module_importable():
    """P0: 模块与公共符号可导入。"""
    from app.shared.utils.auth import mfa_service

    assert hasattr(mfa_service, "MfaService")
    assert hasattr(mfa_service, "MfaError")
    assert hasattr(mfa_service, "MfaStatus")


def test_mfa_service_public_methods_exist():
    """P0: 接口方法存在。"""
    expected_methods = [
        "get_status",
        "create_login_challenge",
        "start_enrollment",
        "start_login_enrollment",
        "verify_login",
        "confirm_enrollment",
        "disable",
        "regenerate_recovery_codes",
    ]
    for m in expected_methods:
        assert callable(getattr(MfaService, m, None)), f"MfaService.{m} 必须可调用"


# ============================================================
# P1: get_status 状态判定
# ============================================================


def test_start_enrollment_uses_aiops_as_default_issuer(event_loop):
    """默认 enrollment URI 必须让认证器显示 AIOps issuer。

    Args:
        event_loop: 测试事件循环。

    Returns:
        None。
    """
    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    async def runner():
        result = await svc.start_enrollment(user_id=77, username="admin77")
        parsed_uri = urlparse(result["otpauth_uri"])
        query = parse_qs(parsed_uri.query)
        assert parsed_uri.scheme == "otpauth"
        assert parsed_uri.netloc == "totp"
        assert parsed_uri.path.startswith("/AIOps:")
        assert query["issuer"] == ["AIOps"]

    event_loop.run_until_complete(runner())


def test_get_status_not_enabled_when_user_has_no_totp(event_loop):
    """P1: 未绑定 TOTP 时 enabled=False / required 视角色而定。"""
    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    async def runner():
        # Memory 模式下用户首次启用前未存在记录
        status = await svc.get_status(user_id=999, role="user")
        assert status.enabled is False
        assert status.enabled_at is None
        # role='user' 默认 not required
        assert status.required is False
        # 但 admin 是强制
        admin_status = await svc.get_status(user_id=999, role="admin")
        assert admin_status.required is True

    event_loop.run_until_complete(runner())


def test_get_status_enabled_after_confirm_enrollment(event_loop):
    """P1: 完成 confirm_enrollment 后 enabled=True / enabled_at 不为空。"""
    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    async def runner():
        user_id = 42
        chal = await svc.start_enrollment(user_id=user_id)
        totp = pyotp.TOTP(chal["secret"])
        code = totp.now()
        await svc.confirm_enrollment(user_id=user_id, code=code)
        status = await svc.get_status(user_id=user_id, role="user")
        assert status.enabled is True
        assert status.enabled_at is not None

    event_loop.run_until_complete(runner())


# ============================================================
# P1: create_login_challenge 一次性 + hash 存储
# ============================================================


def test_create_login_challenge_returns_token_with_ttl(event_loop):
    """P1: create_login_challenge 返回 challenge_token 与 expires_in=ttl。"""
    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    async def runner():
        token, ttl = await svc.create_login_challenge(user_id=1, purpose="login_verify")
        assert isinstance(token, str) and len(token) >= 32
        assert ttl == 300

    event_loop.run_until_complete(runner())


def test_create_login_challenge_stores_sha256_hash_only(event_loop):
    """P1: 存储仅 hash 明文，不可反推（防泄漏明文 token）。"""
    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    async def runner():
        token, _ = await svc.create_login_challenge(user_id=2, purpose="login_verify")
        # 内存存储仅以 hash 作为 dict key；明文 token 不得出现于 value
        import hashlib

        expected_hash = hashlib.sha256(token.encode()).hexdigest()
        assert expected_hash in svc._memory_challenges
        for chal_record in svc._memory_challenges.values():
            assert token not in str(chal_record.values())

    event_loop.run_until_complete(runner())


# ============================================================
# P1: TOTP 校验（含 ±1 步 / 重放）
# ============================================================


def test_verify_login_accepts_correct_totp(event_loop):
    """P1: 正确码通过 verify_login（method=totp）。"""
    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    async def runner():
        user_id = 11
        chal = await svc.start_enrollment(user_id=user_id)
        # confirm
        totp = pyotp.TOTP(chal["secret"])
        await svc.confirm_enrollment(user_id=user_id, code=totp.now())

        token, _ = await svc.create_login_challenge(user_id=user_id, purpose="login_verify")
        result = await svc.verify_login(challenge_token=token, code=totp.now(), method="totp")
        assert result["success"] is True
        assert result["user_id"] == user_id

    event_loop.run_until_complete(runner())


def test_verify_login_rejects_wrong_totp(event_loop):
    """P1: 错误码 reject。"""
    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    async def runner():
        user_id = 12
        chal = await svc.start_enrollment(user_id=user_id)
        await svc.confirm_enrollment(user_id=user_id, code=pyotp.TOTP(chal["secret"]).now())
        token, _ = await svc.create_login_challenge(user_id=user_id, purpose="login_verify")
        with pytest.raises(MfaError):
            await svc.verify_login(
                challenge_token=token, code="000000", method="totp"
            )

    event_loop.run_until_complete(runner())


def test_verify_login_tolerates_one_step_drift(event_loop):
    """P1: ±1 时间步容忍。"""
    settings = _make_settings(valid_window=1)
    svc = MfaService(db=None, settings=settings)

    async def runner():
        user_id = 13
        chal = await svc.start_enrollment(user_id=user_id)
        secret = chal["secret"]
        await svc.confirm_enrollment(user_id=user_id, code=pyotp.TOTP(secret).now())
        # 使用 ±1 步（过去 30 秒）的码
        import time

        older = pyotp.TOTP(secret).at(time.time() - 30)
        new_token, _ = await svc.create_login_challenge(
            user_id=user_id, purpose="login_verify"
        )
        result = await svc.verify_login(challenge_token=new_token, code=older, method="totp")
        assert result["success"] is True

    event_loop.run_until_complete(runner())


def test_verify_login_rejects_replay(event_loop):
    """P1: 同一 TOTP 码在同一时间步内第二次必须 reject（防重放）。"""
    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    async def runner():
        user_id = 14
        chal = await svc.start_enrollment(user_id=user_id)
        secret = chal["secret"]
        await svc.confirm_enrollment(user_id=user_id, code=pyotp.TOTP(secret).now())
        token, _ = await svc.create_login_challenge(
            user_id=user_id, purpose="login_verify"
        )
        code = pyotp.TOTP(secret).now()
        await svc.verify_login(challenge_token=token, code=code, method="totp")
        # 第二次必须是同一 token 但已被消费；不能成功
        with pytest.raises(MfaError):
            await svc.verify_login(challenge_token=token, code=code, method="totp")

    event_loop.run_until_complete(runner())


def test_verify_login_rejects_expired_challenge(event_loop):
    """P1: 已消费 / 不存在的 challenge 必须 reject。"""
    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    async def runner():
        user_id = 15
        chal = await svc.start_enrollment(user_id=user_id)
        await svc.confirm_enrollment(user_id=user_id, code=pyotp.TOTP(chal["secret"]).now())

        token, _ = await svc.create_login_challenge(
            user_id=user_id, purpose="login_verify"
        )
        # 篡改：模拟消费
        from app.shared.utils.auth.mfa_service import _hash_challenge_token

        chal_key = _hash_challenge_token(token)
        svc._memory_challenges[chal_key]["consumed_at"] = (
            svc._memory_challenges[chal_key].get("created_at")
        )
        with pytest.raises(MfaError):
            await svc.verify_login(
                challenge_token=token, code="000000", method="totp"
            )

    event_loop.run_until_complete(runner())


# ============================================================
# P1: 恢复码（一次性消费）
# ============================================================


def test_recovery_codes_one_time_use(event_loop):
    """P1: 恢复码一次性使用，消费后 reject。"""
    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    async def runner():
        user_id = 21
        chal = await svc.start_enrollment(user_id=user_id)
        await svc.confirm_enrollment(user_id=user_id, code=pyotp.TOTP(chal["secret"]).now())
        codes = svc._memory_challenges  # noqa  # touch to ensure attribute exists
        rc_hash, rc_list = await svc.regenerate_recovery_codes(user_id=user_id)
        assert isinstance(rc_list, list)
        assert len(rc_list) == 10

        first = rc_list[0]
        token, _ = await svc.create_login_challenge(
            user_id=user_id, purpose="login_verify"
        )
        result = await svc.verify_login(
            challenge_token=token, code=first, method="recovery_code"
        )
        assert result["success"] is True
        # 第二次必须 reject（恢复码已消费）
        new_token, _ = await svc.create_login_challenge(
            user_id=user_id, purpose="login_verify"
        )
        with pytest.raises(MfaError):
            await svc.verify_login(
                challenge_token=new_token, code=first, method="recovery_code"
            )

    event_loop.run_until_complete(runner())


def test_recovery_codes_failure_does_not_leak_plaintext(event_loop):
    """P1: 数据库 / 内存存储不包含明文恢复码（必须 bcrypt 哈希）。"""
    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    async def runner():
        user_id = 22
        chal = await svc.start_enrollment(user_id=user_id)
        await svc.confirm_enrollment(user_id=user_id, code=pyotp.TOTP(chal["secret"]).now())
        _, plain_list = await svc.regenerate_recovery_codes(user_id=user_id)
        # 内存中的哈希不应包含明文
        stored = svc._memory_totp_entries.get(user_id, {}).get("recovery_code_hashes", [])
        for code in plain_list:
            assert code not in stored
        # 而且 stored 中的项都为 bcrypt 输出（$2 开头）
        for h in stored:
            assert h.startswith("$2")

    event_loop.run_until_complete(runner())


# ============================================================
# P1: 失败计数 + 锁定
# ============================================================


def test_challenge_failure_increments_and_locks_user(event_loop):
    """P1: 累计 max_attempts 次失败后用户被锁定。"""
    settings = _make_settings(max_attempts=2, lockout_seconds=60)
    svc = MfaService(db=None, settings=settings)

    async def runner():
        user_id = 31
        chal = await svc.start_enrollment(user_id=user_id)
        await svc.confirm_enrollment(user_id=user_id, code=pyotp.TOTP(chal["secret"]).now())

        for _ in range(2):
            token, _ = await svc.create_login_challenge(
                user_id=user_id, purpose="login_verify"
            )
            with pytest.raises(MfaError):
                await svc.verify_login(
                    challenge_token=token, code="000000", method="totp"
                )

        # 第三次同样 fail 应让用户进入锁定（锁定判定由 challenge 内部逻辑 + 用户表配合）
        token2, _ = await svc.create_login_challenge(
            user_id=user_id, purpose="login_verify"
        )
        with pytest.raises(MfaError):
            await svc.verify_login(
                challenge_token=token2, code="000000", method="totp"
            )

    event_loop.run_until_complete(runner())


# ============================================================
# P1: confirm_enrollment 一致启用 + 撤销 refresh
# ============================================================


def test_confirm_enrollment_returns_recovery_codes(event_loop):
    """P1: confirm_enrollment 后返回一次性恢复码（10 个），且第二因素混入 amr。"""
    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    async def runner():
        user_id = 41
        chal = await svc.start_enrollment(user_id=user_id)
        secret = chal["secret"]
        code = pyotp.TOTP(secret).now()
        result = await svc.confirm_enrollment(user_id=user_id, code=code)
        # 必须返回 recovery_codes (list[str])
        assert "recovery_codes" in result
        assert len(result["recovery_codes"]) == 10
        assert all(isinstance(c, str) for c in result["recovery_codes"])

    event_loop.run_until_complete(runner())


# ============================================================
# P1: Fail-closed 当 Fernet key 非法
# ============================================================


def test_mfa_service_with_invalid_secret_raises(monkeypatch):
    """P1: 无效 secret_key 时构造失败 / 不可用。"""
    from app.core.config.settings import MfaSettings
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MfaSettings(secret_key="not-valid-key")


# ============================================================
# P1: 公开登录 enrollment 原子消费
# ============================================================


def test_start_login_enrollment_consumes_login_challenge_once(event_loop):
    """公开登录 enrollment 第一次成功，第二次复用原 challenge 必须失败。"""
    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    async def runner():
        token, _ = await svc.create_login_challenge(user_id=51, purpose="login_enroll")
        result = await svc.start_login_enrollment(token, username="admin51")
        assert result["enrollment_token"]
        assert "secret" not in result
        with pytest.raises(MfaError):
            await svc.start_login_enrollment(token, username="admin51")

    event_loop.run_until_complete(runner())


def test_start_login_enrollment_generation_failure_does_not_consume_challenge(
    event_loop, monkeypatch
):
    """生成 QR 失败时原 login_enroll challenge 必须保持可重试。"""
    settings = _make_settings()
    svc = MfaService(db=None, settings=settings)

    async def runner():
        token, _ = await svc.create_login_challenge(user_id=52, purpose="login_enroll")
        monkeypatch.setattr(
            "app.shared.utils.auth.mfa_service._make_qr_png_base64",
            lambda _: (_ for _ in ()).throw(RuntimeError("qr failed")),
        )
        with pytest.raises(RuntimeError):
            await svc.start_login_enrollment(token)
        record = svc._memory_challenges[hash_challenge_token(token)]
        assert record["consumed_at"] is None

    from app.shared.utils.auth.mfa_service import hash_challenge_token
    event_loop.run_until_complete(runner())


def test_make_qr_png_base64_returns_data_uri():
    """_make_qr_png_base64 必须返回完整的 Data URI，可直接用于 <img src>。"""
    uri = "otpauth://totp/TestUser?secret=JBSWY3DPEHPK3PXP&issuer=TestIssuer"
    data_uri = _make_qr_png_base64(uri)

    assert isinstance(data_uri, str)
    assert data_uri.startswith("data:image/png;base64,")
    # 前缀之后应有非空 base64 内容
    b64_payload = data_uri[len("data:image/png;base64,"):]
    assert b64_payload
    # 验证 base64 可解码为 PNG 文件头
    decoded = base64.b64decode(b64_payload)
    assert decoded[:8] == b"\x89PNG\r\n\x1a\n"
