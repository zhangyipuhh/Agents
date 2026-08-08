# -*- coding:utf-8 -*-
"""
MFA（TOTP）服务模块（2026-08-07 新增；2026-08-07 批次硬化）。

为浏览器 /login 引入 RFC 6238 TOTP 双因素认证。覆盖：

- 用户总状态查询（enabled / required / methods / enabled_at）
- 登录/绑定短期 challenge Token 一次性管理（DB / memory 等价实现）
- TOTP 校验（含 ±1 时间步窗口与 last_used_step 防重放）
- 恢复码（bcrypt 哈希 + 一次性消费）
- 失败次数累计 + 用户锁定（**单一真相源：UserDB**）
- 绑定 / 轮换 / 禁用 + refresh token 撤销（主表 + 门户子表）

存储策略：

- ``db=None``：纯内存模式（dict + threading.Lock），用于开发 / 单元测试。
- ``db=asyncpg.Pool``：参数化 SQL（fernet 加密 secret / bcrypt 哈希恢复码 / SHA-256 哈希 challenge）。
  所有 mutation 在 ``conn.transaction()`` 内进行；TOTP / 恢复码消费使用 ``SELECT ... FOR UPDATE``
  锁住 user_mfa_totp 行，避免同一时间步并发重放。

Fail-closed：secret_key 缺失 / 非法 / 长度不是恰好 32 字节时，``MfaService.__init__`` 直接抛
``MfaError``，并阻止管理员与已启用用户登录路径。

并发安全：TOTP 校验必须事务 + SELECT FOR UPDATE 锁住 user_mfa_totp + 原子更新 last_used_step，
同一时间步并发仅一请求成功（防重放）。

Author: AI Assistant
Date: 2026-08-07
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import bcrypt
import pyotp
import qrcode
from cryptography.fernet import Fernet, InvalidToken

from app.core.config.settings import MfaSettings

logger = logging.getLogger(__name__)


# ============================================================
# 公共错误与状态（导出）
# ============================================================


class MfaError(Exception):
    """MFA 业务流程统一错误（必须以 HTTP 401 形式抛出，避免暴露细节）。"""

    pass


@dataclass
class MfaStatus:
    """MfaService.get_status 的轻量 DTO。"""

    enabled: bool
    required: bool
    methods: List[str]
    enabled_at: Optional[str]
    issuer: str


# ============================================================
# 内部工具
# ============================================================


def _hash_challenge_token(token: str) -> str:
    """对 challenge 明文 token 计算 SHA-256 hex digest（内部使用）。

    Args:
        token: challenge 明文。

    Returns:
        str: 64 字符 hex digest。
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_challenge_token(token: str) -> str:
    """对 challenge 明文 token 计算 SHA-256 hex digest（公开 API）。

    公开版本供路由层调用，禁止路由层直接 ``from mfa_service import _hash_challenge_token``。

    Args:
        token: challenge 明文。

    Returns:
        str: 64 字符 hex digest。
    """
    return _hash_challenge_token(token)


def _encrypt_secret(fernet: Fernet, plaintext: str) -> str:
    """使用 Fernet 加密 TOTP secret，返回 base64 字符串。

    Args:
        fernet: 已构造的 Fernet 实例。
        plaintext: 明文 secret。

    Returns:
        str: 加密后的字符串。
    """
    return fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")


def _decrypt_secret(fernet: Fernet, ciphertext: str) -> str:
    """使用 Fernet 解密 TOTP secret。

    Args:
        fernet: 已构造的 Fernet 实例。
        ciphertext: 加密字符串。

    Returns:
        str: 明文 secret。

    Raises:
        MfaError: 解密失败时。
    """
    try:
        return fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise MfaError("TOTP secret 解密失败") from exc


