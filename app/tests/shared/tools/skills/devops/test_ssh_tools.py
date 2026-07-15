# -*- coding:utf-8 -*-
"""
SSHTools 单元测试（2026-07-15 新增）

覆盖目标：
    - 模块暴露的三个 ``@tool(description=...)`` 函数能正确导入并保留工具描述
    - ``execute_command`` 通过 DevOpsServerService 单例获取连接配置，
      并使用 paramiko.SSHClient.exec_command 真正执行
    - 平台派生：service 返回的 server_type 决定走 bash（Linux）还是
      powershell（Windows），LLM 端传入的 ``server_type`` 参数被忽略
    - ``execute_batch_commands`` 一旦某条命令被黑名单拦截 → 整批拒绝
    - ``execute_command`` 返回的 Command（含 ToolMessage）不出现
      连接配置敏感字段（password / ip / username 等）
    - ``get_system_logs`` 内部生成的 shell 命令（tail）也走策略检查
    - 通过 monkeypatch 注入 service 单例与 paramiko 客户端，避免触碰真实 IO

注意：
    - 测试环境 conftest 把 ``langchain.tools.tool`` mock 成 identity 装饰器，
      因此本测试直接调用底层函数（不通过 StructuredTool.invoke）。
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest


def _build_runtime(business_name: str = "alpha", session_id: str = "sess-x"):
    """构造一个简单的 ``ToolRuntime`` 替身（最小字段集）。

    Args:
        business_name: 业务名
        session_id: 会话 ID

    Returns:
        MagicMock: 模拟的 runtime
    """
    runtime = MagicMock(name="ToolRuntime")
    runtime.tool_call_id = "call-x"
    runtime.context = {"business_name": business_name, "session_id": session_id}
    return runtime


def _patch_service(monkeypatch, config):
    """把 ``DevOpsServerService`` 单例换成 stub，返回 ``config``。

    Args:
        monkeypatch: pytest monkeypatch fixture
        config: ``get_connection_config`` 的固定返回
    """
    from app.shared.utils.devops_server_service import DevOpsServerService

    fake_service = MagicMock(name="DevOpsServerService")
    fake_service.get_connection_config = MagicMock(return_value=config)
    DevOpsServerService.set_instance(fake_service)
    return fake_service


def _patch_paramiko(monkeypatch, stdout_text="", stderr_text="", exit_code=0):
    """替换 ``app.shared.tools.skills.devops.SSHTools.paramiko``。

    Args:
        monkeypatch: pytest monkeypatch
        stdout_text: 标准输出
        stderr_text: 标准错误
        exit_code: 退出码

    Returns:
        MagicMock: fake client
    """
    fake_client = MagicMock(name="paramiko.SSHClient")
    stdin = MagicMock()
    stdout = MagicMock()
    stderr = MagicMock()
    stdout.read = MagicMock(return_value=stdout_text.encode("utf-8"))
    stderr.read = MagicMock(return_value=stderr_text.encode("utf-8"))
    stdout.channel.recv_exit_status = MagicMock(return_value=exit_code)
    fake_client.exec_command = MagicMock(return_value=(stdin, stdout, stderr))
    fake_client.close = MagicMock(return_value=None)

    fake_paramiko = MagicMock(name="paramiko")
    fake_paramiko.SSHClient = MagicMock(return_value=fake_client)
    fake_paramiko.AutoAddPolicy = MagicMock(return_value=MagicMock())
    # 真实异常类，方便 isinstance 检查
    import paramiko as real_paramiko
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException

    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, "paramiko", fake_paramiko, raising=False)
    return fake_client


# ----------------------------------------------------------------------
# 1. 模块可导入 + 函数名
# ----------------------------------------------------------------------


def test_module_exposes_three_tools():
    """SSHTools 模块应暴露三个可调用工具（execute_command / batch / logs）。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.SSHTools import (
        execute_command,
        execute_batch_commands,
        get_system_logs,
    )
    for tool_obj in (execute_command, execute_batch_commands, get_system_logs):
        assert callable(tool_obj)
        assert tool_obj.__name__ in {
            "execute_command",
            "execute_batch_commands",
            "get_system_logs",
        }


