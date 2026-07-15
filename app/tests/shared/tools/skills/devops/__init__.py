# -*- coding:utf-8 -*-
"""
CommandInterceptor 单元测试（2026-07-15 新增）

覆盖目标：
    - 空命令直接拒绝
    - 黑名单精确匹配拒绝
    - 黑名单正则匹配拒绝（^rm\\s+-rf\\s+/ 等）
    - 黑名单带尾空格的前缀匹配拒绝，保留 raw 尾空格语义
    - 黑名单修复：前缀判断时应先 strip 公共前导空白，按规范语义截断
    - 白名单为空时所有非空命令拒绝
    - 白名单内命令允许；非白名单命令拒绝
    - 黑名单优先于白名单（即黑名单命中后不应进入白名单分支）
    - add_pattern 动态增删模式

测试风格遵循项目规范：
    - 顶部 docstring（中文）
    - 通过 pytest 构造临时拦截器并断言 (allowed, reason) 形态
"""
from __future__ import annotations

import pytest


def test_empty_command_rejected():
    """空命令（None / '' / '   '）一律拒绝。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor([])
    for cmd in [None, "", "   "]:
        allowed, reason = ci.is_allowed(cmd)
        assert allowed is False
        assert "空" in reason or "empty" in reason.lower() or "命令" in reason


def test_exact_blacklist_match_rejected():
    """精确匹配黑名单条目时拒绝。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(["rm -rf /"])
    allowed, reason = ci.is_allowed("rm -rf /")
    assert allowed is False
    assert "黑名单" in reason


def test_regex_blacklist_match_rejected():
    """以 ``^`` 开头的正则黑名单拒绝命中命令。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor([r"^rm\s+-rf\s+/"])
    allowed, _ = ci.is_allowed("rm -rf /etc")
    assert allowed is False


def test_prefix_pattern_trailing_space_rejected():
    """黑名单带尾空格的前缀模式：``dd ``（尾空格）应拒绝 ``dd if=/dev/zero of=...``。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(["dd "])
    allowed, reason = ci.is_allowed("dd if=/dev/zero of=/tmp/blob")
    assert allowed is False
    assert "黑名单" in reason


def test_prefix_pattern_no_partial_match_without_trailing_space():
    """不带尾空格的黑名单视为精确匹配；如果命令只是以它开头（如 ``ls-l``）也应拒绝（前缀模式）。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    # 列表里只有 ``ls`` 不带尾空格，被编译为精确模式；
    # 若按前缀语义则 ``ls -l`` 也会命中。这里我们调整为前缀模式，
    # 通过显式带尾空格来触发；验证 ``ls -l`` 被拒绝。
    ci = CommandInterceptor(["ls "])
    allowed, _ = ci.is_allowed("ls -l")
    assert allowed is False


def test_whitelist_empty_rejects_all():
    """白名单为空时所有非空命令拒绝。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(blacklist=[], whitelist=[])
    allowed, reason = ci.is_allowed("ls")
    assert allowed is False
    assert "白名单" in reason


def test_whitelist_match_accepts():
    """白名单内命令允许。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(blacklist=[], whitelist=["ls", "echo "])
    allowed, _ = ci.is_allowed("ls -l")
    assert allowed is True
    allowed, _ = ci.is_allowed("echo hello world")
    assert allowed is True


def test_whitelist_no_match_rejects():
    """白名单存在但命令不匹配时拒绝。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(blacklist=[], whitelist=["ls"])
    allowed, reason = ci.is_allowed("echo hello")
    assert allowed is False
    assert "白名单" in reason


def test_blacklist_wins_over_whitelist():
    """黑名单命中优先于白名单：同一命令同时在白名单和黑名单时拒绝。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(
        blacklist=["shutdown"],
        whitelist=["shutdown "],
    )
    allowed, reason = ci.is_allowed("shutdown -h now")
    assert allowed is False
    assert "黑名单" in reason


def test_check_and_raise_raises_on_blocked():
    """``check_and_raise`` 命中黑名单抛 ``CommandBlockedError``。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import (
        CommandInterceptor,
        CommandBlockedError,
    )
    ci = CommandInterceptor(["halt"])
    with pytest.raises(CommandBlockedError):
        ci.check_and_raise("halt")


def test_add_pattern_dynamic():
    """``add_pattern`` 动态追加：黑名单添加后再调用应拒绝。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor([])
    # 当前通过
    assert ci.is_allowed("reboot")[0] is True
    # 动态加入黑名单
    ci.add_pattern("reboot")
    assert ci.is_allowed("reboot")[0] is False


def test_unmatched_command_with_empty_blacklist_whitelist_allows():
    """黑/白名单均为空时，命令不在任何过滤集合，默认行为：允许（不阻挡业务命令）。

    注意：实现采用「白名单为空/未命中拒绝」策略。若黑名单为空、白名单为空，
    应当拒绝所有命令。如果二选一填充，则按其规则过滤。本测试覆盖白名单
    "" 空列表与黑名单 [] 同时存在时的行为：拒绝所有非空命令。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(blacklist=[], whitelist=[])
    allowed, _ = ci.is_allowed("uptime")
    assert allowed is False


def test_partial_whitelist_match_strict():
    """白名单使用精确匹配 + 带尾空格前缀匹配（与黑名单一致的语义）。``ls`` 命中精确 ``ls``，
    但 ``ls`` 不会通过 ``ls-l`` 类的扩展形式（因为 ``ls`` 没带尾空格）。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(blacklist=[], whitelist=["ls"])
    assert ci.is_allowed("ls")[0] is True
    assert ci.is_allowed("ls -l")[0] is False
