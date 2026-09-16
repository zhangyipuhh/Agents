# -*- coding:utf-8 -*-
"""Linux Bash 默认分段脚本资产契约回归测试(2026-09-16 由 YAML 测试改写)。

验证 ``app/shared/utils/inspection/default_scripts.py`` 的 linux-bash 组:
- disk-io 分段通过 /proc/diskstats 双采样采集 IO,不依赖 sysstat(iostat);
- disk-io 分段通过 /sys/block/<dev>/queue/rotational 探测介质并输出 disk_type;
- 四分段输出键并集 == inspection_fields 声明 key 集合(可评估全覆盖);
- 仅使用老版 POSIX 语法(禁止 bash4+ 进程替换 ``<(``)。
"""
import re

from app.shared.utils.inspection.default_scripts import DEFAULT_INSPECTION_GROUPS


def _linux_group():
    """获取 linux-bash 默认组。

    Returns:
        dict: linux-bash 组条目(含 segments / inspection_fields)

    Raises:
        StopIteration: 默认组未声明 linux-bash 时抛出
    """
    return next(g for g in DEFAULT_INSPECTION_GROUPS if g["name"] == "linux-bash")


def _segment(group, key):
    """按 segment_key 取分段。

    Args:
        group: 默认组条目
        key: 分段键

    Returns:
        dict: 分段条目(含 segment_key / display_name / sort_order / script)

    Raises:
        StopIteration: 分段键不存在时抛出
    """
    return next(s for s in group["segments"] if s["segment_key"] == key)


def test_disk_io_segment_uses_proc_diskstats_not_iostat():
    """disk-io 分段应通过 /proc/diskstats 双采样采集 IO。

    Returns:
        None

    Raises:
        AssertionError: 缺少内核接口采样段或混入外部依赖/新版语法时失败
    """
    script = _segment(_linux_group(), "disk-io")["script"]
    assert "/proc/diskstats" in script
    assert "sleep 1" in script
    assert "io_util_pct" in script and "io_await_ms" in script
    assert "iostat" not in script
    assert "<(" not in script  # 禁止 bash4+ 进程替换


def test_disk_io_segment_detects_media_type():
    """disk-io 分段应通过 /sys/block 探测介质并输出 disk_type。

    Returns:
        None

    Raises:
        AssertionError: 缺介质探测逻辑或未输出 disk_type 时失败
    """
    script = _segment(_linux_group(), "disk-io")["script"]
    assert "/sys/block/" in script
    assert "rotational" in script
    assert "disk_type" in script


def test_segments_output_keys_cover_declared_fields():
    """四分段 printf 输出的 JSON 键并集 == 9 条字段规则 key 集 + disks。

    Returns:
        None

    Raises:
        AssertionError: 任何字段规则的 key 在分段输出中找不到对应 JSON 键时失败
    """
    group = _linux_group()
    declared = {f["key"] for f in group["inspection_fields"]}
    produced = set()
    for seg in group["segments"]:
        # 从 printf 格式串提取顶层 JSON 键("key": 形态)
        produced |= set(re.findall(r'\\?"([a-z_0-9]+)\\?"\s*:', seg["script"]))
    produced.discard("disks")
    # disks 数组元素承载 disk_used_pct / io_util_pct / io_await_ms
    produced |= {"disk_used_pct", "io_util_pct", "io_await_ms"}
    assert declared <= produced


def test_disk_usage_segment_emits_host_disk_partition_disk_index():
    """disk-usage 分段必须输出 host_disk / partition / disk_index 字段。

    Returns:
        None

    Raises:
        AssertionError: 任一字段在分段脚本中缺失时失败
    """
    script = _segment(_linux_group(), "disk-usage")["script"]
    assert "host_disk" in script
    assert "partition" in script
    assert "disk_index" in script
    assert "disk_used_pct" in script