def test_tools_have_runtime_param():
    """三个工具函数的签名都包含 ``runtime`` 参数（LangChain ToolRuntime）。

    Returns:
        None
    """
    import inspect

    from app.shared.tools.skills.devops.SSHTools import (
        execute_command,
        execute_batch_commands,
        get_system_logs,
    )
    for tool_obj in (execute_command, execute_batch_commands, get_system_logs):
        sig = inspect.signature(tool_obj)
        assert "runtime" in sig.parameters


# ----------------------------------------------------------------------
# 2. execute_command
# ----------------------------------------------------------------------


def test_execute_command_runs_linux_and_uses_bash(monkeypatch):
    """Linux server_type → /bin/bash；参数 ``runtime`` 由 LangChain 注入。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    secret_config = {
        "ip": "10.0.0.1",
        "port": 22,
        "username": "rootuser",
        "password": "supersecret-pwd-xyz",
        "server_type": "linux",
        "blacklist": [],
        "whitelist": ["echo "],
    }
    fake_service = _patch_service(monkeypatch, secret_config)
    fake_client = _patch_paramiko(monkeypatch, stdout_text="hello\n", exit_code=0)
    runtime = _build_runtime(business_name="alpha")

    from app.shared.tools.skills.devops.SSHTools import execute_command

    out = execute_command(
        command="echo hello",
        runtime=runtime,
    )
    msgs = out.update["messages"]
    assert len(msgs) == 1
    payload = json.loads(msgs[0].content)
    assert payload.get("success") is True
    assert "hello" in payload.get("output", "")
    # 密码、IP、用户名绝不能出现在 ToolMessage
    tool_text = msgs[0].content
    assert "supersecret-pwd-xyz" not in tool_text
    assert "10.0.0.1" not in tool_text
    assert "rootuser" not in tool_text
    # paramiko 实际执行的命令前缀应为 /bin/bash
    args, kwargs = fake_client.exec_command.call_args
    assert "/bin/bash" in args[0]
    assert "echo hello" in args[0]
    # service.get_connection_config 使用 business_name
    fake_service.get_connection_config.assert_called_with("alpha")


def test_execute_command_runs_windows_and_uses_powershell(monkeypatch):
    """windows server_type → powershell.exe。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    win_config = {
        "ip": "10.0.0.2",
        "port": 22,
        "username": "administrator",
        "password": "winsecret-abc",
        "server_type": "windows",
        "blacklist": [],
        "whitelist": ["Get-Service"],
    }
    _patch_service(monkeypatch, win_config)
    fake_client = _patch_paramiko(monkeypatch, stdout_text="win-out", exit_code=0)
    runtime = _build_runtime(business_name="beta")

    from app.shared.tools.skills.devops.SSHTools import execute_command

    out = execute_command(
        command="Get-Service",
        runtime=runtime,
    )
    args, _ = fake_client.exec_command.call_args
    assert "powershell.exe" in args[0]
    # 平台派生由 service 决定；LLM 端无 server_type 参数
    # 确认 ToolMessage 不外泄密码与 IP
    msgs = out.update["messages"]
    raw = msgs[0].content
    raw_text = raw if isinstance(raw, str) else str(raw)
    assert "winsecret-abc" not in raw_text
    assert "10.0.0.2" not in raw_text


def test_execute_command_blacklist_blocks_command(monkeypatch):
    """黑名单正则命中时拒绝执行，不调 paramiko。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    cfg = {
        "ip": "10.0.0.3",
        "port": 22,
        "username": "u",
        "password": "secpwd",
        "server_type": "linux",
        "blacklist": [r"^rm\s+-rf"],
        "whitelist": ["rm -rf /tmp/x"],
    }
    _patch_service(monkeypatch, cfg)
    fake_client = _patch_paramiko(monkeypatch, stdout_text="should-not-run", exit_code=0)
    runtime = _build_runtime(business_name="gamma")

    from app.shared.tools.skills.devops.SSHTools import execute_command

    out = execute_command(
        command="rm -rf /tmp/x",
        runtime=runtime,
    )
    msgs = out.update["messages"]
    payload = json.loads(msgs[0].content)
    assert payload.get("blocked") is True or payload.get("success") is False
    fake_client.exec_command.assert_not_called()


def test_execute_command_whitelist_empty_blocks(monkeypatch):
    """白名单显式空（whitelist=[]）时，所有非空命令拒绝。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    cfg = {
        "ip": "10.0.0.4",
        "port": 22,
        "username": "u",
        "password": "spwd",
        "server_type": "linux",
        "blacklist": [],
        "whitelist": [],
    }
    _patch_service(monkeypatch, cfg)
    fake_client = _patch_paramiko(monkeypatch, stdout_text="should-not-run", exit_code=0)
    runtime = _build_runtime(business_name="delta")

    from app.shared.tools.skills.devops.SSHTools import execute_command

    out = execute_command(command="ls", runtime=runtime)
    msgs = out.update["messages"]
    payload = json.loads(msgs[0].content)
    assert payload.get("success") is False
    fake_client.exec_command.assert_not_called()


