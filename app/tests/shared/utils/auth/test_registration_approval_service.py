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


# =============================================================================
# _send_feishu_to_admin 走 DB（2026-09-11 改造）
# =============================================================================


class _FakeSvcForFeishuAdmin:
    """模拟 NotificationConfigService,支持异步 list_targets 与 resolve_default_channel。"""

    def __init__(self, channel, targets):
        self._channel = channel
        self._targets = targets

    async def resolve_default_channel(self, channel_type):
        return self._channel

    async def list_targets(self, channel_id=None, **kw):
        return self._targets

    def decrypt_field(self, s):
        """简单反转 fake prefix,让 fake 调用链路可识别明文。"""
        if isinstance(s, str) and s.startswith("enc_"):
            return s[len("enc_"):]
        return s


def test_send_feishu_to_admin_uses_db_default_channel_and_first_target():
    """_send_feishu_to_admin 走 DB 默认渠道 + 该渠道下第一个 enabled target。

    验证：
    - 用 notification_config_service.resolve_default_channel("feishu") 解析 channel
    - 用 list_targets 拿 channel 下 enabled=TRUE 的第一个 target 作为接收方
    - 用 channel 明文凭证构造临时 lark.Client 发送
    """
    from app.shared.utils.auth import registration_approval_service as RAS

    fake_channel = {
        "id": 11, "name": "feishu_default",
        "config": {
            "app_id_encrypted": "enc_app_id_xxx",
            "app_secret_encrypted": "enc_app_secret_yyy",
            "log_level": "INFO",
        },
    }
    fake_target = {
        "id": 21, "channel_id": 11, "enabled": True,
        "config": {"chat_id": "oc_admin_chat", "chat_type": "chat_id"},
    }
    fake_svc = _FakeSvcForFeishuAdmin(fake_channel, [fake_target])

    # 完整 mock lark CreateMessageRequest/Body builder 链,存值字段,避免依赖
    # feishu conftest 的 _MessageRequestBuilder（不存字段值）。
    captured = {}

    class _FakeBody:
        receive_id = None
        msg_type = None
        content = None
        uuid = None

    class _FakeReq:
        receive_id_type = None
        request_body = None

    class _FakeReqBuilder:
        def receive_id_type(self, x): captured["req_receive_id_type"] = x; return self
        def request_body(self, x): self._body = x; return self
        def build(self):
            r = _FakeReq(); r.request_body = self._body; return r

    class _FakeBodyBuilder:
        def receive_id(self, x): captured["body_receive_id"] = x; return self
        def msg_type(self, x): captured["body_msg_type"] = x; return self
        def content(self, x): captured["body_content"] = x; return self
        def uuid(self, x): captured["body_uuid"] = x; return self
        def build(self): return _FakeBody()

    class _FakeResp:
        def success(self): return True
        class data: message_id = "om_admin_001"

    class _FakeMsgApi:
        @staticmethod
        def create(req):
            captured["called"] = True
            return _FakeResp()

    class _FakeImV1:
        message = _FakeMsgApi()

    class _FakeIm:
        v1 = _FakeImV1()

    class _FakeClient:
        im = _FakeIm

    import lark_oapi.api.im.v1 as _im_v1_mod
    with patch.object(RAS, "_get_notification_service", lambda: fake_svc), \
         patch.object(RAS, "_build_admin_lark_client", lambda ch: _FakeClient()), \
         patch.object(_im_v1_mod, "CreateMessageRequest") as _mock_req_cls, \
         patch.object(_im_v1_mod, "CreateMessageRequestBody") as _mock_body_cls:
        _mock_req_cls.builder = lambda: _FakeReqBuilder()
        _mock_body_cls.builder = lambda: _FakeBodyBuilder()
        RAS._send_feishu_to_admin("test content")

    # 验证 happy path 三个关键点
    assert captured.get("called") is True, "client.im.v1.message.create 未被调用"
    assert captured["body_receive_id"] == "oc_admin_chat", f"实际: {captured['body_receive_id']}"
    assert captured["req_receive_id_type"] == "chat_id", f"实际: {captured['req_receive_id_type']}"
    assert captured["body_msg_type"] == "text"


