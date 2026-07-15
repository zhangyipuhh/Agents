#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
CommandInterceptor - 命令策略过滤器（2026-07-15）

职责：
    - 接收黑名单与白名单，提供 ``is_allowed(command) -> (allowed, reason)``
    - 支持三种匹配模式：
        * 精确条目（无尾空格、无正则特征）:命令名 + 可选空格匹配
          （``df`` → ``df`` / ``df -h``，但不放行 ``dfu``）
        * 前缀条目（尾空格）:startswith 匹配
        * 正则条目（以 ``^`` 开头或包含正则元字符）:re.search 匹配
    - 内置安全黑名单（默认拒绝命令替换 / 进程替换 / 单 & 后台执行）
    - 黑名单优先于白名单
    - 逐段拆分校验：管道 / 逻辑与或 / 分号连接的子命令均需独立通过校验
    - 引号感知分词：单 / 双引号内的 ``|`` ``;`` ``&`` 视为普通字符
    - 空命令直接拒绝
    - 白名单语义：空列表 → 拒绝所有非黑名单命令；命中 → 允许；未命中 → 拒绝

设计要点：
    - 命令大小写不敏感（统一 ``.lower()``）
    - 拆分器识别 shell 操作符 ``|`` ``||`` ``&&`` ``;``（不在引号内）
    - 子段再走一遍用户黑名单 + 白名单
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple


class CommandBlockedError(Exception):
    """命令被策略拦截时抛出的异常。"""

    pass


# 内置安全黑名单：无需运维手写，默认拒绝高危 shell 语法
# - $() / ``:命令替换，可在引号外任意位置执行任意命令
# - <() / >():进程替换，可绕过管道分词
# - 单 &:后台执行，绕过同步返回值约束
_SAFETY_BLACKLIST: List[str] = [
    r"\$\(",          # $(cmd) 命令替换
    r"`",             # `cmd` 反引号命令替换
    r"<\(",           # <(cmd) 进程替换（输入）
    r">\(",           # >(cmd) 进程替换（输出）
    r"(?<![&|])&(?!&)",  # 单 & 后台执行（避开 && / &|）
]


