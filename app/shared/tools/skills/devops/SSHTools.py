#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
SSHTools - SSH 远程命令执行工具集（2026-07-15 重写）

职责：
    - 通过 ``DevOpsServerService`` 单例获取目标服务器的配置（IP/端口/用户名/密码/类型/名单）
    - 使用 Paramiko 在目标机器执行 SSH 命令
    - 平台派生：Linux → ``/bin/bash -c '...'``；Windows → ``powershell.exe -Command "..."``
    - 决策顺序：黑名单优先（拒绝执行）→ 白名单 allowlist（仅当服务显式配置时启用）
    - 命令批量：任一条命中黑名单 → 整批拒绝（不调用 paramiko）
    - 工具结果不含连接配置（password / ip / username 永不出现在 ToolMessage）

工具清单：
    - execute_command       单条命令执行（Linux/bash 或 Windows/powershell）
    - execute_batch_commands 批量命令执行（任一黑名单命中即整批拒绝）
    - get_system_logs       获取指定类型日志（tail -n <lines> <path>）

注入与发现：
    - 仅使用 ``@tool(description=...)`` 装饰，**不调用** ``register_tool(agent=...)``
    - 工具元数据（module_path / file_path）由 ToolRegistryService 通过源码扫描发现
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import paramiko
from langchain.tools import tool, ToolRuntime
from langgraph.types import Command

try:
    # 生产环境：使用真实 ToolMessage
    from langchain_core.messages import ToolMessage as _RealToolMessage
except Exception:  # noqa: BLE001 - 测试环境被 conftest mock 时降级
    _RealToolMessage = None


def _is_real_tool_message_class(cls) -> bool:
    """判断 ``_RealToolMessage`` 是真实类还是 conftest 注入的 ``Mock``。

    测试环境下 ``conftest.py`` 把 ``langchain_core.messages.ToolMessage = Mock()``
    替换为 Mock，导致 ``from langchain_core.messages import ToolMessage`` 拿到 Mock。
    Mock 对象的 ``.mro``、``__bases__`` 等内省属性都不存在或返回 Mock，
    与真实 ``pydantic.BaseModel`` 子类差异巨大。

    Args:
        cls: 候选类对象

    Returns:
        bool: ``cls`` 是否为真正的 pydantic 类
    """
    if cls is None:
        return False
    try:
        from unittest.mock import Mock as _Mock  # noqa: WPS433 - 局部 import 避免循环

        if isinstance(cls, _Mock):
            return False
    except Exception:  # noqa: BLE001
        pass
    return True


_REAL_TOOL_MESSAGE_OK: bool = _is_real_tool_message_class(_RealToolMessage)

from app.shared.tools.skills.devops.CommandInterceptor import (
    CommandBlockedError,
    CommandInterceptor,
)
from app.shared.utils.devops_server_service import DevOpsServerService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_server_config(
    runtime: ToolRuntime, business_name: Optional[str]
) -> Dict[str, Any]:
    """从 ``DevOpsServerService`` 单例解析指定业务的 SSH 连接配置。

    Args:
        runtime: 工具运行时（用于读取 ``context.business_name`` 兜底）
        business_name: 业务名（优先于 ``runtime.context["business_name"]``）

    Returns:
        Dict[str, Any]: ``ip`` / ``port`` / ``username`` / ``password`` /
        ``server_type`` / ``blacklist`` / ``whitelist``

    Raises:
        RuntimeError: 单例未初始化时抛出
        KeyError: 业务名不存在时抛出
    """
    svc = DevOpsServerService.get_instance()
    name = business_name
    if not name:
        ctx = getattr(runtime, "context", {}) or {}
        name = ctx.get("business_name")
    if not name:
        # 给一个清晰错误：业务名缺失时不让工具失败得莫名其妙
        raise RuntimeError("business_name 缺失（请通过 tool context 注入）")
    return svc.get_connection_config(name)


