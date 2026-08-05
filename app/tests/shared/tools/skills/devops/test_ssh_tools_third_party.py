"""
SSHTools.execute_command 第三方分支测试（2026-08-03 新增）。

覆盖目标：
    - ``runtime.context["use_third_party_executor"] = True`` 时跳过本地 Paramiko，
      通过加密 HTTPS 调用第三方并返回明文结果
    - 黑/白名单仍生效（拦截在第三方分支之前）
    - 第三方调用失败（超时 / HTTP 错误 / 加密失败）统一降级为 ``success=False``
      并落审计日志，metadata 中 ``executor_type='third_party'``
    - ``runtime.context["use_third_party_executor"] = False`` 或缺失时，
      仍走本地 Paramiko（向后兼容）

策略：
    - mock ``third_party_executor.dispatch`` 返回值（避免真打 https）
    - mock ``ThirdPartyEndpointRegistry.get_instance`` 返回端点 stub
    - 沿用 ``test_ssh_tools.py`` 的 ``_build_runtime`` / ``_patch_service`` /
      ``_patch_paramiko`` / ``_install_capturing_log_service`` 模式

Date: 2026-08-03
Author: AI Assistant
"""
from __future__ import annotations
import asyncio
import inspect
import json
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 2026-08-05:第三方分支日志可观测性回归测试需要构造 ThirdPartyExecutorError。
from app.shared.utils.executor.errors import (
    ERR_CONFIG_MISSING,
    ThirdPartyExecutorError,
)

def _run(callable_or_coro):
    """统一包装工具调用:若是 coroutine 则 asyncio.run,否则直接返回结果。

    2026-08-05:SSHTools.execute_command 已改为 ``async def``(LangGraph ToolNode
    在 in-flight asyncio loop 内可直接 await;第三方 HTTPS 直接 ``await dispatch(...)``,
    无需 asyncio.run / run_coroutine_threadsafe 包装)。测试环境无运行中的 loop,
    需用 ``asyncio.run`` 触发同步执行。
    """
    if inspect.iscoroutine(callable_or_coro):
        return asyncio.run(callable_or_coro)
    return callable_or_coro

def _build_runtime(business_name: str='alpha', session_id: str='sess-x', extra_context: Dict[str, Any]=None) -> MagicMock:
    """构造 runtime mock，支持注入额外 context。"""
    runtime = MagicMock(name='ToolRuntime')
    runtime.tool_call_id = 'call-tp'
    ctx: Dict[str, Any] = {'business_name': business_name, 'session_id': session_id}
    if extra_context:
        ctx.update(extra_context)
    runtime.context = ctx
    return runtime

def _patch_service(monkeypatch, config: Dict[str, Any]) -> MagicMock:
    """替换 DevOpsServerService 单例。"""
    from app.shared.utils.devops_server_service import DevOpsServerService
    fake_service = MagicMock(name='DevOpsServerService')
    fake_service.get_connection_config = MagicMock(return_value=config)
    DevOpsServerService.set_instance(fake_service)
    return fake_service

def _install_capturing_log_service(monkeypatch):
    """捕获 LogService.emit 调用。"""
    captured = []

    def fake_emit(event):
        captured.append(event)
        return True
    fake_svc = MagicMock(name='LogService')
    fake_svc.emit = fake_emit
    monkeypatch.setattr('app.shared.utils.log_service._log_service_singleton', fake_svc, raising=False)
    monkeypatch.setattr('app.shared.utils.log_service.get_log_service', lambda: fake_svc, raising=False)
    from app.shared.tools.skills.devops import SSHTools as _SSHTools
    monkeypatch.setattr(_SSHTools, 'get_log_service', lambda: fake_svc, raising=False)
    return (fake_svc, captured)

def _patch_third_party_dispatch(monkeypatch, return_value: Any) -> MagicMock:
    """替换 ``app.shared.utils.executor.third_party_executor.dispatch``。

    SSHTools 内部 ``from X import dispatch as _tp_dispatch`` 是函数体内 lazy import，
    每次进入分支都会重新从 ``third_party_executor.dispatch`` 读取当前属性。
    因此只要把 ``tp_module.dispatch`` 替换为 mock，SSHTools 内的新引用就会拿到 mock。
    """
    from app.shared.utils.executor import third_party_executor as tp_module
    fake_dispatch = AsyncMock(name='dispatch', return_value=return_value)
    monkeypatch.setattr(tp_module, 'dispatch', fake_dispatch)
    return fake_dispatch

