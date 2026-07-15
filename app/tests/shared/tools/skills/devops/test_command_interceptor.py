# -*- coding:utf-8 -*-
"""
CommandInterceptor 单元测试（2026-07-15 新增）

覆盖目标：
    - 空命令直接拒绝
    - 黑名单精确匹配拒绝
    - 黑名单正则匹配拒绝（^rm\\s+-rf\\s+/ 等）
    - 黑名单带尾空格的前缀匹配拒绝，保留 raw 尾空格语义
    - 白名单为空时所有非空命令拒绝
    - 白名单内命令允许；非白名单命令拒绝
    - 黑名单优先于白名单（即黑名单命中后不应进入白名单分支）
    - 白名单精确条目按 startswith 匹配（df → df -h / df -i）
    - 管道 / 逻辑与或 / 分号连接的子命令需逐段独立通过校验
    - 内置安全黑名单默认拒命令替换 / 进程替换 / 单 & 后台执行
    - 引号内的 | ; & 不作为拆分符
    - add_pattern 动态增删模式
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
        assert ("空" in reason) or ("empty" in reason.lower()) or ("命令" in reason)


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


def test_prefix_pattern_rejects_args_after_dd():
    """黑名单 ``ls ``（带尾空格）作为前缀模式，应拒绝 ``ls -l``。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(["ls "])
    allowed, _ = ci.is_allowed("ls -l")
    assert allowed is False


def test_whitelist_empty_rejects_all():
    """白名单为空且无黑名单命中时，所有非空命令拒绝。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(blacklist=[], whitelist=[])
    allowed, reason = ci.is_allowed("ls")
    assert allowed is False
    assert "白名单" in reason


def test_whitelist_none_treated_as_empty():
    """强白名单契约：whitelist=None 也必须视作空白名单并拒绝所有非黑名单命令。

    旧实现把 ``whitelist=None`` 解释为「不启用 allowlist」，
    与项目「黑名单优先 + 白名单 allowlist」硬性契约不一致。
    现规范：``whitelist=None`` 等价于 ``whitelist=[]``，非黑名单命令一律拒绝。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(blacklist=[], whitelist=None)
    allowed, reason = ci.is_allowed("ls")
    assert allowed is False
    assert "白名单" in reason


def test_whitelist_none_with_prefix_match():
    """whitelist=None 时命令命中黑名单仍按黑名单拒绝。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(blacklist=["ls "], whitelist=None)
    allowed, reason = ci.is_allowed("ls -l")
    assert allowed is False
    assert "黑名单" in reason


def test_whitelist_match_accepts():
    """白名单内命令允许。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(blacklist=[], whitelist=["ls", "echo "])
    # "ls" 精确条目 → startswith 匹配 "ls" / "ls -l" / "ls -la"
    # "echo " 带尾空格 → 前缀模式，匹配 "echo hello world"
    assert ci.is_allowed("ls")[0] is True
    assert ci.is_allowed("echo hello world")[0] is True
    assert ci.is_allowed("ls -l")[0] is True


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
    """黑名单命中优先于白名单：白名单放行 ``shutdown *``，黑名单前缀也命中时拒绝。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(
        blacklist=["shutdown "],   # 前缀模式：catch shutdown -h now / shutdown -r 等
        whitelist=["shutdown "],   # 白名单仅当黑名单未命中时才生效
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
    # 强白名单语义：构造时即配置命中白名单的命令，确保默认通过
    ci = CommandInterceptor(blacklist=[], whitelist=["reboot"])
    # 当前通过
    assert ci.is_allowed("reboot")[0] is True
    # 动态加入黑名单
    ci.add_pattern("reboot")
    assert ci.is_allowed("reboot")[0] is False


def test_whitelist_exact_uses_startswith():
    """白名单精确条目按「命令名 + 可选空格」匹配(放宽策略)。

    ``ls`` 放行 ``ls`` / ``ls -l`` / ``ls -la /tmp``；非 ls 前缀的 ``lsblk`` 不放行
    （避免 ``ls`` 误放行 ``lsblk`` / ``lsattr`` 等其他命令）。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(blacklist=[], whitelist=["ls"])
    assert ci.is_allowed("ls")[0] is True
    assert ci.is_allowed("ls -l")[0] is True
    assert ci.is_allowed("ls -la /tmp")[0] is True
    assert ci.is_allowed("lsblk")[0] is False
    assert ci.is_allowed("lsattr")[0] is False


