# -*- coding:utf-8 -*-
"""SSH 命令的平台 Shell 包装。"""


def wrap_script_for_platform(server_type: str, script: str) -> str:
    """将脚本包装为目标平台的 Shell 命令。

    Args:
        server_type: 目标服务器类型，``windows`` 使用 PowerShell，其余使用 Bash。
        script: 要执行的脚本文本。

    Returns:
        str: 可传给 Paramiko ``exec_command`` 的完整命令。

    Raises:
        ValueError: 脚本为空或不是字符串。
    """
    if not isinstance(script, str) or not script.strip():
        raise ValueError("script 不能为空")
    if (server_type or "").lower() == "windows":
        escaped = script.replace('"', '\\"')
        return f'powershell.exe -Command "{escaped}"'
    escaped = script.replace("'", "'\\''")
    return f"/bin/bash -c '{escaped}'"