def _patch_third_party_dispatch_with_error(monkeypatch, exc: BaseException) -> MagicMock:
    """让 dispatch 抛指定异常（用于测试错误分支）。"""
    from app.shared.utils.executor import third_party_executor as tp_module
    fake_dispatch = AsyncMock(name='dispatch', side_effect=exc)
    monkeypatch.setattr(tp_module, 'dispatch', fake_dispatch)
    return fake_dispatch

def _patch_endpoint_registry(monkeypatch) -> MagicMock:
    """替换 ``ThirdPartyEndpointRegistry.get_instance`` 为 stub。"""
    from app.shared.utils.executor.endpoints import ThirdPartyEndpoint, ThirdPartyEndpointRegistry
    from app.shared.utils.executor.errors import ERR_CONFIG_MISSING
    fake_ep = MagicMock(name='ThirdPartyEndpoint', spec=ThirdPartyEndpoint)
    fake_ep.name = 'primary'
    fake_registry = MagicMock(name='ThirdPartyEndpointRegistry')
    fake_registry.get = MagicMock(return_value=fake_ep)
    fake_registry.names = MagicMock(return_value=['primary'])
    monkeypatch.setattr(ThirdPartyEndpointRegistry, 'get_instance', classmethod(lambda cls: fake_registry))
    return fake_registry

def test_execute_command_uses_paramiko_when_ctx_flag_missing(monkeypatch):
    """runtime.context 缺少 use_third_party_executor 时,走本地 Paramiko 分支。"""
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.100', 'port': 22, 'username': 'rootuser', 'password': 'secret-pwd', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo ']}
    _patch_service(monkeypatch, cfg)
    fake_client = MagicMock(name='paramiko.SSHClient')
    stdin = MagicMock()
    stdout = MagicMock()
    stderr = MagicMock()
    stdout.read = MagicMock(return_value=b'hello\n')
    stderr.read = MagicMock(return_value=b'')
    stdout.channel.recv_exit_status = MagicMock(return_value=0)
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
    runtime = _build_runtime(business_name='alpha')
    from app.shared.tools.skills.devops.SSHTools import execute_command
    out = _run(execute_command(command='echo hello', business_name='alpha', runtime=runtime))
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('success') is True
    fake_client.exec_command.assert_called_once()
    evt = captured[-1]
    assert 'executor_type' not in evt.metadata

def test_execute_command_uses_paramiko_when_ctx_flag_false(monkeypatch):
    """``use_third_party_executor=False`` 显式走本地。"""
    cfg = {'ip': '10.0.0.101', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo ']}
    _patch_service(monkeypatch, cfg)
    fake_client = MagicMock(name='paramiko.SSHClient')
    stdin = MagicMock()
    stdout = MagicMock()
    stderr = MagicMock()
    stdout.read = MagicMock(return_value=b'hello\n')
    stderr.read = MagicMock(return_value=b'')
    stdout.channel.recv_exit_status = MagicMock(return_value=0)
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
    runtime = _build_runtime(business_name='alpha', extra_context={'use_third_party_executor': False})
    from app.shared.tools.skills.devops.SSHTools import execute_command
    out = _run(execute_command(command='echo hello', business_name='alpha', runtime=runtime))
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('success') is True
    fake_client.exec_command.assert_called_once()

def test_execute_command_uses_third_party_when_ctx_true(monkeypatch):
    """``use_third_party_executor=True`` 时跳过 Paramiko,走第三方 HTTPS 调用。"""
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.200', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo ']}
    _patch_service(monkeypatch, cfg)
    fake_client = MagicMock(name='paramiko.SSHClient')
    fake_client.exec_command = MagicMock()
    fake_client.close = MagicMock()
    fake_paramiko = MagicMock(name='paramiko')
    fake_paramiko.SSHClient = MagicMock(return_value=fake_client)
    fake_paramiko.AutoAddPolicy = MagicMock(return_value=MagicMock())
    import paramiko as real_paramiko
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException
    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, 'paramiko', fake_paramiko, raising=False)
    _patch_endpoint_registry(monkeypatch)
    fake_dispatch = _patch_third_party_dispatch(monkeypatch, return_value={'success': True, 'output': 'third-party-out', 'exit_code': 0})
    runtime = _build_runtime(business_name='alpha', extra_context={'use_third_party_executor': True, 'third_party_endpoint_name': 'primary'})
    from app.shared.tools.skills.devops.SSHTools import execute_command
    out = _run(execute_command(command='echo hello', business_name='alpha', runtime=runtime))
    payload = json.loads(out.update['messages'][0].content)
    assert payload == {'success': True, 'output': 'third-party-out', 'exit_code': 0}
    fake_client.exec_command.assert_not_called()
    fake_dispatch.assert_awaited_once()
    call_kwargs = fake_dispatch.call_args.kwargs
    assert call_kwargs['endpoint_name'] == 'primary'
    assert call_kwargs['command'] == 'echo hello'
    assert call_kwargs['business_name'] == 'alpha'
    assert call_kwargs['server_type'] == 'linux'
    evt = captured[-1]
    assert evt.metadata['executor_type'] == 'third_party'
    assert evt.metadata['third_party_endpoint'] == 'primary'
    assert evt.metadata['decision'] == 'executed'
    assert str(evt.result) == 'success'

