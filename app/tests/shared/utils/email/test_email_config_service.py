# -*- coding:utf-8 -*-
"""
EmailConfigService.test_connection 单元测试模块。

验证 SMTP 连接测试接口的异常分类逻辑：
- 认证失败 / 服务器主动断开 / 连接失败 / SSL 握手失败 / 网络层失败 / 兜底异常
  各自返回带可读提示的 ``{"success": False, "message": ...}``。
- 成功路径仍返回 ``{"success": True, "message": "SMTP 连接成功"}``。
"""
import asyncio
import smtplib
import ssl
from unittest.mock import MagicMock, patch

import pytest

from app.shared.utils.email.email_config_service import EmailConfigService
from app.shared.utils.email.email_models import EmailServerConfig


# =============================================================================
# P0: 导入与构造
# =============================================================================

def test_email_config_service_importable():
    """测试 EmailConfigService 模块可导入。"""
    from app.shared.utils.email import email_config_service
    assert hasattr(email_config_service, "EmailConfigService")


def _make_config(use_ssl: bool = True, password: str = "authcode") -> EmailServerConfig:
    """构造测试用 SMTP 配置。

    参数:
        use_ssl: 是否启用 SMTP_SSL。
        password: 授权码；传空字符串时跳过 smtp.login。

    返回:
        EmailServerConfig: 测试配置实例。
    """
    return EmailServerConfig(
        host="smtp.qq.com",
        port=465 if use_ssl else 587,
        use_ssl=use_ssl,
        username="zhangyipu@foxmail.com.cn",
        password=password,
        sender_name="测试",
        enabled=True,
    )


def _make_service() -> EmailConfigService:
    """构造不带 DB 的 EmailConfigService（test_connection 不需要 DB）。

    返回:
        EmailConfigService: 实例。
    """
    return EmailConfigService(db=None, credential_key="")


# =============================================================================
# P1: 成功路径
# =============================================================================

def test_test_connection_ssl_success():
    """测试 SMTP_SSL 模式测试连接成功（mock smtplib.SMTP_SSL）。"""
    svc = _make_service()
    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_smtp.__exit__.return_value = False

    with patch("smtplib.SMTP_SSL", return_value=fake_smtp) as mock_ssl:
        result = asyncio.run(svc.test_connection(_make_config(use_ssl=True)))

    assert result == {"success": True, "message": "SMTP 连接成功"}
    fake_smtp.login.assert_called_once_with(
        "zhangyipu@foxmail.com.cn", "authcode"
    )
    mock_ssl.assert_called_once()


def test_test_connection_starttls_success():
    """测试 STARTTLS 模式测试连接成功（mock smtplib.SMTP）。"""
    svc = _make_service()
    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_smtp.__exit__.return_value = False

    with patch("smtplib.SMTP", return_value=fake_smtp) as mock_smtp:
        result = asyncio.run(svc.test_connection(_make_config(use_ssl=False)))

    assert result == {"success": True, "message": "SMTP 连接成功"}
    fake_smtp.starttls.assert_called_once()
    fake_smtp.login.assert_called_once()
    mock_smtp.assert_called_once()


# =============================================================================
# P1: 失败路径（异常分类）
# =============================================================================

def test_test_connection_auth_failure_returns_auth_message():
    """认证失败（535）应返回 ``SMTP 认证失败`` 消息。"""
    svc = _make_service()
    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_smtp.__exit__.return_value = False
    fake_smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, b"auth failed")

    with patch("smtplib.SMTP_SSL", return_value=fake_smtp):
        result = asyncio.run(svc.test_connection(_make_config()))

    assert result["success"] is False
    assert "SMTP 认证失败" in result["message"]
    assert "auth failed" in result["message"]


def test_test_connection_server_disconnected_returns_disconnected_message():
    """服务器主动断开（域名不被识别）应返回 ``服务器主动断开连接`` + 切换主机建议。"""
    svc = _make_service()
    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_smtp.__exit__.return_value = False
    fake_smtp.login.side_effect = smtplib.SMTPServerDisconnected("Connection unexpectedly closed")

    with patch("smtplib.SMTP_SSL", return_value=fake_smtp):
        result = asyncio.run(svc.test_connection(_make_config()))

    assert result["success"] is False
    assert "服务器主动断开连接" in result["message"]
    assert "smtp.exmail.qq.com" in result["message"]


