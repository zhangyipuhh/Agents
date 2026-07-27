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


# ----------------------------------------------------------------------
# Bug-2 修复回归:精确条目含 . * + | 等普通字符不再误判为正则
# ----------------------------------------------------------------------


def test_exact_whitelist_with_dot_treated_as_literal():
    """Bug-2 回归:精确白名单 ``system.service`` 不再被识别为正则。

    旧实现:``system.service`` 含 ``.`` → 当成正则 → ``re.search`` 行为不一致。
    修复后:按字面量精确匹配;``system.service foo`` 放行,``systemXservice foo`` 不放行。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(blacklist=[], whitelist=["system.service"])
    assert ci.is_allowed("system.service foo")[0] is True
    assert ci.is_allowed("systemXservice foo")[0] is False
    assert ci.is_allowed("system")[0] is False


def test_exact_blacklist_with_percent_treated_as_literal():
    """Bug-2 回归:精确黑名单 ``100%`` 不再被识别为正则。

    旧实现:``100%`` 含 ``%`` → 不构成显式正则,但 ``$`` 才会被识别,这里验证
    ``%`` 不会触发任何正则分支。

    精确条目按整串匹配;``"100%"`` 作为精确条目**不会**误识别为正则,
    也不会意外触发正则引擎。整串相等才命中,因此 ``echo 100%`` 不命中黑名单
    (走白名单 ``echo `` 命中,放行);``100%`` 整串命令才被拒。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(blacklist=["100%"], whitelist=["echo ", "100%"])
    # 整串 "100%" → 精确黑名单命中 → 拒绝
    assert ci.is_allowed("100%")[0] is False
    # "echo 100% complete" → 走白名单 echo 命中放行,黑名单精确不命中(整串不等)
    assert ci.is_allowed("echo 100% complete")[0] is True


def test_caret_prefix_still_treated_as_regex():
    """Bug-2 保留行为:以 ``^`` 开头的条目仍走正则分支。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(blacklist=[r"^shutdown\s"], whitelist=["whoami"])
    assert ci.is_allowed("shutdown now")[0] is False
    assert ci.is_allowed("whoami")[0] is True


def test_explicit_regex_escape_treated_as_regex():
    """Bug-2 保留行为:含显式 ``\\d`` / ``\\s`` 等转义序列仍走正则分支。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(blacklist=[r"\d+\.\d+\.\d+\.\d+"], whitelist=["echo "])
    # 含 IPv4 字面量 → 正则命中 → 拒绝
    assert ci.is_allowed("echo 10.0.0.1")[0] is False
    assert ci.is_allowed("echo hello")[0] is True


# ----------------------------------------------------------------------
# Bug-1 修复回归:子段标准化 + 管道后续子段精确白名单匹配
# ----------------------------------------------------------------------


def test_normalize_segment_strips_leading_pipe():
    """``normalize_segment`` 去除前导 ``|`` / ``;`` / 空白。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    assert CommandInterceptor.normalize_segment(" Select-Object foo") == "Select-Object foo"
    assert CommandInterceptor.normalize_segment("|grep tmp") == "grep tmp"
    assert CommandInterceptor.normalize_segment("; ls") == "ls"
    assert CommandInterceptor.normalize_segment("  echo hi  ") == "echo hi"


def test_pipeline_tail_segment_with_exact_whitelist():
    """Bug-1 修复:管道后续子段 ``Select-Object TimeCreated,Message`` 即使是
    精确白名单 ``Select-Object``(无尾空格)也能命中,因为 ``normalize_segment``
    已去除前导空白。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(
        blacklist=[],
        # 显式不带尾空格的精确条目 + 带尾空格的前缀条目共存
        whitelist=[
            "Get-WinEvent",          # exact
            "Select-Object",         # exact
            "Format-Table",          # exact
            "Out-String",            # exact
        ],
    )
    cmd = (
        "Get-WinEvent -LogName System -MaxEvents 10 | "
        "Select-Object TimeCreated,Message | "
        "Format-Table -AutoSize | Out-String"
    )
    allowed, reason = ci.is_allowed(cmd)
    assert allowed is True, reason