def test_execute_command_third_party_default_endpoint(monkeypatch):
    """``third_party_endpoint_name`` 缺失时,使用 ``settings.third_party_executor.default_endpoint``。"""
    import importlib
    cfg = {'ip': '10.0.0.201', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['ls']}
    _patch_service(monkeypatch, cfg)
    fake_paramiko = MagicMock(name='paramiko')
    fake_paramiko.SSHClient = MagicMock()
    fake_paramiko.AutoAddPolicy = MagicMock()
    import paramiko as real_paramiko
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException
    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, 'paramiko', fake_paramiko, raising=False)
    _patch_endpoint_registry(monkeypatch)
    fake_dispatch = _patch_third_party_dispatch(monkeypatch, return_value={'success': True, 'output': 'ok', 'exit_code': 0})
    runtime = _build_runtime(business_name='alpha', extra_context={'use_third_party_executor': True})
    settings_module = importlib.import_module('app.core.config.settings')
    settings_obj = settings_module.settings
    monkeypatch.setattr(settings_obj.third_party_executor, 'default_endpoint', 'primary', raising=False)
    from app.shared.tools.skills.devops.SSHTools import execute_command
    out = _run(execute_command(command='ls', business_name='alpha', runtime=runtime))
    assert out.update['messages']
    assert fake_dispatch.call_args.kwargs['endpoint_name'] == 'primary'

def test_execute_command_third_party_blacklist_still_blocks(monkeypatch):
    """第三方分支前,黑名单仍生效(不调第三方)。"""
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.202', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': ['^rm\\s+-rf'], 'whitelist': ['rm -rf /tmp/x']}
    _patch_service(monkeypatch, cfg)
    fake_paramiko = MagicMock(name='paramiko')
    fake_paramiko.SSHClient = MagicMock()
    fake_paramiko.AutoAddPolicy = MagicMock()
    import paramiko as real_paramiko
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException
    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, 'paramiko', fake_paramiko, raising=False)
    _patch_endpoint_registry(monkeypatch)
    fake_dispatch = _patch_third_party_dispatch(monkeypatch, return_value={'success': True})
    runtime = _build_runtime(business_name='gamma', extra_context={'use_third_party_executor': True})
    from app.shared.tools.skills.devops.SSHTools import execute_command
    out = _run(execute_command(command='rm -rf /tmp/x', business_name='gamma', runtime=runtime))
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('blocked') is True
    assert payload.get('success') is False
    fake_dispatch.assert_not_awaited()

