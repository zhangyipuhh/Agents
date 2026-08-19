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
import inspect
import json
from unittest.mock import AsyncMock, MagicMock
import pytest


def _run(callable_or_coro):
    """统一包装工具调用:若是 coroutine 则 asyncio.run,否则直接返回结果。

    2026-08-05:SSHTools 三个 @tool 已统一改为 ``async def``(LangGraph ToolNode 在
    in-flight asyncio loop 内可直接 await;本地 paramiko 用 asyncio.to_thread)。
    测试环境无运行中的 loop,需用 ``asyncio.run`` 触发同步执行。AST 重写后
    所有调用形如 ``_run(execute_command(...))``,因此这里只需要 await coroutine。
    """
    if inspect.iscoroutine(callable_or_coro):
        return asyncio.run(callable_or_coro)
    return callable_or_coro


def _build_runtime(business_name: str='alpha', session_id: str='sess-x'):
    """构造一个简单的 ``ToolRuntime`` 替身（最小字段集）。

    Args:
        business_name: 业务名
        session_id: 会话 ID

    Returns:
        MagicMock: 模拟的 runtime
    """
    runtime = MagicMock(name='ToolRuntime')
    runtime.tool_call_id = 'call-x'
    runtime.context = {'business_name': business_name, 'session_id': session_id}
    return runtime

def _patch_service(monkeypatch, config):
    """把 ``DevOpsServerService`` 单例换成 stub，返回 ``config``。

    Args:
        monkeypatch: pytest monkeypatch fixture
        config: ``get_connection_config`` 的固定返回
    """
    from app.shared.utils.devops_server_service import DevOpsServerService
    fake_service = MagicMock(name='DevOpsServerService')
    fake_service.get_connection_config = MagicMock(return_value=config)
    DevOpsServerService.set_instance(fake_service)
    return fake_service

def _patch_paramiko(monkeypatch, stdout_text='', stderr_text='', exit_code=0):
    """替换 ``app.shared.tools.skills.devops.SSHTools.paramiko``。

    Args:
        monkeypatch: pytest monkeypatch
        stdout_text: 标准输出
        stderr_text: 标准错误
        exit_code: 退出码

    Returns:
        MagicMock: fake client
    """
    fake_client = MagicMock(name='paramiko.SSHClient')
    stdin = MagicMock()
    stdout = MagicMock()
    stderr = MagicMock()
    stdout.read = MagicMock(return_value=stdout_text.encode('utf-8'))
    stderr.read = MagicMock(return_value=stderr_text.encode('utf-8'))
    stdout.channel.recv_exit_status = MagicMock(return_value=exit_code)
    fake_client.exec_command = MagicMock(return_value=(stdin, stdout, stderr))
    fake_client.close = MagicMock(return_value=None)
    fake_paramiko = MagicMock(name='paramiko')
    fake_paramiko.SSHClient = MagicMock(return_value=fake_client)
    fake_paramiko.AutoAddPolicy = MagicMock(return_value=MagicMock())
    import paramiko as real_paramiko
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException
    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, 'paramiko', fake_paramiko, raising=False)
    return fake_client