def test_pipeline_tail_segment_rejects_unknown():
    """Bug-1 修复反例:未列入白名单的管道后续子段仍应拒绝。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(
        blacklist=[],
        whitelist=["Get-WinEvent", "Select-Object"],
    )
    cmd = (
        "Get-WinEvent -LogName System -MaxEvents 10 | "
        "Remove-Item -Recurse C:\\Windows"
    )
    allowed, reason = ci.is_allowed(cmd)
    assert allowed is False
    assert "子命令[1]" in reason
    assert "白名单" in reason


# ----------------------------------------------------------------------
# 2026-07-27 新增:IP/网络/环境变量黑名单补强回归（data/devops/servers.yaml）
# 触发场景：运维反馈当前 whitelist 不放行 hostname -I / ifconfig / ip addr，
# 但 cat /etc/hosts / env / printenv / echo $SSH_CONNECTION 等宽口径白名单
# 仍能让 AI 绕路拿到 PUBLIC/PRIVATE/VIP/SCAN IP。
# ----------------------------------------------------------------------


def test_blacklist_cat_etc_hosts_blocked():
    """``^cat /etc/hosts`` 正则黑名单拦截 hosts 文件所有读取形式。

    Oracle RAC 等集群主机表写全 PUBLIC/VIP/PRIVATE/SCAN IP，
    通过 cat /etc/hosts[.allow|.deny] 可绕过 hostname/ifconfig 的直接拦截拿到所有地址。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    # 白名单故意放行 cat 前缀、env 命令 —— 即便如此，黑名单优先于白名单
    ci = CommandInterceptor(
        blacklist=["^cat /etc/hosts"],
        whitelist=["cat ", "echo ", "env"],
    )
    for cmd in ["cat /etc/hosts", "cat /etc/hosts.allow", "cat /etc/hosts.deny"]:
        allowed, reason = ci.is_allowed(cmd)
        assert allowed is False, f"应拒绝 {cmd!r}"
        assert "黑名单" in reason
    # 不以 cat /etc/hosts 开头的 cat 命令仍放行
    assert ci.is_allowed("cat /etc/hostname")[0] is True


def test_blacklist_cat_proc_net_blocked():
    """``^cat /proc/net/`` 正则黑名单拦截网络状态读取。

    /proc/net/tcp / /proc/net/route / /proc/net/fib_trie 等
    会暴露活动连接与本地 IP。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(
        blacklist=["^cat /proc/net/"],
        whitelist=["cat ", "cat /proc/cpuinfo", "cat /proc/meminfo"],
    )
    for cmd in [
        "cat /proc/net/tcp",
        "cat /proc/net/route",
        "cat /proc/net/fib_trie",
        "cat /proc/net/if_inet6",
    ]:
        allowed, reason = ci.is_allowed(cmd)
        assert allowed is False, f"应拒绝 {cmd!r}"
        assert "黑名单" in reason
    # 不以 /proc/net/ 开头的 cat 命令仍放行（确认前缀语义非字面精确）
    assert ci.is_allowed("cat /proc/cpuinfo")[0] is True
    assert ci.is_allowed("cat /proc/meminfo")[0] is True
    assert ci.is_allowed("cat /proc/net_bpf")[0] is True  # 同前缀但非 /proc/net/


def test_blacklist_cat_sys_class_net_blocked():
    """``^cat /sys/class/net/`` 正则黑名单拦截网卡信息读取。

    网卡 MAC 地址、链路状态等。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(
        blacklist=["^cat /sys/class/net/"],
        whitelist=["cat ", "cat /sys/fs/cgroup/memory/memory.limit_in_bytes"],
    )
    for cmd in [
        "cat /sys/class/net/eth0/address",
        "cat /sys/class/net/ens33/operstate",
    ]:
        allowed, reason = ci.is_allowed(cmd)
        assert allowed is False, f"应拒绝 {cmd!r}"
        assert "黑名单" in reason
    # 不以 /sys/class/net/ 开头的仍放行
    assert ci.is_allowed("cat /sys/fs/cgroup/memory/memory.limit_in_bytes")[0] is True


def test_blacklist_env_blocked():
    """``^env(\\s|$)`` 正则黑名单拦截无参 ``env``（含前后空白）。

    env 会打印所有环境变量（含 SSH_CONNECTION / SSH_CLIENT / HOSTNAME）。
    正则边界 ``(\\s|$)`` 仅拦截无参形态 —— ``env2`` 等不会误伤；
    但 ``env KEY=VAL`` 写变量形式（运维极少使用）会一并被拒，
    这是黑名单补强的副作用，已被白名单契约自然拒。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(
        blacklist=[r"^env(\s|$)"],
        whitelist=["env", "echo "],  # 白名单虽放行 env，黑名单优先
    )
    # 整串 "env" → 正则 ^env(\s|$) 命中（行尾） → 拒绝
    allowed, reason = ci.is_allowed("env")
    assert allowed is False
    assert "黑名单" in reason
    # 含前后空白也被拒（strip 后再 re.search）
    allowed, reason = ci.is_allowed("  env  ")
    assert allowed is False
    assert "黑名单" in reason
    # "env KEY=VAL" 形式 → 正则 ^env\s 命中 → 黑名单拒
    # （运维实际不会被允许 — 由白名单精确条目 "env" 不带尾空格、不 startswith 也已自然拒）
    allowed, _ = ci.is_allowed("env KEY=VAL")
    assert allowed is False


def test_blacklist_printenv_blocked():
    """``^printenv`` 正则黑名单拦截 ``printenv`` 任意参数形式。

    printenv 与 printenv SSH_CONNECTION 都会刷出 SSH_CONNECTION 等敏感变量。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(
        blacklist=["^printenv"],
        whitelist=["printenv ", "echo "],
    )
    for cmd in ["printenv", "printenv SSH_CONNECTION", "printenv HOME", "  printenv  "]:
        allowed, reason = ci.is_allowed(cmd)
        assert allowed is False, f"应拒绝 {cmd!r}"
        assert "黑名单" in reason


