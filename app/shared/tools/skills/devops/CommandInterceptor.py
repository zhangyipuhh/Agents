#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
CommandInterceptor - 命令策略过滤器（2026-07-15 重写）

职责：
    - 接收黑名单与白名单，提供 ``is_allowed(command) -> (allowed, reason)``
    - 支持三种匹配模式：
        * 精确匹配（条目无尾空格、无正则特征）
        * 前缀匹配（条目末尾带空格；用于 ``ls `` → 匹配 ``ls -l``）
        * 正则匹配（条目以 ``^`` 开头或包含 ``.*`` ``\\s`` ``\\d`` ``(?i`` 等）
    - 黑名单优先于白名单（即 blacklist 命中后即使 whitelist 命中也应拒绝）
    - 空命令直接拒绝
    - 白名单语义：空列表 → 拒绝所有非空命令；命中 → 允许；未命中 → 拒绝

设计要点：
    - 命令大小写不敏感（统一 ``.lower()``）
    - 前缀匹配修复：旧实现在 ``pattern.strip().lower()`` 后会丢失原始的
      「尾部带空格」语义，导致 ``ls`` 与 ``ls `` 在 _prefix_patterns 中
      被等同存储。新实现严格保留原始尾空格：带尾空格才进入前缀列表。
    - 同时维护 blacklist 与 whitelist 两套独立模式；调用前先比黑再比白。
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple


class CommandBlockedError(Exception):
    """命令被策略拦截时抛出的异常。"""

    pass


class CommandInterceptor:
    """命令策略过滤器。

    Attributes:
        _blacklist_raw: 原始黑名单字符串列表
        _whitelist_raw: 原始白名单字符串列表
        _blacklist_exact: 黑名单精确匹配集（小写）
        _blacklist_prefix: 黑名单前缀模式（原始尾空格被保留）
        _blacklist_regex: 黑名单已编译正则列表
        _whitelist_exact: 白名单精确匹配集（小写）
        _whitelist_prefix: 白名单前缀模式（原始尾空格被保留）
        _whitelist_regex: 白名单已编译正则列表（保留以便未来扩展）
    """

    def __init__(
        self,
        blacklist: Optional[List[str]] = None,
        whitelist: Optional[List[str]] = None,
    ) -> None:
        """构造拦截器。

        Args:
            blacklist: 黑名单条目列表，支持字符串（精确 / 前缀 / 正则）。
                传 ``None`` 等价于 ``[]``。
            whitelist: 白名单条目列表。
                强白名单契约：``whitelist=None`` 与 ``whitelist=[]`` 一律视为
                「空白名单」并开启 allowlist，**所有非黑名单命令必须命中白名单才放行**。
                命中规则与黑名单一致（精确 / 前缀 / 正则）。

                调用方如未配置白名单，应至少传 ``[]`` 而非 ``None``，
                以便 SSHTools 显式表达「未配置 → 拒绝所有非黑名单命令」的语义。
        """
        self._blacklist_raw: List[str] = list(blacklist or [])
        # 强白名单：None 与 [] 都视为「空白名单 → 拒绝所有非黑名单命令」。
        # 旧实现把 whitelist=None 解释为「关闭白名单模式」与硬性契约冲突。
        self._whitelist_raw: List[str] = list(whitelist or [])
        self._blacklist_exact: List[str] = []
        self._blacklist_prefix: List[str] = []
        self._blacklist_regex: List[Tuple[str, "re.Pattern[str]"]] = []
        self._whitelist_exact: List[str] = []
        self._whitelist_prefix: List[str] = []
        self._whitelist_regex: List[Tuple[str, "re.Pattern[str]"]] = []
        self._compile_patterns(
            self._blacklist_raw,
            self._blacklist_exact,
            self._blacklist_prefix,
            self._blacklist_regex,
        )
        self._compile_patterns(
            self._whitelist_raw,
            self._whitelist_exact,
            self._whitelist_prefix,
            self._whitelist_regex,
        )

    @staticmethod
    def _compile_patterns(
        raw_list: List[str],
        exact_out: List[str],
        prefix_out: List[str],
        regex_out: List[Tuple[str, "re.Pattern[str]"]],
    ) -> None:
        """把字符串条目分类为精确 / 前缀 / 正则三种模式。

        分类规则：
          - 空字符串忽略；
          - 以 ``^`` 开头或包含正则元字符（``. *`` / ``\\s`` / ``\\d`` / ``(?i``）
            → 尝试编译为正则；编译失败回退为精确（小写）；源串原样存放在前缀集合；
          - 以空格结尾（前缀模式）→ 写入 ``prefix_out``（保留原始尾空格语义）；
          - 否则 → 写入 ``exact_out``（小写）。

        Args:
            raw_list: 原始字符串列表
            exact_out: 收集精确条目（小写）
            prefix_out: 收集前缀条目（保留原始尾空格）
            regex_out: 收集正则表达式（已编译），元素为 (源串, compiled)
        """
        regex_meta = (".*", "\\s", "\\d", "(?i")
        for raw in raw_list:
            if not isinstance(raw, str):
                continue
            pattern = raw.strip()
            if not pattern:
                continue
            # 正则模式：典型以 ^ 开头
            if pattern.startswith("^") or any(meta in pattern for meta in regex_meta):
                try:
                    compiled = re.compile(pattern, re.IGNORECASE)
                    regex_out.append((pattern, compiled))
                    continue
                except re.error:
                    # 编译失败 → 退化为精确匹配（小写）
                    exact_out.append(pattern.lower())
                    continue
            # 前缀模式：以空格结尾。**保留原始尾空格**（strip 后再补回单个空格），
            # 这样 ``startswith`` 用 ``ls `` 仍能命中 ``ls -l``，
            # 但 ``ls``（精确）不会匹配 ``ls -l``（这是预期差异）。
            if raw.endswith(" "):
                # 仅 strip 首尾多余空白，但保留单个尾部空格
                trimmed = raw.rstrip()
                if not trimmed:
                    continue
                prefix_out.append(trimmed.lower() + " ")
                continue
            # 精确匹配
            exact_out.append(pattern.lower())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_allowed(self, command) -> Tuple[bool, Optional[str]]:
        """判断命令是否允许执行。

        决策顺序：
          1) 空命令 → 拒绝
          2) 黑名单（精确 → 前缀 → 正则）→ 拒绝（最高优先级）
          3) 黑名单未命中 → 白名单 allowlist：未命中 → 拒绝
          4) 白名单命中 → 允许

        Args:
            command: 待判断命令（None / str）

        Returns:
            Tuple[bool, Optional[str]]: (是否允许, 拦截原因)。
            若允许则 reason 为 None；否则为可读原因字符串。
        """
        # 1) 空命令
        if command is None:
            return False, "命令不能为空"
        if not isinstance(command, str):
            return False, "命令不能为空"
        stripped = command.strip()
        if not stripped:
            return False, "命令不能为空"

        lower = stripped.lower()

        # 2) 黑名单优先
        # 2.1 精确匹配
        for pattern in self._blacklist_exact:
            if lower == pattern:
                return False, f"命令在黑名单中（精确匹配: {pattern}）"
        # 2.2 前缀匹配（pattern 末尾保留空格）
        for pattern in self._blacklist_prefix:
            if lower.startswith(pattern):
                pretty = pattern.rstrip()
                return False, f"命令在黑名单中（前缀匹配: {pretty} ）"
        # 2.3 正则匹配
        for source, compiled in self._blacklist_regex:
            if compiled.search(stripped):
                return False, f"命令在黑名单中（正则匹配: {source}）"

        # 3) 强白名单：任何非空白名单都必须命中才能放行
        if not self._match_whitelist(lower):
            return False, "命令不在白名单中"
        return True, None

    def _match_whitelist(self, lower_command: str) -> bool:
        """在白名单里查找命令是否命中。

        Args:
            lower_command: 已 ``.strip().lower()`` 的命令

        Returns:
            bool: 是否命中白名单
        """
        for pattern in self._whitelist_exact:
            if lower_command == pattern:
                return True
        for pattern in self._whitelist_prefix:
            if lower_command.startswith(pattern):
                return True
        for _, compiled in self._whitelist_regex:
            if compiled.search(lower_command):
                return True
        return False

    def check_and_raise(self, command) -> None:
        """``is_allowed`` 的异常版本；命中黑名单抛 ``CommandBlockedError``。

        Args:
            command: 待检查命令

        Raises:
            CommandBlockedError: 命中黑名单或未命中白名单时抛出
        """
        allowed, reason = self.is_allowed(command)
        if not allowed:
            raise CommandBlockedError(f"命令被拦截: {reason}")

    def add_pattern(self, pattern: str) -> None:
        """动态向黑名单追加一个条目，并立即重编译。

        Args:
            pattern: 新增的黑名单模式

        Returns:
            None
        """
        self._blacklist_raw.append(pattern)
        # 重编译
        self._blacklist_exact = []
        self._blacklist_prefix = []
        self._blacklist_regex = []
        self._compile_patterns(
            self._blacklist_raw,
            self._blacklist_exact,
            self._blacklist_prefix,
            self._blacklist_regex,
        )
