# -*- coding:utf-8 -*-
"""
EmailService 单元测试模块。

验证邮件发送服务的核心 send_email 方法，包括 SSL/STARTTLS 分支、
附件处理与异常路径。
"""
import asyncio
import os
import smtplib
from unittest.mock import MagicMock, patch

import pytest

from app.shared.utils.email.email_models import EmailServerConfig
from app.shared.utils.email.email_service import EmailSendError, EmailService


# =============================================================================
# P0: 导入与构造
# =============================================================================

def test_email_service_importable():
    """测试 EmailService 模块可导入。"""
    from app.shared.utils.email import email_service
    assert hasattr(email_service, "EmailService")


def test_email_service_raises_on_none_config():
    """测试 config 为 None 时抛出 ValueError。"""
    with pytest.raises(ValueError, match="不能为空"):
        EmailService(None)


# =============================================================================
# P1: 成功路径
# =============================================================================

def _make_config(use_ssl: bool = True) -> EmailServerConfig:
    """构造测试用 SMTP 配置。

    返回:
        EmailServerConfig: 测试配置实例。
    """
    return EmailServerConfig(
        host="smtp.qq.com",
        port=465 if use_ssl else 587,
        use_ssl=use_ssl,
        username="sender@qq.com",
        password="authcode",
        sender_name="测试",
        enabled=True,
    )


def test_send_email_ssl_success():
    """测试 SMTP_SSL 模式发送成功（mock smtplib.SMTP_SSL）。"""
    config = _make_config(use_ssl=True)
    svc = EmailService(config)

    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_smtp.__exit__.return_value = False
    # 2026-07-18 显式置空：smtplib.send_message 在成功时返回空字典
    fake_smtp.send_message.return_value = {}

    with patch("smtplib.SMTP_SSL", return_value=fake_smtp) as mock_ssl:
        result = asyncio.run(svc.send_email(
            to=["a@b.com"], subject="主题", body="正文",
        ))

    assert result["success"] is True
    assert "a@b.com" in result["sent_to"]
    fake_smtp.login.assert_called_once_with("sender@qq.com", "authcode")
    fake_smtp.send_message.assert_called_once()
    mock_ssl.assert_called_once()


def test_send_email_starttls_success():
    """测试 STARTTLS 模式发送成功（mock smtplib.SMTP）。"""
    config = _make_config(use_ssl=False)
    svc = EmailService(config)

    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_smtp.__exit__.return_value = False
    fake_smtp.send_message.return_value = {}

    with patch("smtplib.SMTP", return_value=fake_smtp) as mock_smtp:
        result = asyncio.run(svc.send_email(
            to=["a@b.com"], subject="主题", body="正文",
        ))

    assert result["success"] is True
    fake_smtp.starttls.assert_called_once()
    fake_smtp.login.assert_called_once_with("sender@qq.com", "authcode")
    mock_smtp.assert_called_once()


def test_send_email_with_cc():
    """测试带抄送的发送。"""
    config = _make_config()
    svc = EmailService(config)

    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_smtp.__exit__.return_value = False
    fake_smtp.send_message.return_value = {}

    with patch("smtplib.SMTP_SSL", return_value=fake_smtp):
        result = asyncio.run(svc.send_email(
            to=["a@b.com"], cc=["c@d.com"], subject="主题", body="正文",
        ))

    assert result["success"] is True
    # send_message 的 to_addrs 参数应包含 cc
    call_args = fake_smtp.send_message.call_args
    recipients = call_args.kwargs.get("to_addrs") or call_args.args[1]
    assert "c@d.com" in recipients


def test_send_email_with_attachment_path(tmp_path):
    """测试通过本地路径附件发送。"""
    config = _make_config()
    svc = EmailService(config)

    # 创建临时附件文件
    attachment = tmp_path / "test.txt"
    attachment.write_bytes(b"hello attachment")

    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_smtp.__exit__.return_value = False
    fake_smtp.send_message.return_value = {}

    with patch("smtplib.SMTP_SSL", return_value=fake_smtp):
        result = asyncio.run(svc.send_email(
            to=["a@b.com"], subject="主题", body="正文",
            attachment_paths=[str(attachment)],
        ))

    assert result["success"] is True
    fake_smtp.send_message.assert_called_once()


