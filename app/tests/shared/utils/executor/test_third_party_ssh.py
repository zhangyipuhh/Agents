# -*- coding:utf-8 -*-
"""``app.shared.utils.executor.third_party_ssh`` 同步薄壳测试。

覆盖目标:
    * 同步执行器把 ``async dispatch`` 包装为同步阻塞函数,返回
      ``SSHExecResult``(与 ``app.shared.utils.ssh.executor.execute_script`` 同形);
    * 缺省端点名走 ``settings.third_party_executor.default_endpoint``;
    * 第三方调用异常封进 ``SSHExecResult(success=False, exit_code=1, stderr=...)``,
      **不**向上抛 —— 与 ``execute_script`` 在 paramiko 异常路径下的行为对齐,
      让 ``server_ops._run_one`` 不必引入"识别异常 vs 非零退出码"的分支。

被测对象:
    * :func:`app.shared.utils.executor.third_party_ssh.execute_third_party_script`

策略:
    * monkeypatch ``app.shared.utils.executor.third_party_executor.dispatch``
      为 ``AsyncMock`` 返回受控响应字典;
    * monkeypatch ``app.core.config.settings.settings.third_party_executor``
      验证端点名解析顺序;
    * monkeypatch ``dispatch`` 抛 ``ThirdPartyExecutorError``,验证返回非零退出码
      而非异常上抛。
"""
from __future__ import annotations

from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.shared.utils.executor.errors import (
    ERR_CONFIG_MISSING,
    ThirdPartyExecutorError,
)
from app.shared.utils.executor.third_party_executor import normalize_response
from app.shared.utils.executor.third_party_ssh import execute_third_party_script
from app.shared.utils.ssh.executor import SSHExecResult


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _patch_dispatch(monkeypatch, return_value: Any) -> AsyncMock:
    """替换 ``app.shared.utils.executor.third_party_executor.dispatch``。

    重要：``execute_third_party_script`` 内部通过 ``from ... import dispatch``
    把 dispatch 读为模块属性,所以 monkeypatch 模块属性即可。
    """
    from app.shared.utils.executor import third_party_executor as tp_module

    fake_dispatch = AsyncMock(name='dispatch', return_value=return_value)
    monkeypatch.setattr(tp_module, 'dispatch', fake_dispatch)
    return fake_dispatch


def _patch_dispatch_with_error(monkeypatch, exc: BaseException) -> AsyncMock:
    """让 dispatch 抛指定异常(用于测试错误分支)。"""
    from app.shared.utils.executor import third_party_executor as tp_module

    fake_dispatch = AsyncMock(name='dispatch', side_effect=exc)
    monkeypatch.setattr(tp_module, 'dispatch', fake_dispatch)
    return fake_dispatch


def _patch_settings(monkeypatch, default_endpoint: str = 'primary') -> MagicMock:
    """替换 ``settings.third_party_executor`` 为轻量 stub,验证端点名解析。"""
    from app.core.config.settings import settings as settings_obj

    fake_cfg = MagicMock(name='third_party_executor')
    fake_cfg.default_endpoint = default_endpoint
    monkeypatch.setattr(settings_obj, 'third_party_executor', fake_cfg)
    return fake_cfg


