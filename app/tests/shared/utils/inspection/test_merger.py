# -*- coding:utf-8 -*-
"""merge_inspection_fragments 单元测试(2026-09-16 新增)。

锁定 D1 合并语义:dict 深合并 / list 顺序拼接 / 标量冲突后者覆盖并记冲突键;
并用 linux-bash 四分段样例锁定「合并后键集 == 现有巡检契约键集」。
"""
from app.shared.utils.inspection.merger import merge_inspection_fragments


def test_merge_disjoint_keys():
    merged, conflicts = merge_inspection_fragments(
        [{"a": 1}, {"b": 2}],
    )
    assert merged == {"a": 1, "b": 2}
    assert conflicts == []


def test_merge_lists_concat_in_order():
    """disks 数组拼接:usage 段元素在前,io 段元素在后(等价旧 DISKS_ALL)。"""
    merged, _ = merge_inspection_fragments([
        {"disks": [{"mount": "/", "disk_used_pct": 42}]},
        {"disks": [{"mount": "sda[HDD]", "io_util_pct": 1.0}]},
    ])
    assert [e["mount"] for e in merged["disks"]] == ["/", "sda[HDD]"]


def test_merge_nested_dict_recursive():
    merged, _ = merge_inspection_fragments([
        {"net": {"rx": 1}}, {"net": {"tx": 2}},
    ])
    assert merged == {"net": {"rx": 1, "tx": 2}}


def test_merge_scalar_conflict_later_wins_and_recorded():
    merged, conflicts = merge_inspection_fragments([
        {"mem_used_pct": 50}, {"mem_used_pct": 60},
    ])
    assert merged["mem_used_pct"] == 60
    assert conflicts == ["mem_used_pct"]


def test_merge_empty_fragments_returns_empty():
    assert merge_inspection_fragments([]) == ({}, [])


def test_merge_linux_four_segments_matches_legacy_key_set():
    """回归:linux 四分段样例合并后顶层键集 == 改造前单体脚本输出键集。"""
    fragments = [
        {"disks": [{"mount": "/", "host_disk": "vda", "partition": "vda1",
                    "disk_index": 0, "disk_used_pct": 42}], "inode_used_pct": 3},
        {"disks": [{"mount": "vda[HDD]", "host_disk": "vda", "partition": "",
                    "disk_index": 0, "io_util_pct": 0.5, "io_await_ms": 1.2,
                    "disk_type": "hdd"}]},
        {"mem_used_pct": 55, "swap_used_pct": 0},
        {"cpu_idle_pct": 92.5, "cpu_iowait_pct": 0.3, "load_1m": 0.12},
    ]
    merged, _ = merge_inspection_fragments(fragments)
    assert set(merged) == {
        "disks", "inode_used_pct", "mem_used_pct", "swap_used_pct",
        "cpu_idle_pct", "cpu_iowait_pct", "load_1m",
    }
    assert len(merged["disks"]) == 2