def test_send_email_with_attachment_stream():
    """测试通过字节流附件发送。"""
    config = _make_config()
    svc = EmailService(config)

    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_smtp.__exit__.return_value = False
    fake_smtp.send_message.return_value = {}

    with patch("smtplib.SMTP_SSL", return_value=fake_smtp):
        result = asyncio.run(svc.send_email(
            to=["a@b.com"], subject="主题", body="正文",
            attachment_streams=[("report.pdf", b"%PDF-1.4 fake")],
        ))

    assert result["success"] is True
    fake_smtp.send_message.assert_called_once()


# =============================================================================
# P1: 失败路径
# =============================================================================

def test_send_email_raises_on_empty_to():
    """测试收件人列表为空时抛出 EmailSendError。"""
    config = _make_config()
    svc = EmailService(config)

    with pytest.raises(EmailSendError, match="收件人列表不能为空"):
        asyncio.run(svc.send_email(to=[], subject="主题", body="正文"))


def test_send_email_raises_on_smtp_error():
    """测试 SMTP 异常被包装为 EmailSendError。"""
    config = _make_config()
    svc = EmailService(config)

    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_smtp.__exit__.return_value = False
    fake_smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, b"auth failed")

    with patch("smtplib.SMTP_SSL", return_value=fake_smtp):
        with pytest.raises(EmailSendError, match="邮件发送失败"):
            asyncio.run(svc.send_email(
                to=["a@b.com"], subject="主题", body="正文",
            ))


def test_send_email_raises_on_missing_attachment(tmp_path):
    """测试附件路径不存在时抛出 FileNotFoundError。"""
    config = _make_config()
    svc = EmailService(config)

    with pytest.raises(FileNotFoundError):
        asyncio.run(svc.send_email(
            to=["a@b.com"], subject="主题", body="正文",
            attachment_paths=[str(tmp_path / "nonexistent.pdf")],
        ))


# =============================================================================
# P2: 回归测试 - ASCII 安全的 local_hostname
# =============================================================================

def test_smtp_ssl_uses_ascii_local_hostname():
    """回归测试：SSL 分支必须显式传入 local_hostname=cfg.host，避免
    Windows 中文主机名场景下 socket.getfqdn() 返回非 ASCII 字符串
    导致 smtplib 在 EHLO 命令上抛 UnicodeEncodeError。
    """
    config = _make_config(use_ssl=True)
    svc = EmailService(config)

    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_smtp.__exit__.return_value = False
    fake_smtp.send_message.return_value = {}

    with patch("smtplib.SMTP_SSL", return_value=fake_smtp) as mock_ssl:
        asyncio.run(svc.send_email(
            to=["a@b.com"], subject="主题", body="正文",
        ))

    assert mock_ssl.call_count == 1
    kwargs = mock_ssl.call_args.kwargs
    assert "local_hostname" in kwargs, (
        "smtplib.SMTP_SSL 必须显式传入 local_hostname 参数，"
        "否则 socket.getfqdn() 在中文主机名下会触发 ascii 编码错误"
    )
    assert kwargs["local_hostname"] == config.host
    assert all(ord(ch) < 128 for ch in kwargs["local_hostname"]), (
        "local_hostname 必须为 ASCII 字符串"
    )


def test_smtp_starttls_uses_ascii_local_hostname():
    """回归测试：STARTTLS 分支必须显式传入 local_hostname=cfg.host。"""
    config = _make_config(use_ssl=False)
    svc = EmailService(config)

    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_smtp.__exit__.return_value = False
    fake_smtp.send_message.return_value = {}

    with patch("smtplib.SMTP", return_value=fake_smtp) as mock_smtp:
        asyncio.run(svc.send_email(
            to=["a@b.com"], subject="主题", body="正文",
        ))

    assert mock_smtp.call_count == 1
    kwargs = mock_smtp.call_args.kwargs
    assert "local_hostname" in kwargs, (
        "smtplib.SMTP 必须显式传入 local_hostname 参数，"
        "否则 socket.getfqdn() 在中文主机名下会触发 ascii 编码错误"
    )
    assert kwargs["local_hostname"] == config.host
    assert all(ord(ch) < 128 for ch in kwargs["local_hostname"]), (
        "local_hostname 必须为 ASCII 字符串"
    )


# =============================================================================
# P1: 2026-07-18 新增 - send_message refused 静默拒收校验
# =============================================================================

