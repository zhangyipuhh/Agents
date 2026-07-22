# -*- coding:utf-8 -*-
"""全局 SSH helper 的平台包装测试。"""

import base64

import pytest

from app.shared.utils.ssh.platform_shell import (
    _encode_powershell_for_encoded_command,
    wrap_script_for_platform,
)


def test_wrap_script_for_platform_linux_preserves_multiline_script():
    """Linux 多行 Bash 脚本应保留换行和命令替换语法。"""
    script = "#!/bin/bash\nVALUE=$(df -P / | tail -1 | awk '{print $5}')\nprintf '%s\\n' \"$VALUE\""

    wrapped = wrap_script_for_platform("linux", script)

    assert wrapped.startswith("/bin/bash -c '")
    assert script.replace("'", "'\\''") in wrapped
    assert "$(df -P /" in wrapped
    assert "\n" in wrapped


def test_wrap_script_for_platform_windows_uses_encoded_command():
    """Windows PowerShell 脚本应使用 ``-EncodedCommand`` 传递 Base64(UTF-16 LE)编码。

    触发原因（2026-07-22 实测）：测试服务器 56(Windows + PowerShell)在 ``inspection_script``
    多行执行时,原 naive 的 ``powershell.exe -Command "..."`` 包装方式
    在 Windows OpenSSH server 默认 PATH / ExecutionPolicy / 多行转义三因素下
    无法启动 PowerShell 进程,30 秒后 paramiko ``TimeoutError``, ``exit_code=None``。
    修复策略:统一改用 Microsoft 官方推荐的 ``-EncodedCommand``(UTF-16 LE → Base64),
    完全避免 shell quoting / 转义 / 编码问题,并加上 ``-NoProfile -NonInteractive
    -ExecutionPolicy Bypass`` 三个安全 flag。

    参数:
        无。

    返回值:
        None。

    异常:
        AssertionError: 包装产物不符合预期时抛出。
    """
    script = 'Write-Output "ok"'

    wrapped = wrap_script_for_platform("windows", script)

    # 必须使用 powershell.exe + EncodedCommand(而不是 -Command "...")
    assert wrapped.startswith("powershell.exe ")
    assert "-EncodedCommand" in wrapped
    assert "-ExecutionPolicy Bypass" in wrapped
    assert "-NoProfile" in wrapped
    assert "-NonInteractive" in wrapped
    # 不再使用 -Command "..." 的 naive 包装
    assert '-Command "' not in wrapped


def test_wrap_script_for_platform_windows_multiline_script_decodes_correctly():
    """Windows 多行 PowerShell 脚本经 ``-EncodedCommand`` Base64 反解后必须完整还原。

    验证 round-trip:wrap → 截取 Base64 部分 → 解码 → 用户脚本原文完整保留在
    ``Out-String -Width 4096`` 输出收集包装内(规避非 PTY 宿主 80 列硬换行)。

    参数:
        无。

    返回值:
        None。

    异常:
        AssertionError: round-trip 不一致或解码失败时抛出。
    """
    script = (
        "$diskParts = @()\n"
        "Get-PSDrive -PSProvider FileSystem |\n"
        "  Where-Object { $_.Used -ne $null } |\n"
        "  ForEach-Object {\n"
        "    $mount = $_.Root.Replace('\\\\', '\\\\\\\\')\n"
        "  }\n"
        'Write-Output "ok"\n'
    )

    wrapped = wrap_script_for_platform("windows", script)

    # 截取 -EncodedCommand 之后的 Base64 字符串(以第一个空格切分)
    parts = wrapped.split("-EncodedCommand", 1)
    assert len(parts) == 2, wrapped
    encoded_b64 = parts[1].strip()
    decoded = base64.b64decode(encoded_b64).decode("utf-16-le")
    # PowerShell -EncodedCommand 会跳过 UTF-16 LE BOM,直接接脚本内容;
    # 用户脚本原文必须完整保留在输出收集包装内
    assert script in decoded, (
        f"用户脚本未完整保留:\nscript={script!r}\ndecoded={decoded!r}"
    )
    assert decoded.startswith("$__daimon_out = & {\n")
    assert decoded.endswith(
        "} | Out-String -Width 4096\n[Console]::Out.Write($__daimon_out)\n"
    )


def test_wrap_script_for_platform_windows_handles_special_chars():
    """Windows 包装必须正确处理原脚本里的特殊字符(``$`` / ``{`` / ``\\`` / 反引号 / 单引号)。

    旧的 naive 包装会被外层 ``"..."`` 提前求值 ``$variable``、混淆反斜杠。
    ``-EncodedCommand`` 因为整段脚本作为 Base64 整体传入,完全不存在该问题。

    参数:
        无。

    返回值:
        None。

    异常:
        AssertionError: round-trip 失败时抛出。
    """
    script = (
        "$disk = ((Get-PSDrive C).Used / ((Get-PSDrive C).Used + (Get-PSDrive C).Free)) * 100\n"
        "$bootTime = $os.ConvertToDateTime($os.LastBootUpTime)\n"
        "Write-Output '`n$disk=$disk, env=$env:PATH'\n"
    )

    wrapped = wrap_script_for_platform("windows", script)
    parts = wrapped.split("-EncodedCommand", 1)
    encoded_b64 = parts[1].strip()
    decoded = base64.b64decode(encoded_b64).decode("utf-16-le")
    assert script in decoded


def test_wrap_powershell_output_wraps_user_script():
    """``_wrap_powershell_output`` 应把用户脚本包进 Out-String 输出收集包装。

    非控制台宿主(SSH exec 无 PTY)下 ``Write-Output`` 按宿主 80 列硬换行,
    会破坏单行 JSON;包装后由 ``Out-String -Width 4096`` 收集输出,
    再经 ``[Console]::Out.Write`` 原样写出。

    参数:
        无。

    返回值:
        None。

    异常:
        AssertionError: 包装结构不符合预期时抛出。
    """
    from app.shared.utils.ssh.platform_shell import _wrap_powershell_output

    script = "Write-Output '{}'"
    wrapped = _wrap_powershell_output(script)

    assert wrapped.startswith("$__daimon_out = & {\n")
    assert script in wrapped
    assert "Out-String -Width 4096" in wrapped
    assert wrapped.endswith("[Console]::Out.Write($__daimon_out)\n")


def test_wrap_script_for_platform_rejects_empty_script():
    """空脚本应在建立 SSH 连接前被拒绝。"""
    with pytest.raises(ValueError, match="script 不能为空"):
        wrap_script_for_platform("linux", "  \n")


def test_encode_powershell_for_encoded_command_round_trip():
    """``_encode_powershell_for_encoded_command`` 必须输出 UTF-16 LE Base64,反解与原脚本一致。

    参数:
        无。

    返回值:
        None。

    异常:
        AssertionError: 编码 / 反解不一致时抛出。
    """
    script = "Get-Process | Select-Object -First 1\nWrite-Output 'done'\n"
    encoded_b64 = _encode_powershell_for_encoded_command(script)
    # 必须是合法 Base64
    raw = base64.b64decode(encoded_b64, validate=True)
    # 必须是 UTF-16 LE 编码(每字符 2 字节,ASCII 范围内字节模式为 char + 0x00)
    decoded = raw.decode("utf-16-le")
    assert decoded == script