def test_module_exposes_three_tools():
    """SSHTools 模块应暴露三个可调用工具（execute_command / batch / logs）。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.SSHTools import execute_command, execute_batch_commands, get_system_logs
    for tool_obj in (execute_command, execute_batch_commands, get_system_logs):
        assert callable(tool_obj)
        assert tool_obj.__name__ in {'execute_command', 'execute_batch_commands', 'get_system_logs'}

def test_tools_have_runtime_param():
    """三个工具函数的签名都包含 ``runtime`` 参数（LangChain ToolRuntime）。

    Returns:
        None
    """
    import inspect
    from app.shared.tools.skills.devops.SSHTools import execute_command, execute_batch_commands, get_system_logs
    for tool_obj in (execute_command, execute_batch_commands, get_system_logs):
        sig = inspect.signature(tool_obj)
        assert 'runtime' in sig.parameters

def test_execute_command_runs_linux_and_uses_bash(monkeypatch):
    """Linux server_type → /bin/bash；参数 ``runtime`` 由 LangChain 注入。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    secret_config = {'ip': '10.0.0.1', 'port': 22, 'username': 'rootuser', 'password': 'supersecret-pwd-xyz', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo ']}
    fake_service = _patch_service(monkeypatch, secret_config)
    fake_client = _patch_paramiko(monkeypatch, stdout_text='hello\n', exit_code=0)
    runtime = _build_runtime(business_name='alpha')
    from app.shared.tools.skills.devops.SSHTools import execute_command
    out = _run(execute_command(command='echo hello', business_name='alpha', runtime=runtime))
    msgs = out.update['messages']
    assert len(msgs) == 1
    payload = json.loads(msgs[0].content)
    assert payload.get('success') is True
    assert 'hello' in payload.get('output', '')
    tool_text = msgs[0].content
    assert 'supersecret-pwd-xyz' not in tool_text
    assert '10.0.0.1' not in tool_text
    assert 'rootuser' not in tool_text
    args, kwargs = fake_client.exec_command.call_args
    assert '/bin/bash' in args[0]
    assert 'echo hello' in args[0]
    fake_service.get_connection_config.assert_called_with('alpha')

def test_execute_command_closes_stdin_write_side(monkeypatch):
    """execute_command 执行后应关闭 stdin 写端（发送 EOF）。

    Windows OpenSSH 默认 shell 在非 PTY exec 通道下会等待 stdin EOF 才退出,
    不关闭写端会导致 ``stdout.read()`` 阻塞至超时;命令不读 stdin,关闭写端
    对 Linux / Windows 均无副作用。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    config = {'ip': '10.0.0.1', 'port': 22, 'username': 'rootuser', 'password': 'supersecret-pwd-xyz', 'server_type': 'windows', 'blacklist': [], 'whitelist': ['Get-Date']}
    _patch_service(monkeypatch, config)
    fake_client = _patch_paramiko(monkeypatch, stdout_text='ok\n', exit_code=0)
    runtime = _build_runtime(business_name='alpha')
    from app.shared.tools.skills.devops.SSHTools import execute_command
    _run(execute_command(command='Get-Date', business_name='alpha', runtime=runtime))
    stdin = fake_client.exec_command.return_value[0]
    stdin.close.assert_called_once()

def test_execute_command_runs_windows_and_uses_powershell(monkeypatch):
    """windows server_type → powershell.exe。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    win_config = {'ip': '10.0.0.2', 'port': 22, 'username': 'administrator', 'password': 'winsecret-abc', 'server_type': 'windows', 'blacklist': [], 'whitelist': ['Get-Service']}
    _patch_service(monkeypatch, win_config)
    fake_client = _patch_paramiko(monkeypatch, stdout_text='win-out', exit_code=0)
    runtime = _build_runtime(business_name='beta')
    from app.shared.tools.skills.devops.SSHTools import execute_command
    out = _run(execute_command(command='Get-Service', business_name='beta', runtime=runtime))
    args, _ = fake_client.exec_command.call_args
    assert 'powershell.exe' in args[0]
    msgs = out.update['messages']
    raw = msgs[0].content
    raw_text = raw if isinstance(raw, str) else str(raw)
    assert 'winsecret-abc' not in raw_text
    assert '10.0.0.2' not in raw_text

def test_execute_command_blacklist_blocks_command(monkeypatch):
    """黑名单正则命中时拒绝执行，不调 paramiko。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    cfg = {'ip': '10.0.0.3', 'port': 22, 'username': 'u', 'password': 'secpwd', 'server_type': 'linux', 'blacklist': ['^rm\\s+-rf'], 'whitelist': ['rm -rf /tmp/x']}
    _patch_service(monkeypatch, cfg)
    fake_client = _patch_paramiko(monkeypatch, stdout_text='should-not-run', exit_code=0)
    runtime = _build_runtime(business_name='gamma')
    from app.shared.tools.skills.devops.SSHTools import execute_command
    out = _run(execute_command(command='rm -rf /tmp/x', business_name='gamma', runtime=runtime))
    msgs = out.update['messages']
    payload = json.loads(msgs[0].content)
    assert payload.get('blocked') is True or payload.get('success') is False
    fake_client.exec_command.assert_not_called()

def test_execute_command_whitelist_empty_blocks(monkeypatch):
    """白名单显式空（whitelist=[]）时，所有非空命令拒绝。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    cfg = {'ip': '10.0.0.4', 'port': 22, 'username': 'u', 'password': 'spwd', 'server_type': 'linux', 'blacklist': [], 'whitelist': []}
    _patch_service(monkeypatch, cfg)
    fake_client = _patch_paramiko(monkeypatch, stdout_text='should-not-run', exit_code=0)
    runtime = _build_runtime(business_name='delta')
    from app.shared.tools.skills.devops.SSHTools import execute_command
    out = _run(execute_command(command='ls', business_name='delta', runtime=runtime))
    msgs = out.update['messages']
    payload = json.loads(msgs[0].content)
    assert payload.get('success') is False
    fake_client.exec_command.assert_not_called()

def test_batch_blocked_response_does_not_echo_allowed_commands(monkeypatch):
    """批量被拦截时响应体不得回显 allowed_commands（避免额外命令信息泄露）。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    cfg = {'ip': '10.0.0.50', 'port': 22, 'username': 'u', 'password': 'batch-blocked-pwd', 'server_type': 'linux', 'blacklist': ['^shutdown'], 'whitelist': ['ls', 'whoami', 'shutdown -h now']}
    _patch_service(monkeypatch, cfg)
    fake_client = _patch_paramiko(monkeypatch, stdout_text='ignored', exit_code=0)
    runtime = _build_runtime(business_name='zeta2')
    from app.shared.tools.skills.devops.SSHTools import execute_batch_commands
    out = _run(execute_batch_commands(commands=['ls', 'shutdown -h now', 'whoami'], business_name='zeta2', runtime=runtime))
    msgs = out.update['messages']
    payload = json.loads(msgs[0].content)
    assert payload.get('success') is False
    assert 'blocked_commands' in payload
    assert 'allowed_commands' not in payload
    fake_client.exec_command.assert_not_called()

def test_execute_command_generic_error_does_not_leak_credential(monkeypatch):
    """连接/认证/执行异常返回通用错误信息，不应携带 IP / 密码 / username 等。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    fake_client = MagicMock(name='paramiko.SSHClient')
    stdin = MagicMock()
    stdout = MagicMock()
    stderr = MagicMock()
    stdout.read = MagicMock(return_value=b'')
    stderr.read = MagicMock(return_value=b'')
    stdout.channel.recv_exit_status = MagicMock(return_value=1)
    fake_client.exec_command = MagicMock(side_effect=Exception('failed auth for root@10.0.0.77 with password=hunter2xyz'))
    fake_client.close = MagicMock(return_value=None)
    fake_paramiko = MagicMock(name='paramiko')
    fake_paramiko.SSHClient = MagicMock(return_value=fake_client)
    fake_paramiko.AutoAddPolicy = MagicMock(return_value=MagicMock())
    import paramiko as real_paramiko
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException
    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, 'paramiko', fake_paramiko, raising=False)
    cfg = {'ip': '10.0.0.77', 'port': 22, 'username': 'root', 'password': 'hunter2xyz', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo hello']}
    _patch_service(monkeypatch, cfg)
    runtime = _build_runtime(business_name='kappa')
    from app.shared.tools.skills.devops.SSHTools import execute_command
    out = _run(execute_command(command='echo hello', business_name='kappa', runtime=runtime))
    msgs = out.update['messages']
    raw = msgs[0].content
    assert 'hunter2xyz' not in raw
    assert '10.0.0.77' not in raw
    assert 'root' not in raw

def test_get_system_logs_windows_uses_get_winevent(monkeypatch):
    """Windows get_system_logs 走 PowerShell Get-WinEvent 命令，并经过白名单放行。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    cfg = {'ip': '10.0.0.99', 'port': 22, 'username': 'administrator', 'password': 'winpwd', 'server_type': 'windows', 'blacklist': [], 'whitelist': ['powershell ', 'Get-WinEvent ', 'Select-Object ', 'Format-Table ', 'Out-String']}
    _patch_service(monkeypatch, cfg)
    fake_client = _patch_paramiko(monkeypatch, stdout_text='log lines', exit_code=0)
    runtime = _build_runtime(business_name='winlogs')
    from app.shared.tools.skills.devops.SSHTools import get_system_logs
    out = _run(get_system_logs(business_name='winlogs', log_type='System', lines=10, runtime=runtime))
    msgs = out.update['messages']
    payload = json.loads(msgs[0].content)
    assert payload.get('success') is True
    args, _ = fake_client.exec_command.call_args
    assert 'powershell.exe' in args[0]
    assert '-EncodedCommand' in args[0]
    assert '-ExecutionPolicy Bypass' in args[0]
    assert 'Get-WinEvent' not in args[0]
    import base64 as _b64
    parts = args[0].split('-EncodedCommand', 1)
    decoded = _b64.b64decode(parts[1].strip()).decode('utf-16-le')
    assert 'Get-WinEvent' in decoded

def test_batch_any_block_rejects_entire_batch(monkeypatch):
    """批量中任一条被拦截 → 整批拒绝（不调用 paramiko）。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    cfg = {'ip': '10.0.0.5', 'port': 22, 'username': 'u', 'password': 'pwdbatch', 'server_type': 'linux', 'blacklist': ['^shutdown'], 'whitelist': ['ls', 'shutdown -h now']}
    _patch_service(monkeypatch, cfg)
    fake_client = _patch_paramiko(monkeypatch, stdout_text='ls-output', exit_code=0)
    runtime = _build_runtime(business_name='eps')
    from app.shared.tools.skills.devops.SSHTools import execute_batch_commands
    out = _run(execute_batch_commands(commands=['ls', 'shutdown -h now'], business_name='eps', runtime=runtime))
    msgs = out.update['messages']
    payload = json.loads(msgs[0].content)
    assert payload.get('success') is False
    assert 'blocked_commands' in payload
    fake_client.exec_command.assert_not_called()

def test_batch_success_runs_all(monkeypatch):
    """批量命令全部通过时按顺序调用 paramiko.exec_command。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    cfg = {'ip': '10.0.0.6', 'port': 22, 'username': 'u', 'password': 'batch-pass', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['whoami', 'date']}
    _patch_service(monkeypatch, cfg)
    fake_client = _patch_paramiko(monkeypatch, stdout_text='OK', exit_code=0)
    runtime = _build_runtime(business_name='zeta')
    from app.shared.tools.skills.devops.SSHTools import execute_batch_commands
    out = _run(execute_batch_commands(commands=['whoami', 'date'], business_name='zeta', runtime=runtime))
    msgs = out.update['messages']
    payload = json.loads(msgs[0].content)
    assert payload.get('success') is True
    assert payload.get('total') == 2
    assert fake_client.exec_command.call_count >= 2

def test_get_system_logs_uses_policy(monkeypatch):
    """get_system_logs 内部 ``tail ``（带尾空格前缀模式）命中黑名单 → 拒绝。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    cfg = {'ip': '10.0.0.7', 'port': 22, 'username': 'u', 'password': 'logs-pwd', 'server_type': 'linux', 'blacklist': ['tail '], 'whitelist': ['tail -n 10 /var/log/syslog']}
    _patch_service(monkeypatch, cfg)
    fake_client = _patch_paramiko(monkeypatch, stdout_text='log line 1\nlog line 2\n', exit_code=0)
    runtime = _build_runtime(business_name='eta')
    from app.shared.tools.skills.devops.SSHTools import get_system_logs
    out = _run(get_system_logs(business_name='eta', log_type='syslog', lines=10, runtime=runtime))
    msgs = out.update['messages']
    payload = msgs[0].content
    assert 'logs-pwd' not in payload
    assert '10.0.0.7' not in payload
    fake_client.exec_command.assert_not_called()

def test_get_system_logs_success(monkeypatch):
    """get_system_logs 正常路径走 Linux tail，返回摘要。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    cfg = {'ip': '10.0.0.8', 'port': 22, 'username': 'u', 'password': 'logspwd-ok', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['tail ']}
    _patch_service(monkeypatch, cfg)
    fake_client = _patch_paramiko(monkeypatch, stdout_text='line A\nline B\nline C\n', exit_code=0)
    runtime = _build_runtime(business_name='theta')
    from app.shared.tools.skills.devops.SSHTools import get_system_logs
    out = _run(get_system_logs(business_name='theta', log_type='syslog', lines=100, runtime=runtime))
    msgs = out.update['messages']
    payload = msgs[0].content
    assert 'logspwd-ok' not in payload
    assert '10.0.0.8' not in payload
    args, _ = fake_client.exec_command.call_args
    assert 'tail' in args[0]

def test_execute_command_rejects_empty_business_name(monkeypatch):
    """execute_command 收到空字符串 business_name 时返回明确错误，不调 paramiko。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    cfg = {'ip': '10.0.0.1', 'port': 22, 'username': 'u', 'password': 'pwd', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo ']}
    _patch_service(monkeypatch, cfg)
    fake_client = _patch_paramiko(monkeypatch, stdout_text='', exit_code=0)
    runtime = _build_runtime(business_name='alpha')
    from app.shared.tools.skills.devops.SSHTools import execute_command
    out = _run(execute_command(command='echo hi', business_name='', runtime=runtime))
    msgs = out.update['messages']
    payload = json.loads(msgs[0].content)
    assert payload.get('success') is False
    assert 'business_name 不能为空' in payload.get('error', '')
    fake_client.exec_command.assert_not_called()

def test_execute_command_rejects_whitespace_business_name(monkeypatch):
    """execute_command 收到纯空白 business_name 时返回明确错误，不调 paramiko。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    cfg = {'ip': '10.0.0.1', 'port': 22, 'username': 'u', 'password': 'pwd', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo ']}
    _patch_service(monkeypatch, cfg)
    fake_client = _patch_paramiko(monkeypatch, stdout_text='', exit_code=0)
    runtime = _build_runtime(business_name='alpha')
    from app.shared.tools.skills.devops.SSHTools import execute_command
    out = _run(execute_command(command='echo hi', business_name='   ', runtime=runtime))
    msgs = out.update['messages']
    payload = json.loads(msgs[0].content)
    assert payload.get('success') is False
    assert 'business_name 不能为空' in payload.get('error', '')
    fake_client.exec_command.assert_not_called()

def test_execute_batch_commands_rejects_empty_business_name(monkeypatch):
    """execute_batch_commands 收到空 business_name 时返回明确错误，不调 paramiko。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    cfg = {'ip': '10.0.0.1', 'port': 22, 'username': 'u', 'password': 'pwd', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['ls']}
    _patch_service(monkeypatch, cfg)
    fake_client = _patch_paramiko(monkeypatch, stdout_text='', exit_code=0)
    runtime = _build_runtime(business_name='zeta')
    from app.shared.tools.skills.devops.SSHTools import execute_batch_commands
    out = _run(execute_batch_commands(commands=['ls'], business_name='', runtime=runtime))
    msgs = out.update['messages']
    payload = json.loads(msgs[0].content)
    assert payload.get('success') is False
    assert 'business_name 不能为空' in payload.get('error', '')
    fake_client.exec_command.assert_not_called()

def test_get_system_logs_rejects_empty_business_name(monkeypatch):
    """get_system_logs 收到空 business_name 时返回明确错误，不调 paramiko。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    cfg = {'ip': '10.0.0.1', 'port': 22, 'username': 'u', 'password': 'pwd', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['tail ']}
    _patch_service(monkeypatch, cfg)
    fake_client = _patch_paramiko(monkeypatch, stdout_text='', exit_code=0)
    runtime = _build_runtime(business_name='eta')
    from app.shared.tools.skills.devops.SSHTools import get_system_logs
    out = _run(get_system_logs(business_name='', runtime=runtime))
    msgs = out.update['messages']
    payload = json.loads(msgs[0].content)
    assert payload.get('success') is False
    assert 'business_name 不能为空' in payload.get('error', '')
    fake_client.exec_command.assert_not_called()

def test_execute_command_fernet_value_error_normalized(monkeypatch):
    """Bug-3 回归:get_connection_config 抛 ValueError(Fernet 密钥错配)时,
    工具返回通用错误,不携带 business_name 与「密钥错配」字样。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    fake_service = MagicMock(name='DevOpsServerService')
    fake_service.get_connection_config = MagicMock(side_effect=ValueError('解密失败（Fernet key 与加密时不一致？）: mybiz'))
    from app.shared.utils.devops_server_service import DevOpsServerService
    DevOpsServerService.set_instance(fake_service)
    from app.shared.tools.skills.devops.SSHTools import execute_command
    runtime = _build_runtime(business_name='mybiz')
    out = _run(execute_command(command='echo hi', business_name='mybiz', runtime=runtime))
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('success') is False
    assert payload.get('error') == '无法解析服务器配置'
    raw = out.update['messages'][0].content
    assert 'Fernet' not in raw
    assert '解密失败' not in raw

def test_resolve_server_config_rejects_non_string_business_name_in_context(monkeypatch):
    """Bug-4 回归:runtime.context["business_name"] 是 MagicMock(非 str)时,
    _resolve_server_config 不应把它当作合法 name 传给下游,避免 KeyError 噪声。

    通过直接调用 ``_resolve_server_config`` 验证兜底分支对非 str 容错。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    fake_service = MagicMock(name='DevOpsServerService')
    fake_service.get_connection_config = MagicMock(side_effect=AssertionError('不应到达 service.get_connection_config'))
    from app.shared.utils.devops_server_service import DevOpsServerService
    DevOpsServerService.set_instance(fake_service)
    runtime = MagicMock(name='ToolRuntime')
    runtime.context = {'business_name': MagicMock()}
    from app.shared.tools.skills.devops.SSHTools import _resolve_server_config
    with pytest.raises(RuntimeError, match='business_name 缺失'):
        _resolve_server_config(runtime, business_name='')

def test_open_client_uses_configured_timeout(monkeypatch):
    """Bug-5 回归:_open_client 把 config.ssh_connect_timeout 传给 paramiko.connect。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    from app.shared.tools.skills.devops import SSHTools
    fake_client2 = MagicMock(name='paramiko.SSHClient')
    fake_client2.set_missing_host_key_policy = MagicMock()
    fake_client2.close = MagicMock()
    stdin = MagicMock()
    stdout = MagicMock()
    stderr = MagicMock()
    stdout.read = MagicMock(return_value=b'hi\n')
    stderr.read = MagicMock(return_value=b'')
    stdout.channel.recv_exit_status = MagicMock(return_value=0)
    fake_client2.exec_command = MagicMock(return_value=(stdin, stdout, stderr))
    fake_paramiko = MagicMock(name='paramiko')
    fake_paramiko.SSHClient = MagicMock(return_value=fake_client2)
    fake_paramiko.AutoAddPolicy = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(SSHTools, 'paramiko', fake_paramiko, raising=False)
    cfg = {'ip': '10.0.0.10', 'port': 22, 'username': 'u', 'password': 'pw', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo '], 'ssh_connect_timeout': 7}
    _patch_service(monkeypatch, cfg)
    runtime2 = _build_runtime(business_name='t1')
    from app.shared.tools.skills.devops.SSHTools import execute_command
    _run(execute_command(command='echo hi', business_name='t1', runtime=runtime2))
    _, kwargs = fake_client2.connect.call_args
    assert kwargs.get('timeout') == 7
    assert kwargs.get('auth_timeout') == 7
    assert kwargs.get('banner_timeout') == 7

def test_clamp_timeout_clamps_to_range():
    """Bug-5 辅助:_clamp_timeout 把异常值钳制到 [lo, hi]。"""
    from app.shared.tools.skills.devops.SSHTools import _clamp_timeout
    assert _clamp_timeout(30, default=30, lo=1, hi=120) == 30
    assert _clamp_timeout(0, default=30, lo=1, hi=120) == 1
    assert _clamp_timeout(99999, default=30, lo=1, hi=120) == 120
    assert _clamp_timeout(-5, default=30, lo=1, hi=120) == 1
    assert _clamp_timeout(None, default=30, lo=1, hi=120) == 30
    assert _clamp_timeout('bad', default=30, lo=1, hi=120) == 30

def test_execute_batch_commands_rejects_none_commands(monkeypatch):
    """Bug-7 回归:commands=None 时不崩溃,返回明确错误。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    cfg = {'ip': '10.0.0.20', 'port': 22, 'username': 'u', 'password': 'pw', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['ls']}
    _patch_service(monkeypatch, cfg)
    fake_client = _patch_paramiko(monkeypatch, stdout_text='', exit_code=0)
    runtime = _build_runtime(business_name='b1')
    from app.shared.tools.skills.devops.SSHTools import execute_batch_commands
    out = _run(execute_batch_commands(commands=None, business_name='b1', runtime=runtime))
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('success') is False
    assert 'commands 不能为空' in payload.get('error', '')
    fake_client.exec_command.assert_not_called()

def test_execute_batch_commands_rejects_empty_list(monkeypatch):
    """Bug-7 回归:commands=[] 时返回明确错误。

    Args:
        monkeypatch: pytest monkeypatch

    Returns:
        None
    """
    cfg = {'ip': '10.0.0.21', 'port': 22, 'username': 'u', 'password': 'pw', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['ls']}
    _patch_service(monkeypatch, cfg)
    fake_client = _patch_paramiko(monkeypatch, stdout_text='', exit_code=0)
    runtime = _build_runtime(business_name='b2')
    from app.shared.tools.skills.devops.SSHTools import execute_batch_commands
    out = _run(execute_batch_commands(commands=[], business_name='b2', runtime=runtime))
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('success') is False
    assert 'commands 不能为空' in payload.get('error', '')
    fake_client.exec_command.assert_not_called()

def _install_capturing_log_service(monkeypatch):
    """注入一个 MagicMock 风格的 LogService 用于观察 emit 调用。

    返回 ``(service, captured)``,其中 ``captured`` 是按调用顺序收集的 LogEvent 列表。
    通过 monkeypatch.setattr 替换 ``app.shared.utils.log_service._log_service_singleton``
    与 ``get_log_service``,SSHTools 内部对 ``get_log_service()`` 的调用就会拿到这个 fake。
    """
    from app.shared.utils.log_service import LogService
    captured = []

    def fake_emit(event):
        captured.append(event)
        return True
    fake_svc = MagicMock(name='LogService')
    fake_svc.emit = fake_emit
    monkeypatch.setattr('app.shared.utils.log_service._log_service_singleton', fake_svc, raising=False)
    monkeypatch.setattr('app.shared.utils.log_service.get_log_service', lambda: fake_svc, raising=False)
    return (fake_svc, captured)

def test_execute_command_success_emits_ssh_log_event(monkeypatch):
    """execute_command 成功路径通过 ``LogService.emit`` 写一条 ``log_type='ssh'`` 的日志。

    契约：
        - ``action='ssh_execute_command'``
        - ``log_type='ssh'``、``result='success'``
        - ``target_type='devops_server'``、``target_name=business_name``
        - ``metadata`` 含 ``event_type/server_type/command_redacted/command_hash/decision/exit_code/duration_ms/stdout_size/stderr_size/error_code``
        - 不出现原命令、IP、用户名、密码、stdout、stderr
    """
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.55', 'port': 22, 'username': 'root-secret', 'password': 'supersecret-pwd-xyz', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo ']}
    _patch_service(monkeypatch, cfg)
    _patch_paramiko(monkeypatch, stdout_text='hello\n', exit_code=0)
    runtime = _build_runtime(business_name='alpha')
    from app.shared.tools.skills.devops.SSHTools import execute_command
    out = _run(execute_command(command='echo hello', business_name='alpha', runtime=runtime))
    msgs = out.update['messages']
    assert msgs
    assert captured, 'execute_command 成功路径必须 emit 一条 LogEvent'
    evt = captured[-1]
    assert evt.action == 'ssh_execute_command'
    assert str(evt.log_type) == 'ssh'
    assert str(evt.result) == 'success'
    assert evt.target_type == 'devops_server'
    assert evt.target_name == 'alpha'
    md = evt.metadata
    for k in ('event_type', 'server_type', 'command_redacted', 'command_hash', 'decision', 'exit_code', 'duration_ms', 'stdout_size', 'stderr_size', 'error_code'):
        assert k in md, f'metadata 必须包含 {k}, 实际 {list(md.keys())}'
    assert md['server_type'] == 'linux'
    assert md['decision'] == 'executed'
    assert md['exit_code'] == 0
    assert isinstance(md['command_redacted'], str)
    assert md['command_redacted']
    meta_blob = json.dumps(md, ensure_ascii=False)
    assert '10.0.0.55' not in meta_blob
    assert 'root-secret' not in meta_blob
    assert 'supersecret-pwd-xyz' not in meta_blob

def test_execute_command_blocked_emits_ssh_log_event(monkeypatch):
    """execute_command 黑名单拦截路径 emit ``result='blocked'``,``command_redacted`` 与 ``command_hash`` 仍写齐。"""
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.56', 'port': 22, 'username': 'root-secret', 'password': 'supersecret-pwd-xyz', 'server_type': 'linux', 'blacklist': ['^rm\\s+-rf'], 'whitelist': ['rm -rf /tmp/x']}
    _patch_service(monkeypatch, cfg)
    _patch_paramiko(monkeypatch, stdout_text='should-not-run', exit_code=0)
    runtime = _build_runtime(business_name='gamma')
    from app.shared.tools.skills.devops.SSHTools import execute_command
    _run(execute_command(command='rm -rf /tmp/x', business_name='gamma', runtime=runtime))
    assert captured, '黑名单拦截路径必须 emit 一条 LogEvent'
    evt = captured[-1]
    assert evt.action == 'ssh_execute_command'
    assert str(evt.result) == 'blocked'
    md = evt.metadata
    assert md['decision'] == 'blocked'
    assert 'intercept_reason' in md
    assert isinstance(md['command_redacted'], str)
    assert md['command_redacted']
    assert md['command_hash']
    from app.shared.utils.log_service import hash_command
    assert md['command_hash'] == hash_command('rm -rf /tmp/x')

def test_execute_command_fail_soft_when_log_service_missing(monkeypatch):
    """execute_command 在 LogService 不可用(emit 返回 False / get_log_service=None)时仍正常返回工具响应。

    验证 fail-soft：日志失败不阻断业务路径。
    """
    fake_svc = MagicMock(name='LogService')
    fake_svc.emit = MagicMock(return_value=False)
    monkeypatch.setattr('app.shared.utils.log_service._log_service_singleton', fake_svc, raising=False)
    monkeypatch.setattr('app.shared.utils.log_service.get_log_service', lambda: fake_svc, raising=False)
    cfg = {'ip': '10.0.0.57', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo ']}
    _patch_service(monkeypatch, cfg)
    _patch_paramiko(monkeypatch, stdout_text='ok\n', exit_code=0)
    runtime = _build_runtime(business_name='delta')
    from app.shared.tools.skills.devops.SSHTools import execute_command
    out = _run(execute_command(command='echo hi', business_name='delta', runtime=runtime))
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('success') is True
    fake_svc.emit.assert_called()

def test_execute_command_emits_even_when_emit_raises(monkeypatch):
    """execute_command 在 emit() 抛异常时业务响应仍 200(fail-soft)。"""
    fake_svc = MagicMock(name='LogService')

    def fake_emit_raises(_event):
        raise RuntimeError('log emit died')
    fake_svc.emit = fake_emit_raises
    monkeypatch.setattr('app.shared.utils.log_service._log_service_singleton', fake_svc, raising=False)
    monkeypatch.setattr('app.shared.utils.log_service.get_log_service', lambda: fake_svc, raising=False)
    cfg = {'ip': '10.0.0.58', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo ']}
    _patch_service(monkeypatch, cfg)
    _patch_paramiko(monkeypatch, stdout_text='ok\n', exit_code=0)
    runtime = _build_runtime(business_name='epsilon')
    from app.shared.tools.skills.devops.SSHTools import execute_command
    out = _run(execute_command(command='echo hi', business_name='epsilon', runtime=runtime))
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('success') is True

def test_execute_command_log_event_uses_runtime_identity(monkeypatch):
    """execute_command 的 LogEvent 必须从 ``runtime`` / ``runtime.context`` 读 ``tool_call_id`` / ``session_id`` / ``log_user_id`` / ``log_username``。"""
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.59', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo ']}
    _patch_service(monkeypatch, cfg)
    _patch_paramiko(monkeypatch, stdout_text='ok\n', exit_code=0)
    runtime = MagicMock(name='ToolRuntime')
    runtime.tool_call_id = 'call-zzz'
    runtime.context = {'business_name': 'zeta', 'session_id': 'sess-zeta-001', 'log_user_id': 42, 'log_username': 'alice-real'}
    from app.shared.tools.skills.devops.SSHTools import execute_command
    _run(execute_command(command='echo hi', business_name='zeta', runtime=runtime))
    evt = captured[-1]
    assert evt.tool_call_id == 'call-zzz'
    assert evt.session_id == 'sess-zeta-001'
    assert evt.user_id == 42
    assert evt.username == 'alice-real'

def test_execute_command_log_event_carries_ip_address_from_runtime_context(monkeypatch):
    """execute_command 的 LogEvent 必须从 ``runtime.context['log_ip']`` 读客户端 IP。

    业务语义(2026-07-30 新增):SSH 工具审计日志的 ``ip_address`` 字段必须非空,
    写入 ``audit_logs.ip_address`` 用于追踪真正触发命令的客户端。
    来源:``agent_router.chat`` 用 ``request.client.host`` 强制覆盖后注入。
    """
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.59', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo ']}
    _patch_service(monkeypatch, cfg)
    _patch_paramiko(monkeypatch, stdout_text='ok\n', exit_code=0)
    runtime = MagicMock(name='ToolRuntime')
    runtime.tool_call_id = 'call-ipv4'
    runtime.context = {'business_name': 'zeta', 'session_id': 'sess-zeta-001', 'log_user_id': 42, 'log_username': 'alice-real', 'log_ip': '203.0.113.5'}
    from app.shared.tools.skills.devops.SSHTools import execute_command
    _run(execute_command(command='echo hi', business_name='zeta', runtime=runtime))
    evt = captured[-1]
    assert evt.ip_address == '203.0.113.5'

def test_execute_command_log_event_ip_address_none_when_missing(monkeypatch):
    """execute_command 的 LogEvent 在 ``runtime.context`` 缺 ``log_ip`` 时, ``ip_address`` 应为 ``None``。

    行为契约:不抛异常,允许 Lifespan 异常 / 离线脚本 / 测试桩场景写入 ``NULL``。
    """
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.59', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo ']}
    _patch_service(monkeypatch, cfg)
    _patch_paramiko(monkeypatch, stdout_text='ok\n', exit_code=0)
    runtime = MagicMock(name='ToolRuntime')
    runtime.tool_call_id = 'call-noip'
    runtime.context = {'business_name': 'zeta', 'session_id': 'sess-zeta-001', 'log_user_id': 42, 'log_username': 'alice-real'}
    from app.shared.tools.skills.devops.SSHTools import execute_command
    _run(execute_command(command='echo hi', business_name='zeta', runtime=runtime))
    evt = captured[-1]
    assert evt.ip_address is None

def test_execute_command_log_event_ip_address_ignores_non_str_type(monkeypatch):
    """execute_command 的 LogEvent 在 ``runtime.context['log_ip']`` 非 str 时, ``ip_address`` 应为 ``None``。

    防御性:防止客户端(虽然 router 已覆盖)伪造非 str 值,例如 ``int`` / ``list`` /
    ``dict`` 绕过类型校验写脏数据。
    """
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.59', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo ']}
    _patch_service(monkeypatch, cfg)
    _patch_paramiko(monkeypatch, stdout_text='ok\n', exit_code=0)
    runtime = MagicMock(name='ToolRuntime')
    runtime.tool_call_id = 'call-bad-ip'
    runtime.context = {'business_name': 'zeta', 'session_id': 'sess-zeta-001', 'log_ip': 12345}
    from app.shared.tools.skills.devops.SSHTools import execute_command
    _run(execute_command(command='echo hi', business_name='zeta', runtime=runtime))
    evt = captured[-1]
    assert evt.ip_address is None

def test_execute_command_log_event_ip_address_strips_whitespace(monkeypatch):
    """execute_command 的 LogEvent 应 ``strip`` 掉 ``log_ip`` 前后空白,避免脏数据。"""
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.59', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo ']}
    _patch_service(monkeypatch, cfg)
    _patch_paramiko(monkeypatch, stdout_text='ok\n', exit_code=0)
    runtime = MagicMock(name='ToolRuntime')
    runtime.tool_call_id = 'call-ws-ip'
    runtime.context = {'business_name': 'zeta', 'session_id': 'sess-zeta-001', 'log_ip': '  203.0.113.5\n'}
    from app.shared.tools.skills.devops.SSHTools import execute_command
    _run(execute_command(command='echo hi', business_name='zeta', runtime=runtime))
    evt = captured[-1]
    assert evt.ip_address == '203.0.113.5'

def test_execute_command_metadata_never_leaks_original_command(monkeypatch):
    """``command_redacted`` 字段不得保留原始命令中含密码的片段(由 ``redact_command`` 统一处理)。"""
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.60', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['mysql ']}
    _patch_service(monkeypatch, cfg)
    _patch_paramiko(monkeypatch, stdout_text='ok\n', exit_code=0)
    runtime = _build_runtime(business_name='zeta2')
    from app.shared.tools.skills.devops.SSHTools import execute_command
    _run(execute_command(command="mysql --password=hunter2xyz -e 'select 1'", business_name='zeta2', runtime=runtime))
    evt = captured[-1]
    meta_blob = json.dumps(evt.metadata, ensure_ascii=False)
    assert 'hunter2xyz' not in meta_blob

def test_execute_command_does_not_emit_stdout_stderr_in_metadata(monkeypatch):
    """execute_command 元数据不写入 stdout / stderr 正文(只写 stdout_size / stderr_size)。"""
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.61', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo ']}
    _patch_service(monkeypatch, cfg)
    _patch_paramiko(monkeypatch, stdout_text='secret-output-line\n', stderr_text='secret-err-line\n', exit_code=0)
    runtime = _build_runtime(business_name='eta')
    from app.shared.tools.skills.devops.SSHTools import execute_command
    _run(execute_command(command='echo hi', business_name='eta', runtime=runtime))
    evt = captured[-1]
    md = evt.metadata
    meta_blob = json.dumps(md, ensure_ascii=False)
    assert 'secret-output-line' not in meta_blob
    assert 'secret-err-line' not in meta_blob
    assert md['stdout_size'] == len('secret-output-line')
    assert md['stderr_size'] == len('secret-err-line')

def test_execute_batch_commands_emits_one_summary_and_one_per_command(monkeypatch):
    """execute_batch_commands 正常路径 emit:
    - 1 条 ``action='ssh_execute_batch'`` 的汇总日志(同一 correlation_id)
    - N 条 ``action='ssh_execute_command'`` 的子命令日志(同一 correlation_id)
    """
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.62', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['whoami', 'date']}
    _patch_service(monkeypatch, cfg)
    _patch_paramiko(monkeypatch, stdout_text='ok', exit_code=0)
    runtime = _build_runtime(business_name='theta')
    from app.shared.tools.skills.devops.SSHTools import execute_batch_commands
    out = _run(execute_batch_commands(commands=['whoami', 'date'], business_name='theta', runtime=runtime))
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('success') is True
    assert len(captured) == 3, f'期望 3 条 emit, 实际 {len(captured)}'
    summary = next((e for e in captured if e.action == 'ssh_execute_batch'), None)
    children = [e for e in captured if e.action == 'ssh_execute_command']
    assert summary is not None
    assert len(children) == 2
    assert str(summary.log_type) == 'ssh'
    assert str(summary.result) == 'success'
    assert summary.target_name == 'theta'
    summary_cid = summary.correlation_id
    assert summary_cid
    for child in children:
        assert child.correlation_id == summary_cid
        assert child.target_name == 'theta'

def test_execute_batch_commands_blocked_emits_blocked_and_skipped(monkeypatch):
    """execute_batch_commands 任一条被拦截：emit 拦截项 ``blocked`` + 其余项 ``skipped`` + 1 条汇总 ``blocked``。"""
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.63', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': ['^shutdown'], 'whitelist': ['ls', 'shutdown -h now', 'whoami']}
    _patch_service(monkeypatch, cfg)
    _patch_paramiko(monkeypatch, stdout_text='ignored', exit_code=0)
    runtime = _build_runtime(business_name='iota')
    from app.shared.tools.skills.devops.SSHTools import execute_batch_commands
    out = _run(execute_batch_commands(commands=['ls', 'shutdown -h now', 'whoami'], business_name='iota', runtime=runtime))
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('success') is False
    assert len(captured) == 4, f'期望 4 条 emit, 实际 {len(captured)}: {[e.action for e in captured]}'
    summary = next((e for e in captured if e.action == 'ssh_execute_batch'), None)
    assert summary is not None
    assert str(summary.result) == 'blocked'
    summary_cid = summary.correlation_id
    sub_events = [e for e in captured if e.action == 'ssh_execute_command']
    blocked = [e for e in sub_events if str(e.result) == 'blocked']
    skipped = [e for e in sub_events if str(e.result) == 'skipped']
    assert len(blocked) == 1
    assert len(skipped) == 2
    assert blocked[0].metadata.get('error_code') == 'blocked'
    for s in skipped:
        assert s.metadata.get('error_code') == 'batch_rejected'

def test_execute_batch_commands_invalid_list_emits_one_failure(monkeypatch):
    """execute_batch_commands 在 commands 为非法(空 list / None)时,只 emit 1 条 ``failure`` 日志(批次维度, 不展开子项)。"""
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.64', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['ls']}
    _patch_service(monkeypatch, cfg)
    _patch_paramiko(monkeypatch, stdout_text='', exit_code=0)
    runtime = _build_runtime(business_name='kappa')
    from app.shared.tools.skills.devops.SSHTools import execute_batch_commands
    out = _run(execute_batch_commands(commands=[], business_name='kappa', runtime=runtime))
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('success') is False
    assert len(captured) == 1, f'非法列表仅批次 failure, 实际 {len(captured)}'
    evt = captured[0]
    assert evt.action == 'ssh_execute_batch'
    assert str(evt.result) == 'failure'
    assert evt.metadata.get('error_code') == 'invalid_commands'

def test_get_system_logs_success_emits_ssh_log_event(monkeypatch):
    """get_system_logs 成功路径 emit ``action='ssh_get_system_logs'`` 的 ssh 日志。"""
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.65', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['tail ']}
    _patch_service(monkeypatch, cfg)
    _patch_paramiko(monkeypatch, stdout_text='line1\nline2\n', exit_code=0)
    runtime = _build_runtime(business_name='lamda')
    from app.shared.tools.skills.devops.SSHTools import get_system_logs
    out = _run(get_system_logs(business_name='lamda', log_type='syslog', lines=10, runtime=runtime))
    msgs = out.update['messages']
    payload = msgs[0].content
    assert len(captured) == 1
    evt = captured[0]
    assert evt.action == 'ssh_get_system_logs'
    assert str(evt.log_type) == 'ssh'
    assert str(evt.result) == 'success'
    md = evt.metadata
    assert md['server_type'] == 'linux'
    assert 'command_redacted' in md
    assert 'command_hash' in md
    assert md['decision'] == 'executed'

def test_get_system_logs_blocked_emits_blocked_ssh_log_event(monkeypatch):
    """get_system_logs 黑名单拦截路径 emit ``result='blocked'``。"""
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.66', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': ['tail '], 'whitelist': ['tail -n 10 /var/log/syslog']}
    _patch_service(monkeypatch, cfg)
    _patch_paramiko(monkeypatch, stdout_text='', exit_code=0)
    runtime = _build_runtime(business_name='mu')
    from app.shared.tools.skills.devops.SSHTools import get_system_logs
    _run(get_system_logs(business_name='mu', log_type='syslog', lines=10, runtime=runtime))
    assert len(captured) == 1
    evt = captured[0]
    assert evt.action == 'ssh_get_system_logs'
    assert str(evt.result) == 'blocked'
    md = evt.metadata
    assert md['decision'] == 'blocked'
    assert 'intercept_reason' in md

def test_execute_command_correlation_id_is_none_per_call(monkeypatch):
    """两次 execute_command 调用产生的 ssh_execute_command 日志 correlation_id 都是 ``None``。

    2026-07-29 修订：单命令不自动生成 UUID,避免污染 ``get_correlated_logs`` 查询语义;
    批量场景由调用方显式传入共享 UUID。
    """
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.67', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo ']}
    _patch_service(monkeypatch, cfg)
    _patch_paramiko(monkeypatch, stdout_text='ok', exit_code=0)
    runtime = _build_runtime(business_name='nu')
    from app.shared.tools.skills.devops.SSHTools import execute_command
    _run(execute_command(command='echo a', business_name='nu', runtime=runtime))
    _run(execute_command(command='echo b', business_name='nu', runtime=runtime))
    assert len(captured) == 2
    assert captured[0].correlation_id is None
    assert captured[1].correlation_id is None

def test_execute_command_blocked_path_emits_no_paramiko_call(monkeypatch):
    """黑名单拦截路径既不调 paramiko 也不污染工具响应,但仍 emit LogEvent(满足"每个终态一条")。"""
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.68', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': ['^rm\\s+-rf'], 'whitelist': ['rm -rf /tmp/x']}
    _patch_service(monkeypatch, cfg)
    fake_client = _patch_paramiko(monkeypatch, stdout_text='', exit_code=0)
    runtime = _build_runtime(business_name='xi')
    from app.shared.tools.skills.devops.SSHTools import execute_command
    _run(execute_command(command='rm -rf /tmp/x', business_name='xi', runtime=runtime))
    fake_client.exec_command.assert_not_called()
    assert len(captured) == 1

def test_execute_command_uses_runtime_tool_call_id_when_present(monkeypatch):
    """execute_command 从 ``runtime.tool_call_id`` 取 ID,没有时退回 'unknown'。"""
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.69', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo ']}
    _patch_service(monkeypatch, cfg)
    _patch_paramiko(monkeypatch, stdout_text='ok', exit_code=0)
    runtime = MagicMock(name='ToolRuntime')
    runtime.tool_call_id = 'call-abc'
    runtime.context = {'business_name': 'omikron', 'session_id': 's'}
    from app.shared.tools.skills.devops.SSHTools import execute_command
    _run(execute_command(command='echo hi', business_name='omikron', runtime=runtime))
    assert captured[-1].tool_call_id == 'call-abc'
    captured.clear()
    _run(execute_command(command='echo hi', business_name='omikron', runtime=None))
    assert captured[-1].tool_call_id == 'unknown'

def test_execute_command_success_even_when_stderr_noisy(monkeypatch):
    """exit_code == 0 但 stderr 非空 → ``success=True``,不依赖 stderr。

    2026-07-29 统一语义:Linux /root/.bashrc 注释噪声或 cron stderr 警告
    不应让 exit 0 命令被视为失败;``error_code`` 仅在 ``exit_code != 0`` 时
    才为 ``non_zero_exit``。
    """
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.70', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo ']}
    _patch_service(monkeypatch, cfg)
    _patch_paramiko(monkeypatch, stdout_text='ok\n', stderr_text='No such file or directory: bashrc-comment-noise\n', exit_code=0)
    runtime = _build_runtime(business_name='zeta-noise')
    from app.shared.tools.skills.devops.SSHTools import execute_command
    out = _run(execute_command(command='echo hi', business_name='zeta-noise', runtime=runtime))
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('success') is True
    evt = captured[-1]
    assert evt.metadata['exit_code'] == 0
    assert evt.metadata['error_code'] is None
    assert str(evt.result) == 'success'

def test_execute_command_failure_only_when_exit_nonzero(monkeypatch):
    """exit_code != 0 → ``success=False`` / ``error_code='non_zero_exit'``(stderr 可有可无)。"""
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.71', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['false']}
    _patch_service(monkeypatch, cfg)
    _patch_paramiko(monkeypatch, stdout_text='', stderr_text='some error\n', exit_code=2)
    runtime = _build_runtime(business_name='zeta-fail')
    from app.shared.tools.skills.devops.SSHTools import execute_command
    out = _run(execute_command(command='false', business_name='zeta-fail', runtime=runtime))
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('success') is False
    evt = captured[-1]
    assert evt.metadata['exit_code'] == 2
    assert evt.metadata['error_code'] == 'non_zero_exit'
    assert str(evt.result) == 'failure'

def test_execute_command_blocked_intercept_reason_is_fixed_category(monkeypatch):
    """黑名单拦截日志只持久化固定类别代码，禁止原命令进入原因字段。

    参数:
        monkeypatch: pytest monkeypatch。
    返回值:
        None。
    异常:
        AssertionError: 拦截原因不是固定类别时抛出。
    """
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.72', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': ['^mysql'], 'whitelist': ['mysql ']}
    _patch_service(monkeypatch, cfg)
    _patch_paramiko(monkeypatch, stdout_text='ignored', exit_code=0)
    runtime = _build_runtime(business_name='redact-test')
    from app.shared.tools.skills.devops.SSHTools import execute_command
    _run(execute_command(command='mysql --password=blocked-secret', business_name='redact-test', runtime=runtime))
    metadata = captured[-1].metadata
    assert metadata['intercept_reason'] == 'command_blacklisted'
    assert 'blocked-secret' not in json.dumps(metadata, ensure_ascii=False)

def test_execute_command_redact_intercept_reason_truncates_to_1000():
    """``_redact_intercept_reason`` 必须把超长 reason 截断到 1000 字符。"""
    from app.shared.tools.skills.devops.SSHTools import _redact_intercept_reason
    long_reason = 'blocked: ' + 'X' * 5000
    redacted = _redact_intercept_reason(long_reason)
    assert redacted is not None
    assert len(redacted) <= 1000

def test_execute_command_redact_intercept_reason_empty_returns_empty():
    """空 reason 透传(不抛异常)。"""
    from app.shared.tools.skills.devops.SSHTools import _redact_intercept_reason
    assert _redact_intercept_reason(None) is None
    assert _redact_intercept_reason('') == ''

def test_execute_batch_commands_auth_failure_emits_summary_and_members(monkeypatch):
    """execute_batch_commands 在 paramiko.AuthenticationException 时:1 条汇总 + N 条明细共享 batch_cid。"""
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.73', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['whoami', 'date', 'ls']}
    _patch_service(monkeypatch, cfg)
    fake_paramiko = MagicMock(name='paramiko')
    fake_paramiko.SSHClient = MagicMock()
    fake_paramiko.AutoAddPolicy = MagicMock()
    import paramiko as real_paramiko
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException
    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, 'paramiko', fake_paramiko, raising=False)

    def fake_open_client(_config):
        raise real_paramiko.AuthenticationException('auth failed')
    monkeypatch.setattr(SSHTools, '_open_client', fake_open_client)
    runtime = _build_runtime(business_name='auth-fail')
    from app.shared.tools.skills.devops.SSHTools import execute_batch_commands
    out = _run(execute_batch_commands(commands=['whoami', 'date', 'ls'], business_name='auth-fail', runtime=runtime))
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('success') is False
    assert payload.get('error') == 'SSH 认证失败'
    assert len(captured) == 4
    summary = next((e for e in captured if e.action == 'ssh_execute_batch'), None)
    members = [e for e in captured if e.action == 'ssh_execute_command']
    assert summary is not None
    assert len(members) == 3
    summary_cid = summary.correlation_id
    for m in members:
        assert m.correlation_id == summary_cid
    assert summary.metadata['error_code'] == 'auth_failed'
    for m in members:
        assert m.metadata['error_code'] == 'auth_failed'
        assert m.metadata['decision'] == 'allowed'
        assert str(m.result) == 'failure'

def test_execute_batch_commands_ssh_exception_emits_summary_and_members(monkeypatch):
    """execute_batch_commands 在 paramiko.SSHException 时:1 条汇总 + N 条明细共享 batch_cid。"""
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.74', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['a', 'b']}
    _patch_service(monkeypatch, cfg)
    import paramiko as real_paramiko
    fake_paramiko = MagicMock(name='paramiko')
    fake_paramiko.SSHClient = MagicMock()
    fake_paramiko.AutoAddPolicy = MagicMock()
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException
    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, 'paramiko', fake_paramiko, raising=False)

    def fake_open_client(_config):
        raise real_paramiko.SSHException('ssh conn lost')
    monkeypatch.setattr(SSHTools, '_open_client', fake_open_client)
    runtime = _build_runtime(business_name='ssh-fail')
    from app.shared.tools.skills.devops.SSHTools import execute_batch_commands
    out = _run(execute_batch_commands(commands=['a', 'b'], business_name='ssh-fail', runtime=runtime))
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('success') is False
    assert len(captured) == 3
    summary = next((e for e in captured if e.action == 'ssh_execute_batch'), None)
    members = [e for e in captured if e.action == 'ssh_execute_command']
    assert summary is not None
    assert len(members) == 2
    assert summary.metadata['error_code'] == 'ssh_error'
    for m in members:
        assert m.metadata['error_code'] == 'ssh_error'
        assert m.correlation_id == summary.correlation_id

def test_execute_batch_commands_generic_exception_emits_summary_and_members(monkeypatch):
    """execute_batch_commands 在通用 Exception 时:1 条汇总 + N 条明细共享 batch_cid。"""
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.75', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['c', 'd']}
    _patch_service(monkeypatch, cfg)
    fake_paramiko = MagicMock(name='paramiko')
    fake_paramiko.SSHClient = MagicMock()
    fake_paramiko.AutoAddPolicy = MagicMock()
    import paramiko as real_paramiko
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException
    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, 'paramiko', fake_paramiko, raising=False)

    def fake_open_client(_config):
        raise RuntimeError('connection failed')
    monkeypatch.setattr(SSHTools, '_open_client', fake_open_client)
    runtime = _build_runtime(business_name='exec-fail')
    from app.shared.tools.skills.devops.SSHTools import execute_batch_commands
    out = _run(execute_batch_commands(commands=['c', 'd'], business_name='exec-fail', runtime=runtime))
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('success') is False
    assert len(captured) == 3
    summary = next((e for e in captured if e.action == 'ssh_execute_batch'), None)
    members = [e for e in captured if e.action == 'ssh_execute_command']
    assert summary is not None
    assert len(members) == 2
    assert summary.metadata['error_code'] == 'execution_failed'
    for m in members:
        assert m.metadata['error_code'] == 'execution_failed'
        assert m.correlation_id == summary.correlation_id

def test_execute_batch_commands_config_unresolved_emits_summary_and_members(monkeypatch):
    """execute_batch_commands 在 config_unresolved 时:1 条汇总 + N 条明细共享 batch_cid,decision=config_failed。"""
    _, captured = _install_capturing_log_service(monkeypatch)
    fake_service = MagicMock(name='DevOpsServerService')
    fake_service.get_connection_config = MagicMock(side_effect=ValueError('解密失败（Fernet key 与加密时不一致？）: mybiz'))
    from app.shared.utils.devops_server_service import DevOpsServerService
    DevOpsServerService.set_instance(fake_service)
    runtime = _build_runtime(business_name='mybiz')
    from app.shared.tools.skills.devops.SSHTools import execute_batch_commands
    out = _run(execute_batch_commands(commands=['ls', 'whoami'], business_name='mybiz', runtime=runtime))
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('success') is False
    assert payload.get('error') == '无法解析服务器配置'
    assert len(captured) == 3
    summary = next((e for e in captured if e.action == 'ssh_execute_batch'), None)
    members = [e for e in captured if e.action == 'ssh_execute_command']
    assert summary is not None
    assert len(members) == 2
    summary_cid = summary.correlation_id
    for m in members:
        assert m.correlation_id == summary_cid
    assert summary.metadata['error_code'] == 'config_unresolved'
    for m in members:
        assert m.metadata['error_code'] == 'config_unresolved'
        assert m.metadata['decision'] == 'config_failed'
        assert str(m.result) == 'failure'

def test_get_system_logs_success_even_when_stderr_noisy(monkeypatch):
    """get_system_logs: exit 0 + stderr 非空 → ``success=True``(2026-07-29 语义统一)。"""
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.76', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['tail ']}
    _patch_service(monkeypatch, cfg)
    _patch_paramiko(monkeypatch, stdout_text='log line A\nlog line B\n', stderr_text='bashrc noise\n', exit_code=0)
    runtime = _build_runtime(business_name='logs-noise')
    from app.shared.tools.skills.devops.SSHTools import get_system_logs
    out = _run(get_system_logs(business_name='logs-noise', log_type='syslog', lines=10, runtime=runtime))
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('success') is True
    evt = captured[-1]
    assert str(evt.result) == 'success'
    assert evt.metadata['exit_code'] == 0
    assert evt.metadata['error_code'] is None


# ============================================================================
# 2026-08-19 新增：SSH 执行时长高内聚方案 —— 3 个 @tool 改读 config["ssh_timeout"]
# ============================================================================


def test_execute_command_ignores_llm_timeout_param(monkeypatch):
    """LLM 误传 timeout=5，节点 ssh_timeout=120 → 实际取 120（LLM 不可覆盖）。"""
    _patch_service(
        monkeypatch,
        {
            'ip': '10.0.0.11', 'port': 22, 'username': 'u', 'password': 'p',
            'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo '],
            'ssh_timeout': 120,
        },
    )
    client = _patch_paramiko(monkeypatch, stdout_text='hi\n')
    runtime = _build_runtime(business_name='beta')
    from app.shared.tools.skills.devops.SSHTools import execute_command
    _run(execute_command(command='echo hi', business_name='beta',
                          timeout=5, runtime=runtime))
    # paramiko.exec_command 实际收到 timeout=120（高内聚，直接读 config）
    _args, kwargs = client.exec_command.call_args
    assert kwargs.get('timeout') == 120


def test_execute_command_uses_config_ssh_timeout_45(monkeypatch):
    """execute_command 直接读 config["ssh_timeout"]，节点值 45 时实际取 45。"""
    _, _ = _install_capturing_log_service(monkeypatch)
    cfg = {
        'ip': '10.0.0.10', 'port': 22, 'username': 'u', 'password': 'p',
        'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo '],
        'ssh_timeout': 45,
    }
    _patch_service(monkeypatch, cfg)
    client = _patch_paramiko(monkeypatch, stdout_text='hi\n')
    runtime = _build_runtime(business_name='alpha')
    from app.shared.tools.skills.devops.SSHTools import execute_command
    # LLM 传 timeout=999999 应被忽略；实际取 config["ssh_timeout"]=45
    _run(execute_command(command='echo hi', business_name='alpha',
                          timeout=999999, runtime=runtime))
    _args, kwargs = client.exec_command.call_args
    assert kwargs.get('timeout') == 45


def test_execute_batch_commands_uses_config_ssh_timeout_directly(monkeypatch):
    """execute_batch_commands 每条命令共享 config["ssh_timeout"]。"""
    _patch_service(
        monkeypatch,
        {
            'ip': '10.0.0.12', 'port': 22, 'username': 'u', 'password': 'p',
            'server_type': 'linux', 'blacklist': [],
            'whitelist': ['echo ', 'whoami'],
            'ssh_timeout': 60,
        },
    )
    client = _patch_paramiko(monkeypatch, stdout_text='hi\n')
    runtime = _build_runtime(business_name='gamma')
    from app.shared.tools.skills.devops.SSHTools import execute_batch_commands
    _run(execute_batch_commands(
        commands=['echo hi', 'whoami'], business_name='gamma',
        timeout=999999, runtime=runtime,
    ))
    # 每条命令的 paramiko.exec_command 都应收到 timeout=60
    assert client.exec_command.call_count == 2
    for _args, kwargs in client.exec_command.call_args_list:
        assert kwargs.get('timeout') == 60


def test_get_system_logs_uses_config_ssh_timeout_directly(monkeypatch):
    """get_system_logs 直接读 config["ssh_timeout"]，替换原硬编码 30s。"""
    _patch_service(
        monkeypatch,
        {
            'ip': '10.0.0.13', 'port': 22, 'username': 'u', 'password': 'p',
            'server_type': 'linux', 'blacklist': [],
            'whitelist': ['tail '],
            'ssh_timeout': 90,
        },
    )
    client = _patch_paramiko(monkeypatch, stdout_text='log line\n')
    runtime = _build_runtime(business_name='delta')
    from app.shared.tools.skills.devops.SSHTools import get_system_logs
    _run(get_system_logs(business_name='delta', log_type='syslog',
                          lines=10, runtime=runtime))
    _args, kwargs = client.exec_command.call_args
    assert kwargs.get('timeout') == 90

def test_blocked_sensitive_command_persists_redacted_via_real_log_service(monkeypatch):
    """真实 LogService(memory_only) 持久化敏感命令拦截日志。

    端到端覆盖:SSHTools → LogService.emit → consume_loop → _store_memory
    → query_logs 返回的 metadata 中敏感口令片段不外泄(``mysql --password=secret``)。

    Args:
        monkeypatch: pytest monkeypatch
    """
    import asyncio
    from app.shared.utils.log_service import LogService, reset_log_service, set_log_service
    svc = LogService(memory_only=True, flush_interval_seconds=0.05, batch_size=10)

    async def _lifecycle():
        await svc.start()
        from app.shared.tools.skills.devops.SSHTools import execute_command
        cfg = {'ip': '10.0.0.77', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['mysql ']}
        _patch_service(monkeypatch, cfg)
        _patch_paramiko(monkeypatch, stdout_text='ok', exit_code=0)
        runtime = _build_runtime(business_name='persist-redact')
        # 2026-08-05:execute_command 是 async,已在 running loop 内,直接 await。
        # 不使用 _run helper,因为它内部 asyncio.run() 在 running loop 里会抛
        # RuntimeError('asyncio.run() cannot be called from a running event loop')。
        await execute_command(command="mysql --password=secret123 -e 'select 1'", business_name='persist-redact', runtime=runtime)
        await asyncio.sleep(0.15)
        await svc.stop()
    set_log_service(svc)
    try:
        asyncio.run(_lifecycle())

        async def _query():
            return await svc.query_logs(log_type='ssh')
        rows = asyncio.run(_query())
    finally:
        reset_log_service()
    assert rows
    success = [r for r in rows if str(r.get('result')) == 'success']
    assert len(success) == 1
    md = success[0]['metadata']
    blob = json.dumps(md, ensure_ascii=False)
    assert 'secret123' not in blob
    assert md.get('command_redacted')
    from app.shared.utils.log_service import hash_command
    assert md.get('command_hash') == hash_command("mysql --password=secret123 -e 'select 1'")


# ---------------------------------------------------------------------------
# 2026-08-05 新增:回归保护 - SSHTools 三个 @tool 改为 async def 后,
# 在 LangGraph ToolNode 的 in-flight asyncio loop 内直接 await 调用,
# 不会再触发旧实现中的 `asyncio.run() cannot be called from a running event loop`
# 或 `run_coroutine_threadsafe(...).result()` 死锁。下面两个测试模拟该调用场景。
# ---------------------------------------------------------------------------


def test_execute_command_works_inside_running_event_loop(monkeypatch):
    """execute_command 在 running asyncio loop 内调用不抛 RuntimeError。

    回归保护:旧实现走 ``asyncio.run()`` 包装异步 dispatch,在 running loop
    内会触发 ``RuntimeError: asyncio.run() cannot be called from a running
    event loop``;改 async def 后直接 await,问题不再出现。

    Args:
        monkeypatch: pytest monkeypatch
    """
    secret_config = {'ip': '10.0.0.50', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo ']}
    _patch_service(monkeypatch, secret_config)
    _patch_paramiko(monkeypatch, stdout_text='in-loop\n', exit_code=0)
    runtime = _build_runtime(business_name='loop-test')

    async def _run_in_loop():
        """模拟 LangGraph ToolNode 在 in-flight loop 内调 execute_command。"""
        from app.shared.tools.skills.devops.SSHTools import execute_command
        result = await execute_command(command='echo in-loop', business_name='loop-test', runtime=runtime)
        return result

    # 不抛 RuntimeError = 修复成功
    out = asyncio.run(_run_in_loop())
    msgs = out.update['messages']
    assert len(msgs) == 1
    payload = json.loads(msgs[0].content)
    assert payload.get('success') is True
    assert 'in-loop' in payload.get('output', '')


def test_execute_command_third_party_inside_running_event_loop(monkeypatch):
    """execute_command 走第三方分支时在 running loop 内调用不抛 RuntimeError。

    回归保护:旧实现走 ``run_coroutine_threadsafe(coro, loop).result()``
    在 in-flight loop 里死锁 / 抛 RuntimeError;改 async def 后直接
    ``await _tp_dispatch(...)``,无包装层。

    Args:
        monkeypatch: pytest monkeypatch
    """
    cfg = {'ip': '10.0.0.51', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo ']}
    _patch_service(monkeypatch, cfg)
    # patch paramiko(确保不调本地)
    fake_client = MagicMock()
    fake_client.exec_command = MagicMock()
    fake_client.close = MagicMock()
    fake_paramiko = MagicMock()
    fake_paramiko.SSHClient = MagicMock(return_value=fake_client)
    fake_paramiko.AutoAddPolicy = MagicMock()
    import paramiko as real_paramiko
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException
    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, 'paramiko', fake_paramiko, raising=False)

    # patch third_party_executor.dispatch 为 AsyncMock
    from app.shared.utils.executor import third_party_executor as tp_module
    fake_dispatch = AsyncMock(name='dispatch', return_value={'success': True, 'output': 'tp-in-loop', 'exit_code': 0})
    monkeypatch.setattr(tp_module, 'dispatch', fake_dispatch)

    # patch endpoint registry
    from app.shared.utils.executor.endpoints import ThirdPartyEndpoint, ThirdPartyEndpointRegistry
    fake_ep = MagicMock(name='ThirdPartyEndpoint', spec=ThirdPartyEndpoint)
    fake_ep.name = 'primary'
    fake_registry = MagicMock(name='ThirdPartyEndpointRegistry')
    fake_registry.get = MagicMock(return_value=fake_ep)
    monkeypatch.setattr(ThirdPartyEndpointRegistry, 'get_instance', classmethod(lambda cls: fake_registry))

    runtime = MagicMock(name='ToolRuntime')
    runtime.tool_call_id = 'call-tp-loop'
    runtime.context = {
        'business_name': 'alpha',
        'session_id': 'sess-tp',
        'use_third_party_executor': True,
        'third_party_endpoint_name': 'primary',
    }

    async def _run_in_loop():
        from app.shared.tools.skills.devops.SSHTools import execute_command
        result = await execute_command(command='echo hi', business_name='alpha', runtime=runtime)
        return result

    out = asyncio.run(_run_in_loop())
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('success') is True
    assert payload.get('output') == 'tp-in-loop'
    fake_dispatch.assert_awaited_once()