# ----------------------------------------------------------------------
# 3. execute_batch_commands
# ----------------------------------------------------------------------


def test_batch_blocked_response_does_not_echo_allowed_commands(monkeypatch):
    """批量被拦截时响应体不得回显 allowed_commands（避免额外命令信息泄露）。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    cfg = {
        "ip": "10.0.0.50",
        "port": 22,
        "username": "u",
        "password": "batch-blocked-pwd",
        "server_type": "linux",
        "blacklist": [r"^shutdown"],
        "whitelist": ["ls", "whoami", "shutdown -h now"],
    }
    _patch_service(monkeypatch, cfg)
    fake_client = _patch_paramiko(monkeypatch, stdout_text="ignored", exit_code=0)
    runtime = _build_runtime(business_name="zeta2")

    from app.shared.tools.skills.devops.SSHTools import execute_batch_commands

    out = execute_batch_commands(
        commands=["ls", "shutdown -h now", "whoami"],
        runtime=runtime,
    )
    msgs = out.update["messages"]
    payload = json.loads(msgs[0].content)
    assert payload.get("success") is False
    assert "blocked_commands" in payload
    # 不应回显已放行命令，避免泄漏额外命令信息
    assert "allowed_commands" not in payload
    fake_client.exec_command.assert_not_called()


def test_execute_command_generic_error_does_not_leak_credential(monkeypatch):
    """连接/认证/执行异常返回通用错误信息，不应携带 IP / 密码 / username 等。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    fake_client = MagicMock(name="paramiko.SSHClient")
    stdin = MagicMock()
    stdout = MagicMock()
    stderr = MagicMock()
    stdout.read = MagicMock(return_value=b"")
    stderr.read = MagicMock(return_value=b"")
    stdout.channel.recv_exit_status = MagicMock(return_value=1)
    # 让 exec_command 抛 AuthenticationException，message 内含敏感片段
    fake_client.exec_command = MagicMock(
        side_effect=Exception(
            "failed auth for root@10.0.0.77 with password=hunter2xyz"
        )
    )
    fake_client.close = MagicMock(return_value=None)
    fake_paramiko = MagicMock(name="paramiko")
    fake_paramiko.SSHClient = MagicMock(return_value=fake_client)
    fake_paramiko.AutoAddPolicy = MagicMock(return_value=MagicMock())
    import paramiko as real_paramiko
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException
    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, "paramiko", fake_paramiko, raising=False)

    cfg = {
        "ip": "10.0.0.77",
        "port": 22,
        "username": "root",
        "password": "hunter2xyz",
        "server_type": "linux",
        "blacklist": [],
        "whitelist": ["echo hello"],
    }
    _patch_service(monkeypatch, cfg)
    runtime = _build_runtime(business_name="kappa")

    from app.shared.tools.skills.devops.SSHTools import execute_command

    out = execute_command(command="echo hello", runtime=runtime)
    msgs = out.update["messages"]
    raw = msgs[0].content
    # 通用错误：不含敏感片段
    assert "hunter2xyz" not in raw
    assert "10.0.0.77" not in raw
    assert "root" not in raw


