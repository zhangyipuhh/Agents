# -*- coding:utf-8 -*-
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
import json
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 复用 test_ssh_tools 的 helper（避免重复实现）
# ---------------------------------------------------------------------------


def _build_runtime(
    business_name: str = "alpha",
    session_id: str = "sess-x",
    extra_context: Dict[str, Any] = None,
) -> MagicMock:
    """构造 runtime mock，支持注入额外 context。"""
    runtime = MagicMock(name="ToolRuntime")
    runtime.tool_call_id = "call-tp"
    ctx: Dict[str, Any] = {"business_name": business_name, "session_id": session_id}
    if extra_context:
        ctx.update(extra_context)
    runtime.context = ctx
    return runtime


def _patch_service(monkeypatch, config: Dict[str, Any]) -> MagicMock:
    """替换 DevOpsServerService 单例。"""
    from app.shared.utils.devops_server_service import DevOpsServerService

    fake_service = MagicMock(name="DevOpsServerService")
    fake_service.get_connection_config = MagicMock(return_value=config)
    DevOpsServerService.set_instance(fake_service)
    return fake_service


def _install_capturing_log_service(monkeypatch):
    """捕获 LogService.emit 调用。"""
    captured = []

    def fake_emit(event):
        captured.append(event)
        return True

    fake_svc = MagicMock(name="LogService")
    fake_svc.emit = fake_emit

    monkeypatch.setattr(
        "app.shared.utils.log_service._log_service_singleton", fake_svc, raising=False
    )
    monkeypatch.setattr(
        "app.shared.utils.log_service.get_log_service", lambda: fake_svc, raising=False
    )
    # 关键：SSHTools 顶部 ``from ... import get_log_service`` 会把 get_log_service 名字绑定到
    # log_service 模块在 import 时的对象。monkeypatch 修改模块属性不会改变已绑定名字。
    # 这里同步把 SSHTools 模块内的 ``get_log_service`` 引用替换为 lambda。
    from app.shared.tools.skills.devops import SSHTools as _SSHTools

    monkeypatch.setattr(_SSHTools, "get_log_service", lambda: fake_svc, raising=False)
    return fake_svc, captured


def _patch_third_party_dispatch(monkeypatch, return_value: Any) -> MagicMock:
    """替换 ``app.shared.utils.executor.third_party_executor.dispatch``。

    SSHTools 内部 ``from X import dispatch as _tp_dispatch`` 是函数体内 lazy import，
    每次进入分支都会重新从 ``third_party_executor.dispatch`` 读取当前属性。
    因此只要把 ``tp_module.dispatch`` 替换为 mock，SSHTools 内的新引用就会拿到 mock。
    """
    from app.shared.utils.executor import third_party_executor as tp_module

    fake_dispatch = AsyncMock(name="dispatch", return_value=return_value)
    monkeypatch.setattr(tp_module, "dispatch", fake_dispatch)
    return fake_dispatch


def _patch_third_party_dispatch_with_error(
    monkeypatch, exc: BaseException
) -> MagicMock:
    """让 dispatch 抛指定异常（用于测试错误分支）。"""
    from app.shared.utils.executor import third_party_executor as tp_module

    fake_dispatch = AsyncMock(name="dispatch", side_effect=exc)
    monkeypatch.setattr(tp_module, "dispatch", fake_dispatch)
    return fake_dispatch


def _patch_endpoint_registry(monkeypatch) -> MagicMock:
    """替换 ``ThirdPartyEndpointRegistry.get_instance`` 为 stub。"""
    from app.shared.utils.executor.endpoints import (
        ThirdPartyEndpoint,
        ThirdPartyEndpointRegistry,
    )
    from app.shared.utils.executor.errors import ERR_CONFIG_MISSING

    fake_ep = MagicMock(name="ThirdPartyEndpoint", spec=ThirdPartyEndpoint)
    fake_ep.name = "primary"
    fake_registry = MagicMock(name="ThirdPartyEndpointRegistry")
    fake_registry.get = MagicMock(return_value=fake_ep)
    fake_registry.names = MagicMock(return_value=["primary"])
    monkeypatch.setattr(
        ThirdPartyEndpointRegistry,
        "get_instance",
        classmethod(lambda cls: fake_registry),
    )
    return fake_registry


# ---------------------------------------------------------------------------
# 1. 默认行为：ctx 缺 use_third_party_executor → 走本地 Paramiko
# ---------------------------------------------------------------------------


