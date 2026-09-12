# -*- coding:utf-8 -*-
"""login-api 登录失败锁定集成测试（2026-09-12 等保三级补齐）。

/login-api 免验证码（设计如此,server-to-server 场景）,但必须与 /login
一样执行「连续失败锁定」——此前该端点只调 verify_credentials,
错无限次都不锁定,构成绕过 CAPTCHA 且绕过锁定的暴力破解通道。
"""

BASE = "/api/auth/login-api"


def test_login_api_locked_user_rejected_even_with_correct_password(
    client, user_headers, monkeypatch,
):
    """锁定期间即使密码正确也 401（fail-closed）。"""
    import time

    async def fake_verify(username, password):
        return True

    async def fake_get_user(username):
        return {"id": 2, "username": "testuser", "role": "user", "status": "active"}

    async def fake_lock_state(user_id):
        return {"locked_until": time.time() + 600}

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.verify_credentials", fake_verify,
    )
    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username", fake_get_user,
    )
    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_login_lock_state", fake_lock_state,
    )

    response = client.post(
        BASE, json={"username": "testuser", "password": "whatever"},
    )
    assert response.status_code == 401
    assert "锁定" in response.json()["detail"]


def test_login_api_failure_records_and_locks(monkeypatch, client):
    """连续失败累计达阈值后返回锁定文案。"""
    calls = {"count": 0}

    async def fake_verify(username, password):
        return False

    async def fake_get_user(username):
        return {"id": 2, "username": "testuser", "role": "user", "status": "active"}

    async def fake_record(user_id, max_attempts, lockout_seconds):
        calls["count"] += 1
        return 5  # 已达阈值

    async def fake_lock_state(user_id):
        return {"locked_until": None}

    # MFA fail-closed 防线：测试环境补一个 mfa_service stub 避免 503
    from types import SimpleNamespace
    client.app.state.mfa_service = SimpleNamespace(
        _settings=SimpleNamespace(lockout_seconds=1800, max_attempts=5),
    )

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.verify_credentials", fake_verify,
    )
    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username", fake_get_user,
    )
    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.record_failed_login", fake_record,
    )
    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_login_lock_state", fake_lock_state,
    )

    response = client.post(
        BASE, json={"username": "testuser", "password": "wrong"},
    )
    assert response.status_code == 401
    assert "锁定" in response.json()["detail"]
    assert calls["count"] == 1
