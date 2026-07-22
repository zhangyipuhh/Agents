# -*- coding:utf-8 -*-
"""全局 SSH 执行辅助包。"""

from .executor import SSHExecResult, execute_script
from .platform_shell import wrap_script_for_platform
from .timeout_guard import clamp_timeout

__all__ = [
    "SSHExecResult",
    "clamp_timeout",
    "execute_script",
    "wrap_script_for_platform",
]