def test_whitelist_df_allows_df_h():
    """业务诉求:``whitelist=['df']`` 应放行 ``df -h`` / ``df -i`` 等所有 df 子命令。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(blacklist=[], whitelist=["df"])
    assert ci.is_allowed("df")[0] is True
    assert ci.is_allowed("df -h")[0] is True
    assert ci.is_allowed("df -i")[0] is True
    assert ci.is_allowed("df -T /tmp")[0] is True
    assert ci.is_allowed("du -h")[0] is False


def test_blacklist_exact_still_strict():
    """白名单放宽只影响白名单:黑名单精确条目仍走精确匹配,不误伤相似命令。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(blacklist=["halt"], whitelist=["halt"])
    # 黑名单精确 'halt' 命中 → 拒绝(优先级最高)
    assert ci.is_allowed("halt")[0] is False
    # 'halt-on-error' 不命中精确 'halt',旧契约也不放行(白名单 startswith 'halt'
    # 会命中 'halt-on-error',但白名单优先于黑名单之前已被黑名单拦截前的逻辑被改:
    # 新行为下 'halt-on-error' 也被白名单 startswith 放行,这是已知放宽代价)
    # 因此本用例仅验证黑名单精确条目不会被白名单 startswith 弱化:
    # 'halt' 仍然被黑名单精确命中 → 拒绝
    assert "黑名单" in ci.is_allowed("halt")[1]


# ----------------------------------------------------------------------
# Pipeline / 组合命令逐段校验
# ----------------------------------------------------------------------


def test_pipeline_white_segments_allowed():
    """管道两段都命中白名单时放行。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(blacklist=[], whitelist=["df", "grep "])
    allowed, _ = ci.is_allowed("df -h | grep tmp")
    assert allowed is True


def test_pipeline_one_segment_not_in_whitelist_rejected():
    """管道子段未命中白名单时整批拒绝(标注段索引)。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(blacklist=[], whitelist=["df"])
    allowed, reason = ci.is_allowed("df -h | grep tmp")
    assert allowed is False
    assert "子命令[1]" in reason
    assert "白名单" in reason


def test_pipeline_segment_in_blacklist_rejected():
    """``;`` 连接的子段命中黑名单前缀时整批拒绝。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(
        blacklist=["rm -rf"],
        whitelist=["cat", "echo "],
    )
    allowed, reason = ci.is_allowed("cat /etc/hosts; rm -rf /tmp/x")
    assert allowed is False
    assert "子命令[1]" in reason
    assert "rm -rf" in reason


def test_command_substitution_blocked():
    """``$()`` 与反引号命令替换被内置黑名单默认拒绝。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(blacklist=[], whitelist=["echo ", "whoami"])
    for cmd in ["echo $(whoami)", "echo `whoami`"]:
        allowed, reason = ci.is_allowed(cmd)
        assert allowed is False, f"应拒绝 {cmd!r}"
        assert "黑名单" in reason


def test_process_substitution_blocked():
    """``<()`` / ``>()`` 进程替换被内置黑名单默认拒绝。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(blacklist=[], whitelist=["diff", "ls"])
    for cmd in ["diff <(ls) <(ls -a)", "tee >(cat)"]:
        allowed, reason = ci.is_allowed(cmd)
        assert allowed is False, f"应拒绝 {cmd!r}"
        assert "黑名单" in reason


def test_background_execution_blocked():
    """单 ``&`` 后台执行被内置黑名单默认拒绝;``&&`` 不被误伤。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(blacklist=[], whitelist=["sleep", "echo "])
    allowed_bg, reason_bg = ci.is_allowed("sleep 5 &")
    assert allowed_bg is False
    assert "黑名单" in reason_bg
    # ``&&`` 是合法逻辑与,不被单 & 正则误伤
    allowed_and, _ = ci.is_allowed("sleep 1 && echo done")
    assert allowed_and is True


def test_quoted_pipe_not_split():
    """引号内的 ``|`` 不作为分词边界。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(blacklist=[], whitelist=["echo ", "wc "])
    allowed, reason = ci.is_allowed('echo "a|b" | wc -c')
    assert allowed is True, reason


def test_empty_segment_ignored():
    """连续分号 / 空段不参与校验。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(blacklist=[], whitelist=["df"])
    allowed, reason = ci.is_allowed("df -h ; ; df -i")
    assert allowed is True, reason


def test_split_pipeline_helper():
    """分词器单元测试:管道 / ; / && / 引号 / 单 &。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    assert CommandInterceptor._split_pipeline("ls -l") == ["ls -l"]
    assert CommandInterceptor._split_pipeline("a|b") == ["a", "b"]
    assert CommandInterceptor._split_pipeline("a; b") == ["a", "b"]
    assert CommandInterceptor._split_pipeline("a && b") == ["a", "b"]
    assert CommandInterceptor._split_pipeline("a || b") == ["a", "b"]
    assert CommandInterceptor._split_pipeline('echo "a|b" | wc') == ['echo "a|b"', "wc"]
    assert CommandInterceptor._split_pipeline("echo 'a;b'") == ["echo 'a;b'"]