def test_test_connection_ssl_failure_returns_ssl_message():
    """SSL 握手失败应返回 ``SSL 握手失败`` + 切换 STARTTLS 建议。"""
    svc = _make_service()
    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_smtp.__exit__.return_value = False
    fake_smtp.login.side_effect = ssl.SSLError("CERTIFICATE_VERIFY_FAILED")

    with patch("smtplib.SMTP_SSL", return_value=fake_smtp):
        result = asyncio.run(svc.test_connection(_make_config(use_ssl=True)))

    assert result["success"] is False
    assert "SSL 握手失败" in result["message"]
    assert "STARTTLS" in result["message"]


def test_test_connection_network_failure_returns_network_message():
    """网络层失败（DNS / 不可达）应返回 ``网络层失败`` + 防火墙提示。"""
    svc = _make_service()
    fake_smtp = MagicMock()
    fake_smtp.__enter__.side_effect = OSError(11001, "getaddrinfo failed")

    with patch("smtplib.SMTP_SSL", return_value=fake_smtp):
        result = asyncio.run(svc.test_connection(_make_config()))

    assert result["success"] is False
    assert "网络层失败" in result["message"]
    assert "DNS" in result["message"] or "防火墙" in result["message"]


def test_test_connection_connect_failure_ssl_includes_hint():
    """SMTPConnectError 在 SSL 模式下应在错误消息中引导切到 587。"""
    svc = _make_service()
    fake_smtp = MagicMock()
    fake_smtp.__enter__.side_effect = smtplib.SMTPConnectError(421, "Cannot connect")

    with patch("smtplib.SMTP_SSL", return_value=fake_smtp):
        result = asyncio.run(svc.test_connection(_make_config(use_ssl=True)))

    assert result["success"] is False
    assert "SMTP 连接失败" in result["message"]
    assert "STARTTLS" in result["message"] or "587" in result["message"]


def test_test_connection_connect_failure_starttls_includes_firewall_hint():
    """SMTPConnectError 在 STARTTLS 模式下应给出防火墙/RST 提示。"""
    svc = _make_service()
    fake_smtp = MagicMock()
    fake_smtp.__enter__.side_effect = smtplib.SMTPConnectError(421, "Cannot connect")

    with patch("smtplib.SMTP", return_value=fake_smtp):
        result = asyncio.run(svc.test_connection(_make_config(use_ssl=False)))

    assert result["success"] is False
    assert "SMTP 连接失败" in result["message"]
    assert "RST" in result["message"] or "防火墙" in result["message"]


def test_test_connection_unexpected_exception_returns_generic_message():
    """其他未分类异常应走兜底分支返回 ``SMTP 测试失败``。"""
    svc = _make_service()
    fake_smtp = MagicMock()
    fake_smtp.__enter__.side_effect = RuntimeError("unknown boom")

    with patch("smtplib.SMTP_SSL", return_value=fake_smtp):
        result = asyncio.run(svc.test_connection(_make_config()))

    assert result["success"] is False
    assert "SMTP 测试失败" in result["message"]
    assert "unknown boom" in result["message"]


def test_test_connection_skips_login_when_password_empty():
    """密码为空时不应调用 smtp.login（保留与之前实现的兼容行为）。"""
    svc = _make_service()
    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_smtp.__exit__.return_value = False

    with patch("smtplib.SMTP_SSL", return_value=fake_smtp):
        result = asyncio.run(svc.test_connection(_make_config(password="")))

    assert result["success"] is True
    fake_smtp.login.assert_not_called()


# =============================================================================
# P2: 回归测试 - ASCII 安全的 local_hostname
# =============================================================================

def test_test_connection_ssl_uses_ascii_local_hostname():
    """回归测试：SSL 分支必须显式传入 local_hostname=config.host，
    避免 Windows 中文主机名场景下 socket.getfqdn() 返回非 ASCII 字符串
    导致 smtplib 在 EHLO 命令上抛 UnicodeEncodeError。
    """
    svc = _make_service()
    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_smtp.__exit__.return_value = False

    with patch("smtplib.SMTP_SSL", return_value=fake_smtp) as mock_ssl:
        asyncio.run(svc.test_connection(_make_config(use_ssl=True)))

    assert mock_ssl.call_count == 1
    kwargs = mock_ssl.call_args.kwargs
    assert "local_hostname" in kwargs, (
        "smtplib.SMTP_SSL 必须显式传入 local_hostname 参数，"
        "否则 socket.getfqdn() 在中文主机名下会触发 ascii 编码错误"
    )
    assert kwargs["local_hostname"] == "smtp.qq.com"
    assert all(ord(ch) < 128 for ch in kwargs["local_hostname"]), (
        "local_hostname 必须为 ASCII 字符串"
    )