def _ssh_config(**overrides: Any) -> Dict[str, Any]:
    """构造与 ``ssh.executor.execute_script`` 同形的 config。"""
    base = {
        'ip': '10.0.0.10',
        'port': 22,
        'username': 'rootuser',
        'password': 'secret-pwd',
        'server_type': 'linux',
        'business_name': '业务A-生产',
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# P0 导入 / 存在性
# ---------------------------------------------------------------------------


def test_execute_third_party_script_is_importable() -> None:
    """薄壳入口必须可导入,且函数签名同步。"""
    import inspect

    assert callable(execute_third_party_script)
    sig = inspect.signature(execute_third_party_script)
    params = list(sig.parameters.values())
    assert params[0].name == 'config'
    assert params[1].name == 'script'
    assert params[2].name == 'timeout'
    assert 'endpoint_name' in sig.parameters
    # endpoint_name 是 keyword-only。
    assert sig.parameters['endpoint_name'].kind is inspect.Parameter.KEYWORD_ONLY


# ---------------------------------------------------------------------------
# P1 成功路径
# ---------------------------------------------------------------------------


def test_execute_third_party_script_returns_ssh_exec_result_shape(monkeypatch) -> None:
    """成功路径:dispatch 返回归一化结果,薄壳返回与 execute_script 同形的 SSHExecResult。"""
    _patch_settings(monkeypatch, 'primary')
    fake_response = {
        'success': True,
        'output': 'cpu_used_pct=12.5',
        'exit_code': 0,
    }
    _patch_dispatch(monkeypatch, fake_response)

    result = execute_third_party_script(
        config=_ssh_config(),
        script='echo cpu_used_pct=12.5',
        timeout=30,
        endpoint_name='primary',
    )

    assert isinstance(result, SSHExecResult)
    assert result.success is True
    assert result.stdout == 'cpu_used_pct=12.5'
    assert result.stderr == ''
    assert result.exit_code == 0


def test_execute_third_party_script_passes_endpoint_name_to_dispatch(monkeypatch) -> None:
    """显式 endpoint_name 应透传给 dispatch,空字符串时退回 settings。"""
    _patch_settings(monkeypatch, 'primary')
    captured = _patch_dispatch(
        monkeypatch,
        {'success': True, 'output': 'ok', 'exit_code': 0},
    )
    _ssh_cfg = _ssh_config()

    execute_third_party_script(
        config=_ssh_cfg,
        script='echo ok',
        timeout=30,
        endpoint_name='alt-endpoint',
    )
    # dispatch 是 async 的,被 asyncio.run 驱动;我们只断言它被调用 + 端点名正确。
    assert captured.await_count == 1
    kwargs = captured.await_args.kwargs
    assert kwargs['endpoint_name'] == 'alt-endpoint'
    # ssh_config 子集必须包含 ip/port/username/password。
    assert kwargs['ssh_config']['ip'] == _ssh_cfg['ip']
    assert kwargs['ssh_config']['username'] == _ssh_cfg['username']
    assert kwargs['ssh_config']['password'] == _ssh_cfg['password']
    assert kwargs['business_name'] == _ssh_cfg['business_name']


def test_endpoint_name_falls_back_to_settings_default(monkeypatch) -> None:
    """缺省 / 空字符串 endpoint_name 时使用 settings.third_party_executor.default_endpoint。"""
    fake_cfg = _patch_settings(monkeypatch, 'fallback-name')
    captured = _patch_dispatch(
        monkeypatch,
        {'success': True, 'output': '', 'exit_code': 0},
    )

    # 不传 endpoint_name → 走 settings
    result_a = execute_third_party_script(
        config=_ssh_config(),
        script='echo x',
        timeout=30,
    )
    # 空字符串 endpoint_name → 走 settings
    result_b = execute_third_party_script(
        config=_ssh_config(),
        script='echo x',
        timeout=30,
        endpoint_name='',
    )
    # 全空白字符串 endpoint_name → 走 settings
    result_c = execute_third_party_script(
        config=_ssh_config(),
        script='echo x',
        timeout=30,
        endpoint_name='   ',
    )

    assert captured.await_count == 3
    for call in captured.await_args_list:
        assert call.kwargs['endpoint_name'] == 'fallback-name'
    assert fake_cfg.default_endpoint == 'fallback-name'
    # 三次调用都应得到正常 SSHExecResult。
    assert all(isinstance(r, SSHExecResult) for r in (result_a, result_b, result_c))
    assert all(r.success is True for r in (result_a, result_b, result_c))


# ---------------------------------------------------------------------------
# P1 失败路径:异常必须封进 SSHExecResult,绝不向上抛
# ---------------------------------------------------------------------------


def test_third_party_executor_error_returns_nonzero_exit_no_raise(monkeypatch) -> None:
    """ThirdPartyExecutorError 必须封进 SSHExecResult(success=False, exit_code=1)"""
    _patch_settings(monkeypatch, 'primary')
    exc = ThirdPartyExecutorError(
        error_code=ERR_CONFIG_MISSING,
        reason="third_party endpoint 'primary' 未配置",
        user_message="第三方端点未配置",
    )
    _patch_dispatch_with_error(monkeypatch, exc)

    # 必须不向上抛:函数应当返回 SSHExecResult,而不是抛出 ThirdPartyExecutorError。
    result = execute_third_party_script(
        config=_ssh_config(),
        script='echo x',
        timeout=30,
        endpoint_name='primary',
    )
    assert isinstance(result, SSHExecResult)
    assert result.success is False
    assert result.exit_code == 1
    assert 'third_party' in result.stderr
    # stderr 必须含有原始 reason,便于运维从日志定位。
    assert "未配置" in result.stderr


def test_unexpected_exception_returns_no_raise(monkeypatch) -> None:
    """未预期的非 ThirdPartyExecutorError 同样封进结果,不向上抛。"""
    _patch_settings(monkeypatch, 'primary')
    _patch_dispatch_with_error(monkeypatch, RuntimeError('boom'))

    result = execute_third_party_script(
        config=_ssh_config(),
        script='echo x',
        timeout=30,
        endpoint_name='primary',
    )
    assert result.success is False
    assert result.exit_code == 1
    assert 'unexpected' in result.stderr
    assert 'RuntimeError' in result.stderr


# ---------------------------------------------------------------------------
# P2 边界条件:timeout 钳制 + normalize_response 集成
# ---------------------------------------------------------------------------


def test_timeout_is_clamped_to_valid_range(monkeypatch) -> None:
    """timeout 会被钳制到 [1, 120],传给 dispatch。"""
    _patch_settings(monkeypatch, 'primary')
    captured = _patch_dispatch(
        monkeypatch,
        {'success': True, 'output': '', 'exit_code': 0},
    )
    # 上界 9999 应被钳制到 120;下界 0 应被钳制到 1。
    execute_third_party_script(
        config=_ssh_config(),
        script='echo x',
        timeout=9999,
        endpoint_name='primary',
    )
    execute_third_party_script(
        config=_ssh_config(),
        script='echo x',
        timeout=0,
        endpoint_name='primary',
    )
    assert captured.await_count == 2
    assert captured.await_args_list[0].kwargs['timeout'] == 120
    assert captured.await_args_list[1].kwargs['timeout'] == 1


def test_third_party_response_with_error_field_propagates_to_stderr(monkeypatch) -> None:
    """dispatch 响应 success=False 且含 error 字段时,stderr 必须保留错误信息。"""
    _patch_settings(monkeypatch, 'primary')
    fake_response = {
        'success': False,
        'output': 'partial-output',
        'exit_code': 2,
        'error': '远端命令执行失败(stderr)',
    }
    _patch_dispatch(monkeypatch, fake_response)

    result = execute_third_party_script(
        config=_ssh_config(),
        script='echo x',
        timeout=30,
        endpoint_name='primary',
    )
    assert result.success is False
    assert result.exit_code == 2
    assert result.stdout == 'partial-output'
    # normalize_response 把 error 转写到 payload['error'],薄壳再写到 result.stderr
    assert 'stderr' in result.stderr
