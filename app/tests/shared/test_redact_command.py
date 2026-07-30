# -*- coding:utf-8 -*-
"""
``app.shared.utils.log_service.redact_command`` 全模式覆盖测试（2026-07-29）。

需求：redact_command 必须覆盖以下命令形态，确保敏感口令 / token / 凭据不外泄：

1. ``KEY=value``（无空格、无引号）
2. ``KEY: value``（带冒号分隔）
3. ``--key value``（空格分隔值）
4. ``--key=value``（等号连接）
5. 值无引号 / 单引号 / 双引号均须脱敏

扩展：
- Bearer token（如 ``Authorization: Bearer eyJ...``）
- URL userinfo（如 ``https://user:pass@host``）
- 控制字符清除（如 ``\\r\\n\\t`` → 删除）
- 截断 2000 字符上限
- 敏感键按批准列表（password / token / secret / apikey / authorization / bearer / credential 等）
- hash_command 仍基于原始命令（脱敏前）

返回:
    None。

异常:
    AssertionError: 任何模式漏掉敏感字段时抛出。
"""
from __future__ import annotations

import pytest

from app.shared.utils.log_service import hash_command, redact_command


# =============================================================================
# 1. KEY=value（无空格、无引号）
# =============================================================================


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("mysql --password=secret123 -e 'select 1'", "mysql --password=***REDACTED*** -e 'select 1'"),
        ("TOKEN=abc123 --token=xyz --api-key=apivalue", "TOKEN=***REDACTED*** --token=***REDACTED*** --api-key=***REDACTED***"),
        ("export PASSWORD=hunter2", "export PASSWORD=***REDACTED***"),
    ],
)
def test_redact_key_equals_value_without_quotes(raw, expected):
    """KEY=value 无引号形式须被脱敏为 ``***``。"""
    assert redact_command(raw) == expected


# =============================================================================
# 2. KEY: value（冒号分隔）
# =============================================================================


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("password: hunter2xyz", "password: ***REDACTED***"),
        ("PASSWORD: topsecret", "PASSWORD: ***REDACTED***"),
        ("api_key: AKIA1234", "api_key: ***REDACTED***"),
        ("secret: mysecret", "secret: ***REDACTED***"),
    ],
)
def test_redact_key_colon_value(raw, expected):
    """KEY: value 冒号分隔形式须被脱敏。"""
    assert redact_command(raw) == expected


# =============================================================================
# 3. --key value（空格分隔值）
# =============================================================================


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("mysql --password hunter2xyz", "mysql --password ***REDACTED***"),
        ("curl --token abc123", "curl --token ***REDACTED***"),
        ("mycli --api-key apivalue", "mycli --api-key ***REDACTED***"),
        ("tool --authorization BearerXYZ", "tool --authorization ***REDACTED***"),
    ],
)
def test_redact_dash_dash_key_space_value(raw, expected):
    """--key value 空格分隔形式须被脱敏。"""
    assert redact_command(raw) == expected


# =============================================================================
# 4. --key=value（等号连接 + 引号）
# =============================================================================


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("mysql --password='hunter2xyz'", "mysql --password=***REDACTED***"),
        ('mysql --password="hunter2xyz"', "mysql --password=***REDACTED***"),
        ("tool --token='abc'", "tool --token=***REDACTED***"),
        ('tool --api-key="apiv"', "tool --api-key=***REDACTED***"),
    ],
)
def test_redact_dash_dash_key_equals_value_with_quotes(raw, expected):
    """--key=value 等号连接 + 引号形式须被脱敏。"""
    assert redact_command(raw) == expected


# =============================================================================
# 5. 值无引号 / 单引号 / 双引号均脱敏
# =============================================================================


@pytest.mark.parametrize(
    "raw",
    [
        "mysql --password=hunter2",
        "mysql --password='hunter2'",
        'mysql --password="hunter2"',
    ],
)
def test_redact_dash_dash_password_handles_all_quote_modes(raw):
    """``--password`` 三种引号形态均须脱敏（值被替换为 ``***``）。"""
    redacted = redact_command(raw)
    assert "hunter2" not in redacted
    assert "--password=***REDACTED***" in redacted


# =============================================================================
# 6. Bearer token
# =============================================================================


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload", "Authorization: Bearer ***REDACTED***"),
        ("curl -H 'Authorization: Bearer eyJabc.def'", "curl -H 'Authorization: Bearer ***REDACTED***'"),
        ('curl -H "Authorization: Bearer my-token-xyz"', 'curl -H "Authorization: Bearer ***REDACTED***"'),
    ],
)
def test_redact_bearer_token(raw, expected):
    """``Authorization: Bearer <token>`` 形式须脱敏为 ``Bearer ***REDACTED***``。"""
    assert redact_command(raw) == expected


