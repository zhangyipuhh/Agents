# -*- coding:utf-8 -*-
"""
UserDB.create_user / update_password 入口密码复杂度拦截测试（2026-08-11 等保三级 Task 3）。

目的：
- 验证 ``UserDB.create_user`` / ``UserDB.update_password`` 在 ``hash_password`` 之前调用
  ``password_policy.validate_password``；
- 弱口令（长度 < 8 / 缺大小写 / 缺数字 / 缺特殊字符）必须抛 ``ValueError``；
- 强口令通过校验。

本测试为 Task 5 改造前的回归基线。fixture 仍按字面量调用 ``UserDB``，弱口令
被抛 ``ValueError`` 是预期结果。
"""
import asyncio
import pytest
from app.shared.utils.auth.user_db import UserDB


def _clear():
    """每个用例执行前重置 UserDB 内存状态，确保用例之间不互相污染。"""
    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0
    UserDB._memory_login_lock.clear()


def test_create_user_rejects_7_chars():
    """7 位密码必须被 ``create_user`` 拒绝（长度 < 8）。"""
    _clear()
    with pytest.raises(ValueError):
        asyncio.run(UserDB.create_user("u", "Aa1!aaa"))


def test_create_user_rejects_missing_upper():
    """缺大写字母必须被 ``create_user`` 拒绝。"""
    _clear()
    with pytest.raises(ValueError):
        asyncio.run(UserDB.create_user("u", "aa1!aaaa"))


def test_create_user_rejects_missing_lower():
    """缺小写字母必须被 ``create_user`` 拒绝。"""
    _clear()
    with pytest.raises(ValueError):
        asyncio.run(UserDB.create_user("u", "AA1!AAAA"))


def test_create_user_rejects_missing_digit():
    """缺数字必须被 ``create_user`` 拒绝。"""
    _clear()
    with pytest.raises(ValueError):
        asyncio.run(UserDB.create_user("u", "Aaa!aaaa"))


def test_create_user_rejects_missing_special():
    """缺特殊字符必须被 ``create_user`` 拒绝。"""
    _clear()
    with pytest.raises(ValueError):
        asyncio.run(UserDB.create_user("u", "Aa1aaaaa"))


def test_create_user_accepts_strong():
    """强口令（大写 + 小写 + 数字 + 特殊字符 + ≥8 位）必须通过 ``create_user``。"""
    _clear()
    asyncio.run(UserDB.create_user("u", "P@ssword1!", role="user"))


def test_update_password_rejects_7_chars():
    """7 位密码必须被 ``update_password`` 拒绝（长度 < 8）。"""
    _clear()
    uid = asyncio.run(UserDB.create_user("u", "P@ssword1!", role="user"))
    with pytest.raises(ValueError):
        asyncio.run(UserDB.update_password(uid, "Aa1!aaa"))