def test_test_connection_starttls_uses_ascii_local_hostname():
    """回归测试：STARTTLS 分支必须显式传入 local_hostname=config.host。"""
    svc = _make_service()
    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_smtp.__exit__.return_value = False

    with patch("smtplib.SMTP", return_value=fake_smtp) as mock_smtp:
        asyncio.run(svc.test_connection(_make_config(use_ssl=False)))

    assert mock_smtp.call_count == 1
    kwargs = mock_smtp.call_args.kwargs
    assert "local_hostname" in kwargs, (
        "smtplib.SMTP 必须显式传入 local_hostname 参数，"
        "否则 socket.getfqdn() 在中文主机名下会触发 ascii 编码错误"
    )
    assert kwargs["local_hostname"] == "smtp.qq.com"
    assert all(ord(ch) < 128 for ch in kwargs["local_hostname"]), (
        "local_hostname 必须为 ASCII 字符串"
    )


# =============================================================================
# P1: 2026-07-18 新增 - 企业邮箱兼容字段（方案 Z）
# =============================================================================

def test_force_plain_skips_starttls():
    """force_plain=True 时不应调用 smtp.starttls（支持 25 端口明文 SMTP）。"""
    svc = _make_service()
    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_smtp.__exit__.return_value = False

    config = _make_config(use_ssl=False, password="authcode")
    config.force_plain = True  # 2026-07-18 新增字段

    with patch("smtplib.SMTP", return_value=fake_smtp) as mock_smtp:
        result = asyncio.run(svc.test_connection(config))

    assert result == {"success": True, "message": "SMTP 连接成功"}
    fake_smtp.starttls.assert_not_called()
    fake_smtp.login.assert_called_once_with("zhangyipu@foxmail.com.cn", "authcode")
    mock_smtp.assert_called_once()


def test_default_force_plain_still_calls_starttls():
    """force_plain 默认 False 时仍应调用 smtp.starttls（保持向后兼容）。"""
    svc = _make_service()
    fake_smtp = MagicMock()
    fake_smtp.__enter__.return_value = fake_smtp
    fake_smtp.__exit__.return_value = False

    config = _make_config(use_ssl=False, password="authcode")
    # force_plain 不显式设置，走默认 False
    assert config.force_plain is False

    with patch("smtplib.SMTP", return_value=fake_smtp):
        result = asyncio.run(svc.test_connection(config))

    assert result["success"] is True
    fake_smtp.starttls.assert_called_once()


def test_build_ssl_context_minimum_tls_v1():
    """_build_ssl_context 必须把 SSLContext.minimum_version 降级到 TLSv1，
    以兼容老企业 SMTP 服务器（Python 3.10+ 默认要求 TLSv1.2 会触发 WRONG_VERSION_NUMBER）。
    """
    config = _make_config(use_ssl=True, password="authcode")
    ctx = EmailConfigService._build_ssl_context(config)

    # minimum_version 属性返回 TLSVersion 枚举；TLSv1 对应整数 769 (0x0301)
    assert ctx.minimum_version <= ssl.TLSVersion.TLSv1, (
        f"minimum_version 应 <= TLSv1，实际 {ctx.minimum_version}"
    )


def test_build_ssl_context_disables_verification_when_verify_ssl_false():
    """verify_ssl=False 时应关闭证书校验（自签证书场景）。"""
    config = _make_config(use_ssl=True, password="authcode")
    config.verify_ssl = False

    ctx = EmailConfigService._build_ssl_context(config)

    assert ctx.check_hostname is False
    assert ctx.verify_mode == ssl.CERT_NONE


def test_build_ssl_context_default_verify_ssl_true_keeps_strict():
    """verify_ssl 默认 True 时保持证书校验严格（CERT_REQUIRED）。"""
    config = _make_config(use_ssl=True, password="authcode")
    ctx = EmailConfigService._build_ssl_context(config)

    # 默认 verify_ssl=True，证书校验应为 REQUIRED
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True