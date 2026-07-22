# -*- coding:utf-8 -*-
"""SSH 命令的平台 Shell 包装。

Windows 巡检脚本通过 SSH 远程执行时,naive 的 ``powershell.exe -Command "..."`` 包装在
多行脚本 + 特殊字符(``$`` / 反斜杠 / 反引号 / 单引号) + Windows OpenSSH 默认受限 PATH +
默认 ExecutionPolicy 多重因素下极不稳定。统一改用 Microsoft 官方推荐的
``-EncodedCommand``(UTF-16 LE → Base64)传参,完全避开 shell quoting / 转义 / 编码问题,
同时附加 ``-NoProfile -NonInteractive -ExecutionPolicy Bypass`` 三个安全 flag 防止
``$PROFILE`` / 交互提示 / 策略拦截。

此外,Windows PowerShell 5.1 在非控制台宿主(SSH exec 无 PTY 通道)下,
``Write-Output`` 经 ``Out-Default`` 格式化时会按宿主缓冲区宽度(默认 80 列)
对长行硬换行(插入 ``\\r\\n``),会破坏单行 JSON 等结构化输出。
统一在编码前把用户脚本包进 ScriptBlock,经 ``Out-String -Width 4096`` 收集输出,
再用 ``[Console]::Out.Write`` 原样写出,彻底规避宿主宽度换行。
"""

import base64


def _encode_powershell_for_encoded_command(script: str) -> str:
    """把 PowerShell 脚本编码为 ``-EncodedCommand`` 期望的 UTF-16 LE Base64 字符串。

    PowerShell ``-EncodedCommand`` 接收 Base64 后先解码为 UTF-16 LE 字节序列,然后跳过
    可选的 UTF-16 LE BOM(``\\xff\\xfe``)直接作为脚本执行。``utf-16-le`` 编码天然不写 BOM,
    与 PowerShell 行为完全对齐。

    参数:
        script: 原始 PowerShell 脚本(任意长度 / 任意字符,允许 ``$`` / 反引号 / 单双引号 /
            反斜杠 / 大括号 / 换行)。

    返回值:
        str: 不含换行的 Base64 字符串,可直接拼接在 ``-EncodedCommand`` 之后通过 SSH
        ``exec_command`` 发送。
    """
    raw = script.encode("utf-16-le")
    return base64.b64encode(raw).decode("ascii")


def _wrap_powershell_output(script: str) -> str:
    """把用户 PowerShell 脚本包进输出收集包装,规避非控制台宿主的 80 列硬换行。

    包装后形态::

        $__daimon_out = & {
        <用户脚本原文>
        } | Out-String -Width 4096
        [Console]::Out.Write($__daimon_out)

    原理:
        * ``& { ... }`` 在用户脚本原有作用域语义下执行,成功流输出被管道捕获;
        * ``Out-String -Width 4096`` 以 4096 列宽度格式化,不再按宿主 80 列换行;
        * ``[Console]::Out.Write`` 绕过 Out-Default 格式化,把文本原样写入 stdout。
        * stderr(Write-Error 等)不经管道,仍走独立错误流,不受影响。

    参数:
        script: 原始 PowerShell 巡检脚本(多行)。

    返回值:
        str: 含输出收集包装的完整 PowerShell 脚本。
    """
    return (
        "$__daimon_out = & {\n"
        + script
        + "\n} | Out-String -Width 4096\n"
        + "[Console]::Out.Write($__daimon_out)\n"
    )


def wrap_script_for_platform(server_type: str, script: str) -> str:
    """将脚本包装为目标平台的 Shell 命令。

    Windows 分支使用 ``powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass
    -EncodedCommand <Base64>``(UTF-16 LE 编码),完全避开 shell quoting / 转义 / 编码问题,
    并在编码前经 ``_wrap_powershell_output`` 包装,规避非 PTY 宿主 80 列硬换行;
    Linux 分支沿用 ``/bin/bash -c '...'(单引号包裹 + 单引号转义)``。

    参数:
        server_type: 目标服务器类型, ``windows`` 使用 PowerShell,其余使用 Bash。
        script: 要执行的脚本文本。

    返回值:
        str: 可传给 Paramiko ``exec_command`` 的完整命令。

    异常:
        ValueError: 脚本为空或不是字符串。
    """
    if not isinstance(script, str) or not script.strip():
        raise ValueError("script 不能为空")
    if (server_type or "").lower() == "windows":
        encoded = _encode_powershell_for_encoded_command(_wrap_powershell_output(script))
        return (
            "powershell.exe -NoProfile -NonInteractive "
            "-ExecutionPolicy Bypass "
            f"-EncodedCommand {encoded}"
        )
    escaped = script.replace("'", "'\\''")
    return f"/bin/bash -c '{escaped}'"
