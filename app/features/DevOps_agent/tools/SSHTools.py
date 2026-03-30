#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
SSHTools - SSH 工具模块

该模块实现 SSH 连接管理和远程命令执行功能。
支持 Linux (bash) 和 Windows (PowerShell) 双平台。

Date: 2026-03-30
"""

import json
import paramiko
from typing import Optional
from datetime import datetime
from langchain.tools import tool, ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from app.features.DevOps_agent.tools.CommandInterceptor import CommandInterceptor, CommandBlockedError


@tool(description="在远程服务器执行命令。Linux 使用 bash 命令，Windows 使用 PowerShell 命令。")
def execute_command(
    command: str,
    server_type: str = "linux",
    timeout: int = 30,
    runtime: ToolRuntime = None
) -> Command:
    """
    在远程服务器执行命令

    Args:
        command: 要执行的命令
        server_type: 服务器类型，"linux" 或 "windows"
        timeout: 命令执行超时时间（秒）
        runtime: 工具运行时上下文

    Returns:
        Command: 包含执行结果的命令对象
    """
    if runtime is None:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "success": False,
                            "error": "运行时上下文不能为空"
                        }, ensure_ascii=False),
                        tool_call_id="unknown"
                    )
                ]
            }
        )

    session_id = runtime.context.get("session_id", "default")

    # 1. 获取 SSH 配置
    ssh_config_str = runtime.context.get("ssh_config")
    if not ssh_config_str:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "success": False,
                            "error": "SSH 配置未找到，请检查配置文件"
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )

    try:
        ssh_config = json.loads(ssh_config_str) if isinstance(ssh_config_str, str) else ssh_config_str
    except json.JSONDecodeError as e:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "success": False,
                            "error": f"SSH 配置解析失败: {str(e)}"
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )

    # 2. 获取命令黑名单并检查
    blacklist = runtime.context.get("command_blacklist", [])
    interceptor = CommandInterceptor(blacklist)

    is_allowed, block_reason = interceptor.is_allowed(command)
    if not is_allowed:
        # 记录被拦截的命令到历史
        _log_command_history(runtime, session_id, command, "", True, block_reason, False)

        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "success": False,
                            "error": f"命令被拦截: {block_reason}",
                            "blocked": True,
                            "block_reason": block_reason
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )

    # 3. 获取或创建 SSH 连接
    ssh_client = None
    try:
        ssh_client = _get_or_create_ssh_client(runtime, session_id, ssh_config)

        # 4. 执行命令
        if server_type.lower() == "windows":
            # Windows PowerShell
            escaped_command = command.replace('"', '\\"')
            wrapped_command = f'powershell.exe -Command "{escaped_command}"'
        else:
            # Linux bash
            escaped_command = command.replace("'", "'\\''")
            wrapped_command = f"/bin/bash -c '{escaped_command}'"

        stdin, stdout, stderr = ssh_client.exec_command(wrapped_command, timeout=timeout)

        # 5. 获取输出
        output = stdout.read().decode("utf-8", errors="replace").strip()
        error = stderr.read().decode("utf-8", errors="replace").strip()

        exit_code = stdout.channel.recv_exit_status()
        success = exit_code == 0 and not error

        # 6. 记录命令历史
        _log_command_history(runtime, session_id, command, output, False, "", success)

        # 7. 更新 SSH 会话信息
        _update_session_info(runtime, session_id, command)

        result = {
            "success": success,
            "output": output,
            "exit_code": exit_code
        }

        if error:
            result["error"] = error

        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps(result, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )

    except CommandBlockedError as e:
        _log_command_history(runtime, session_id, command, "", True, str(e), False)
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "success": False,
                            "error": str(e),
                            "blocked": True
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )

    except paramiko.AuthenticationException as e:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "success": False,
                            "error": f"SSH 认证失败: {str(e)}"
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )

    except paramiko.SSHException as e:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "success": False,
                            "error": f"SSH 连接错误: {str(e)}"
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )

    except TimeoutError as e:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "success": False,
                            "error": f"命令执行超时（{timeout}秒）"
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )

    except Exception as e:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "success": False,
                            "error": f"执行失败: {str(e)}"
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )

    finally:
        # 注意：这里不关闭连接，以便复用
        pass


def _get_or_create_ssh_client(runtime, session_id: str, ssh_config: dict) -> paramiko.SSHClient:
    """
    获取或创建 SSH 客户端连接

    Args:
        runtime: 工具运行时上下文
        session_id: 会话 ID
        ssh_config: SSH 配置

    Returns:
        paramiko.SSHClient: SSH 客户端实例
    """
    # 尝试从 Store 获取现有连接
    namespace = (session_id,)
    session_data = None

    try:
        store_item = runtime.store.get(namespace, "ssh/sessions")
        if store_item and store_item.value:
            session_data = store_item.value
            # 检查连接是否仍然有效
            if session_data.get("transport") and session_data["transport"].is_active():
                return session_data["client"]
    except Exception:
        pass

    # 创建新连接
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    host = ssh_config.get("host")
    username = ssh_config.get("username")
    password = ssh_config.get("password")
    private_key_path = ssh_config.get("private_key_path")
    port = ssh_config.get("port", 22)

    if private_key_path:
        # 使用私钥认证
        private_key = paramiko.RSAKey.from_private_key_file(private_key_path)
        client.connect(hostname=host, port=port, username=username, pkey=private_key)
    else:
        # 使用密码认证
        client.connect(hostname=host, port=port, username=username, password=password)

    # 保存连接到 Store
    session_data = {
        "client": client,
        "transport": client.get_transport(),
        "host": host,
        "username": username,
        "connected_at": datetime.now().isoformat(),
        "last_active_at": datetime.now().isoformat(),
        "command_count": 0
    }

    try:
        runtime.store.put(namespace, "ssh/sessions", session_data)
    except Exception:
        pass

    return client


def _log_command_history(runtime, session_id: str, command: str, output: str,
                         blocked: bool, block_reason: str, success: bool) -> None:
    """
    记录命令执行历史到 Store

    Args:
        runtime: 工具运行时上下文
        session_id: 会话 ID
        command: 执行的命令
        output: 命令输出
        blocked: 是否被拦截
        block_reason: 拦截原因
        success: 是否成功
    """
    namespace = (session_id,)

    try:
        # 获取现有历史
        history_item = runtime.store.get(namespace, "ssh/history")
        history = history_item.value if history_item and history_item.value else []

        # 添加新记录
        history.append({
            "index": len(history) + 1,
            "command": command,
            "output": output[:1000] if output else "",  # 限制输出长度
            "blocked": blocked,
            "block_reason": block_reason,
            "executed_at": datetime.now().isoformat(),
            "success": success
        })

        # 保存历史
        runtime.store.put(namespace, "ssh/history", history)

    except Exception:
        pass


def _update_session_info(runtime, session_id: str, command: str) -> None:
    """
    更新 SSH 会话信息

    Args:
        runtime: 工具运行时上下文
        session_id: 会话 ID
        command: 执行的命令
    """
    namespace = (session_id,)

    try:
        session_item = runtime.store.get(namespace, "ssh/sessions")
        if session_item and session_item.value:
            session_data = session_item.value
            session_data["last_active_at"] = datetime.now().isoformat()
            session_data["command_count"] = session_data.get("command_count", 0) + 1
            runtime.store.put(namespace, "ssh/sessions", session_data)
    except Exception:
        pass
