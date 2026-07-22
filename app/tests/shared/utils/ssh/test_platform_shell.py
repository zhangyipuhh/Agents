# -*- coding:utf-8 -*-
"""全局 SSH helper 的平台包装测试。"""

import pytest

from app.shared.utils.ssh.platform_shell import wrap_script_for_platform


def test_wrap_script_for_platform_linux_preserves_multiline_script():
    """Linux 多行 Bash 脚本应保留换行和命令替换语法。"""
    script = "#!/bin/bash\nVALUE=$(df -P / | tail -1 | awk '{print $5}')\nprintf '%s\\n' \"$VALUE\""

    wrapped = wrap_script_for_platform("linux", script)

    assert wrapped.startswith("/bin/bash -c '")
    assert script.replace("'", "'\\''") in wrapped
    assert "$(df -P /" in wrapped
    assert "\n" in wrapped


def test_wrap_script_for_platform_windows_escapes_double_quotes():
    """Windows PowerShell 脚本应转义双引号并使用 PowerShell。"""
    wrapped = wrap_script_for_platform("windows", 'Write-Output "ok"')

    assert wrapped == 'powershell.exe -Command "Write-Output \\\"ok\\\""'


def test_wrap_script_for_platform_rejects_empty_script():
    """空脚本应在建立 SSH 连接前被拒绝。"""
    with pytest.raises(ValueError, match="script 不能为空"):
        wrap_script_for_platform("linux", "  \n")