def _make_interceptor(config: Dict[str, Any]) -> CommandInterceptor:
    """根据服务器配置构造 ``CommandInterceptor``。

    Args:
        config: ``_resolve_server_config`` 的返回值

    Returns:
        CommandInterceptor: 已配好黑/白名单的拦截器
    """
    blacklist = config.get("blacklist") or []
    whitelist = config.get("whitelist")  # 可能是 None / [] / list
    return CommandInterceptor(blacklist=blacklist, whitelist=whitelist)


def _wrap_for_platform(server_type: str, command: str) -> str:
    """按平台派生真正的 shell 调用命令前缀。

    - ``server_type.lower() == "windows"`` →
      ``powershell.exe -Command "<escaped>"``
    - 其他（含 ``linux``） → ``/bin/bash -c '<escaped>'``

    Args:
        server_type: 服务端的 ``server_type`` 字段（来自 service）
        command: 原始用户命令

    Returns:
        str: 已包裹的 shell 调用
    """
    if (server_type or "").lower() == "windows":
        escaped = command.replace('"', '\\"')
        return f'powershell.exe -Command "{escaped}"'
    escaped = command.replace("'", "'\\''")
    return f"/bin/bash -c '{escaped}'"


def _open_client(config: Dict[str, Any]) -> paramiko.SSHClient:
    """打开一个 Paramiko SSHClient 并返回。

    Args:
        config: SSH 连接配置（含明文 password）

    Returns:
        paramiko.SSHClient: 已建立连接的客户端
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=config["ip"],
        port=int(config.get("port") or 22),
        username=config["username"],
        password=config["password"],
    )
    return client


def _make_tool_message(
    tool_call_id: str, content: Any
):
    """构造一个消息对象（生产环境用真实的 ``ToolMessage``，测试环境用 duck-typed）。

    Args:
        tool_call_id: 工具调用 ID
        content: ``dict`` 或 ``str`` 内容

    Returns:
        一个带 ``.content`` 与 ``.tool_call_id`` 属性的对象
    """
    if isinstance(content, dict):
        text = json.dumps(content, ensure_ascii=False)
    else:
        text = str(content)
    if _REAL_TOOL_MESSAGE_OK:
        return _RealToolMessage(content=text, tool_call_id=tool_call_id)  # type: ignore[misc]  # noqa: ERA001 - 真实类已确认

    # 降级：测试环境 conftest 把 ``ToolMessage`` mock 为 MagicMock，
    # 实际构造出来的对象 ``.content`` 也是 Mock。为此提供 duck-typed 实现：
    class _DuckMessage:
        """简易消息载体，提供 ``content`` 与 ``tool_call_id`` 属性。"""

        def __init__(self, content: str, tool_call_id: str) -> None:
            self.content = content
            self.tool_call_id = tool_call_id

        def __repr__(self) -> str:
            return f"<_DuckMessage tool_call_id={self.tool_call_id!r} content={self.content[:80]!r}>"

    return _DuckMessage(text, tool_call_id)


# ---------------------------------------------------------------------------
# Tool: execute_command
# ---------------------------------------------------------------------------


@tool(description="在已配置的远程服务器上执行单条命令（Linux/bash 或 Windows/powershell）。")
def execute_command(
    command: str,
    business_name: Optional[str] = None,
    timeout: int = 30,
    runtime: ToolRuntime = None,
) -> Command:
    """在远程服务器执行单条命令。

    步骤：
      1) 通过 ``DevOpsServerService`` 取连接配置（**忽略调用方传入的 server_type**）
      2) ``CommandInterceptor`` 黑名单优先 → 白名单 allowlist
      3) 平台派生并通过 paramiko.exec_command 执行
      4) 把执行结果（无敏感字段）封装为 ``ToolMessage`` 返回 Command

    Args:
        command: 待执行的命令字符串
        business_name: 业务名（可选；缺省时读 ``runtime.context["business_name"]``）
        timeout: 命令执行超时（秒）
        runtime: LangChain ToolRuntime（langchain runtime 自动注入）

    Returns:
        Command: 包含 messages 的 LangChain 命令对象
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    try:
        config = _resolve_server_config(runtime, business_name)
    except (RuntimeError, KeyError):
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": "无法解析服务器配置"},
                    )
                ]
            }
        )

    interceptor = _make_interceptor(config)
    try:
        interceptor.check_and_raise(command)
    except CommandBlockedError as e:
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {
                            "success": False,
                            "error": f"命令被拦截: {e}",
                            "blocked": True,
                        },
                    )
                ]
            }
        )

    # 平台派生（service 决定 platform）
    wrapped = _wrap_for_platform(config["server_type"], command)
    client = None
    try:
        client = _open_client(config)
        stdin, stdout, stderr = client.exec_command(wrapped, timeout=timeout)
        output = stdout.read().decode("utf-8", errors="replace").strip()
        err = stderr.read().decode("utf-8", errors="replace").strip()
        exit_code = stdout.channel.recv_exit_status()
        success = exit_code == 0 and not err
        payload: Dict[str, Any] = {
            "success": success,
            "output": output,
            "exit_code": exit_code,
        }
        if err:
            payload["error"] = err
        return Command(
            update={"messages": [_make_tool_message(tool_call_id, payload)]}
        )
    except paramiko.AuthenticationException:
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": "SSH 认证失败"},
                    )
                ]
            }
        )
    except paramiko.SSHException:
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": "SSH 连接错误"},
                    )
                ]
            }
        )
    except Exception:  # noqa: BLE001 - 捕获所有并以通用错误返回，避免泄漏 IP/凭据
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": "远程命令执行失败"},
                    )
                ]
            }
        )
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Tool: execute_batch_commands
# ---------------------------------------------------------------------------