def test_execute_command_third_party_http_error_returns_failure(monkeypatch):
    """第三方返回 HTTP 错误 → success=False + 审计日志 error_code=third_party_http_error。"""
    from app.shared.utils.executor.errors import ERR_HTTP, ThirdPartyExecutorError
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.203', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['ls']}
    _patch_service(monkeypatch, cfg)
    fake_paramiko = MagicMock(name='paramiko')
    fake_paramiko.SSHClient = MagicMock()
    fake_paramiko.AutoAddPolicy = MagicMock()
    import paramiko as real_paramiko
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException
    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, 'paramiko', fake_paramiko, raising=False)
    _patch_endpoint_registry(monkeypatch)
    fake_dispatch = _patch_third_party_dispatch_with_error(monkeypatch, ThirdPartyExecutorError(error_code=ERR_HTTP, reason='第三方返回 HTTP 503', user_message='第三方调用失败'))
    runtime = _build_runtime(business_name='alpha', extra_context={'use_third_party_executor': True})
    from app.shared.tools.skills.devops.SSHTools import execute_command
    out = _run(execute_command(command='ls', business_name='alpha', runtime=runtime))
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('success') is False
    assert payload.get('error') == '第三方调用失败'
    evt = captured[-1]
    assert str(evt.result) == 'failure'
    assert evt.metadata['error_code'] == 'third_party_http_error'
    assert evt.metadata['executor_type'] == 'third_party'

def test_execute_command_third_party_timeout_returns_failure(monkeypatch):
    """第三方超时 → ``error_code=third_party_timeout``。"""
    from app.shared.utils.executor.errors import ERR_TIMEOUT, ThirdPartyExecutorError
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.204', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['ls']}
    _patch_service(monkeypatch, cfg)
    fake_paramiko = MagicMock(name='paramiko')
    fake_paramiko.SSHClient = MagicMock()
    fake_paramiko.AutoAddPolicy = MagicMock()
    import paramiko as real_paramiko
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException
    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, 'paramiko', fake_paramiko, raising=False)
    _patch_endpoint_registry(monkeypatch)
    fake_dispatch = _patch_third_party_dispatch_with_error(monkeypatch, ThirdPartyExecutorError(error_code=ERR_TIMEOUT, reason='第三方调用超时', user_message='第三方执行超时'))
    runtime = _build_runtime(business_name='alpha', extra_context={'use_third_party_executor': True})
    from app.shared.tools.skills.devops.SSHTools import execute_command
    out = _run(execute_command(command='ls', business_name='alpha', runtime=runtime))
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('success') is False
    assert payload.get('error') == '第三方执行超时'
    evt = captured[-1]
    assert evt.metadata['error_code'] == 'third_party_timeout'

def test_execute_command_third_party_config_missing(monkeypatch):
    """端点未配置 → ``error_code=third_party_config_missing``。"""
    from app.shared.utils.executor.errors import ERR_CONFIG_MISSING, ThirdPartyExecutorError
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.205', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['ls']}
    _patch_service(monkeypatch, cfg)
    fake_paramiko = MagicMock(name='paramiko')
    fake_paramiko.SSHClient = MagicMock()
    fake_paramiko.AutoAddPolicy = MagicMock()
    import paramiko as real_paramiko
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException
    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, 'paramiko', fake_paramiko, raising=False)
    fake_dispatch = _patch_third_party_dispatch_with_error(monkeypatch, ThirdPartyExecutorError(error_code=ERR_CONFIG_MISSING, reason="third_party endpoint 'primary' 未配置", user_message='第三方端点 primary 未配置'))
    runtime = _build_runtime(business_name='alpha', extra_context={'use_third_party_executor': True})
    from app.shared.tools.skills.devops.SSHTools import execute_command
    out = _run(execute_command(command='ls', business_name='alpha', runtime=runtime))
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('success') is False
    assert '未配置' in payload.get('error', '')
    evt = captured[-1]
    assert evt.metadata['error_code'] == 'third_party_config_missing'

def test_execute_command_third_party_unexpected_exception(monkeypatch):
    """dispatch 抛非 ``ThirdPartyExecutorError`` → 归类为 ``third_party_unexpected_error``。"""
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.206', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['ls']}
    _patch_service(monkeypatch, cfg)
    fake_paramiko = MagicMock(name='paramiko')
    fake_paramiko.SSHClient = MagicMock()
    fake_paramiko.AutoAddPolicy = MagicMock()
    import paramiko as real_paramiko
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException
    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, 'paramiko', fake_paramiko, raising=False)
    _patch_endpoint_registry(monkeypatch)
    fake_dispatch = _patch_third_party_dispatch_with_error(monkeypatch, RuntimeError('unexpected boom'))
    runtime = _build_runtime(business_name='alpha', extra_context={'use_third_party_executor': True})
    from app.shared.tools.skills.devops.SSHTools import execute_command
    out = _run(execute_command(command='ls', business_name='alpha', runtime=runtime))
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('success') is False
    assert payload.get('error') == '第三方调用异常'
    evt = captured[-1]
    assert evt.metadata['error_code'] == 'third_party_unexpected_error'