def test_send_email_raises_when_smtp_refuses_recipients_ssl():
    """SSL 模式下 smtp.send_message() 返回非空 refused 字典时，
    EmailService 必须抛 EmailSendError 而不是返回 success=True。

    设计原因：smtplib.SMTP.send_message() 在 RCPT TO 被拒时仅把失败项
    存到 smtp.refused 字典而不抛异常，导致 UI 显示「发送成功」但实际
    邮件未送达（用户场景：企业邮箱 → QQ 邮箱被反垃圾拦截）。
    """
    config = _make_config(use_ssl=True)
    svc = EmailService(config)

    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_smtp.__exit__.return_value = False
    # 模拟 send_message 返回 refused 字典（非空 → 部分收件人被拒）
    fake_smtp.send_message.return_value = {
        "bad@qq.com": (550, b"User unknown"),
    }

    with patch("smtplib.SMTP_SSL", return_value=fake_smtp):
        with pytest.raises(EmailSendError) as exc_info:
            asyncio.run(svc.send_email(
                to=["bad@qq.com"], subject="ceshi", body="ceshi",
            ))

    assert "拒收部分收件人" in str(exc_info.value)
    assert "bad@qq.com" in str(exc_info.value)


def test_send_email_raises_when_smtp_refuses_recipients_starttls():
    """STARTTLS 模式下同样的 refused 校验。"""
    config = _make_config(use_ssl=False)
    svc = EmailService(config)

    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_smtp.__exit__.return_value = False
    fake_smtp.send_message.return_value = {
        "spam@qq.com": (550, b"Message rejected as spam"),
    }

    with patch("smtplib.SMTP", return_value=fake_smtp):
        with pytest.raises(EmailSendError):
            asyncio.run(svc.send_email(
                to=["spam@qq.com"], subject="ceshi", body="ceshi",
            ))


# =============================================================================
# P1: 2026-07-18 新增 - RFC 5322 必备头（Date / MIME-Version / Message-ID 域）
# =============================================================================

def test_build_message_includes_date_header():
    """邮件必须包含 Date 头，否则被反垃圾系统判为伪造邮件。

    根因：Python EmailMessage 默认不自动加 Date；用户实测发现，
    用我们系统发到企业邮箱 / QQ 邮箱的邮件全部"显示成功但收不到"，
    但用 QQ 邮箱网页版直接发就能收到。补齐 Date / MIME-Version 后
    通过主流邮件服务器反垃圾校验。
    """
    from email.utils import parsedate_to_datetime

    config = _make_config()
    svc = EmailService(config)
    msg = svc._build_message(
        to=["recv@example.com"], subject="s", body="b",
        cc=None, attachment_paths=None, attachment_streams=None,
    )

    assert msg["Date"] is not None
    # 解析回 datetime 不抛异常 = 格式合法
    parsedate_to_datetime(msg["Date"])


def test_build_message_includes_mime_version_header():
    """包含附件或非 ASCII 字符时，MIME-Version: 1.0 是 RFC 2045 必备字段。"""
    config = _make_config()
    svc = EmailService(config)
    msg = svc._build_message(
        to=["recv@example.com"], subject="s", body="b",
        cc=None, attachment_paths=None, attachment_streams=None,
    )

    assert msg["MIME-Version"] == "1.0"


def test_build_message_uses_from_addr_domain_for_message_id():
    """Message-ID 域必须与 From 域一致，否则反垃圾判为伪造邮件。

    原代码用 cfg.host（如 smtp.qq.com）作为 Message-ID 域，
    但 From 是 zhangyipu@foxmail.com，域不一致会被反垃圾系统标记。
    """
    config = _make_config()
    config.host = "smtp.qq.com"
    config.username = "zhangyipu@foxmail.com"  # 故意让 host 与 username 域不一致
    svc = EmailService(config)
    msg = svc._build_message(
        to=["recv@example.com"], subject="s", body="b",
        cc=None, attachment_paths=None, attachment_streams=None,
    )

    # Message-ID 必须是 <...@foxmail.com>，不是 <...@smtp.qq.com>
    message_id = msg["Message-ID"]
    assert message_id.endswith("@foxmail.com>"), (
        f"Message-ID 域应等于 From 域（foxmail.com），实际: {message_id}"
    )


def test_build_message_message_id_fallback_when_no_at_in_username():
    """username 不含 @ 时退化为 cfg.host（防御性 fallback）。"""
    config = _make_config()
    config.host = "mail.geostar.com.cn"
    config.username = "zhangyipu"  # 无 @ 后缀
    svc = EmailService(config)
    msg = svc._build_message(
        to=["recv@example.com"], subject="s", body="b",
        cc=None, attachment_paths=None, attachment_streams=None,
    )

    # 没有 @ 时回退到 host
    assert msg["Message-ID"].endswith("@mail.geostar.com.cn>")
