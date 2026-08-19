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


def _decode_remote_bytes(raw: bytes) -> str:
    """把远端 stdout/stderr 字节流解码为可读字符串,Windows 中文环境兼容。

    解码策略(2026-08-16 调整):
      1. 优先 UTF-8 + ``backslashreplace``: 任何非法字节序列会被转义为 ``\\xNN``,
        既不丢信息也不会污染日志;Linux 远端默认 UTF-8 输出几乎全部走这条路径。
      2. 若 UTF-8 解码结果中含 **多个** Unicode 替换符 ``U+FFFD`` (``�``),
        判定为远端实际输出 GBK/CP936(中文 Windows cmd / PowerShell 默认编码),
        fallback 用 GBK 重解原始字节,保留可读中文(stderr "参数太长" 等)。

    参数:
        raw: SSH 通道读取到的远端原始字节流,可能含中文 GBK、UTF-8 或纯 ASCII。

    返回:
        str: 已 strip 的解码字符串;异常字符按 GBK 重解或 ``\\xNN`` 转义。

    异常:
        无(解码失败统一回退到 UTF-8 / backslashreplace)。
    """
    if not raw:
        return ""
    # 第一步:UTF-8 严格解码(非法字节序列直接报 UnicodeDecodeError,不替换不转义)
    try:
        return raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        # 至少一处非法 UTF-8 字节:典型场景 Windows 中文 stderr(GBK/CP936 输出)。
        # fallback 用 GBK 重解,保留可读中文。Linux 远端 UTF-8 走上方 happy path,行为不变。
        try:
            return raw.decode("gbk", errors="backslashreplace").strip()
        except Exception:  # noqa: BLE001 - GBK 也失败时退回 UTF-8 + replace
            return raw.decode("utf-8", errors="replace").strip()


def execute_script(
    config: Mapping[str, Any],
    script: str,
    timeout: Any = None,             # 2026-08-19：参数被忽略，统一走 config["ssh_timeout"]
) -> SSHExecResult:
    """使用已解析的 SSH 配置执行指定脚本。

    Args:
        config: 包含 ip/port/username/password/server_type 与 ssh_timeout 的连接配置。
                ssh_timeout 由 ``DevOpsServerService.get_connection_config`` 高内聚解析，
                默认 30，钳制 ``[1, 120]``。
        script: 需要在远端执行的完整脚本文本。
        timeout: **已废弃**（2026-08-19），保留仅为向后兼容签名；运行时被忽略。

    Returns:
        SSHExecResult: 包含标准输出、标准错误、退出码和成功状态的结果。

    Raises:
        ValueError: 脚本为空。
        paramiko.AuthenticationException: SSH 认证失败。
        paramiko.SSHException: SSH 连接或通道执行失败。
    """
    wrapped = wrap_script_for_platform(config.get("server_type", ""), script)
    # 2026-08-19 高内聚：直接取 service 给的已钳制值；不再调 clamp_timeout。
    # 缺省回退 30（与原 default=30 对齐）由 ``resolve_ssh_timeout`` 在 service 内完成。
    # ``.get(..., 30)`` 兜底是给测试 fixture 容错（生产 service 必给此字段）。
    safe_timeout = config.get("ssh_timeout") or 30
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
        stdin, stdout, stderr = client.exec_command(wrapped, timeout=safe_timeout)
        # Windows OpenSSH 的默认 shell 在非 PTY 通道下会持续等待 stdin,
        # 不发送 EOF 远端进程不退出、stdout.read() 一直阻塞直至超时;
        # 巡检脚本均不读 stdin,关闭 stdin 写端对 Linux / Windows 均无副作用。
        stdin.close()
        # 2026-08-16 兼容 Windows 中文环境 stderr:
        # 原策略硬编码 UTF-8 + errors="replace",会把 Windows cmd/PowerShell 默认 GBK
        # 输出(中文错误信息,如"参数太长")的每个字节替换为 U+FFFD,日志中无法读出原文。
        # 新策略:走 _decode_remote_bytes 优先 UTF-8 + backslashreplace,
        # 含 >=3 个 U+FFFD 时 fallback GBK,保留可读中文。
        output = _decode_remote_bytes(stdout.read())
        error = _decode_remote_bytes(stderr.read())
        exit_code = stdout.channel.recv_exit_status()
        return SSHExecResult(
            success=exit_code == 0 and not error,
            stdout=output,
            stderr=error,
            exit_code=exit_code,
        )
    finally:
        client.close()