def test_execute_command_uses_paramiko_when_ctx_flag_missing(monkeypatch):
    """runtime.context 缺少 use_third_party_executor 时,走本地 Paramiko 分支。"""
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {
        "ip": "10.0.0.100",
        "port": 22,
        "username": "rootuser",
        "password": "secret-pwd",
        "server_type": "linux",
        "blacklist": [],
        "whitelist": ["echo "],
    }
    _patch_service(monkeypatch, cfg)
    # patch paramiko
    fake_client = MagicMock(name="paramiko.SSHClient")
    stdin = MagicMock()
    stdout = MagicMock()
    stderr = MagicMock()
    stdout.read = MagicMock(return_value=b"hello\n")
    stderr.read = MagicMock(return_value=b"")
    stdout.channel.recv_exit_status = MagicMock(return_value=0)
    fake_client.exec_command = MagicMock(return_value=(stdin, stdout, stderr))
    fake_client.close = MagicMock(return_value=None)
    fake_paramiko = MagicMock(name="paramiko")
    fake_paramiko.SSHClient = MagicMock(return_value=fake_client)
    fake_paramiko.AutoAddPolicy = MagicMock(return_value=MagicMock())
    import paramiko as real_paramiko
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException
    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, "paramiko", fake_paramiko, raising=False)

    # ctx 中没有 use_third_party_executor
    runtime = _build_runtime(business_name="alpha")

    from app.shared.tools.skills.devops.SSHTools import execute_command

    out = execute_command(command="echo hello", business_name="alpha", runtime=runtime)
    payload = json.loads(out.update["messages"][0].content)
    assert payload.get("success") is True
    # 走本地 → paramiko.exec_command 被调用
    fake_client.exec_command.assert_called_once()
    # 审计日志 metadata 不含 executor_type 字段（保持向后兼容）
    evt = captured[-1]
    assert "executor_type" not in evt.metadata


def test_execute_command_uses_paramiko_when_ctx_flag_false(monkeypatch):
    """``use_third_party_executor=False`` 显式走本地。"""
    cfg = {
        "ip": "10.0.0.101",
        "port": 22,
        "username": "u",
        "password": "p",
        "server_type": "linux",
        "blacklist": [],
        "whitelist": ["echo "],
    }
    _patch_service(monkeypatch, cfg)
    fake_client = MagicMock(name="paramiko.SSHClient")
    stdin = MagicMock()
    stdout = MagicMock()
    stderr = MagicMock()
    stdout.read = MagicMock(return_value=b"hello\n")
    stderr.read = MagicMock(return_value=b"")
    stdout.channel.recv_exit_status = MagicMock(return_value=0)
    fake_client.exec_command = MagicMock(return_value=(stdin, stdout, stderr))
    fake_client.close = MagicMock(return_value=None)
    fake_paramiko = MagicMock(name="paramiko")
    fake_paramiko.SSHClient = MagicMock(return_value=fake_client)
    fake_paramiko.AutoAddPolicy = MagicMock(return_value=MagicMock())
    import paramiko as real_paramiko
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException
    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, "paramiko", fake_paramiko, raising=False)

    runtime = _build_runtime(
        business_name="alpha", extra_context={"use_third_party_executor": False}
    )

    from app.shared.tools.skills.devops.SSHTools import execute_command

    out = execute_command(command="echo hello", business_name="alpha", runtime=runtime)
    payload = json.loads(out.update["messages"][0].content)
    assert payload.get("success") is True
    fake_client.exec_command.assert_called_once()


# ---------------------------------------------------------------------------
# 2. 第三方分支成功路径
# ---------------------------------------------------------------------------