def test_execute_command_third_party_passes_business_name_to_config_resolution(monkeypatch):
    """即使走第三方分支,_resolve_server_config 仍按 business_name 解析(用于审计元数据 + 平台派生)。"""
    cfg = {'ip': '10.0.0.207', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'windows', 'blacklist': [], 'whitelist': ['Get-Date']}
    fake_service = _patch_service(monkeypatch, cfg)
    fake_paramiko = MagicMock(name='paramiko')
    fake_paramiko.SSHClient = MagicMock()
    fake_paramiko.AutoAddPolicy = MagicMock()
    import paramiko as real_paramiko
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException
    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, 'paramiko', fake_paramiko, raising=False)
    _patch_endpoint_registry(monkeypatch)
    fake_dispatch = _patch_third_party_dispatch(monkeypatch, return_value={'success': True, 'output': 'ok', 'exit_code': 0})
    runtime = _build_runtime(business_name='winbiz', extra_context={'use_third_party_executor': True})
    from app.shared.tools.skills.devops.SSHTools import execute_command
    _run(execute_command(command='Get-Date', business_name='winbiz', runtime=runtime))
    fake_service.get_connection_config.assert_called_with('winbiz')
    assert fake_dispatch.call_args.kwargs['server_type'] == 'windows'


# ---------------------------------------------------------------------------
# 2026-08-05 新增:回归保护 - SSHTools.execute_command 走第三方分支时,
# 在 LangGraph ToolNode 的 in-flight asyncio loop 内直接 await 调用,
# 不会再触发旧实现的 ``asyncio.run() cannot be called from a running event loop``
# 或 ``run_coroutine_threadsafe(...).result()`` 死锁。
# ---------------------------------------------------------------------------


def test_execute_command_third_party_inside_running_loop_no_runtime_error(monkeypatch):
    """execute_command 第三方分支在 in-flight loop 内直接 await 不抛 RuntimeError。

    回归保护:旧实现在 running loop 内用 ``asyncio.run`` / ``run_coroutine_threadsafe``
    包装异步 dispatch,会触发 RuntimeError 或死锁;改 async def 后直接
    ``await dispatch(...)``,问题消失。

    Args:
        monkeypatch: pytest monkeypatch
    """
    cfg = {'ip': '10.0.0.100', 'port': 22, 'username': 'u', 'password': 'p', 'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo ']}
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

    _patch_endpoint_registry(monkeypatch)
    fake_dispatch = _patch_third_party_dispatch(monkeypatch, return_value={'success': True, 'output': 'tp-in-loop', 'exit_code': 0})

    runtime = _build_runtime(business_name='alpha', extra_context={'use_third_party_executor': True, 'third_party_endpoint_name': 'primary'})

    async def _run_in_loop():
        from app.shared.tools.skills.devops.SSHTools import execute_command
        result = await execute_command(command='echo hi', business_name='alpha', runtime=runtime)
        return result

    out = asyncio.run(_run_in_loop())
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('success') is True
    assert payload.get('output') == 'tp-in-loop'
    fake_dispatch.assert_awaited_once()


# ---------------------------------------------------------------------------
# 2026-08-05 新增:第三方分支审计日志可观测性回归保护。
# 旧实现失败时只写 ``intercept_reason``(如 ``third_party endpoint 'primary' 未配置``),
# 运维无法区分「name 拼错」「JSON 配错」「PEM 非法」「URL 非 https」「enabled=False」等根因。
# 修复后第三方分支失败/成功都会把注册表实际加载的端点摘要写到 metadata.loaded_endpoints。
# ---------------------------------------------------------------------------


