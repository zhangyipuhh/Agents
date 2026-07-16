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