def test_get_system_logs_windows_uses_get_winevent(monkeypatch):
    """Windows get_system_logs 走 PowerShell Get-WinEvent 命令，并经过白名单放行。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    cfg = {
        "ip": "10.0.0.99",
        "port": 22,
        "username": "administrator",
        "password": "winpwd",
        "server_type": "windows",
        "blacklist": [],
        "whitelist": ["powershell ", "Get-WinEvent "],
    }
    _patch_service(monkeypatch, cfg)
    fake_client = _patch_paramiko(monkeypatch, stdout_text="log lines", exit_code=0)
    runtime = _build_runtime(business_name="winlogs")

    from app.shared.tools.skills.devops.SSHTools import get_system_logs

    out = get_system_logs(
        log_type="System",
        lines=10,
        runtime=runtime,
    )
    msgs = out.update["messages"]
    payload = json.loads(msgs[0].content)
    assert payload.get("success") is True
    args, _ = fake_client.exec_command.call_args
    # Windows 路径必须走 PowerShell + Get-WinEvent，不应再使用 tail
    assert "powershell.exe" in args[0]
    assert "Get-WinEvent" in args[0]
    assert "tail" not in args[0]


def test_batch_any_block_rejects_entire_batch(monkeypatch):
    """批量中任一条被拦截 → 整批拒绝（不调用 paramiko）。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    cfg = {
        "ip": "10.0.0.5",
        "port": 22,
        "username": "u",
        "password": "pwdbatch",
        "server_type": "linux",
        "blacklist": [r"^shutdown"],
        "whitelist": ["ls", "shutdown -h now"],
    }
    _patch_service(monkeypatch, cfg)
    fake_client = _patch_paramiko(monkeypatch, stdout_text="ls-output", exit_code=0)
    runtime = _build_runtime(business_name="eps")

    from app.shared.tools.skills.devops.SSHTools import execute_batch_commands

    out = execute_batch_commands(
        commands=["ls", "shutdown -h now"],
        runtime=runtime,
    )
    msgs = out.update["messages"]
    payload = json.loads(msgs[0].content)
    assert payload.get("success") is False
    assert "blocked_commands" in payload
    fake_client.exec_command.assert_not_called()


def test_batch_success_runs_all(monkeypatch):
    """批量命令全部通过时按顺序调用 paramiko.exec_command。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    cfg = {
        "ip": "10.0.0.6",
        "port": 22,
        "username": "u",
        "password": "batch-pass",
        "server_type": "linux",
        "blacklist": [],
        "whitelist": ["whoami", "date"],
    }
    _patch_service(monkeypatch, cfg)
    fake_client = _patch_paramiko(monkeypatch, stdout_text="OK", exit_code=0)
    runtime = _build_runtime(business_name="zeta")

    from app.shared.tools.skills.devops.SSHTools import execute_batch_commands

    out = execute_batch_commands(
        commands=["whoami", "date"],
        runtime=runtime,
    )
    msgs = out.update["messages"]
    payload = json.loads(msgs[0].content)
    assert payload.get("success") is True
    assert payload.get("total") == 2
    assert fake_client.exec_command.call_count >= 2


# ----------------------------------------------------------------------
# 4. get_system_logs 走策略
# ----------------------------------------------------------------------


def test_get_system_logs_uses_policy(monkeypatch):
    """get_system_logs 内部 ``tail ``（带尾空格前缀模式）命中黑名单 → 拒绝。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    cfg = {
        "ip": "10.0.0.7",
        "port": 22,
        "username": "u",
        "password": "logs-pwd",
        "server_type": "linux",
        "blacklist": ["tail "],
        "whitelist": ["tail -n 10 /var/log/syslog"],
    }
    _patch_service(monkeypatch, cfg)
    fake_client = _patch_paramiko(monkeypatch, stdout_text="log line 1\nlog line 2\n", exit_code=0)
    runtime = _build_runtime(business_name="eta")

    from app.shared.tools.skills.devops.SSHTools import get_system_logs

    out = get_system_logs(
        log_type="syslog",
        lines=10,
        runtime=runtime,
    )
    msgs = out.update["messages"]
    payload = msgs[0].content
    assert "logs-pwd" not in payload
    assert "10.0.0.7" not in payload
    fake_client.exec_command.assert_not_called()


def test_get_system_logs_success(monkeypatch):
    """get_system_logs 正常路径走 Linux tail，返回摘要。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    cfg = {
        "ip": "10.0.0.8",
        "port": 22,
        "username": "u",
        "password": "logspwd-ok",
        "server_type": "linux",
        "blacklist": [],
        "whitelist": ["tail "],
    }
    _patch_service(monkeypatch, cfg)
    fake_client = _patch_paramiko(monkeypatch, stdout_text="line A\nline B\nline C\n", exit_code=0)
    runtime = _build_runtime(business_name="theta")

    from app.shared.tools.skills.devops.SSHTools import get_system_logs

    out = get_system_logs(
        log_type="syslog",
        lines=100,
        runtime=runtime,
    )
    msgs = out.update["messages"]
    payload = msgs[0].content
    assert "logspwd-ok" not in payload
    assert "10.0.0.8" not in payload
    args, _ = fake_client.exec_command.call_args
    assert "tail" in args[0]
