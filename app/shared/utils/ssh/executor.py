# -*- coding:utf-8 -*-
"""与 LangChain 解耦的 Paramiko SSH 脚本执行器。"""

from dataclasses import dataclass
from typing import Any, List, Mapping

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
      2. 若 UTF-8 解码结果中含 **多个** Unicode 替换符 ``U+FFFD`` (````),
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


def _exec_one(
    client: "paramiko.SSHClient",
    config: Mapping[str, Any],
    script: str,
) -> SSHExecResult:
    """在已连接 client 上执行单段脚本(wrap → exec → 解码 → 收退出码)。

    参数:
        client: 已 connect 的 paramiko SSHClient。
        config: 连接配置(server_type / ssh_timeout)。
        script: 脚本文本。

    返回:
        SSHExecResult
    """
    wrapped = wrap_script_for_platform(config.get("server_type", ""), script)
    safe_timeout = config.get("ssh_timeout") or 30
    stdin, stdout, stderr = client.exec_command(wrapped, timeout=safe_timeout)
    # Windows OpenSSH 默认 shell 在非 PTY 通道下持续等待 stdin,关闭写端无副作用
    stdin.close()
    output = _decode_remote_bytes(stdout.read())
    error = _decode_remote_bytes(stderr.read())
    exit_code = stdout.channel.recv_exit_status()
    return SSHExecResult(
        success=exit_code == 0 and not error,
        stdout=output,
        stderr=error,
        exit_code=exit_code,
    )


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
        timeout: **已废弃**(2026-08-19),保留仅为向后兼容签名;运行时被忽略。

    Returns:
        SSHExecResult: 包含标准输出、标准错误、退出码和成功状态的结果。

    Raises:
        ValueError: 脚本为空。
        paramiko.AuthenticationException: SSH 认证失败。
        paramiko.SSHException: SSH 连接或通道执行失败。
    """
    if not script or not script.strip():
        raise ValueError("script 不能为空")
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
        return _exec_one(client, config, script)
    finally:
        client.close()


def execute_script_batch(
    config: Mapping[str, Any],
    scripts: List[str],
) -> List[SSHExecResult]:
    """单 SSH 连接顺序执行多段巡检脚本(2026-09-16 新增)。

    参数:
        config: 与 ``execute_script`` 同形。
        scripts: 分段脚本文本列表(按执行顺序)。

    返回:
        List[SSHExecResult]: 与 scripts 等长、按序对应;单段 exec 异常折叠为
        ``SSHExecResult(success=False, exit_code=1,
        stderr="executor:Type: msg")`` 并继续后续分段。

    异常:
        paramiko.AuthenticationException / SSHException: connect/鉴权失败
        向上抛(与 ``execute_script`` 语义一致,此时无任何分段结果)。
    """
    safe_connect = clamp_timeout(
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
            timeout=safe_connect,
            auth_timeout=safe_connect,
            banner_timeout=safe_connect,
        )
        results: List[SSHExecResult] = []
        for script in scripts:
            try:
                results.append(_exec_one(client, config, script))
            except Exception as exc:  # noqa: BLE001 - 单段失败不中断后续分段
                results.append(
                    SSHExecResult(
                        success=False,
                        stdout="",
                        stderr=f"executor:{type(exc).__name__}: {exc}",
                        exit_code=1,
                    )
                )
        return results
    finally:
        client.close()