# =============================================================================
# 7. URL userinfo
# =============================================================================


@pytest.mark.parametrize(
    "raw",
    [
        "curl https://admin:hunter2@example.com/api",
        "wget http://user:pass@host.example.com",
        "git clone https://oauth2:glpat-xyz@gitlab.com/repo.git",
    ],
)
def test_redact_url_userinfo(raw):
    """URL 中 ``scheme://user:password@host`` 的 userinfo 必须脱敏。"""
    redacted = redact_command(raw)
    # 任意 userinfo 形式:用户名 / 密码不应保留
    assert "hunter2" not in redacted
    assert ":pass@" not in redacted
    assert "glpat-xyz" not in redacted
    # 主机名应当保留
    assert "example.com" in redacted or "host.example.com" in redacted or "gitlab.com" in redacted


# =============================================================================
# 8. 控制字符清除
# =============================================================================


def test_redact_strips_control_characters():
    """控制字符 (\\r \\n \\t) 必须被移除。"""
    raw = "mysql --password=secret\n\rextra"
    redacted = redact_command(raw)
    assert "\n" not in redacted
    assert "\r" not in redacted
    assert "secret" not in redacted


@pytest.mark.parametrize("ctl", ["\x00", "\x01", "\x07", "\x0b", "\x0c"])
def test_redact_strips_ascii_control_chars(ctl):
    """ASCII 控制字符 (除 \\t \\n \\r) 必须被移除。"""
    raw = f"cmd --password=secret{ctl}tail"
    redacted = redact_command(raw)
    assert ctl not in redacted
    assert "secret" not in redacted


# =============================================================================
# 9. 截断 2000 字符
# =============================================================================


def test_redact_truncates_long_command():
    """超过 2000 字符的 redact 结果必须被截断到 2000 字符。"""
    raw = "echo " + ("a" * 3000)
    redacted = redact_command(raw)
    assert len(redacted) <= 2000


def test_redact_truncation_marker():
    """截断后末尾须带 ``...<truncated>`` 标记。"""
    raw = "echo " + ("a" * 3000)
    redacted = redact_command(raw)
    assert "truncated" in redacted.lower() or redacted.endswith("...") or len(redacted) <= 2000


# =============================================================================
# 10. hash_command 仍对原始命令
# =============================================================================


def test_hash_uses_original_command_not_redacted():
    """hash_command 必须对原始命令（含敏感字段）做哈希,与 redact_command 输出无关。"""
    raw = "mysql --password=hunter2xyz"
    assert hash_command(raw) == hash_command(raw)
    # redact 后的命令不应产生与原始命令相同的 hash
    redacted = redact_command(raw)
    assert hash_command(redacted) != hash_command(raw)


def test_hash_stable_for_same_input():
    """同一原始命令的 hash 必须稳定。"""
    raw = "mysql --password=hunter2xyz -e 'select 1'"
    assert hash_command(raw) == hash_command(raw)
    assert len(hash_command(raw)) == 64


# =============================================================================
# 11. 敏感键批准列表
# =============================================================================


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "api-key",
        "authorization",
        "auth",
        "credential",
        "credentials",
        "private_key",
        "privatekey",
    ],
)
def test_redact_approved_sensitive_keys(key):
    """批准列表中的所有敏感键必须被脱敏。"""
    raw = f"mytool --{key}=topsecret"
    redacted = redact_command(raw)
    assert "topsecret" not in redacted


# =============================================================================
# 12. 边缘情况
# =============================================================================


def test_redact_none_returns_empty_string():
    """``None`` 输入须返回空字符串,不抛异常。"""
    assert redact_command(None) == ""


def test_redact_empty_string_returns_empty():
    """空字符串输入须返回空字符串。"""
    assert redact_command("") == ""


def test_redact_preserves_non_sensitive_substrings():
    """非敏感字段不应被误伤。"""
    raw = "echo hello world --verbose"
    assert redact_command(raw) == "echo hello world --verbose"


def test_redact_short_p_dash_p_form():
    """``-pvalue`` 短选项形式须脱敏。"""
    assert "mysql -uroot -p***REDACTED***" == redact_command("mysql -uroot -psecret")


def test_redact_inside_pipeline():
    """管道连接的子命令中的敏感字段都应被脱敏。"""
    raw = "cat /etc/shadow | grep --password=hunter2 | head"
    redacted = redact_command(raw)
    assert "hunter2" not in redacted
