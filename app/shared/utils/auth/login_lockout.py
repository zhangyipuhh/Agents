#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
共享登录失败锁定助手（2026-09-12 等保三级 §1.4 补齐）。

/login 与 /login-api 共用同一套锁定逻辑,消除两处漂移风险:
- ``check_login_lock``:凭据校验通过后调用,锁定期间即使密码正确也拒绝
  （fail-closed）；不存在的用户名返回 None（反枚举）。
- ``record_failed_login_and_is_locked``:凭据失败时累计计数并返回是否
  已锁定（含 DB 状态二次判定兜底）；异常时 logger.exception 记录堆栈但
  返回 False,绝不让登录接口因此 5xx（反枚举特性不变）。

阈值来源优先级:app.state.mfa_service._settings → 默认 5 次 / 1800 秒,
与 auth_router /login 既有行为完全一致。
"""
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_DEFAULT_MAX_ATTEMPTS = 5
_DEFAULT_LOCKOUT_SECONDS = 1800


async def check_login_lock(username: str) -> Optional[Dict[str, Any]]:
    """检查用户名对应账号是否处于锁定期。

    参数:
        username: 登录用户名。

    返回:
        Optional[Dict[str, Any]]: 锁定时返回 {"user_id": int, "locked_until": float};
        用户不存在或未锁定时返回 None。
    """
    from app.shared.utils.auth.user_db import UserDB

    existing = await UserDB.get_user_by_username(username)
    if existing is None:
        return None
    lock_state = await UserDB.get_login_lock_state(int(existing.get("id")))
    locked_until = lock_state.get("locked_until")
    if locked_until is not None and locked_until > time.time():
        return {"user_id": int(existing.get("id")), "locked_until": locked_until}
    return None


async def record_failed_login_and_is_locked(username: str, app) -> bool:
    """累计一次登录失败并返回账号是否已锁定。

    参数:
        username: 登录用户名。
        app: FastAPI app 对象（读 app.state.mfa_service._settings 阈值）。

    返回:
        bool: True = 已触发锁定（调用方应拒绝并返回锁定文案）；
        False = 未锁定或用户不存在或累计链路异常（走常规凭据错误 401）。
    """
    from app.shared.utils.auth.user_db import UserDB

    try:
        try:
            existing = await UserDB.get_user_by_username(username)
        except Exception:  # noqa: BLE001
            existing = None
        if existing is None:
            return False

        mfa_service_ref = getattr(app.state, "mfa_service", None)
        lockout_seconds = (
            getattr(mfa_service_ref, "_settings", None)
            and mfa_service_ref._settings.lockout_seconds
        ) or _DEFAULT_LOCKOUT_SECONDS
        max_attempts = (
            getattr(mfa_service_ref, "_settings", None)
            and mfa_service_ref._settings.max_attempts
        ) or _DEFAULT_MAX_ATTEMPTS

        new_count = await UserDB.record_failed_login(
            int(existing.get("id")),
            max_attempts=max_attempts,
            lockout_seconds=lockout_seconds,
        )
        # 兜底二次判定:即便 record_failed_login 主路径 SQL CASE 漂移未触发
        # locked_until 写入,仍基于 new_count 显式判定（2026-08-08 修复先例）。
        lock_state = await UserDB.get_login_lock_state(int(existing.get("id")))
        now_ts = time.time()
        return (
            (lock_state.get("locked_until") is not None
             and lock_state["locked_until"] > now_ts)
            or new_count >= max_attempts
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "[login_lockout] record_failed_login raised: %s", exc,
        )
        return False