def test_execute_command_uses_third_party_when_ctx_true(monkeypatch):
    """``use_third_party_executor=True`` 时跳过 Paramiko,走第三方 HTTPS 调用。"""
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {
        "ip": "10.0.0.200",
        "port": 22,
        "username": "u",
        "password": "p",
        "server_type": "linux",
        "blacklist": [],
        "whitelist": ["echo "],
    }
    _patch_service(monkeypatch, cfg)
    # patch paramiko（验证不走它）
    fake_client = MagicMock(name="paramiko.SSHClient")
    fake_client.exec_command = MagicMock()
    fake_client.close = MagicMock()
    fake_paramiko = MagicMock(name="paramiko")
    fake_paramiko.SSHClient = MagicMock(return_value=fake_client)
    fake_paramiko.AutoAddPolicy = MagicMock(return_value=MagicMock())
    import paramiko as real_paramiko
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException
    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, "paramiko", fake_paramiko, raising=False)

    _patch_endpoint_registry(monkeypatch)
    fake_dispatch = _patch_third_party_dispatch(
        monkeypatch,
        return_value={"success": True, "output": "third-party-out", "exit_code": 0},
    )

    runtime = _build_runtime(
        business_name="alpha",
        extra_context={"use_third_party_executor": True, "third_party_endpoint_name": "primary"},
    )

    from app.shared.tools.skills.devops.SSHTools import execute_command

    out = execute_command(command="echo hello", business_name="alpha", runtime=runtime)
    payload = json.loads(out.update["messages"][0].content)
    assert payload == {
        "success": True,
        "output": "third-party-out",
        "exit_code": 0,
    }
    # paramiko.exec_command 未被调用
    fake_client.exec_command.assert_not_called()
    # dispatch 被调用一次,带正确参数
    fake_dispatch.assert_awaited_once()
    call_kwargs = fake_dispatch.call_args.kwargs
    assert call_kwargs["endpoint_name"] == "primary"
    assert call_kwargs["command"] == "echo hello"
    assert call_kwargs["business_name"] == "alpha"
    assert call_kwargs["server_type"] == "linux"

    # 审计日志 metadata 含 executor_type='third_party'
    evt = captured[-1]
    assert evt.metadata["executor_type"] == "third_party"
    assert evt.metadata["third_party_endpoint"] == "primary"
    assert evt.metadata["decision"] == "executed"
    assert str(evt.result) == "success"


def test_execute_command_third_party_default_endpoint(monkeypatch):
    """``third_party_endpoint_name`` 缺失时,使用 ``settings.third_party_executor.default_endpoint``。"""
    import importlib

    cfg = {
        "ip": "10.0.0.201",
        "port": 22,
        "username": "u",
        "password": "p",
        "server_type": "linux",
        "blacklist": [],
        "whitelist": ["ls"],
    }
    _patch_service(monkeypatch, cfg)
    fake_paramiko = MagicMock(name="paramiko")
    fake_paramiko.SSHClient = MagicMock()
    fake_paramiko.AutoAddPolicy = MagicMock()
    import paramiko as real_paramiko
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException
    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, "paramiko", fake_paramiko, raising=False)

    _patch_endpoint_registry(monkeypatch)
    fake_dispatch = _patch_third_party_dispatch(
        monkeypatch,
        return_value={"success": True, "output": "ok", "exit_code": 0},
    )

    # 不传 third_party_endpoint_name
    runtime = _build_runtime(
        business_name="alpha",
        extra_context={"use_third_party_executor": True},
    )

    # 把 settings.third_party_executor.default_endpoint 显式设回 "primary"
    settings_module = importlib.import_module("app.core.config.settings")
    settings_obj = settings_module.settings
    monkeypatch.setattr(
        settings_obj.third_party_executor,
        "default_endpoint",
        "primary",
        raising=False,
    )

    from app.shared.tools.skills.devops.SSHTools import execute_command

    out = execute_command(command="ls", business_name="alpha", runtime=runtime)
    assert out.update["messages"]
    # dispatch 接收 endpoint_name 应该是 settings 默认值 "primary"
    assert fake_dispatch.call_args.kwargs["endpoint_name"] == "primary"


def test_execute_command_third_party_blacklist_still_blocks(monkeypatch):
    """第三方分支前,黑名单仍生效(不调第三方)。"""
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {
        "ip": "10.0.0.202",
        "port": 22,
        "username": "u",
        "password": "p",
        "server_type": "linux",
        "blacklist": [r"^rm\s+-rf"],
        "whitelist": ["rm -rf /tmp/x"],
    }
    _patch_service(monkeypatch, cfg)
    fake_paramiko = MagicMock(name="paramiko")
    fake_paramiko.SSHClient = MagicMock()
    fake_paramiko.AutoAddPolicy = MagicMock()
    import paramiko as real_paramiko
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException
    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, "paramiko", fake_paramiko, raising=False)

    _patch_endpoint_registry(monkeypatch)
    fake_dispatch = _patch_third_party_dispatch(
        monkeypatch, return_value={"success": True}
    )

    runtime = _build_runtime(
        business_name="gamma",
        extra_context={"use_third_party_executor": True},
    )

    from app.shared.tools.skills.devops.SSHTools import execute_command

    out = execute_command(command="rm -rf /tmp/x", business_name="gamma", runtime=runtime)
    payload = json.loads(out.update["messages"][0].content)
    assert payload.get("blocked") is True
    assert payload.get("success") is False
    # dispatch 未被调用
    fake_dispatch.assert_not_awaited()


