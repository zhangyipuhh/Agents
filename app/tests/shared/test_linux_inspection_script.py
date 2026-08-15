# -*- coding:utf-8 -*-
"""Linux Bash 巡检脚本 IO 采集契约回归测试（2026-08-15 新增）。

验证 ``data/devops/inspection_scripts.yaml.example`` 的 linux-bash 条目：
- 通过内核自带 ``/proc/diskstats`` 双采样计算 io_util_pct / io_await_ms，
  不依赖 sysstat(iostat) 等外部包；
- 通过 ``/sys/block/<dev>/queue/rotational`` 探测 SSD/HDD 介质并输出
  ``disk_type`` 元素键；
- 输出 JSON 键集合与 ``inspection_fields`` 声明的 key 集合一致；
- 仅使用老版 POSIX 语法（禁止 bash4+ / GNU 扩展混入）。
"""

from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _load_linux_bash_entry():
    """读取 .example 模板中的 linux-bash 条目。

    Returns:
        dict: linux-bash 脚本库条目（含 inspection_script / inspection_fields）

    Raises:
        StopIteration: 模板中不存在 linux-bash 条目时抛出
    """
    document = yaml.safe_load(
        (PROJECT_ROOT / "data" / "devops" / "inspection_scripts.yaml.example")
        .read_text(encoding="utf-8")
    )
    return next(
        item for item in document["inspection_scripts"]
        if item.get("name") == "linux-bash"
    )


def test_linux_inspection_script_uses_proc_diskstats_not_iostat():
    """linux-bash 条目应通过 /proc/diskstats 双采样采集 IO，无 sysstat 外部依赖。

    Returns:
        None

    Raises:
        AssertionError: 缺少内核接口采样段或混入外部依赖/新版语法时失败
    """
    entry = _load_linux_bash_entry()
    script = entry["inspection_script"]
    # IO 采集核心: 双采样 + 间隔 + 输出字段 + 整盘过滤
    assert "/proc/diskstats" in script
    assert "sleep 1" in script
    assert "io_util_pct" in script and "io_await_ms" in script
    assert "sd[a-z]+" in script
    assert "nvme[0-9]+n[0-9]+" in script
    # 介质探测
    assert "/sys/block/" in script
    assert "rotational" in script
    assert "disk_type" in script
    # 无外部包依赖: 注释可提及 iostat, 但脚本不能 ``$(iostat ...)`` 调用
    assert "$(iostat" not in script and "`iostat" not in script
    assert "iostat -" not in script
    # 老版 Linux 兼容性守卫: 禁止 bash4+ / GNU 扩展语法
    assert "<(" not in script        # 进程替换
    assert "<<<" not in script      # herestring
    assert "declare" not in script  # bash 关联数组
    assert "mapfile" not in script  # bash4 内建


def test_linux_inspection_output_keys_match_fields():
    """脚本输出键集合须与 inspection_fields key 集合一致（含 IO 两个新字段）。

    Returns:
        None

    Raises:
        AssertionError: 键集合不一致或 io_await_ms 缺 ssd 阈值对时失败
    """
    entry = _load_linux_bash_entry()
    output_keys = {
        "disk_used_pct", "mem_used_pct", "cpu_idle_pct", "load_1m",
        "io_util_pct", "io_await_ms",
    }
    configured_keys = {field["key"] for field in entry["inspection_fields"]}
    assert output_keys == configured_keys
    await_rule = next(
        f for f in entry["inspection_fields"] if f["key"] == "io_await_ms"
    )
    assert await_rule["warn"] == 100 and await_rule["crit"] == 200
    assert await_rule["ssd_warn"] == 20 and await_rule["ssd_crit"] == 50