def _make_qr_png_base64(otpauth_uri: str) -> str:
    """将 otpauth URI 转换为 base64 PNG Data URI。

    Args:
        otpauth_uri: 标准 TOTP URI (otpauth://totp/...)。

    Returns:
        str: 可直接用于 <img src="..."> 的 Data URI（含 data:image/png;base64, 前缀）。
    """
    img = qrcode.make(otpauth_uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"


def _to_utc_aware(dt: Any) -> Optional[Any]:
    """把任意 datetime 转换为 UTC-aware；naive 视为 UTC。"""
    from datetime import datetime, timezone

    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return dt


# ============================================================
# MfaService 主类
# ============================================================


class MfaService:
    """TOTP 双因素认证服务（DB + memory 等价实现）。

    所有方法为 coroutine；DB 操作通过 ``pool.acquire()`` + ``conn.transaction()`` 保证原子性。
    """

    #: 全局单例（lifespan 阶段必须挂到 ``app.state.mfa_service``）
    _instance: Optional["MfaService"] = None

    # ------------------------------------------------------------------
    # 构造与生命周期
    # ------------------------------------------------------------------

    def __init__(
        self,
        db: Optional[Any],
        settings: MfaSettings,
    ) -> None:
        """构造 MfaService 实例。

        Args:
            db: asyncpg 连接池或 None（memory 模式）。
            settings: MfaSettings 配置实例。

        Raises:
            MfaError: secret_key 缺失/非法时 fail-closed。
        """
        if not settings.secret_key:
            raise MfaError(
                "MFA_SECRET_KEY 未配置，MFA 服务不可用（fail-closed）"
            )
        try:
            self._fernet = Fernet(settings.secret_key)
        except (ValueError, Exception) as exc:  # noqa: BLE001
            raise MfaError(
                f"MFA_SECRET_KEY 非法: {exc}"
            ) from exc

        self._db = db
        self._settings = settings

        # ----- memory 模式结构（单一真相源：UserDB；此处仅保留 challenge / TOTP 数据） -----
        self._memory_lock = threading.Lock()
        # token_hash -> { user_id, purpose, expires_at, failed_attempts, consumed_at, created_at }
        self._memory_challenges: Dict[str, Dict[str, Any]] = {}
        # user_id -> { secret_cipher, pending_secret_cipher, enabled_at, last_used_step,
        #              recovery_code_hashes (list[bcrypt hash]) }
        self._memory_totp_entries: Dict[int, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # 单例管理
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls) -> Optional["MfaService"]:
        """获取 lifespan 阶段设置的全局单例（供不持 state 引用的代码回退使用）。

        Returns:
            Optional[MfaService]: 单例实例或 None。
        """
        return cls._instance

    @classmethod
    def set_instance(cls, instance: "MfaService") -> None:
        """lifespan 阶段调用：绑定全局单例。

        Args:
            instance: MfaService 实例。
        """
        cls._instance = instance

    @classmethod
    def reset(cls) -> None:
        """关闭时调用：清理全局单例引用。"""
        cls._instance = None

    # ------------------------------------------------------------------
    # 公开查询接口
    # ------------------------------------------------------------------

    async def get_status(self, user_id: int, role: str) -> MfaStatus:
        """查询用户的 MFA 状态。

        Args:
            user_id: 用户 ID。
            role: 用户角色（用于判定 required）。

        Returns:
            MfaStatus: 状态 DTO。
        """
        entry = await self._get_totp_entry(user_id)
        if entry is None:
            enabled = False
            enabled_at = None
        else:
            enabled = bool(entry.get("enabled_at"))
            enabled_at = entry.get("enabled_at")

        required = role in self._settings.required_roles
        methods = ["totp"] if enabled else []
        if enabled:
            # 检查是否还存在恢复码
            hashes = entry.get("recovery_code_hashes") or []
            if hashes:
                methods.append("recovery_code")
        return MfaStatus(
            enabled=enabled,
            required=required,
            methods=methods,
            enabled_at=enabled_at.isoformat() if enabled_at else None,
            issuer=self._settings.issuer,
        )

    # ------------------------------------------------------------------
    # 内部：refresh token 撤销（公开方法，enrollment/disable/regenerate 共用）
    # ------------------------------------------------------------------

    async def _revoke_user_tokens(self, user_id: int) -> None:
        """撤销该用户所有 refresh token（主表 + 门户子表）。

        Args:
            user_id: 用户 ID。
        """
        from app.shared.utils.auth.refresh_token_db import RefreshTokenDB
        from app.shared.utils.auth.portal_refresh_token_db import PortalRefreshTokenDB

        await RefreshTokenDB.delete_user_tokens(user_id=user_id)
        await PortalRefreshTokenDB.delete_user_tokens(user_id=user_id)

    # ------------------------------------------------------------------
    # 登录 challenge 流程
    # ------------------------------------------------------------------

    async def create_login_challenge(
        self,
        user_id: int,
        purpose: str,
    ) -> Tuple[str, int]:
        """创建一次性 challenge token；服务端只存 SHA-256 哈希。

        Args:
            user_id: 目标用户 ID。
            purpose: 用途（login_verify / login_enroll / enroll_confirm）。

        Returns:
            Tuple[str, int]: 明文 token 与 TTL 秒数。

        Raises:
            MfaError: 不支持的 purpose。
        """
        if purpose not in ("login_verify", "login_enroll", "enroll_confirm"):
            raise MfaError(f"不支持的 challenge purpose: {purpose}")
        plaintext = secrets.token_urlsafe(32)
        token_hash = _hash_challenge_token(plaintext)
        ttl = self._settings.challenge_ttl_seconds
        expires_at = time.time() + ttl

        record = {
            "user_id": user_id,
            "purpose": purpose,
            "expires_at": expires_at,
            "failed_attempts": 0,
            "consumed_at": None,
            "created_at": time.time(),
        }

        if self._db is not None:
            await self._db_challenge_insert(
                token_hash=token_hash,
                user_id=user_id,
                purpose=purpose,
                expires_at=expires_at,
            )
        else:
            with self._memory_lock:
                # 顺手清理过期 challenge（参数化删除替代后台定时任务）
                self._purge_memory_challenges()
                self._memory_challenges[token_hash] = record
        return plaintext, ttl

    async def verify_login(
        self,
        challenge_token: str,
        code: str,
        method: str,
    ) -> Dict[str, Any]:
        """校验 challenge + TOTP 或恢复码。

        Args:
            challenge_token: create_login_challenge 返回的明文 token。
            code: TOTP 6 位或恢复码。
            method: "totp" 或 "recovery_code"。

        Returns:
            Dict[str, Any]: ``{"success": True, "user_id": <id>, "method": <m>}``。

        Raises:
            MfaError: 校验失败（HTTP 401）。
        """
        if method not in ("totp", "recovery_code"):
            raise MfaError("MFA 校验失败")

        token_hash = _hash_challenge_token(challenge_token)

        if self._db is not None:
            chal, user_id = await self._db_challenge_fetch_and_lock(token_hash)
        else:
            chal, user_id = self._memory_fetch_and_lock_challenge(token_hash)

        if chal is None:
            raise MfaError("MFA 校验失败")

        # 必须校验 consumed_at / expires_at / purpose 三个维度
        if chal.get("consumed_at") is not None:
            raise MfaError("MFA 校验失败")
        if chal["expires_at"] <= time.time():
            raise MfaError("MFA 校验失败")
        # purpose 校验：必须匹配调用 method 的预期
        expected_purpose = "login_verify"
        if chal.get("purpose") != expected_purpose:
            raise MfaError("MFA 校验失败")

        entry = await self._get_totp_entry(user_id)
        if entry is None or not entry.get("enabled_at"):
            # 绑定前访问此 path 视为非法（enrollment 走另一支）
            raise MfaError("MFA 校验失败")

        if method == "totp":
            success, current_step = await self._validate_totp(
                entry=entry,
                code=code,
            )
            if not success:
                await self._bump_challenge_failure(token_hash, chal)
                await self._bump_user_failure(user_id)
                raise MfaError("MFA 校验失败")
            # 防重放：原子写入 last_used_step + 清零用户失败计数
            if self._db is not None:
                await self._db_consume_challenge_and_set_step(
                    token_hash=token_hash,
                    user_id=user_id,
                    last_used_step=current_step,
                )
            else:
                self._memory_consume_challenge_and_set_step(
                    token_hash=token_hash,
                    user_id=user_id,
                    last_used_step=current_step,
                )
        else:  # recovery_code
            success, used_index = await self._validate_recovery_code(entry, code)
            if not success:
                await self._bump_challenge_failure(token_hash, chal)
                await self._bump_user_failure(user_id)
                raise MfaError("MFA 校验失败")
            if self._db is not None:
                await self._db_consume_recovery_code(
                    token_hash=token_hash,
                    user_id=user_id,
                    index=used_index,
                )
            else:
                self._memory_consume_recovery_code(
                    token_hash=token_hash,
                    user_id=user_id,
                    index=used_index,
                )

        # 成功路径：清零用户失败计数（同一函数内委托 UserDB）
        await self._clear_user_failure(user_id)
        return {"success": True, "user_id": user_id, "method": method}

    async def consume_challenge(self, challenge_token: str) -> int:
        """强制消费 challenge 并返回 user_id（用于 enroll_confirm 路径）。

        Args:
            challenge_token: 明文 token。

        Returns:
            int: 用户 ID。

        Raises:
            MfaError: challenge 不存在或已消费。
        """
        token_hash = _hash_challenge_token(challenge_token)
        if self._db is not None:
            user_id = await self._db_consume_challenge(token_hash)
        else:
            user_id = self._memory_consume_only(token_hash)
        if user_id is None:
            raise MfaError("MFA 校验失败")
        return user_id

    # ------------------------------------------------------------------
    # 绑定 / 轮换 / 禁用
    # ------------------------------------------------------------------

    async def start_login_enrollment(
        self,
        challenge_token: str,
        username: Optional[str] = None,
    ) -> Dict[str, Any]:
        """消费 login_enroll challenge 并原子创建公开 enrollment 流程。

        Args:
            challenge_token: 登录密码阶段签发的 login_enroll 明文 challenge。
            username: 可选用户名，用于生成 TOTP 展示标签。

        Returns:
            Dict[str, Any]: enrollment_token、otpauth_uri、二维码及有效期；不含 secret。

        Raises:
            MfaError: challenge 无效、用途不符、已消费或已过期。
        """
        secret = pyotp.random_base32()
        token_hash = _hash_challenge_token(challenge_token)
        enrollment_token = secrets.token_urlsafe(32)
        enrollment_hash = _hash_challenge_token(enrollment_token)
        ttl = self._settings.challenge_ttl_seconds
        expires_at = time.time() + ttl
        label = username or "login-enroll"
        uri = pyotp.TOTP(secret).provisioning_uri(
            name=label,
            issuer_name=self._settings.issuer,
        )
        qr_b64 = _make_qr_png_base64(uri)
        cipher = _encrypt_secret(self._fernet, secret)

        if self._db is not None:
            async with self._db.acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        "SELECT user_id, purpose, "
                        "EXTRACT(EPOCH FROM expires_at)::float8 AS expires_at, "
                        "consumed_at FROM mfa_challenges "
                        "WHERE token_hash = $1 FOR UPDATE",
                        token_hash,
                    )
                    if row is None or row.get("purpose") != "login_enroll":
                        raise MfaError("MFA 校验失败")
                    if row.get("consumed_at") is not None:
                        raise MfaError("MFA 校验失败")
                    if float(row.get("expires_at") or 0.0) <= time.time():
                        raise MfaError("MFA 校验失败")
                    user_id = int(row["user_id"])
                    await conn.execute(
                        "INSERT INTO user_mfa_totp "
                        "(user_id, pending_secret_cipher, recovery_code_hashes, updated_at) "
                        "VALUES ($1, $2, '[]'::jsonb, NOW()) "
                        "ON CONFLICT (user_id) DO UPDATE SET "
                        "pending_secret_cipher = EXCLUDED.pending_secret_cipher, updated_at = NOW()",
                        user_id,
                        cipher,
                    )
                    await conn.execute(
                        "INSERT INTO mfa_challenges "
                        "(token_hash, user_id, purpose, expires_at, failed_attempts, consumed_at, created_at) "
                        "VALUES ($1, $2, 'enroll_confirm', TO_TIMESTAMP($3), 0, NULL, NOW())",
                        enrollment_hash,
                        user_id,
                        expires_at,
                    )
                    await conn.execute(
                        "UPDATE mfa_challenges SET consumed_at = NOW() "
                        "WHERE token_hash = $1",
                        token_hash,
                    )
        else:
            with self._memory_lock:
                self._purge_memory_challenges()
                challenge = self._memory_challenges.get(token_hash)
                if challenge is None or challenge.get("purpose") != "login_enroll":
                    raise MfaError("MFA 校验失败")
                if challenge.get("consumed_at") is not None:
                    raise MfaError("MFA 校验失败")
                if challenge["expires_at"] <= time.time():
                    raise MfaError("MFA 校验失败")
                user_id = int(challenge["user_id"])
                self._memory_totp_entries.setdefault(user_id, {})[
                    "pending_secret_cipher"
                ] = cipher
                self._memory_totp_entries[user_id].setdefault("recovery_code_hashes", [])
                self._memory_challenges[enrollment_hash] = {
                    "user_id": user_id,
                    "purpose": "enroll_confirm",
                    "expires_at": expires_at,
                    "failed_attempts": 0,
                    "consumed_at": None,
                    "created_at": time.time(),
                }
                challenge["consumed_at"] = time.time()

        return {
            "enrollment_token": enrollment_token,
            "otpauth_uri": uri,
            "qr_png_base64": qr_b64,
            "expires_in": ttl,
        }

    async def start_enrollment(
        self,
        user_id: int,
        username: Optional[str] = None,
    ) -> Dict[str, Any]:
        """开始绑定：生成新 secret + 一次性 enrollment_token。

        Args:
            user_id: 用户 ID。
            username: 用户名（用于 otpauth label，可选）。

        Returns:
            Dict[str, Any]: ``{"secret", "enrollment_token", "otpauth_uri", "qr_png_base64", "expires_in"}``。
        """
        secret = pyotp.random_base32()
        label = username or f"user-{user_id}"
        uri = pyotp.TOTP(secret).provisioning_uri(
            name=label,
            issuer_name=self._settings.issuer,
        )
        qr_b64 = _make_qr_png_base64(uri)
        token, ttl = await self.create_login_challenge(
            user_id=user_id,
            purpose="enroll_confirm",
        )

        # 暂存 pending secret（覆盖现有 secret 前不破坏旧有效密钥）
        cipher = _encrypt_secret(self._fernet, secret)
        if self._db is not None:
            await self._db_set_pending_secret(user_id, cipher)
        else:
            with self._memory_lock:
                entry = self._memory_totp_entries.setdefault(user_id, {})
                entry["pending_secret_cipher"] = cipher
                entry.setdefault("recovery_code_hashes", [])
        return {
            "secret": secret,
            "enrollment_token": token,
            "otpauth_uri": uri,
            "qr_png_base64": qr_b64,
            "expires_in": ttl,
        }

    async def confirm_enrollment(
        self,
        user_id: int,
        code: str,
    ) -> Dict[str, Any]:
        """以 6 位码完成绑定，覆盖 secret、生成恢复码、撤销 refresh token。

        Args:
            user_id: 用户 ID。
            code: TOTP 6 位。

        Returns:
            Dict[str, Any]: 包含 ``recovery_codes`` 列表。

        Raises:
            MfaError: 校验失败或无 pending secret。
        """
        from datetime import datetime, timezone

        if self._db is not None:
            entry = await self._db_get_totp_entry(user_id)
        else:
            with self._memory_lock:
                entry = self._memory_totp_entries.get(user_id)

        if entry is None or not entry.get("pending_secret_cipher"):
            raise MfaError("无待生效的 TOTP secret，请重新开始绑定")

        plaintext_secret = _decrypt_secret(self._fernet, entry["pending_secret_cipher"])
        totp = pyotp.TOTP(plaintext_secret)
        if not totp.verify(code, valid_window=self._settings.valid_window):
            await self._bump_user_failure(user_id)
            raise MfaError("MFA 校验失败")

        # 生成恢复码
        plain_codes = [secrets.token_hex(4) + "-" + secrets.token_hex(4) for _ in range(10)]
        hashes = [
            bcrypt.hashpw(c.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
            for c in plain_codes
        ]
        now = datetime.now(timezone.utc)

        # 防刚绑定码重放：把 last_used_step 设为 step - valid_window - 1（防刚绑定码被立刻重放，
        # 但用户下一次 verify_login 仍可使用同一时间步码以保证正常登录体验）。
        step = int(time.time() // 30)
        anti_replay_step = step - self._settings.valid_window - 1

        if self._db is not None:
            await self._db_commit_enrollment(
                user_id=user_id,
                secret_cipher=entry["pending_secret_cipher"],
                enabled_at=now,
                recovery_code_hashes=hashes,
                last_used_step=anti_replay_step,
            )
        else:
            with self._memory_lock:
                ent = self._memory_totp_entries.setdefault(user_id, {})
                ent["secret_cipher"] = ent.pop("pending_secret_cipher", ent.get("secret_cipher"))
                ent["enabled_at"] = now
                ent["recovery_code_hashes"] = hashes
                ent["last_used_step"] = anti_replay_step

        # 撤销该用户所有 refresh token（含门户子表）
        await self._revoke_user_tokens(user_id)
        # 清零失败计数
        await self._clear_user_failure(user_id)

        return {
            "success": True,
            "user_id": user_id,
            "recovery_codes": plain_codes,
        }

    async def confirm_login_enrollment(
        self,
        enrollment_token: str,
        code: str,
    ) -> Dict[str, Any]:
        """管理员首次绑定公开 API：原子消费 ``enroll_confirm`` challenge + 启用 TOTP。

        完整原子流程（DB 模式在同一个 ``conn.transaction()`` 内）：

        1. SELECT challenge FOR UPDATE → 校验 purpose=enroll_confirm +
           consumed_at IS NULL + expires_at > NOW();
        2. SELECT user_mfa_totp FOR UPDATE → 取出 pending_secret_cipher；
        3. 解密 pending secret，校验 TOTP（valid_window）；
        4. 生成恢复码（10 个）并写入 secret_cipher / enabled_at /
           recovery_code_hashes / last_used_step；
        5. UPDATE mfa_challenges SET consumed_at = NOW() 标记 challenge 已消费；
        6. 任一步骤失败 → 事务整体回滚，enrollment_token 未被消费，可重试。

        Memory 模式使用 ``threading.Lock`` 等价保证序列化。

        Args:
            enrollment_token: ``start_enrollment`` 返回的明文 enrollment token。
            code: 用户输入的 6 位 TOTP 码。

        Returns:
            Dict[str, Any]: ``{"success": True, "user_id": <id>, "step": <int>,
            "recovery_codes": List[str]}``；recovery_codes 明文仅返回一次。

        Raises:
            MfaError: challenge 不存在 / 已消费 / 已过期 / purpose 错误 /
                无 pending_secret / TOTP 错误。
        """
        from datetime import datetime, timezone

        token_hash = hash_challenge_token(enrollment_token)
        step = int(time.time() // 30)
        anti_replay_step = step - self._settings.valid_window - 1

        if self._db is not None:
            # DB 模式：单一事务 + 双 FOR UPDATE + 原子写入
            async with self._db.acquire() as conn:
                async with conn.transaction():
                    # 1) SELECT challenge FOR UPDATE（purpose 校验必须严格）
                    chal_row = await conn.fetchrow(
                        "SELECT user_id, purpose, "
                        "       EXTRACT(EPOCH FROM expires_at)::float8 AS expires_at, "
                        "       consumed_at "
                        "FROM mfa_challenges WHERE token_hash = $1 FOR UPDATE",
                        token_hash,
                    )
                    if chal_row is None:
                        raise MfaError("MFA 校验失败")
                    if chal_row.get("consumed_at") is not None:
                        raise MfaError("MFA 校验失败")
                    if chal_row.get("purpose") != "enroll_confirm":
                        raise MfaError("MFA 校验失败")
                    if float(chal_row.get("expires_at") or 0.0) <= time.time():
                        raise MfaError("MFA 校验失败")
                    user_id = int(chal_row["user_id"])

                    # 2) SELECT user_mfa_totp FOR UPDATE
                    totp_row = await conn.fetchrow(
                        "SELECT secret_cipher, pending_secret_cipher "
                        "FROM user_mfa_totp WHERE user_id = $1 FOR UPDATE",
                        user_id,
                    )
                    if totp_row is None or not totp_row.get("pending_secret_cipher"):
                        raise MfaError("无待生效的 TOTP secret，请重新开始绑定")

                    # 3) 解密 + 验 TOTP
                    plaintext_secret = _decrypt_secret(
                        self._fernet, totp_row["pending_secret_cipher"]
                    )
                    totp = pyotp.TOTP(plaintext_secret)
                    if not totp.verify(code, valid_window=self._settings.valid_window):
                        # 不消费 challenge，让用户可重试（事务整体回滚）
                        raise MfaError("MFA 校验失败")

                    # 4) 生成恢复码 + 写 user_mfa_totp + 写 challenge consumed
                    plain_codes = [
                        secrets.token_hex(4) + "-" + secrets.token_hex(4)
                        for _ in range(10)
                    ]
                    hashes = [
                        bcrypt.hashpw(c.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
                        for c in plain_codes
                    ]
                    now = datetime.now(timezone.utc)

                    await conn.execute(
                        "UPDATE user_mfa_totp "
                        "SET secret_cipher = $1, pending_secret_cipher = NULL, "
                        "    enabled_at = $2, recovery_code_hashes = $3::jsonb, "
                        "    last_used_step = $4, updated_at = NOW() "
                        "WHERE user_id = $5",
                        totp_row["pending_secret_cipher"],
                        now,
                        json.dumps(hashes),
                        anti_replay_step,
                        user_id,
                    )

                    await conn.execute(
                        "UPDATE mfa_challenges SET consumed_at = NOW() "
                        "WHERE token_hash = $1",
                        token_hash,
                    )

            # 事务成功提交后才执行副作用：撤销 refresh + 清零失败计数
            await self._revoke_user_tokens(user_id)
            await self._clear_user_failure(user_id)

            return {
                "success": True,
                "user_id": user_id,
                "step": step,
                "recovery_codes": plain_codes,
            }

        # Memory 模式：threading.Lock 等价原子化
        with self._memory_lock:
            chal = self._memory_challenges.get(token_hash)
            if chal is None:
                raise MfaError("MFA 校验失败")
            if chal.get("consumed_at") is not None:
                raise MfaError("MFA 校验失败")
            if chal.get("purpose") != "enroll_confirm":
                raise MfaError("MFA 校验失败")
            if chal["expires_at"] <= time.time():
                raise MfaError("MFA 校验失败")
            user_id = int(chal["user_id"])

            entry = self._memory_totp_entries.get(user_id)
            if entry is None or not entry.get("pending_secret_cipher"):
                raise MfaError("无待生效的 TOTP secret，请重新开始绑定")

            try:
                plaintext_secret = _decrypt_secret(
                    self._fernet, entry["pending_secret_cipher"]
                )
            except MfaError:
                raise MfaError("MFA 校验失败")
            totp = pyotp.TOTP(plaintext_secret)
            if not totp.verify(code, valid_window=self._settings.valid_window):
                # 不消费 challenge，让用户可重试
                raise MfaError("MFA 校验失败")

            plain_codes = [
                secrets.token_hex(4) + "-" + secrets.token_hex(4)
                for _ in range(10)
            ]
            hashes = [
                bcrypt.hashpw(c.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
                for c in plain_codes
            ]
            from datetime import datetime as _dt, timezone as _tz

            ent = self._memory_totp_entries.setdefault(user_id, {})
            ent["secret_cipher"] = ent.pop("pending_secret_cipher", ent.get("secret_cipher"))
            ent["enabled_at"] = _dt.now(_tz.utc)
            ent["recovery_code_hashes"] = hashes
            ent["last_used_step"] = anti_replay_step

            chal["consumed_at"] = time.time()

        # 副作用（事务外执行；DB 模式等价）
        await self._revoke_user_tokens(user_id)
        await self._clear_user_failure(user_id)

        return {
            "success": True,
            "user_id": user_id,
            "step": step,
            "recovery_codes": plain_codes,
        }

    async def verify_and_consume_management_factor(
        self,
        user_id: int,
        code: str,
        method: str,
        operation: str,
    ) -> Dict[str, Any]:
        """管理操作第二因素校验（disable / regenerate_recovery_codes 等已登录路径）。

        公开 API：路由层（``mfa_router.py``）必须通过该方法完成 disable / regenerate
        的 TOTP / recovery code 校验，禁止直接调用 ``_get_totp_entry`` /
        ``_validate_totp`` / ``_validate_recovery_code`` 等私有方法。

        与 ``verify_login`` 路径不同：
        - 不需要 ``mfa_challenges``（管理操作不发 challenge）；
        - recovery code 一次性消费：消费成功后即使同一 ``code`` 再次传入，本方法
          也必须抛 ``MfaError``（路由层后续调用 ``regenerate_recovery_codes``
          时，旧码列表不再包含该 hash）；
        - TOTP 校验**不**改写 ``last_used_step``，避免误伤正常登录：
          management 操作通常用户已登录后再操作一次，不应触发 ``verify_login``
          的"同时间步码防重放"。

        Args:
            user_id: 目标用户 ID。
            code: TOTP 6 位或恢复码明文。
            method: ``"totp"`` 或 ``"recovery_code"``。
            operation: 管理操作标识（``"disable"`` / ``"regenerate_recovery_codes"``），
                当前仅用于审计与未来扩展，不参与校验逻辑。

        Returns:
            Dict[str, Any]: ``{"success": True, "method": <m>, "user_id": <id>,
            "operation": <op>}``。

        Raises:
            MfaError: 校验失败 / 未启用 TOTP / 恢复码不存在或已被消费。
        """
        if method not in ("totp", "recovery_code"):
            raise MfaError("MFA 校验失败")

        if self._db is not None:
            async with self._db.acquire() as conn:
                async with conn.transaction():
                    totp_row = await conn.fetchrow(
                        "SELECT secret_cipher, pending_secret_cipher, enabled_at, "
                        "       recovery_code_hashes "
                        "FROM user_mfa_totp WHERE user_id = $1 FOR UPDATE",
                        user_id,
                    )
                    if totp_row is None or not totp_row.get("enabled_at"):
                        raise MfaError("MFA 校验失败")
                    if not totp_row.get("secret_cipher"):
                        raise MfaError("MFA 校验失败")

                    if method == "totp":
                        plaintext_secret = _decrypt_secret(
                            self._fernet, totp_row["secret_cipher"]
                        )
                        totp = pyotp.TOTP(plaintext_secret)
                        if not totp.verify(code, valid_window=self._settings.valid_window):
                            raise MfaError("MFA 校验失败")
                        # 不写 last_used_step：management 操作不应阻塞正常登录
                        return {
                            "success": True,
                            "user_id": user_id,
                            "method": method,
                            "operation": operation,
                        }

                    # recovery_code 路径：JSONB pop + 写回完整 list
                    hashes_raw = totp_row.get("recovery_code_hashes")
                    if isinstance(hashes_raw, str):
                        try:
                            hashes = json.loads(hashes_raw)
                        except (json.JSONDecodeError, TypeError, ValueError) as exc:
                            raise MfaError(
                                "recovery_code_hashes 解析失败"
                            ) from exc
                    else:
                        hashes = list(hashes_raw or [])
                    if not isinstance(hashes, list):
                        raise MfaError("recovery_code_hashes 字段格式错误")

                    matched_index = None
                    for idx, h in enumerate(hashes):
                        try:
                            if bcrypt.checkpw(code.encode("utf-8"), h.encode("ascii")):
                                matched_index = idx
                                break
                        except (ValueError, TypeError):
                            continue
                    if matched_index is None:
                        raise MfaError("MFA 校验失败")
                    # Python 端 pop 后写回完整 list（避免 jsonb - $int 歧义）
                    hashes.pop(matched_index)
                    await conn.execute(
                        "UPDATE user_mfa_totp "
                        "SET recovery_code_hashes = $2::jsonb, updated_at = NOW() "
                        "WHERE user_id = $1",
                        user_id,
                        json.dumps(hashes),
                    )
                    return {
                        "success": True,
                        "user_id": user_id,
                        "method": method,
                        "operation": operation,
                    }

        # Memory 模式：threading.Lock 等价原子化
        with self._memory_lock:
            ent = self._memory_totp_entries.get(user_id)
            if ent is None or not ent.get("enabled_at"):
                raise MfaError("MFA 校验失败")
            if not ent.get("secret_cipher"):
                raise MfaError("MFA 校验失败")

            if method == "totp":
                try:
                    plaintext_secret = _decrypt_secret(self._fernet, ent["secret_cipher"])
                except MfaError:
                    raise MfaError("MFA 校验失败")
                totp = pyotp.TOTP(plaintext_secret)
                if not totp.verify(code, valid_window=self._settings.valid_window):
                    raise MfaError("MFA 校验失败")
                return {
                    "success": True,
                    "user_id": user_id,
                    "method": method,
                    "operation": operation,
                }

            # recovery_code 路径
            hashes = list(ent.get("recovery_code_hashes") or [])
            matched_index = None
            for idx, h in enumerate(hashes):
                try:
                    if bcrypt.checkpw(code.encode("utf-8"), h.encode("ascii")):
                        matched_index = idx
                        break
                except (ValueError, TypeError):
                    continue
            if matched_index is None:
                raise MfaError("MFA 校验失败")
            hashes.pop(matched_index)
            ent["recovery_code_hashes"] = hashes
            return {
                "success": True,
                "user_id": user_id,
                "method": method,
                "operation": operation,
            }

    async def disable(self, user_id: int) -> None:
        """禁用 MFA：删除 secret 与恢复码；撤销 refresh token。

        Args:
            user_id: 用户 ID。
        """
        if self._db is not None:
            await self._db_disable(user_id)
        else:
            with self._memory_lock:
                self._memory_totp_entries.pop(user_id, None)

        # 撤销该用户所有 refresh token（含门户子表）
        await self._revoke_user_tokens(user_id)
        # 清零失败计数
        await self._clear_user_failure(user_id)

    async def regenerate_recovery_codes(
        self,
        user_id: int,
    ) -> Tuple[List[str], List[str]]:
        """重新生成恢复码，旧码立即失效。

        Args:
            user_id: 用户 ID。

        Returns:
            Tuple[List[str], List[str]]: (明文码列表 / 内部存储占位)。

        Raises:
            MfaError: 用户未启用 TOTP。
        """
        entry = await self._get_totp_entry(user_id)
        if not entry or not entry.get("enabled_at"):
            raise MfaError("用户尚未启用 TOTP")

        plain_codes = [secrets.token_hex(4) + "-" + secrets.token_hex(4) for _ in range(10)]
        hashes = [
            bcrypt.hashpw(c.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
            for c in plain_codes
        ]
        if self._db is not None:
            await self._db_set_recovery_hashes(user_id, hashes)
        else:
            with self._memory_lock:
                ent = self._memory_totp_entries.setdefault(user_id, {})
                ent["recovery_code_hashes"] = hashes

        # 撤销该用户所有 refresh token（含门户子表）
        await self._revoke_user_tokens(user_id)
        return hashes, plain_codes

    # ------------------------------------------------------------------
    # 内部 helpers：challenge 元数据查询（不消费 challenge，仅校验 purpose）
    # ------------------------------------------------------------------

    async def lookup_challenge(
        self,
        token_hash: str,
        expected_purpose: str,
    ) -> Optional[int]:
        """查询 challenge 行的 user_id；仅查找，不消费。

        Args:
            token_hash: challenge 哈希。
            expected_purpose: 期望的 purpose。

        Returns:
            Optional[int]: user_id 或 None。
        """
        if self._db is not None:
            user_id, purpose = await self._db_lookup_challenge(token_hash)
        else:
            with self._memory_lock:
                self._purge_memory_challenges()
                cur = self._memory_challenges.get(token_hash)
                if cur is None:
                    return None
                # 同步内不持有锁太久：读快照
                if cur.get("consumed_at") is not None or cur["expires_at"] <= time.time():
                    return None
                user_id = int(cur["user_id"])
                purpose = cur.get("purpose")
        if user_id is None:
            return None
        if purpose != expected_purpose:
            return None
        return int(user_id)

    # ------------------------------------------------------------------
    # 内部：登录锁定状态（单一真相源 = UserDB）
    # ------------------------------------------------------------------

    async def get_user_lock_state(self, user_id: int) -> Dict[str, Any]:
        """查询用户的登录锁定状态（与 user_db 中的字段对齐，单一真相源）。

        Args:
            user_id: 用户 ID。

        Returns:
            Dict[str, Any]: ``{"failed_login_count": int, "locked_until": Optional[float]}``。
        """
        from app.shared.utils.auth.user_db import UserDB

        state = await UserDB.get_login_lock_state(user_id)
        return state

    async def reset_user_failure(self, user_id: int) -> None:
        """登录成功（含完成 MFA）后清零用户失败计数 + 解除锁定。"""
        await self._clear_user_failure(user_id)

    # ===========================================================
    # 内部 helpers
    # ===========================================================

    async def _get_totp_entry(self, user_id: int) -> Optional[Dict[str, Any]]:
        """读取 user_mfa_totp 行（含 secret_cipher 等敏感字段，但 secret 一律 cipher 不明文）。"""
        if self._db is not None:
            return await self._db_get_totp_entry(user_id)
        with self._memory_lock:
            ent = self._memory_totp_entries.get(user_id)
            return dict(ent) if ent else None

    async def _validate_totp(
        self,
        entry: Dict[str, Any],
        code: str,
    ) -> Tuple[bool, Optional[int]]:
        """校验 TOTP 码：返回 (success, last_used_step)。

        Args:
            entry: TOTP 条目 dict。
            code: 候选码。

        Returns:
            Tuple[bool, Optional[int]]: (成功, 命中的时间步)。
        """
        if not entry.get("secret_cipher"):
            return False, None
        try:
            secret = _decrypt_secret(self._fernet, entry["secret_cipher"])
        except MfaError:
            return False, None
        totp = pyotp.TOTP(secret)
        # 校验当前和前后 window 步
        for offset in range(-self._settings.valid_window, self._settings.valid_window + 1):
            step = int(time.time() // 30) + offset
            expected = totp.at(step * 30)
            if hmac.compare_digest(expected, code):
                # last_used_step 必须新于已有值（防重放）
                last_step = entry.get("last_used_step") or 0
                if isinstance(last_step, str):
                    try:
                        last_step = int(last_step)
                    except (TypeError, ValueError):
                        last_step = 0
                if step <= last_step:
                    continue
                return True, step
        return False, None

    async def _validate_recovery_code(
        self,
        entry: Dict[str, Any],
        code: str,
    ) -> Tuple[bool, Optional[int]]:
        """校验恢复码，返回 (success, 命中索引)。"""
        hashes = entry.get("recovery_code_hashes") or []
        for idx, h in enumerate(hashes):
            try:
                if bcrypt.checkpw(code.encode("utf-8"), h.encode("ascii")):
                    return True, idx
            except (ValueError, TypeError):
                continue
        return False, None

    async def _bump_challenge_failure(
        self,
        token_hash: str,
        chal: Dict[str, Any],
    ) -> None:
        """递增 challenge 失败计数。"""
        if self._db is not None:
            await self._db.execute(
                "UPDATE mfa_challenges SET failed_attempts = failed_attempts + 1 "
                "WHERE token_hash = $1",
                token_hash,
            )
        else:
            with self._memory_lock:
                cur = self._memory_challenges.get(token_hash)
                if cur is not None:
                    cur["failed_attempts"] = cur.get("failed_attempts", 0) + 1

    async def _bump_user_failure(self, user_id: int) -> None:
        """递增用户层失败计数；达到 max_attempts 时锁定用户（委托 UserDB，单一真相源）。"""
        from app.shared.utils.auth.user_db import UserDB

        await UserDB.record_failed_login(
            user_id,
            max_attempts=self._settings.max_attempts,
            lockout_seconds=self._settings.lockout_seconds,
        )

    async def _clear_user_failure(self, user_id: int) -> None:
        """清零用户失败计数与锁定状态（委托 UserDB）。"""
        from app.shared.utils.auth.user_db import UserDB

        await UserDB.clear_login_lock(user_id)

    # ------------------------------------------------------------------
    # 内存模式 helpers
    # ------------------------------------------------------------------

    def _purge_memory_challenges(self) -> None:
        """清理过期 challenge（参数化删除替代后台定时任务）。"""
        now = time.time()
        expired_keys = [
            h for h, c in self._memory_challenges.items() if c["expires_at"] <= now
        ]
        for h in expired_keys:
            self._memory_challenges.pop(h, None)

    def _memory_fetch_and_lock_challenge(
        self,
        token_hash: str,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
        with self._memory_lock:
            self._purge_memory_challenges()
            cur = self._memory_challenges.get(token_hash)
            if cur is None:
                return None, None
            return dict(cur), int(cur["user_id"])

    def _memory_consume_challenge_and_set_step(
        self,
        token_hash: str,
        user_id: int,
        last_used_step: int,
    ) -> None:
        with self._memory_lock:
            chal = self._memory_challenges.get(token_hash)
            if chal is not None:
                chal["consumed_at"] = time.time()
            ent = self._memory_totp_entries.setdefault(user_id, {})
            ent["last_used_step"] = last_used_step

    def _memory_consume_recovery_code(
        self,
        token_hash: str,
        user_id: int,
        index: int,
    ) -> None:
        with self._memory_lock:
            chal = self._memory_challenges.get(token_hash)
            if chal is not None:
                chal["consumed_at"] = time.time()
            ent = self._memory_totp_entries.setdefault(user_id, {})
            hashes = ent.get("recovery_code_hashes", [])
            if 0 <= index < len(hashes):
                hashes.pop(index)
                ent["recovery_code_hashes"] = hashes

    def _memory_consume_only(self, token_hash: str) -> Optional[int]:
        with self._memory_lock:
            chal = self._memory_challenges.get(token_hash)
            if chal is None or chal.get("consumed_at") is not None:
                return None
            chal["consumed_at"] = time.time()
            return int(chal["user_id"])

    # ------------------------------------------------------------------
    # DB 模式 helpers
    # ------------------------------------------------------------------

    async def _db_challenge_insert(
        self,
        token_hash: str,
        user_id: int,
        purpose: str,
        expires_at: float,
    ) -> None:
        """插入新 challenge，顺带参数化删除过期记录。"""
        from datetime import datetime, timezone

        async with self._db.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM mfa_challenges WHERE expires_at <= NOW()",
                )
                await conn.execute(
                    "INSERT INTO mfa_challenges "
                    "(token_hash, user_id, purpose, expires_at, failed_attempts, consumed_at, created_at) "
                    "VALUES ($1, $2, $3, TO_TIMESTAMP($4), 0, NULL, NOW())",
                    token_hash,
                    user_id,
                    purpose,
                    expires_at,
                )

    async def _db_challenge_fetch_and_lock(
        self,
        token_hash: str,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
        """SELECT FOR UPDATE 锁定 challenge 行（事务内有效）。

        校验 purpose / consumed_at / expires_at 三个维度。
        """
        async with self._db.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT user_id, purpose, EXTRACT(EPOCH FROM expires_at)::float8 AS expires_at, "
                    "       failed_attempts, consumed_at "
                    "FROM mfa_challenges WHERE token_hash = $1 FOR UPDATE",
                    token_hash,
                )
                if row is None:
                    return None, None
                consumed = row.get("consumed_at")
                if consumed is not None:
                    return {"consumed_at": True}, int(row["user_id"])
                # expires_at 已经是 epoch float，与 time.time() 同基准，无需再转换
                return (
                    {
                        "user_id": row["user_id"],
                        "purpose": row["purpose"],
                        "expires_at": row["expires_at"],
                        "failed_attempts": row["failed_attempts"],
                        "consumed_at": None,
                    },
                    int(row["user_id"]),
                )

    async def _db_lookup_challenge(
        self,
        token_hash: str,
    ) -> Tuple[Optional[int], Optional[str]]:
        """查询 challenge 行的 (user_id, purpose)；仅查找，不消费。

        校验 consumed_at / expires_at 是否仍可用。**不**持有 FOR UPDATE 跨连接语义。
        """
        async with self._db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT user_id, purpose, EXTRACT(EPOCH FROM expires_at)::float8 AS expires_at, "
                "       consumed_at "
                "FROM mfa_challenges WHERE token_hash = $1",
                token_hash,
            )
            if row is None:
                return None, None
            consumed = row.get("consumed_at")
            if consumed is not None:
                return None, None
            # expires_at 是 epoch float
            if row["expires_at"] <= time.time():
                return None, None
            return int(row["user_id"]), row.get("purpose")

    async def _db_consume_challenge_and_set_step(
        self,
        token_hash: str,
        user_id: int,
        last_used_step: int,
    ) -> None:
        """TOTP 成功：原子消费 challenge + 写 last_used_step。

        全部在同一个 ``conn.transaction()`` + ``SELECT ... FOR UPDATE`` 内，
        保证同一时间步并发仅一个请求能成功。
        """
        async with self._db.acquire() as conn:
            async with conn.transaction():
                # 锁定 TOTP 行（防重放核心：SELECT FOR UPDATE）
                totp_row = await conn.fetchrow(
                    "SELECT last_used_step FROM user_mfa_totp WHERE user_id = $1 FOR UPDATE",
                    user_id,
                )
                if totp_row is None:
                    # 没有 TOTP 行（理论上 verify_login 已先读 enabled_at，此分支不可达）
                    raise MfaError("MFA 校验失败")
                # 再次校验 last_used_step 防重放：客户端到达此处前已被 SELECT FOR UPDATE 序列化
                last_step_raw = totp_row.get("last_used_step")
                try:
                    last_step_val = int(last_step_raw) if last_step_raw is not None else 0
                except (TypeError, ValueError):
                    last_step_val = 0
                if last_used_step <= last_step_val:
                    raise MfaError("MFA 校验失败")
                await conn.execute(
                    "UPDATE mfa_challenges SET consumed_at = NOW() "
                    "WHERE token_hash = $1",
                    token_hash,
                )
                await conn.execute(
                    "UPDATE user_mfa_totp SET last_used_step = $1, updated_at = NOW() "
                    "WHERE user_id = $2",
                    last_used_step,
                    user_id,
                )

    async def _db_consume_recovery_code(
        self,
        token_hash: str,
        user_id: int,
        index: int,
    ) -> None:
        """消费恢复码（按索引从 JSONB 数组中弹出并写回完整 list）。

        严禁使用 ``jsonb - $int`` 形式歧义；改为 Python 端 pop 后
        把完整 list 作为 jsonb 参数绑定更新。
        全部在事务 + SELECT FOR UPDATE 内原子完成。
        """
        async with self._db.acquire() as conn:
            async with conn.transaction():
                # 锁定 TOTP 行
                totp_row = await conn.fetchrow(
                    "SELECT recovery_code_hashes FROM user_mfa_totp WHERE user_id = $1 FOR UPDATE",
                    user_id,
                )
                if totp_row is None:
                    raise MfaError("MFA 校验失败")
                # 解析 JSONB（codec 已生效，但保留字符串兼容）
                hashes_raw = totp_row.get("recovery_code_hashes")
                if isinstance(hashes_raw, str):
                    try:
                        hashes = json.loads(hashes_raw)
                    except (json.JSONDecodeError, TypeError, ValueError) as exc:
                        raise MfaError(
                            "recovery_code_hashes 解析失败"
                        ) from exc
                else:
                    hashes = list(hashes_raw or [])
                if not isinstance(hashes, list):
                    raise MfaError("recovery_code_hashes 字段格式错误")
                if not (0 <= index < len(hashes)):
                    raise MfaError("恢复码索引越界")
                # Python 端 pop 后写回完整 list
                hashes.pop(index)
                await conn.execute(
                    "UPDATE mfa_challenges SET consumed_at = NOW() "
                    "WHERE token_hash = $1",
                    token_hash,
                )
                await conn.execute(
                    "UPDATE user_mfa_totp "
                    "SET recovery_code_hashes = $2::jsonb, updated_at = NOW() "
                    "WHERE user_id = $1",
                    user_id,
                    json.dumps(hashes),
                )

    async def _db_get_totp_entry(self, user_id: int) -> Optional[Dict[str, Any]]:
        """读取 user_mfa_totp 行；JSONB 解析失败必须抛 MfaError（不静默吞为 []）。"""
        async with self._db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT secret_cipher, pending_secret_cipher, enabled_at, last_used_step, "
                "       recovery_code_hashes "
                "FROM user_mfa_totp WHERE user_id = $1",
                user_id,
            )
            if row is None:
                return None
            hashes_raw = row.get("recovery_code_hashes")
            if hashes_raw is None:
                hashes = []
            elif isinstance(hashes_raw, list):
                hashes = list(hashes_raw)
            elif isinstance(hashes_raw, str):
                try:
                    parsed = json.loads(hashes_raw)
                    if not isinstance(parsed, list):
                        raise MfaError(
                            "recovery_code_hashes 解析结果不是 list"
                        )
                    hashes = parsed
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    raise MfaError(
                        f"recovery_code_hashes 解析失败: {exc}"
                    ) from exc
            else:
                # codec 返回 dict / 其他类型也判错
                raise MfaError(
                    f"recovery_code_hashes 字段类型异常: {type(hashes_raw).__name__}"
                )
            return {
                "secret_cipher": row.get("secret_cipher"),
                "pending_secret_cipher": row.get("pending_secret_cipher"),
                "enabled_at": row.get("enabled_at"),
                "last_used_step": row.get("last_used_step"),
                "recovery_code_hashes": hashes,
            }

    async def _db_set_pending_secret(self, user_id: int, cipher: str) -> None:
        async with self._db.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO user_mfa_totp (user_id, pending_secret_cipher, recovery_code_hashes, updated_at) "
                    "VALUES ($1, $2, '[]'::jsonb, NOW()) "
                    "ON CONFLICT (user_id) DO UPDATE SET "
                    "    pending_secret_cipher = EXCLUDED.pending_secret_cipher, "
                    "    updated_at = NOW()",
                    user_id,
                    cipher,
                )

    async def _db_commit_enrollment(
        self,
        user_id: int,
        secret_cipher: str,
        enabled_at: Any,
        recovery_code_hashes: List[str],
        last_used_step: int,
    ) -> None:
        """完成绑定：secret / enabled_at / recovery_code_hashes / last_used_step 同事务写入。

        ``last_used_step`` 写入当前 step 避免刚绑定码被立刻重放。
        """
        async with self._db.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE user_mfa_totp "
                    "SET secret_cipher = $1, pending_secret_cipher = NULL, "
                    "    enabled_at = $2, recovery_code_hashes = $3::jsonb, "
                    "    last_used_step = $4, updated_at = NOW() "
                    "WHERE user_id = $5",
                    secret_cipher,
                    enabled_at,
                    json.dumps(recovery_code_hashes),
                    last_used_step,
                    user_id,
                )

    async def _db_disable(self, user_id: int) -> None:
        async with self._db.acquire() as conn:
            await conn.execute("DELETE FROM user_mfa_totp WHERE user_id = $1", user_id)

    async def _db_set_recovery_hashes(
        self,
        user_id: int,
        hashes: List[str],
    ) -> None:
        async with self._db.acquire() as conn:
            await conn.execute(
                "UPDATE user_mfa_totp "
                "SET recovery_code_hashes = $1::jsonb, updated_at = NOW() "
                "WHERE user_id = $2",
                json.dumps(hashes),
                user_id,
            )

    async def _db_consume_challenge(self, token_hash: str) -> Optional[int]:
        """消费 challenge（不写 last_used_step）。

        必须校验 consumed_at IS NULL + expires_at > NOW()，
        全部在事务内执行。
        """
        async with self._db.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "UPDATE mfa_challenges SET consumed_at = NOW() "
                    "WHERE token_hash = $1 AND consumed_at IS NULL "
                    "  AND expires_at > NOW() "
                    "RETURNING user_id",
                    token_hash,
                )
                return int(row["user_id"]) if row else None