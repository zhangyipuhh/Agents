# -*- coding:utf-8 -*-
"""全局 SSH helper 的脚本执行测试。"""

from unittest.mock import MagicMock

import pytest

from app.shared.utils.ssh.executor import SSHExecResult, _decode_remote_bytes, execute_script


@pytest.fixture
def ssh_config():
    """返回不包含真实凭据的 SSH 测试配置。"""
    return {
        "ip": "10.0.0.1",
        "port": 22,
        "username": "tester",
        "password": "secret",
        "server_type": "linux",
    }


def _patch_paramiko(monkeypatch, stdout_text="ok\n", stderr_text="", exit_code=0):
    """替换 executor 使用的 Paramiko 客户端。"""
    client = MagicMock(name="ssh-client")
    stdout = MagicMock()
    stderr = MagicMock()
    stdout.read.return_value = stdout_text.encode("utf-8")
    stderr.read.return_value = stderr_text.encode("utf-8")
    stdout.channel.recv_exit_status.return_value = exit_code
    client.exec_command.return_value = (MagicMock(), stdout, stderr)

    paramiko_mock = MagicMock()
    paramiko_mock.SSHClient.return_value = client
    paramiko_mock.AutoAddPolicy.return_value = MagicMock()
    monkeypatch.setattr("app.shared.utils.ssh.executor.paramiko", paramiko_mock)
    return client


def test_execute_script_runs_multiline_script_without_command_interceptor(
    monkeypatch, ssh_config
):
    """helper 应执行包含 $() 的完整多行脚本并返回标准结果。"""
    client = _patch_paramiko(monkeypatch, stdout_text='{"ok":true}\n')
    script = "#!/bin/bash\nVALUE=$(df -P / | tail -1)\nprintf '{\"ok\":true}\\n'"

    result = execute_script(ssh_config, script, timeout=999)

    assert isinstance(result, SSHExecResult)
    assert result.success is True
    assert result.stdout == '{"ok":true}'
    assert result.stderr == ""
    assert result.exit_code == 0
    client.exec_command.assert_called_once()
    wrapped, kwargs = client.exec_command.call_args
    assert wrapped is not None
    assert "/bin/bash -c" in wrapped[0]
    assert "$(df -P /" in wrapped[0]
    assert kwargs["timeout"] == 120
    client.close.assert_called_once()


def test_execute_script_returns_stderr_and_failed_status(monkeypatch, ssh_config):
    """远程脚本有 stderr 时应返回失败状态和原始错误输出。"""
    client = _patch_paramiko(
        monkeypatch, stdout_text="partial\n", stderr_text="failed\n", exit_code=1
    )

    result = execute_script(ssh_config, "echo partial")

    assert result.success is False
    assert result.stdout == "partial"
    assert result.stderr == "failed"
    assert result.exit_code == 1
    client.close.assert_called_once()


def test_execute_script_empty_script_does_not_connect(monkeypatch, ssh_config):
    """空脚本应直接失败，且不创建或连接 SSH 客户端。"""
    paramiko_mock = MagicMock()
    monkeypatch.setattr("app.shared.utils.ssh.executor.paramiko", paramiko_mock)

    with pytest.raises(ValueError, match="script 不能为空"):
        execute_script(ssh_config, "\n")

    paramiko_mock.SSHClient.assert_not_called()


def test_decode_remote_bytes_uses_utf8_for_clean_input():
    """远端输出为合法 UTF-8 时,直接返回 UTF-8 解码结果。"""
    raw = "OK\n".encode("utf-8")
    assert _decode_remote_bytes(raw) == "OK"


def test_decode_remote_bytes_falls_back_to_gbk_for_chinese_stderr():
    """Windows 中文环境 stderr 默认 GBK 输出,>=3 个 U+FFFD 时 fallback GBK 还原中文。

    2026-08-16 改造:原策略硬编码 UTF-8 + errors="replace",把中文 stderr 全部替换为
    U+FFFD,日志中无法读出原文。本测试锁定 GBK fallback 行为。
    """
    # "参数太长" GBK 编码 = b2ce cafd ccab b3a4
    raw = bytes([0xb2, 0xce, 0xca, 0xfd, 0xcc, 0xab, 0xb3, 0xa4])
    decoded = _decode_remote_bytes(raw)
    # GBK fallback 应能还原中文
    assert "参" in decoded
    assert "太" in decoded
    assert "长" in decoded
    # 不应再有 U+FFFD
    assert "\ufffd" not in decoded


def test_decode_remote_bytes_handles_empty_input():
    """空字节流直接返回空字符串,不抛异常。"""
    assert _decode_remote_bytes(b"") == ""


def test_execute_script_closes_stdin_write_side(monkeypatch, ssh_config):
    """exec_command 后应关闭 stdin 写端（向远端发送 EOF）。

    Windows OpenSSH 默认 shell 在非 PTY exec 通道下会等待 stdin EOF 才退出,
    不关闭写端会导致 ``stdout.read()`` 永久阻塞直至超时（TimeoutError）;
    巡检脚本均不读取 stdin,关闭写端对 Linux / Windows 均无副作用。

    参数:
        monkeypatch: pytest monkeypatch fixture。
        ssh_config: 测试 SSH 配置 fixture。

    返回:
        None。

    异常:
        无（断言失败由 pytest 抛出）。
    """
    client = _patch_paramiko(monkeypatch, stdout_text="ok\n")

    execute_script(ssh_config, "echo ok")

    stdin = client.exec_command.return_value[0]
    stdin.close.assert_called_once()
