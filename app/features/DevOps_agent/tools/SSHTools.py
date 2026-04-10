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
from langgraph.types import Command, interrupt
from langgraph.config import get_stream_writer

from app.features.DevOps_agent.tools.CommandInterceptor import CommandInterceptor, CommandBlockedError


@tool(description="批量执行多个远程命令。适用于需要执行多个相关命令的场景，如同时检查磁盘、内存、CPU等。")
def execute_batch_commands(
    commands: list[str],
    server_type: str = "linux",
    timeout: int = 30,
    runtime: ToolRuntime = None
) -> Command:
    """
    批量执行多个远程命令

    Args:
        commands: 要执行的命令列表
        server_type: 服务器类型，"linux" 或 "windows"
        timeout: 每个命令执行超时时间（秒）
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
                        tool_call_id=runtime.tool_call_id
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

    # 2. 检查命令黑名单
    blacklist = runtime.context.get("command_blacklist", [])
    interceptor = CommandInterceptor(blacklist)

    blocked_commands = []
    allowed_commands = []
    for i, cmd in enumerate(commands):
        is_allowed, block_reason = interceptor.is_allowed(cmd)
        if not is_allowed:
            blocked_commands.append({
                "index": i,
                "command": cmd,
                "reason": block_reason
            })
        else:
            allowed_commands.append({"index": i, "command": cmd})

    # 如果有命令被拦截，返回拦截信息
    if blocked_commands:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "success": False,
                            "error": "部分命令被拦截",
                            "blocked_commands": blocked_commands,
                            "allowed_commands": [c["command"] for c in allowed_commands]
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )

    # === 人工确认中断 ===
    tool_confirmation = runtime.context.get("tool_confirmation", {})
    require_confirmation = tool_confirmation.get("execute_batch_commands", True)

    if require_confirmation:
        decision = interrupt({
            "type": "batch_confirmation",
            "commands": commands,
            "server_type": server_type,
            "timeout": timeout,
            "message": f"确认在 [{server_type}] 服务器执行以下 {len(commands)} 个命令?",
            "options": {
                "1": "全部执行",
                "2": "全部拒绝",
                "3": "选择性执行",
                "4": "修改命令"
            }
        })

        # 处理用户决策
        if isinstance(decision, dict):
            action = decision.get("action")

            # 用户拒绝全部
            if action == "reject":
                for cmd in commands:
                    _log_command_history(runtime, session_id, cmd, "", False, "User rejected", False)
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                content=json.dumps({
                                    "success": False,
                                    "error": "用户拒绝执行所有命令",
                                    "original_commands": commands,
                                    "user_decision": "rejected"
                                }, ensure_ascii=False),
                                tool_call_id=runtime.tool_call_id
                            )
                        ]
                    }
                )

            # 用户要求修改
            if action == "modify":
                user_feedback = decision.get("feedback", "")
                # 设置跳过下一次确认的标志
                runtime.context["skip_next_confirmation"] = True
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                content=json.dumps({
                                    "success": False,
                                    "error": "用户要求修改命令",
                                    "original_commands": commands,
                                    "user_feedback": user_feedback,
                                    "user_decision": "modify"
                                }, ensure_ascii=False),
                                tool_call_id=runtime.tool_call_id
                            )
                        ]
                    }
                )

            # 用户选择性执行
            if action == "selective":
                selected_indices = decision.get("selected_indices", [])
                commands_to_execute = [commands[i] for i in selected_indices if i < len(commands)]
                if not commands_to_execute:
                    return Command(
                        update={
                            "messages": [
                                ToolMessage(
                                    content=json.dumps({
                                        "success": False,
                                        "error": "用户未选择任何命令执行",
                                        "user_decision": "selective_empty"
                                    }, ensure_ascii=False),
                                    tool_call_id=runtime.tool_call_id
                                )
                            ]
                        }
                    )
                # 继续执行选中的命令
                commands = commands_to_execute

    # 3. 获取或创建 SSH 连接并执行命令
    ssh_client = None
    results = []

    try:
        ssh_client = _get_or_create_ssh_client(runtime, session_id, ssh_config)

        for cmd in commands:
            try:
                # 执行命令
                if server_type.lower() == "windows":
                    escaped_command = cmd.replace('"', '\\"')
                    wrapped_command = f'powershell.exe -Command "{escaped_command}"'
                else:
                    escaped_command = cmd.replace("'", "'\\''")
                    wrapped_command = f"/bin/bash -c '{escaped_command}'"

                stdin, stdout, stderr = ssh_client.exec_command(wrapped_command, timeout=timeout)

                output = stdout.read().decode("utf-8", errors="replace").strip()
                error = stderr.read().decode("utf-8", errors="replace").strip()
                exit_code = stdout.channel.recv_exit_status()
                success = exit_code == 0 and not error

                _log_command_history(runtime, session_id, cmd, output, False, "", success)

                result = {
                    "command": cmd,
                    "success": success,
                    "output": output,
                    "exit_code": exit_code
                }
                if error:
                    result["error"] = error

                results.append(result)

            except Exception as e:
                _log_command_history(runtime, session_id, cmd, "", False, str(e), False)
                results.append({
                    "command": cmd,
                    "success": False,
                    "error": str(e)
                })

        _update_session_info(runtime, session_id, f"batch:{len(commands)}")

        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "success": all(r["success"] for r in results),
                            "results": results,
                            "total": len(results),
                            "succeeded": sum(1 for r in results if r["success"])
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

    except Exception as e:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "success": False,
                            "error": f"批量执行失败: {str(e)}"
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )

    finally:
        pass


@tool(description="在远程服务器执行单个命令。适用于只需要执行一个命令的场景。")
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

    # === 人工确认中断 ===
    tool_confirmation = runtime.context.get("tool_confirmation", {})
    require_confirmation = tool_confirmation.get("execute_command", True)

    if require_confirmation:
        decision = interrupt({
            "type": "command_confirmation",
            "command": command,
            "server_type": server_type,
            "timeout": timeout,
            "message": f"确认在 [{server_type}] 服务器执行此命令?",
            "options": {
                "1": "是，执行命令",
                "2": "否，拒绝执行",
                "3": "其他要求"
            }
        })

        # 处理用户决策
        if isinstance(decision, dict):
            action = decision.get("action")

            # 用户拒绝
            if action == "reject":
                _log_command_history(runtime, session_id, command, "", False, "User rejected", False)
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                content=json.dumps({
                                    "success": False,
                                    "error": "用户拒绝执行此命令",
                                    "original_command": command,
                                    "user_decision": "rejected"
                                }, ensure_ascii=False),
                                tool_call_id=runtime.tool_call_id
                            )
                        ]
                    }
                )

            # 用户要求修改
            if action == "modify":
                user_feedback = decision.get("feedback", "")
                # 设置跳过下一次确认的标志
                runtime.context["skip_next_confirmation"] = True
                _log_command_history(runtime, session_id, command, "", False, f"User requested modification: {user_feedback}", False)
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                content=json.dumps({
                                    "success": False,
                                    "error": "用户要求修改命令",
                                    "original_command": command,
                                    "user_feedback": user_feedback,
                                    "user_decision": "modify"
                                }, ensure_ascii=False),
                                tool_call_id=runtime.tool_call_id
                            )
                        ]
                    }
                )

            # 用户批准 - 继续执行
            if action == "approve":
                pass

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


# ============================================================================
# 工具输出模板示例
# ============================================================================

@tool(description="获取服务器系统日志。返回大量日志文本但不占用主模型上下文。")
def get_system_logs(
    log_type: str = "syslog",
    lines: int = 100,
    runtime: ToolRuntime = None
) -> Command:
    """
    获取服务器系统日志（模板示例）
    
    此函数演示如何返回大量文本数据而不占用主模型 token。
    使用 get_stream_writer 发送数据，使用 Command 返回状态。
    
    统一输出格式：
    {
        "header": {
            "tool_name": "工具名称",
            "tool_call_id": "工具调用ID",
            "timestamp": "时间戳",
            "status": "start|progress|complete|error",
            "version": "1.0"
        },
        "body": {
            "data": "实际数据内容",
            "metadata": {
                "total_lines": 总行数,
                "current_line": 当前行,
                "percentage": 百分比
            }
        },
        "footer": {
            "success": true/false,
            "message": "完成消息",
            "stats": {
                "total": 总数,
                "processed": 已处理数,
                "failed": 失败数
            }
        }
    }
    
    Args:
        log_type: 日志类型 (syslog, auth, kern, etc.)
        lines: 要获取的日志行数
        runtime: 工具运行时上下文
    
    Returns:
        Command: 不包含 messages，只更新 tool_results
    """
    writer = get_stream_writer()
    
    if runtime is None:
        writer({
            "header": {
                "tool_name": "get_system_logs",
                "tool_call_id": "unknown",
                "timestamp": datetime.now().isoformat(),
                "status": "error",
                "version": "1.0"
            },
            "body": {
                "data": None,
                "metadata": {
                    "error": "运行时上下文不能为空"
                }
            },
            "footer": {
                "success": False,
                "message": "运行时上下文不能为空",
                "stats": {
                    "total": 0,
                    "processed": 0,
                    "failed": 1
                }
            }
        })
        
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content="错误：运行时上下文不能为空",
                        tool_call_id="unknown"
                    )
                ],
                "tool_results": {
                    "unknown": {
                        "tool": "get_system_logs",
                        "status": "error",
                        "error": "运行时上下文不能为空"
                    }
                }
            }
        )
    
    tool_call_id = runtime.tool_call_id
    
    # === 1. 发送开始标记（头部） ===
    writer({
        "header": {
            "tool_name": "get_system_logs",
            "tool_call_id": tool_call_id,
            "timestamp": datetime.now().isoformat(),
            "status": "start",
            "version": "1.0"
        },
        "body": {
            "data": None,
            "metadata": {
                "log_type": log_type,
                "requested_lines": lines
            }
        },
        "footer": None
    })
    
    # === 2. 模拟获取日志数据 ===
    session_id = runtime.context.get("session_id", "default")
    ssh_config_str = runtime.context.get("ssh_config")
    
    if not ssh_config_str:
        writer({
            "header": {
                "tool_name": "get_system_logs",
                "tool_call_id": tool_call_id,
                "timestamp": datetime.now().isoformat(),
                "status": "error",
                "version": "1.0"
            },
            "body": {
                "data": None,
                "metadata": {
                    "error": "SSH 配置未找到"
                }
            },
            "footer": {
                "success": False,
                "message": "SSH 配置未找到",
                "stats": {
                    "total": 0,
                    "processed": 0,
                    "failed": 1
                }
            }
        })
        
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content="错误：SSH 配置未找到",
                        tool_call_id=tool_call_id
                    )
                ],
                "tool_results": {
                    tool_call_id: {
                        "tool": "get_system_logs",
                        "status": "error",
                        "error": "SSH 配置未找到"
                    }
                }
            }
        )
    
    try:
        ssh_config = json.loads(ssh_config_str) if isinstance(ssh_config_str, str) else ssh_config_str
    except json.JSONDecodeError as e:
        writer({
            "header": {
                "tool_name": "get_system_logs",
                "tool_call_id": tool_call_id,
                "timestamp": datetime.now().isoformat(),
                "status": "error",
                "version": "1.0"
            },
            "body": {
                "data": None,
                "metadata": {
                    "error": f"SSH 配置解析失败: {str(e)}"
                }
            },
            "footer": {
                "success": False,
                "message": f"SSH 配置解析失败: {str(e)}",
                "stats": {
                    "total": 0,
                    "processed": 0,
                    "failed": 1
                }
            }
        })
        
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"错误：SSH 配置解析失败: {str(e)}",
                        tool_call_id=tool_call_id
                    )
                ],
                "tool_results": {
                    tool_call_id: {
                        "tool": "get_system_logs",
                        "status": "error",
                        "error": f"SSH 配置解析失败: {str(e)}"
                    }
                }
            }
        )
    
    # === 3. 执行命令获取日志 ===
    ssh_client = None
    log_lines = []
    
    try:
        ssh_client = _get_or_create_ssh_client(runtime, session_id, ssh_config)
        
        # 根据日志类型选择命令
        if log_type == "syslog":
            command = f"tail -n {lines} /var/log/syslog"
        elif log_type == "auth":
            command = f"tail -n {lines} /var/log/auth.log"
        elif log_type == "kern":
            command = f"tail -n {lines} /var/log/kern.log"
        else:
            command = f"tail -n {lines} /var/log/{log_type}"
        
        stdin, stdout, stderr = ssh_client.exec_command(command, timeout=30)
        
        output = stdout.read().decode("utf-8", errors="replace").strip()
        error = stderr.read().decode("utf-8", errors="replace").strip()
        
        if error:
            writer({
                "header": {
                    "tool_name": "get_system_logs",
                    "tool_call_id": tool_call_id,
                    "timestamp": datetime.now().isoformat(),
                    "status": "error",
                    "version": "1.0"
                },
                "body": {
                    "data": None,
                    "metadata": {
                        "error": error
                    }
                },
                "footer": {
                    "success": False,
                    "message": f"命令执行失败: {error}",
                    "stats": {
                        "total": 0,
                        "processed": 0,
                        "failed": 1
                    }
                }
            })
            
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=f"错误：命令执行失败",
                            tool_call_id=tool_call_id
                        )
                    ],
                    "tool_results": {
                        tool_call_id: {
                            "tool": "get_system_logs",
                            "status": "error",
                            "error": error
                        }
                    }
                }
            )
        
        # 分行处理
        log_lines = output.split('\n')
        total_lines = len(log_lines)
        
        # === 4. 流式发送日志内容（主体） ===
        # 每次发送 10 行，避免单个消息过大
        batch_size = 10
        for i in range(0, total_lines, batch_size):
            batch = log_lines[i:i + batch_size]
            current_line = min(i + batch_size, total_lines)
            percentage = int((current_line / total_lines) * 100) if total_lines > 0 else 0
            
            writer({
                "header": {
                    "tool_name": "get_system_logs",
                    "tool_call_id": tool_call_id,
                    "timestamp": datetime.now().isoformat(),
                    "status": "progress",
                    "version": "1.0"
                },
                "body": {
                    "data": batch,
                    "metadata": {
                        "total_lines": total_lines,
                        "current_line": current_line,
                        "percentage": percentage,
                        "batch_index": i // batch_size,
                        "batch_size": len(batch)
                    }
                },
                "footer": None
            })
        
        # === 5. 发送完成标记（尾部） ===
        writer({
            "header": {
                "tool_name": "get_system_logs",
                "tool_call_id": tool_call_id,
                "timestamp": datetime.now().isoformat(),
                "status": "complete",
                "version": "1.0"
            },
            "body": {
                "data": None,
                "metadata": {
                    "log_type": log_type,
                    "total_lines": total_lines,
                    "lines_requested": lines
                }
            },
            "footer": {
                "success": True,
                "message": f"成功获取 {total_lines} 行日志",
                "stats": {
                    "total": total_lines,
                    "processed": total_lines,
                    "failed": 0
                }
            }
        })
        
        # === 6. 返回 Command（包含简短的 ToolMessage） ===
        # 关键：使用 ToolMessage 告诉大模型工具执行了什么（简短摘要）
        # 详细数据已通过 get_stream_writer 发送，不占用上下文
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"成功获取 {total_lines} 行 {log_type} 日志",
                        tool_call_id=tool_call_id
                    )
                ],
                "tool_results": {
                    tool_call_id: {
                        "tool": "get_system_logs",
                        "status": "success",
                        "log_type": log_type,
                        "total_lines": total_lines,
                        "summary": f"成功获取 {total_lines} 行 {log_type} 日志"
                    }
                }
            }
        )
    
    except paramiko.AuthenticationException as e:
        writer({
            "header": {
                "tool_name": "get_system_logs",
                "tool_call_id": tool_call_id,
                "timestamp": datetime.now().isoformat(),
                "status": "error",
                "version": "1.0"
            },
            "body": {
                "data": None,
                "metadata": {
                    "error": f"SSH 认证失败: {str(e)}"
                }
            },
            "footer": {
                "success": False,
                "message": f"SSH 认证失败: {str(e)}",
                "stats": {
                    "total": 0,
                    "processed": 0,
                    "failed": 1
                }
            }
        })
        
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"错误：SSH 认证失败",
                        tool_call_id=tool_call_id
                    )
                ],
                "tool_results": {
                    tool_call_id: {
                        "tool": "get_system_logs",
                        "status": "error",
                        "error": f"SSH 认证失败: {str(e)}"
                    }
                }
            }
        )
    
    except Exception as e:
        writer({
            "header": {
                "tool_name": "get_system_logs",
                "tool_call_id": tool_call_id,
                "timestamp": datetime.now().isoformat(),
                "status": "error",
                "version": "1.0"
            },
            "body": {
                "data": None,
                "metadata": {
                    "error": f"获取日志失败: {str(e)}"
                }
            },
            "footer": {
                "success": False,
                "message": f"获取日志失败: {str(e)}",
                "stats": {
                    "total": 0,
                    "processed": 0,
                    "failed": 1
                }
            }
        })
        
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"错误：获取日志失败",
                        tool_call_id=tool_call_id
                    )
                ],
                "tool_results": {
                    tool_call_id: {
                        "tool": "get_system_logs",
                        "status": "error",
                        "error": f"获取日志失败: {str(e)}"
                    }
                }
            }
        )
    
    finally:
        if ssh_client:
            try:
                ssh_client.close()
            except:
                pass
