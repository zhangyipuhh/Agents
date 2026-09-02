# -*- coding:utf-8 -*-
"""RegistrationApprovalService 单元测试(2026-08-30 新增)"""
import asyncio
from unittest.mock import patch

import pytest

from app.shared.utils.auth.registration_approval_service import (
    RegistrationApprovalService,
    notify_admin_new_registration,
)


@pytest.fixture
def user_in_pending():
    """构造一个 pending_approval 用户。"""
    from app.shared.utils.auth.user_db import UserDB
    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0
    user_id = asyncio.run(
        UserDB.create_user(
            "testuser", "P@ssword1!", status="pending_approval", email="u@example.com"
        )
    )
    return user_id, "testuser", "u@example.com"


def test_approve_user_success(user_in_pending):
    """测试 approve_user 成功路径。"""
    user_id, username, email = user_in_pending

    with patch(
        "app.shared.utils.auth.registration_approval_service._send_approval_email"
    ) as mock_email, patch(
        "app.shared.utils.auth.registration_approval_service._emit_audit"
    ) as mock_audit:
        result = asyncio.run(
            RegistrationApprovalService.approve_user(
                user_id=user_id, operator_user_id=1, operator_username="admin"
            )
        )

    assert result is True
    mock_email.assert_called_once()
    args, _ = mock_email.call_args
    assert email in args[0]
    mock_audit.assert_called_once()
    audit_kwargs = mock_audit.call_args.kwargs
    assert audit_kwargs.get("action") == "register_approved"


def test_reject_user_success(user_in_pending):
    """测试 reject_user 成功路径。"""
    user_id, username, email = user_in_pending

    with patch(
        "app.shared.utils.auth.registration_approval_service._send_approval_email"
    ) as mock_email, patch(
        "app.shared.utils.auth.registration_approval_service._emit_audit"
    ) as mock_audit:
        result = asyncio.run(
            RegistrationApprovalService.reject_user(
                user_id=user_id,
                reason="信息不实",
                operator_user_id=1,
                operator_username="admin",
            )
        )

    assert result is True
    mock_email.assert_called_once()
    mock_audit.assert_called_once()
    audit_kwargs = mock_audit.call_args.kwargs
    assert audit_kwargs.get("action") == "register_rejected"
    assert audit_kwargs.get("reason") == "信息不实"


def test_approve_user_not_found_raises():
    """测试 approve_user 对不存在的 user_id 抛 ValueError。"""
    from app.shared.utils.auth.user_db import UserDB
    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0

    with pytest.raises(ValueError, match="用户不存在"):
        asyncio.run(
            RegistrationApprovalService.approve_user(
                user_id=99999, operator_user_id=1, operator_username="admin"
            )
        )


def test_reject_user_non_pending_returns_none():
    """测试 reject_user 对非 pending_approval 的 user 返回 None。"""
    from app.shared.utils.auth.user_db import UserDB
    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0
    user_id = asyncio.run(UserDB.create_user("active_user", "P@ssword1!"))

    result = asyncio.run(
        RegistrationApprovalService.reject_user(
            user_id=user_id,
            reason="X",
            operator_user_id=1,
            operator_username="admin",
        )
    )
    assert result is None


def test_reject_user_missing_reason_raises(user_in_pending):
    """测试 reject_user 缺 reason 抛 ValueError。"""
    user_id, _, _ = user_in_pending

    with pytest.raises(ValueError, match="reason"):
        asyncio.run(
            RegistrationApprovalService.reject_user(
                user_id=user_id,
                reason="",
                operator_user_id=1,
                operator_username="admin",
            )
        )


def test_email_send_failure_does_not_break_approval(user_in_pending):
    """测试邮件发送失败时整体 fail-soft。"""
    user_id, _, _ = user_in_pending

    with patch(
        "app.shared.utils.auth.registration_approval_service._send_approval_email",
        side_effect=Exception("SMTP 暂时不可用"),
    ):
        result = asyncio.run(
            RegistrationApprovalService.approve_user(
                user_id=user_id, operator_user_id=1, operator_username="admin"
            )
        )
    assert result is True


def test_notify_admin_new_registration(monkeypatch):
    """测试注册提交通知 admin(邮件 + 飞书开关)。"""
    from app.core.config.settings import RegistrationSecuritySettings
    from app.shared.utils.auth.registration_approval_service import (
        notify_admin_new_registration,
    )

    monkeypatch.setattr(
        "app.shared.utils.auth.registration_approval_service.settings.registration_security",
        RegistrationSecuritySettings(
            enabled=True,
            admin_notification_emails=["admin@example.com"],
            feishu_notify_enabled=False,
        ),
    )

    with patch(
        "app.shared.utils.auth.registration_approval_service._send_admin_email"
    ) as mock_email:
        asyncio.run(
            notify_admin_new_registration(
                username="newuser",
                real_name="新人",
                email="new@example.com",
                register_ip="10.0.0.5",
            )
        )
    mock_email.assert_called_once()