def test_execute_command_third_party_logs_loaded_endpoints_on_config_missing(monkeypatch):
    """第三方配置缺失时,日志 metadata 必须含 loaded_endpoints 摘要,方便排查 name 拼错。

    2026-08-05 新增: 修复前运维看日志只能看到 ``third_party endpoint 'X' 未配置``,
    无法分辨「注册表根本没加载到这个 name」(JSON 配错 / PEM 非法 / URL 不合规)
    vs「加载了其他 name」(name 拼错)。修复后 ``loaded_endpoints`` 字段暴露注册表实际状态。

    Args:
        monkeypatch: pytest monkeypatch
    """
    from app.shared.utils.executor.endpoints import (
        ThirdPartyEndpointRegistry,
    )

    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.10', 'port': 22, 'username': 'u', 'password': 'p',
           'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo ']}
    _patch_service(monkeypatch, cfg)

    # 关键: stub 的 registry 实际加载了一个 name='other'(模拟 name 拼错场景)。
    fake_registry = MagicMock(name='ThirdPartyEndpointRegistry')
    fake_registry.diagnostic_summary = MagicMock(
        return_value=[{'name': 'other', 'enabled': True, 'url': 'https://other.example.com'}]
    )
    monkeypatch.setattr(
        ThirdPartyEndpointRegistry,
        'get_instance',
        classmethod(lambda cls: fake_registry),
    )

    # patch dispatch 让其抛 ThirdPartyExecutorError(模拟真实 ERR_CONFIG_MISSING 路径)
    fake_dispatch = _patch_third_party_dispatch_with_error(
        monkeypatch,
        ThirdPartyExecutorError(
            error_code=ERR_CONFIG_MISSING,
            reason="third_party endpoint 'primary' 未配置",
            user_message='第三方端点 primary 未配置',
        ),
    )

    runtime = _build_runtime(
        business_name='alpha',
        extra_context={'use_third_party_executor': True, 'third_party_endpoint_name': 'primary'},
    )

    from app.shared.tools.skills.devops.SSHTools import execute_command
    out = _run(execute_command(command='echo hi', business_name='alpha', runtime=runtime))
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('success') is False

    evt = captured[-1]
    # 核心断言:日志 metadata 暴露 loaded_endpoints + loaded_endpoint_count
    assert evt.metadata['loaded_endpoints'] == [
        {'name': 'other', 'enabled': True, 'url': 'https://other.example.com'}
    ]
    assert evt.metadata['loaded_endpoint_count'] == 1
    assert evt.metadata['third_party_endpoint'] == 'primary'
    assert evt.metadata['error_code'] == 'third_party_config_missing'
    # diagnostic_summary 被调用过
    fake_registry.diagnostic_summary.assert_called_once()


def test_execute_command_third_party_logs_empty_loaded_endpoints_when_registry_invalid(monkeypatch):
    """第三方注册表加载失败(JSON 错 / PEM 非法 / URL 不合规)时,loaded_endpoints=[]。

    2026-08-05 新增: 当所有 endpoint 都因校验失败被 skip 时,运维看日志能看到
    ``loaded_endpoint_count=0``,立即知道问题不是 name 拼错,而是 JSON / PEM / URL 配置。

    Args:
        monkeypatch: pytest monkeypatch
    """
    from app.shared.utils.executor.endpoints import (
        ThirdPartyEndpointRegistry,
    )

    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.11', 'port': 22, 'username': 'u', 'password': 'p',
           'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo ']}
    _patch_service(monkeypatch, cfg)

    # 注册表为空(模拟 JSON/PEM/URL 全校验失败)
    fake_registry = MagicMock(name='ThirdPartyEndpointRegistry')
    fake_registry.diagnostic_summary = MagicMock(return_value=[])
    monkeypatch.setattr(
        ThirdPartyEndpointRegistry,
        'get_instance',
        classmethod(lambda cls: fake_registry),
    )

    _patch_third_party_dispatch_with_error(
        monkeypatch,
        ThirdPartyExecutorError(
            error_code=ERR_CONFIG_MISSING,
            reason="third_party endpoint 'primary' 未配置",
            user_message='第三方端点 primary 未配置',
        ),
    )

    runtime = _build_runtime(
        business_name='alpha',
        extra_context={'use_third_party_executor': True, 'third_party_endpoint_name': 'primary'},
    )

    from app.shared.tools.skills.devops.SSHTools import execute_command
    out = _run(execute_command(command='echo hi', business_name='alpha', runtime=runtime))
    payload = json.loads(out.update['messages'][0].content)
    assert payload.get('success') is False

    evt = captured[-1]
    assert evt.metadata['loaded_endpoints'] == []
    assert evt.metadata['loaded_endpoint_count'] == 0
    assert evt.metadata['error_code'] == 'third_party_config_missing'


