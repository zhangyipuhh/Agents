# -*- coding:utf-8 -*-
"""与 LangChain 解耦的 Paramiko SSH 脚本执行器。"""

from dataclasses import dataclass
from typing import Any, Mapping

import paramiko

from .platform_shell import wrap_script_for_platform
from .timeout_guard import clamp_timeout


@dataclass(frozen=True)
class SSHExecResult:
    """SSH 脚本执行结果。"""

    success: bool
    stdout: str
    stderr: str
    exit_code: int


def execute_script(
    config: Mapping[str, Any],
    script: str,
    timeout: Any = 30,
) -> SSHExecResult:
    """使用已解析的 SSH 配置执行指定脚本。

    Args:
        config: 包含 ip、port、username、password、server_type 的连接配置。
        script: 需要在远端执行的完整脚本文本。
        timeout: 远程命令执行超时时间，限制在 1 到 120 秒。

    Returns:
        SSHExecResult: 包含标准输出、标准错误、退出码和成功状态的结果。

    Raises:
        ValueError: 脚本为空。
        paramiko.AuthenticationException: SSH 认证失败。
        paramiko.SSHException: SSH 连接或通道执行失败。
    """
    wrapped = wrap_script_for_platform(config.get("server_type", ""), script)
    safe_timeout = clamp_timeout(timeout)
    connect_timeout = clamp_timeout(
        config.get("ssh_connect_timeout"), default=10, lo=1, hi=60
    )
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=config["ip"],
            port=int(config.get("port") or 22),
            username=config["username"],
            password=config["password"],
            timeout=connect_timeout,
            auth_timeout=connect_timeout,
            banner_timeout=connect_timeout,
        )
        _, stdout, stderr = client.exec_command(wrapped, timeout=safe_timeout)
        output = stdout.read().decode("utf-8", errors="replace").strip()
        error = stderr.read().decode("utf-8", errors="replace").strip()
        exit_code = stdout.channel.recv_exit_status()
        return SSHExecResult(
            success=exit_code == 0 and not error,
            stdout=output,
            stderr=error,
            exit_code=exit_code,
        )
    finally:
        client.close()