class CommandInterceptor:
    """命令策略过滤器。

    Attributes:
        _blacklist_raw: 原始黑名单字符串列表（含内置安全黑名单）
        _whitelist_raw: 原始白名单字符串列表
        _blacklist_exact: 黑名单精确匹配集（小写）
        _blacklist_prefix: 黑名单前缀模式（原始尾空格被保留）
        _blacklist_regex: 黑名单已编译正则列表
        _whitelist_exact: 白名单精确条目集（小写，按 startswith 匹配）
        _whitelist_prefix: 白名单前缀模式（保留原始尾空格）
        _whitelist_regex: 白名单已编译正则列表
    """

    def __init__(
        self,
        blacklist: Optional[List[str]] = None,
        whitelist: Optional[List[str]] = None,
    ) -> None:
        """构造拦截器。

        Args:
            blacklist: 用户黑名单条目列表（精确 / 前缀 / 正则）。
                传 ``None`` 等价于 ``[]``。
                内部自动前置 ``_SAFETY_BLACKLIST``（命令替换 / 进程替换 / 后台执行）。
            whitelist: 白名单条目列表。
                强白名单契约：``whitelist=None`` 与 ``whitelist=[]`` 一律视为
                「空白名单」并开启 allowlist，**所有非黑名单命令必须命中白名单才放行**。
                命中规则与黑名单一致（精确 / 前缀 / 正则）。
        """
        # 内置安全黑名单在前，用户黑名单在后；编译时统一走正则路径
        self._blacklist_raw: List[str] = list(_SAFETY_BLACKLIST) + list(blacklist or [])
        # 强白名单：None 与 [] 都视为「空白名单 → 拒绝所有非黑名单命令」。
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
          - 以 ``^`` 开头或包含正则元字符 → 尝试编译为正则；
          - 以空格结尾（前缀模式）→ 写入 ``prefix_out``（保留单个尾部空格）；
          - 否则 → 写入 ``exact_out``（小写）。

        Args:
            raw_list: 原始字符串列表
            exact_out: 收集精确条目（小写）
            prefix_out: 收集前缀条目（保留原始尾空格）
            regex_out: 收集正则表达式（已编译），元素为 (源串, compiled)
        """
        regex_meta = (".*", "\\s", "\\d", "(?", "\\(", "\\[", "\\$", "\\^", "\\.", "\\+", "\\*", "\\|", "\\{", "\\}", "\\\\", "`", "<", ">")
        for raw in raw_list:
            if not isinstance(raw, str):
                continue
            pattern = raw.strip()
            if not pattern:
                continue
            # 正则模式：典型以 ^ 开头或包含正则元字符（含反斜杠转义序列）
            if pattern.startswith("^") or any(meta in pattern for meta in regex_meta):
                try:
                    compiled = re.compile(pattern, re.IGNORECASE)
                    regex_out.append((pattern, compiled))
                    continue
                except re.error:
                    # 编译失败 → 退化为精确匹配（小写）
                    exact_out.append(pattern.lower())
                    continue
            # 前缀模式：以空格结尾
            if raw.endswith(" "):
                trimmed = raw.rstrip()
                if not trimmed:
                    continue
                prefix_out.append(trimmed.lower() + " ")
                continue
            # 精确匹配（小写）
            exact_out.append(pattern.lower())

    # ------------------------------------------------------------------
    # Pipeline splitter
    # ------------------------------------------------------------------

    @staticmethod
    def _split_pipeline(command: str) -> List[str]:
        """按 shell 操作符拆分命令为子命令列表。

        支持的拆分符（仅在引号外生效）：
          - ``|``  /  ``||``
          - ``&&``
          - ``;``
          - 单 ``&`` 不作为拆分符（视为后台执行标记，由内置黑名单拒），
            但其前后的子命令仍按 ``&`` 边界切分，以便错误信息精确。

        Args:
            command: 原始命令字符串（已 strip，未做大小写转换）

        Returns:
            List[str]: 子命令列表（至少 1 段，空字符串已过滤）

        Examples:
            >>> CommandInterceptor._split_pipeline("ls -l")
            ['ls -l']
            >>> CommandInterceptor._split_pipeline("df -h | grep tmp")
            ['df -h ', ' grep tmp']
            >>> CommandInterceptor._split_pipeline('echo "a|b" | wc -c')
            ['echo "a|b" ', ' wc -c']
        """
        segments: List[str] = []
        buf: List[str] = []
        in_single = False
        in_double = False
        i = 0
        n = len(command)
        while i < n:
            ch = command[i]
            if in_single:
                buf.append(ch)
                if ch == "'":
                    in_single = False
                i += 1
                continue
            if in_double:
                buf.append(ch)
                if ch == '"':
                    in_double = False
                i += 1
                continue
            # 未在引号内
            if ch == "'":
                in_single = True
                buf.append(ch)
                i += 1
                continue
            if ch == '"':
                in_double = True
                buf.append(ch)
                i += 1
                continue
            # 转义字符：保留 \ 与下一字符
            if ch == "\\" and i + 1 < n:
                buf.append(ch)
                buf.append(command[i + 1])
                i += 2
                continue
            # 拆分符检测
            if ch == "|" or ch == ";":
                # 段尾
                seg = "".join(buf).strip()
                if seg:
                    segments.append(seg)
                buf = []
                i += 1
                continue
            if ch == "&":
                # 单 & / && 都作为段边界（单 & 由内置黑名单拒）
                seg = "".join(buf).strip()
                if seg:
                    segments.append(seg)
                buf = []
                # 跳过第二个 &（如有）
                i += 1
                if i < n and command[i] == "&":
                    i += 1
                continue
            buf.append(ch)
            i += 1

        seg = "".join(buf).strip()
        if seg:
            segments.append(seg)
        return segments

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_allowed(self, command) -> Tuple[bool, Optional[str]]:
        """判断命令是否允许执行。

        决策顺序：
          1) 空命令 → 拒绝
          2) 内置安全黑名单 + 用户黑名单（精确 → 前缀 → 正则，整串扫描）→ 拒绝
          3) ``_split_pipeline`` 拆分子命令，每段独立走：
              - 黑名单（精确 → 前缀 → 正则）
              - 白名单（精确 → 前缀 → 正则）
              任一子段失败 → 拒绝（标注失败段索引）
          4) 全部通过 → 允许

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

        lower_full = stripped.lower()

        # 2) 整串黑名单（包含内置安全黑名单 + 用户黑名单）
        blk_exact_hit, blk_exact_pat = self._match_blacklist_exact(lower_full)
        if blk_exact_hit:
            return False, f"命令在黑名单中（精确匹配: {blk_exact_pat}）"
        blk_prefix_hit, blk_prefix_pat = self._match_blacklist_prefix(lower_full)
        if blk_prefix_hit:
            pretty = blk_prefix_pat.rstrip()
            return False, f"命令在黑名单中（前缀匹配: {pretty} ）"
        for source, compiled in self._blacklist_regex:
            if compiled.search(stripped):
                return False, f"命令在黑名单中（正则匹配: {source}）"

        # 3) 拆分子命令，逐段校验
        segments = self._split_pipeline(stripped)
        if not segments:
            return False, "命令不能为空"

        for idx, seg in enumerate(segments):
            seg_lower = seg.lower()
            # 子段黑名单（精确 / 前缀 / 正则）
            seg_blk_exact_hit, seg_blk_exact_pat = self._match_blacklist_exact(seg_lower)
            if seg_blk_exact_hit:
                return False, (
                    f"子命令[{idx}]='{seg}' 在黑名单中（精确匹配: {seg_blk_exact_pat}）"
                )
            seg_blk_prefix_hit, seg_blk_prefix_pat = self._match_blacklist_prefix(seg_lower)
            if seg_blk_prefix_hit:
                pretty = seg_blk_prefix_pat.rstrip()
                return False, (
                    f"子命令[{idx}]='{seg}' 在黑名单中（前缀匹配: {pretty} ）"
                )
            for source, compiled in self._blacklist_regex:
                if compiled.search(seg):
                    return False, (
                        f"子命令[{idx}]='{seg}' 在黑名单中（正则匹配: {source}）"
                    )
            # 子段白名单
            if not self._match_whitelist(seg_lower):
                return False, f"子命令[{idx}]='{seg}' 不在白名单中"

        return True, None

    # ------------------------------------------------------------------
    # Internal matchers
    # ------------------------------------------------------------------

    def _match_blacklist_exact(self, lower_command: str) -> Tuple[bool, Optional[str]]:
        """整串精确黑名单匹配。

        Args:
            lower_command: 已 ``.strip().lower()`` 的命令

        Returns:
            Tuple[bool, Optional[str]]: (是否命中, 命中的 pattern)
        """
        for pattern in self._blacklist_exact:
            if lower_command == pattern:
                return True, pattern
        return False, None

    def _match_blacklist_prefix(self, lower_command: str) -> Tuple[bool, Optional[str]]:
        """整串前缀黑名单匹配。

        Args:
            lower_command: 已 ``.strip().lower()`` 的命令

        Returns:
            Tuple[bool, Optional[str]]: (是否命中, 命中的 pattern)
        """
        for pattern in self._blacklist_prefix:
            if lower_command.startswith(pattern):
                return True, pattern
        return False, None

    def _match_whitelist(self, lower_command: str) -> bool:
        """在白名单里查找命令是否命中。

        精确条目按「命令名 + 可选空格」匹配，避免误伤同前缀的其它命令：
          - ``ls`` 放行 ``ls`` / ``ls -l``，但不放行 ``lsblk``
          - ``df`` 放行 ``df`` / ``df -h`` / ``df -i``，但不放行 ``dfu``
        前缀条目（带尾空格）按 startswith 匹配（与历史行为一致）。
        正则条目按 re.search 匹配。

        Args:
            lower_command: 已 ``.strip().lower()`` 的命令

        Returns:
            bool: 是否命中白名单
        """
        # 精确条目：lower == pattern or lower.startswith(pattern + " ")
        for pattern in self._whitelist_exact:
            if lower_command == pattern or lower_command.startswith(pattern + " "):
                return True
        # 前缀条目：startswith 匹配（带尾空格已由 _compile_patterns 保证）
        for pattern in self._whitelist_prefix:
            if lower_command.startswith(pattern):
                return True
        # 正则条目：re.search 匹配
        for _, compiled in self._whitelist_regex:
            if compiled.search(lower_command):
                return True
        return False

    def check_and_raise(self, command) -> None:
        """``is_allowed`` 的异常版本；命中黑名单或未命中白名单时抛 ``CommandBlockedError``。

        Args:
            command: 待检查命令

        Raises:
            CommandBlockedError: 命中黑名单或未命中白名单时抛出
        """
        allowed, reason = self.is_allowed(command)
        if not allowed:
            raise CommandBlockedError(f"命令被拦截: {reason}")

    def add_pattern(self, pattern: str) -> None:
        """动态向用户黑名单追加一个条目，并立即重编译。

        Args:
            pattern: 新增的黑名单模式（不会进入内置安全黑名单之外的位置）

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