def test_execute_command_third_party_logs_loaded_endpoints_on_success(monkeypatch):
    """第三方成功路径也写 loaded_endpoints,运维查"为什么走 default 不是 prod"时能直接看到。

    2026-08-05 新增。

    Args:
        monkeypatch: pytest monkeypatch
    """
    from app.shared.utils.executor.endpoints import (
        ThirdPartyEndpointRegistry,
    )

    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.12', 'port': 22, 'username': 'u', 'password': 'p',
           'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo ']}
    _patch_service(monkeypatch, cfg)

    fake_registry = MagicMock(name='ThirdPartyEndpointRegistry')
    fake_registry.diagnostic_summary = MagicMock(return_value=[
        {'name': 'primary', 'enabled': True, 'url': 'https://primary.example.com'},
        {'name': 'staging', 'enabled': False, 'url': 'https://staging.example.com'},
    ])
    monkeypatch.setattr(
        ThirdPartyEndpointRegistry,
        'get_instance',
        classmethod(lambda cls: fake_registry),
    )

    _patch_third_party_dispatch(
        monkeypatch, return_value={'success': True, 'output': 'ok', 'exit_code': 0},
    )

    runtime = _build_runtime(
        business_name='alpha',
        extra_context={'use_third_party_executor': True, 'third_party_endpoint_name': 'primary'},
    )

    from app.shared.tools.skills.devops.SSHTools import execute_command
    _run(execute_command(command='echo hi', business_name='alpha', runtime=runtime))

    evt = captured[-1]
    assert evt.metadata['executor_type'] == 'third_party'
    assert evt.metadata['loaded_endpoints'] == [
        {'name': 'primary', 'enabled': True, 'url': 'https://primary.example.com'},
        {'name': 'staging', 'enabled': False, 'url': 'https://staging.example.com'},
    ]
    assert evt.metadata['loaded_endpoint_count'] == 2


def test_execute_command_third_party_logged_endpoints_summary_omits_public_key_pem(monkeypatch):
    """loaded_endpoints 摘要必须**不**含 public_key_pem,避免敏感密钥泄漏到审计日志。

    2026-08-05 新增。

    Args:
        monkeypatch: pytest monkeypatch
    """
    from app.shared.utils.executor.endpoints import (
        ThirdPartyEndpointRegistry,
    )

    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {'ip': '10.0.0.13', 'port': 22, 'username': 'u', 'password': 'p',
           'server_type': 'linux', 'blacklist': [], 'whitelist': ['echo ']}
    _patch_service(monkeypatch, cfg)

    fake_registry = MagicMock(name='ThirdPartyEndpointRegistry')
    fake_registry.diagnostic_summary = MagicMock(return_value=[
        {'name': 'primary', 'enabled': True, 'url': 'https://primary.example.com'},
    ])
    monkeypatch.setattr(
        ThirdPartyEndpointRegistry,
        'get_instance',
        classmethod(lambda cls: fake_registry),
    )

    _patch_third_party_dispatch(
        monkeypatch, return_value={'success': True, 'output': 'ok', 'exit_code': 0},
    )

    runtime = _build_runtime(
        business_name='alpha',
        extra_context={'use_third_party_executor': True, 'third_party_endpoint_name': 'primary'},
    )

    from app.shared.tools.skills.devops.SSHTools import execute_command
    _run(execute_command(command='echo hi', business_name='alpha', runtime=runtime))

    evt = captured[-1]
    # 直接 stringify 全 metadata 后 grep,确保 public_key_pem 不会以任何形式出现
    blob = json.dumps(evt.metadata, ensure_ascii=False, default=str)
    assert 'public_key_pem' not in blob
    assert 'BEGIN PUBLIC KEY' not in blob
    assert 'BEGIN PRIVATE KEY' not in blob