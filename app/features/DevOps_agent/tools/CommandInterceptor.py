#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
CommandInterceptor - 命令拦截器模块

该模块实现命令黑名单过滤逻辑，支持精确匹配、前缀匹配和正则匹配。
用于拦截高危命令，防止误操作导致系统损坏。

Date: 2026-03-30
"""

import re
from typing import Tuple, Optional


class CommandInterceptor:
    """
    命令拦截器类

    用于检查命令是否在黑名单中，支持多种匹配模式：
    - 精确匹配：命令完全匹配黑名单项
    - 前缀匹配：命令以黑名单项开头
    - 正则匹配：命令匹配黑名单中的正则表达式

    Attributes:
        _blacklist: 黑名单列表，包含字符串和正则表达式模式
    """

    def __init__(self, blacklist: list[str] = None):
        """
        初始化命令拦截器

        Args:
            blacklist: 黑名单列表，支持普通字符串和正则表达式（以 ^ 开头）
        """
        self._blacklist = blacklist or []
        self._compiled_patterns = []
        self._prefix_patterns = []
        self._exact_patterns = []

        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """编译黑名单模式"""
        for pattern in self._blacklist:
            pattern = pattern.strip()
            if not pattern:
                continue

            # 正则表达式模式（以 ^ 开头或包含正则特殊字符）
            if pattern.startswith("^") or any(c in pattern for c in [".*", "\\s", "\\d", "(?i"]):
                try:
                    self._compiled_patterns.append(re.compile(pattern, re.IGNORECASE))
                except re.error:
                    # 如果编译失败，作为普通字符串处理
                    self._exact_patterns.append(pattern.lower())
            # 前缀匹配模式（以空格结尾）
            elif pattern.endswith(" "):
                self._prefix_patterns.append(pattern.strip().lower())
            # 精确匹配
            else:
                self._exact_patterns.append(pattern.lower())

    def is_allowed(self, command: str) -> Tuple[bool, Optional[str]]:
        """
        检查命令是否允许执行

        Args:
            command: 要检查的命令

        Returns:
            Tuple[bool, Optional[str]]: (是否允许, 拦截原因)
            - 如果允许执行，返回 (True, None)
            - 如果被拦截，返回 (False, 拦截原因)
        """
        if not command or not command.strip():
            return False, "命令不能为空"

        command_lower = command.strip().lower()

        # 1. 精确匹配检查
        for pattern in self._exact_patterns:
            if command_lower == pattern:
                return False, f"命令在黑名单中（精确匹配: {pattern}）"

        # 2. 前缀匹配检查
        for pattern in self._prefix_patterns:
            if command_lower.startswith(pattern):
                return False, f"命令在黑名单中（前缀匹配: {pattern}）"

        # 3. 正则匹配检查
        for compiled_pattern in self._compiled_patterns:
            if compiled_pattern.search(command):
                return False, f"命令在黑名单中（正则匹配: {compiled_pattern.pattern}）"

        return True, None

    def check_and_raise(self, command: str) -> None:
        """
        检查命令，如果被拦截则抛出异常

        Args:
            command: 要检查的命令

        Raises:
            CommandBlockedError: 如果命令被拦截
        """
        is_allowed, reason = self.is_allowed(command)
        if not is_allowed:
            raise CommandBlockedError(f"命令被拦截: {reason}")

    def add_pattern(self, pattern: str) -> None:
        """
        动态添加黑名单模式

        Args:
            pattern: 要添加的黑名单模式
        """
        self._blacklist.append(pattern)
        # 重新编译所有模式
        self._compiled_patterns = []
        self._prefix_patterns = []
        self._exact_patterns = []
        self._compile_patterns()


class CommandBlockedError(Exception):
    """命令被拦截异常"""
    pass