# ---------------------------------------------------------------------------
# 3. 第三方分支失败路径
# ---------------------------------------------------------------------------


def test_execute_command_third_party_http_error_returns_failure(monkeypatch):
    """第三方返回 HTTP 错误 → success=False + 审计日志 error_code=third_party_http_error。"""
    from app.shared.utils.executor.errors import (
        ERR_HTTP,
        ThirdPartyExecutorError,
    )

    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {
        "ip": "10.0.0.203",
        "port": 22,
        "username": "u",
        "password": "p",
        "server_type": "linux",
        "blacklist": [],
        "whitelist": ["ls"],
    }
    _patch_service(monkeypatch, cfg)
    fake_paramiko = MagicMock(name="paramiko")
    fake_paramiko.SSHClient = MagicMock()
    fake_paramiko.AutoAddPolicy = MagicMock()
    import paramiko as real_paramiko
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException
    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, "paramiko", fake_paramiko, raising=False)

    _patch_endpoint_registry(monkeypatch)
    fake_dispatch = _patch_third_party_dispatch_with_error(
        monkeypatch,
        ThirdPartyExecutorError(
            error_code=ERR_HTTP,
            reason="第三方返回 HTTP 503",
            user_message="第三方调用失败",
        ),
    )

    runtime = _build_runtime(
        business_name="alpha",
        extra_context={"use_third_party_executor": True},
    )

    from app.shared.tools.skills.devops.SSHTools import execute_command

    out = execute_command(command="ls", business_name="alpha", runtime=runtime)
    payload = json.loads(out.update["messages"][0].content)
    assert payload.get("success") is False
    assert payload.get("error") == "第三方调用失败"
    # 审计日志
    evt = captured[-1]
    assert str(evt.result) == "failure"
    assert evt.metadata["error_code"] == "third_party_http_error"
    assert evt.metadata["executor_type"] == "third_party"


def test_execute_command_third_party_timeout_returns_failure(monkeypatch):
    """第三方超时 → ``error_code=third_party_timeout``。"""
    from app.shared.utils.executor.errors import (
        ERR_TIMEOUT,
        ThirdPartyExecutorError,
    )

    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {
        "ip": "10.0.0.204",
        "port": 22,
        "username": "u",
        "password": "p",
        "server_type": "linux",
        "blacklist": [],
        "whitelist": ["ls"],
    }
    _patch_service(monkeypatch, cfg)
    fake_paramiko = MagicMock(name="paramiko")
    fake_paramiko.SSHClient = MagicMock()
    fake_paramiko.AutoAddPolicy = MagicMock()
    import paramiko as real_paramiko
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException
    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, "paramiko", fake_paramiko, raising=False)

    _patch_endpoint_registry(monkeypatch)
    fake_dispatch = _patch_third_party_dispatch_with_error(
        monkeypatch,
        ThirdPartyExecutorError(
            error_code=ERR_TIMEOUT,
            reason="第三方调用超时",
            user_message="第三方执行超时",
        ),
    )

    runtime = _build_runtime(
        business_name="alpha",
        extra_context={"use_third_party_executor": True},
    )

    from app.shared.tools.skills.devops.SSHTools import execute_command

    out = execute_command(command="ls", business_name="alpha", runtime=runtime)
    payload = json.loads(out.update["messages"][0].content)
    assert payload.get("success") is False
    assert payload.get("error") == "第三方执行超时"
    evt = captured[-1]
    assert evt.metadata["error_code"] == "third_party_timeout"