def test_send_feishu_to_admin_skips_when_service_unavailable():
    """notification_config_service 未初始化 → warning 日志 + 不抛异常。"""
    from app.shared.utils.auth import registration_approval_service as RAS

    with patch.object(RAS, "_get_notification_service", lambda: None):
        # 不应抛异常
        RAS._send_feishu_to_admin("test content")


def test_send_feishu_to_admin_skips_when_no_default_channel():
    """DB 无默认飞书渠道 → warning 日志 + 不抛异常。"""
    from app.shared.utils.auth import registration_approval_service as RAS

    fake_svc = _FakeSvcForFeishuAdmin(channel=None, targets=[])

    with patch.object(RAS, "_get_notification_service", lambda: fake_svc):
        # 不应抛异常
        RAS._send_feishu_to_admin("test content")


def test_send_feishu_to_admin_skips_when_no_enabled_target():
    """channel 存在但无 enabled target → warning 日志 + 不抛异常。"""
    from app.shared.utils.auth import registration_approval_service as RAS

    fake_channel = {"id": 11, "name": "feishu_default", "config": {}}
    fake_svc = _FakeSvcForFeishuAdmin(fake_channel, targets=[])

    with patch.object(RAS, "_get_notification_service", lambda: fake_svc):
        # 不应抛异常
        RAS._send_feishu_to_admin("test content")


def test_send_feishu_to_admin_skips_when_target_chat_id_empty():
    """target.config.chat_id 为空 → warning 日志 + 不抛异常。"""
    from app.shared.utils.auth import registration_approval_service as RAS

    fake_channel = {"id": 11, "name": "feishu_default", "config": {}}
    fake_target = {
        "id": 21, "channel_id": 11, "enabled": True,
        "config": {"chat_type": "chat_id"},  # 缺 chat_id
    }
    fake_svc = _FakeSvcForFeishuAdmin(fake_channel, [fake_target])

    with patch.object(RAS, "_get_notification_service", lambda: fake_svc):
        # 不应抛异常
        RAS._send_feishu_to_admin("test content")


def test_send_feishu_to_admin_swallow_send_exception():
    """client.im.v1.message.create 抛异常 → warning 日志 + 不向上抛。"""
    from app.shared.utils.auth import registration_approval_service as RAS

    fake_channel = {"id": 11, "name": "feishu_default", "config": {}}
    fake_target = {
        "id": 21, "channel_id": 11, "enabled": True,
        "config": {"chat_id": "oc_x", "chat_type": "chat_id"},
    }
    fake_svc = _FakeSvcForFeishuAdmin(fake_channel, [fake_target])

    class _BoomClient:
        class im:
            class v1:
                class message:
                    @staticmethod
                    def create(req):
                        raise RuntimeError("network down")

    with patch.object(RAS, "_get_notification_service", lambda: fake_svc), \
         patch.object(RAS, "_build_admin_lark_client", lambda ch: _BoomClient()):
        # 不应抛异常
        RAS._send_feishu_to_admin("test content")


def test_notify_admin_new_registration_calls_feishu_when_enabled(monkeypatch):
    """notify_admin_new_registration 在 feishu_notify_enabled=True 时调 _send_feishu_to_admin。

    验证集成路径：_send_feishu_to_admin 被 monkeypatch 拦截,验证调用发生。
    """
    from app.core.config.settings import RegistrationSecuritySettings
    from app.shared.utils.auth import registration_approval_service as RAS_mod

    cfg = RegistrationSecuritySettings(
        enabled=True,
        admin_notification_emails=[],
        feishu_notify_enabled=True,
    )
    monkeypatch.setattr(RAS_mod.settings, "registration_security", cfg)
    called = []
    monkeypatch.setattr(
        RAS_mod, "_send_feishu_to_admin", lambda content: called.append(content)
    )
    monkeypatch.setattr(RAS_mod, "_send_admin_email", lambda *a, **kw: None)

    asyncio.run(RAS_mod.notify_admin_new_registration(
        username="newuser", real_name="新人",
        email="x@x.com", register_ip="10.0.0.1",
    ))
    assert len(called) == 1
