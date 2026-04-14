#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
安全工具模块

提供 Credential 脱敏和环境变量过滤功能。
借鉴 hermes-agent tools/mcp_tool.py 安全设计。

Date: 2026-04-14
"""

import os
import re
import shutil
from typing import Dict, Optional

logger = __import__("logging").getLogger(__name__)

# Credential 正则模式
_CREDENTIAL_PATTERN = re.compile(
    r"(?:"
    r"ghp_[A-Za-z0-9_]{1,255}"  # GitHub PAT
    r"|sk-[A-Za-z0-9_]{1,255}"  # OpenAI-style key
    r"|Bearer\s+\S+"  # Bearer token
    r"|token=[^\s&,;\"']{1,255}"  # token=...
    r"|key=[^\s&,;\"']{1,255}"  # key=...
    r"|API_KEY=[^\s&,;\"']{1,255}"  # API_KEY=...
    r"|password=[^\s&,;\"']{1,255}"  # password=...
    r"|secret=[^\s&,;\"']{1,255}"  # secret=...
    r")",
    re.IGNORECASE,
)

# 安全环境变量白名单
_SAFE_ENV_KEYS = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LANG",
        "LC_ALL",
        "TERM",
        "SHELL",
        "TMPDIR",
    }
)


def _sanitize_error(text: str) -> str:
    """
    脱敏敏感信息

    将错误信息中的凭证模式替换为 [REDACTED]，防止敏感信息泄露。

    Args:
        text: 原始错误信息

    Returns:
        脱敏后的错误信息
    """
    return _CREDENTIAL_PATTERN.sub("[REDACTED]", text)


def _build_safe_env(user_env: Optional[Dict[str, str]]) -> Dict[str, str]:
    """
    构建安全的环境变量

    只传递白名单环境变量和用户显式配置的变量，
    防止 API Key 等敏感信息泄露到子进程。

    Args:
        user_env: 用户显式配置的环境变量

    Returns:
        过滤后的安全环境变量字典
    """
    env: Dict[str, str] = {}
    for key, value in os.environ.items():
        if key in _SAFE_ENV_KEYS or key.startswith("XDG_"):
            env[key] = value
    if user_env:
        env.update(user_env)
    return env


def _prepend_path(env: Dict[str, str], directory: str) -> Dict[str, str]:
    """
    将目录添加到 PATH 环境变量

    Args:
        env: 环境变量字典
        directory: 要添加的目录

    Returns:
        更新后的环境变量字典
    """
    updated = dict(env or {})
    if not directory:
        return updated

    existing = updated.get("PATH", "")
    parts = [part for part in existing.split(os.pathsep) if part]
    if directory not in parts:
        parts = [directory, *parts]
    updated["PATH"] = os.pathsep.join(parts) if parts else directory
    return updated


def _resolve_stdio_command(
    command: str, env: Dict[str, str]
) -> tuple[str, Dict[str, str]]:
    """
    解析 stdio MCP 命令路径

    解析命令并确保 PATH 包含命令所在目录，
    使 npx/npm/node 等命令能正确执行。

    Args:
        command: 命令字符串
        env: 环境变量字典

    Returns:
        (解析后的命令, 更新后的环境变量)
    """
    resolved_command = os.path.expanduser(str(command).strip())
    resolved_env = dict(env or {})

    if os.sep not in resolved_command:
        path_arg = resolved_env.get("PATH")
        which_hit = shutil.which(resolved_command, path=path_arg)
        if which_hit:
            resolved_command = which_hit
        elif resolved_command in {"npx", "npm", "node"}:
            # 尝试常见位置
            candidates = [
                os.path.join(
                    os.path.expanduser("~"), ".hermes", "node", "bin", resolved_command
                ),
                os.path.join(
                    os.path.expanduser("~"), ".local", "bin", resolved_command
                ),
            ]
            for candidate in candidates:
                if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                    resolved_command = candidate
                    break

    command_dir = os.path.dirname(resolved_command)
    if command_dir:
        resolved_env = _prepend_path(resolved_env, command_dir)

    return resolved_command, resolved_env