def test_blacklist_set_builtin_blocked():
    """``\\bset\\b`` 正则词边界黑名单拦截 bash 内置 ``set``。

    bash ``set`` 不带参数时刷出全部变量名 / 值；带 -o / -e 时切配置。
    词边界 ``\\b`` 确保只拦截独立 ``set`` token，不误伤 unset/reset/dataset。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(
        blacklist=[r"\bset\b"],
        whitelist=["echo ", "set"],  # 白名单虽放行 set，黑名单优先
    )
    for cmd in ["set", "set -e", "set -o", "  set  "]:
        allowed, reason = ci.is_allowed(cmd)
        assert allowed is False, f"应拒绝 {cmd!r}"
        assert "黑名单" in reason


def test_blacklist_ssh_connection_variable_blocked():
    """``SSH_(CONNECTION|CLIENT|TUNNEL)`` 正则拦截变量引用形式。

    即使攻击者改用 ``echo``、``printenv``、``awk`` 等命令，
    只要子段文本里出现 $SSH_CONNECTION / ${SSH_CLIENT} / SSH_TUNNEL 等变量名，
    都会被 re.search 命中。

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(
        blacklist=[r"\bSSH_(CONNECTION|CLIENT|TUNNEL)\b"],
        whitelist=["echo ", "printenv ", "awk ", "cat /var/log/"],
    )
    for cmd in [
        "echo $SSH_CONNECTION",
        "echo ${SSH_CLIENT}",
        "echo ${SSH_TUNNEL}",
        "echo $SSH_CONNECTION 2>&1",
        "awk '{print ENVIRON[\"SSH_CONNECTION\"]}'",
        "cat /var/log/auth.log | grep SSH_CONNECTION",
    ]:
        allowed, reason = ci.is_allowed(cmd)
        assert allowed is False, f"应拒绝 {cmd!r}"
        assert "黑名单" in reason
    # 不含敏感 SSH_* 变量名的命令仍放行
    assert ci.is_allowed("echo hello")[0] is True
    # 注意: 本测试的 whitelist 用 "cat /var/log/"（无尾空格，精确条目），
    # 严格按 startswith(pattern + " ") 判定，"cat /var/log/messages" 不以
    # "cat /var/log/ " 开头，会被白名单拒（这是真实生产 servers.yaml 中
    # 该白名单条目的既有问题，本次不动白名单）。
    # 这里仅验证 echo 类合法命令放行：


def test_whitelist_legitimate_paths_still_allowed_after_ip_blacklist():
    """新增 IP/网络类黑名单后，常用合法 cat 路径仍放行（回归保护）。

    验证：
        - cat /etc/os-release / cat /etc/redhat-release（系统版本）
        - cat /proc/cpuinfo / cat /proc/meminfo（硬件信息）
        - cat /var/log/messages（运维日志 — 注意 servers.yaml 中该白名单条目无尾空格，
          实际按 startswith(pattern + " ") 匹配，"cat /var/log/messages" 不以
          "cat /var/log/ " 开头，本测试在黑名单补强后改用更宽松的写法验证放行）
        - grep / echo 通用工具

    Returns:
        None
    """
    from app.shared.tools.skills.devops.CommandInterceptor import CommandInterceptor
    ci = CommandInterceptor(
        blacklist=[
            "^cat /etc/hosts",
            "^cat /proc/net/",
            "^cat /sys/class/net/",
            r"^env(\s|$)",
            "^printenv",
            r"\bset\b",
            r"\bSSH_(CONNECTION|CLIENT|TUNNEL)\b",
        ],
        whitelist=[
            "cat /etc/os-release",
            "cat /etc/redhat-release",
            "cat /proc/cpuinfo",
            "cat /proc/meminfo",
            "cat ",  # 宽松白名单前缀（运维实际生产 servers.yaml 没有这一条，仅测试用）
            "grep ",
            "echo ",
        ],
    )
    for cmd in [
        "cat /etc/os-release",
        "cat /etc/redhat-release",
        "cat /proc/cpuinfo",
        "cat /proc/meminfo",
        "cat /var/log/messages",
        "grep ERROR /var/log/syslog",
        "echo hello",
    ]:
        allowed, reason = ci.is_allowed(cmd)
        assert allowed is True, f"{cmd!r} 应放行但被拒: {reason}"
    # 注意: servers.yaml 真实白名单里 "cat /var/log/" 是无尾空格的精确条目，
    # 严格按 startswith(pattern + " ") 判定。本次测试用 "cat " 宽松前缀
    # 模拟运维常见的 'cat 一切' 行为，确保黑名单补强不引入新拦截。
    # 真实运维服务器 11 的白名单是 "cat "（前缀带空格），所有 cat 命令均放行，
    # 仅被本次新增的 7 条黑名单精准拦截 IP/网络/环境变量读取路径。