@tool(description="在已配置的远程服务器上批量执行多条命令；任何一条被策略拦截即整批拒绝。")
def execute_batch_commands(
    commands: List[str],
    business_name: Optional[str] = None,
    timeout: int = 30,
    runtime: ToolRuntime = None,
) -> Command:
    """批量执行多条 SSH 命令。

    策略：
      - 任一命令被黑名单拦截 → 整个 batch 拒绝（不调 paramiko）
      - 全部通过 → 按顺序执行

    Args:
        commands: 命令字符串列表
        business_name: 业务名
        timeout: 单条命令超时（秒）
        runtime: LangChain ToolRuntime

    Returns:
        Command: 含 messages 的 LangChain 命令对象
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    try:
        config = _resolve_server_config(runtime, business_name)
    except (RuntimeError, KeyError):
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": "无法解析服务器配置"},
                    )
                ]
            }
        )

    interceptor = _make_interceptor(config)

    # 先做拦截；任一被拦 → 整批拒绝
    blocked: List[Dict[str, Any]] = []
    allowed_cmds: List[str] = []
    for idx, cmd in enumerate(commands):
        is_allowed, reason = interceptor.is_allowed(cmd)
        if not is_allowed:
            blocked.append({"index": idx, "command": cmd, "reason": reason})
        else:
            allowed_cmds.append(cmd)
    if blocked:
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {
                            "success": False,
                            "error": "部分命令被拦截",
                            "blocked_commands": blocked,
                        },
                    )
                ]
            }
        )

    # 全部通过；按顺序执行
    results: List[Dict[str, Any]] = []
    client = None
    try:
        client = _open_client(config)
        for cmd in allowed_cmds:
            wrapped = _wrap_for_platform(config["server_type"], cmd)
            try:
                stdin, stdout, stderr = client.exec_command(wrapped, timeout=timeout)
                output = stdout.read().decode("utf-8", errors="replace").strip()
                err = stderr.read().decode("utf-8", errors="replace").strip()
                exit_code = stdout.channel.recv_exit_status()
                success = exit_code == 0 and not err
                item: Dict[str, Any] = {
                    "command": cmd,
                    "success": success,
                    "output": output,
                    "exit_code": exit_code,
                }
                if err:
                    item["error"] = err
                results.append(item)
            except Exception:  # noqa: BLE001 - 单条出错不影响其他条；不携带异常字符串避免凭据泄漏
                results.append(
                    {"command": cmd, "success": False, "error": "执行失败"}
                )

        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {
                            "success": all(r.get("success") for r in results),
                            "results": results,
                            "total": len(results),
                            "succeeded": sum(1 for r in results if r.get("success")),
                        },
                    )
                ]
            }
        )
    except paramiko.AuthenticationException:
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": "SSH 认证失败"},
                    )
                ]
            }
        )
    except paramiko.SSHException:
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": "SSH 连接错误"},
                    )
                ]
            }
        )
    except Exception:  # noqa: BLE001 - 通用错误，避免泄漏 IP/凭据
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": "批量远程命令执行失败"},
                    )
                ]
            }
        )
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Tool: get_system_logs
# ---------------------------------------------------------------------------


@tool(description="获取远程服务器系统日志（tail）。返回成功摘要，不含连接配置。")
def get_system_logs(
    business_name: Optional[str] = None,
    log_type: str = "syslog",
    lines: int = 100,
    runtime: ToolRuntime = None,
) -> Command:
    """获取服务器系统日志。

    内部命令 ``tail -n <lines> <path>`` 同样走 ``CommandInterceptor`` 检查。

    Args:
        business_name: 业务名
        log_type: 日志类型（syslog / auth / kern / 其他）
        lines: 行数
        runtime: LangChain ToolRuntime

    Returns:
        Command: 含 messages 的 LangChain 命令对象
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    try:
        config = _resolve_server_config(runtime, business_name)
    except (RuntimeError, KeyError):
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": "无法解析服务器配置"},
                    )
                ]
            }
        )

    # 派生内部命令：Linux 走 tail，Windows 走 PowerShell Get-WinEvent
    server_type = (config.get("server_type") or "linux").lower()
    if server_type == "windows":
        # Windows：PowerShell Get-WinEvent；常见日志名 LogName 映射
        win_log_map = {
            "system": "System",
            "application": "Application",
            "security": "Security",
            "setup": "Setup",
        }
        log_name = win_log_map.get(log_type.lower(), log_type)
        # PowerShell 内部命令（不含外层 powershell.exe 包裹，由 _wrap_for_platform 注入）
        inner_cmd = (
            f"Get-WinEvent -LogName {log_name} -MaxEvents {int(lines)} "
            f"| Select-Object TimeCreated,Message | Format-Table -AutoSize | Out-String"
        )
    else:
        if log_type == "syslog":
            path = "/var/log/syslog"
        elif log_type == "auth":
            path = "/var/log/auth.log"
        elif log_type == "kern":
            path = "/var/log/kern.log"
        else:
            path = f"/var/log/{log_type}"
        inner_cmd = f"tail -n {int(lines)} {path}"

    interceptor = _make_interceptor(config)
    try:
        interceptor.check_and_raise(inner_cmd)
    except CommandBlockedError as e:
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {
                            "success": False,
                            "error": f"内部命令被拦截: {e}",
                            "blocked": True,
                        },
                    )
                ]
            }
        )

    client = None
    try:
        client = _open_client(config)
        wrapped = _wrap_for_platform(config["server_type"], inner_cmd)
        stdin, stdout, stderr = client.exec_command(wrapped, timeout=30)
        output = stdout.read().decode("utf-8", errors="replace").strip()
        err = stderr.read().decode("utf-8", errors="replace").strip()
        exit_code = stdout.channel.recv_exit_status()
        if err and exit_code != 0:
            return Command(
                update={
                    "messages": [
                        _make_tool_message(
                            tool_call_id,
                            {
                                "success": False,
                                "error": err or "日志获取失败",
                            },
                        )
                    ]
                }
            )
        # 统计行数 & 返回摘要；不外泄连接配置
        log_lines = output.split("\n") if output else []
        total = len(log_lines)
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {
                            "success": True,
                            "log_type": log_type,
                            "total_lines": total,
                            "lines_requested": int(lines),
                            "summary": f"成功获取 {total} 行 {log_type} 日志",
                        },
                    )
                ]
            }
        )
    except Exception:  # noqa: BLE001 - 通用错误，避免泄漏 IP/凭据
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": "获取日志失败"},
                    )
                ]
            }
        )
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
