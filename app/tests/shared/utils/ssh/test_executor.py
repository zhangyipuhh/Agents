# -*- coding:utf-8 -*-
"""全局 SSH helper 的脚本执行测试。"""

from unittest.mock import MagicMock

import pytest

from app.shared.utils.ssh.executor import SSHExecResult, execute_script


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