def test_execute_command_third_party_config_missing(monkeypatch):
    """端点未配置 → ``error_code=third_party_config_missing``。"""
    from app.shared.utils.executor.errors import (
        ERR_CONFIG_MISSING,
        ThirdPartyExecutorError,
    )

    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {
        "ip": "10.0.0.205",
        "port": 22,
        "username": "u",
        "password": "p",
        "server_type": "linux",
        "blacklist": [],
        "whitelist": ["ls"],
    }
    _patch_service(monkeypatch, cfg)
    fake_paramiko = MagicMock(name="paramiko")
    fake_paramiko.SSHClient = MagicMock()
    fake_paramiko.AutoAddPolicy = MagicMock()
    import paramiko as real_paramiko
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException
    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, "paramiko", fake_paramiko, raising=False)

    fake_dispatch = _patch_third_party_dispatch_with_error(
        monkeypatch,
        ThirdPartyExecutorError(
            error_code=ERR_CONFIG_MISSING,
            reason="third_party endpoint 'primary' 未配置",
            user_message="第三方端点 primary 未配置",
        ),
    )

    runtime = _build_runtime(
        business_name="alpha",
        extra_context={"use_third_party_executor": True},
    )

    from app.shared.tools.skills.devops.SSHTools import execute_command

    out = execute_command(command="ls", business_name="alpha", runtime=runtime)
    payload = json.loads(out.update["messages"][0].content)
    assert payload.get("success") is False
    assert "未配置" in payload.get("error", "")
    evt = captured[-1]
    assert evt.metadata["error_code"] == "third_party_config_missing"


def test_execute_command_third_party_unexpected_exception(monkeypatch):
    """dispatch 抛非 ``ThirdPartyExecutorError`` → 归类为 ``third_party_unexpected_error``。"""
    _, captured = _install_capturing_log_service(monkeypatch)
    cfg = {
        "ip": "10.0.0.206",
        "port": 22,
        "username": "u",
        "password": "p",
        "server_type": "linux",
        "blacklist": [],
        "whitelist": ["ls"],
    }
    _patch_service(monkeypatch, cfg)
    fake_paramiko = MagicMock(name="paramiko")
    fake_paramiko.SSHClient = MagicMock()
    fake_paramiko.AutoAddPolicy = MagicMock()
    import paramiko as real_paramiko
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException
    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, "paramiko", fake_paramiko, raising=False)

    _patch_endpoint_registry(monkeypatch)
    fake_dispatch = _patch_third_party_dispatch_with_error(
        monkeypatch, RuntimeError("unexpected boom")
    )

    runtime = _build_runtime(
        business_name="alpha",
        extra_context={"use_third_party_executor": True},
    )

    from app.shared.tools.skills.devops.SSHTools import execute_command

    out = execute_command(command="ls", business_name="alpha", runtime=runtime)
    payload = json.loads(out.update["messages"][0].content)
    assert payload.get("success") is False
    assert payload.get("error") == "第三方调用异常"
    evt = captured[-1]
    assert evt.metadata["error_code"] == "third_party_unexpected_error"


def test_execute_command_third_party_passes_business_name_to_config_resolution(
    monkeypatch,
):
    """即使走第三方分支,_resolve_server_config 仍按 business_name 解析(用于审计元数据 + 平台派生)。"""
    cfg = {
        "ip": "10.0.0.207",
        "port": 22,
        "username": "u",
        "password": "p",
        "server_type": "windows",  # 验证 server_type 被透传给 dispatch
        "blacklist": [],
        "whitelist": ["Get-Date"],
    }
    fake_service = _patch_service(monkeypatch, cfg)
    fake_paramiko = MagicMock(name="paramiko")
    fake_paramiko.SSHClient = MagicMock()
    fake_paramiko.AutoAddPolicy = MagicMock()
    import paramiko as real_paramiko
    fake_paramiko.AuthenticationException = real_paramiko.AuthenticationException
    fake_paramiko.SSHException = real_paramiko.SSHException
    from app.shared.tools.skills.devops import SSHTools
    monkeypatch.setattr(SSHTools, "paramiko", fake_paramiko, raising=False)

    _patch_endpoint_registry(monkeypatch)
    fake_dispatch = _patch_third_party_dispatch(
        monkeypatch,
        return_value={"success": True, "output": "ok", "exit_code": 0},
    )

    runtime = _build_runtime(
        business_name="winbiz",
        extra_context={"use_third_party_executor": True},
    )

    from app.shared.tools.skills.devops.SSHTools import execute_command

    execute_command(command="Get-Date", business_name="winbiz", runtime=runtime)
    # service.get_connection_config 仍被调用,且参数是 business_name
    fake_service.get_connection_config.assert_called_with("winbiz")
    # dispatch 的 server_type 来自 config → 'windows'
    assert fake_dispatch.call_args.kwargs["server_type"] == "windows"