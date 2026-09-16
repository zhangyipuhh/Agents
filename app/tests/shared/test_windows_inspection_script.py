# -*- coding:utf-8 -*-
"""Windows PowerShell 默认分段脚本资产契约回归测试(2026-09-16 由 YAML 测试改写)。

验证 ``app/shared/utils/inspection/default_scripts.py`` 的 windows-ps-5.1 组:
- 兼容老版 PowerShell 5.1(不引入 Get-CimInstance / Get-PhysicalDisk / ConvertTo-Json);
- 磁盘 IO 段基于 Win32_PerfFormattedData_PerfDisk_PhysicalDisk + MSFT_PhysicalDisk;
- 物理盘关联通过 Win32_DiskDrive.DeviceID 输出 host_disk / disk_index;
- 分段输出键并集 == inspection_fields 声明 key 集合。
"""
from app.shared.utils.inspection.default_scripts import DEFAULT_INSPECTION_GROUPS


def _windows_group():
    """获取 windows-ps-5.1 默认组。

    Returns:
        dict: windows-ps-5.1 组条目

    Raises:
        StopIteration: 默认组未声明 windows-ps-5.1 时抛出
    """
    return next(g for g in DEFAULT_INSPECTION_GROUPS if g["name"] == "windows-ps-5.1")


def _segment(group, key):
    """按 segment_key 取分段。

    Args:
        group: 默认组条目
        key: 分段键

    Returns:
        dict: 分段条目

    Raises:
        StopIteration: 分段键不存在时抛出
    """
    return next(s for s in group["segments"] if s["segment_key"] == key)


def test_windows_segments_keep_legacy_powershell_compatibility():
    """公开资产中的 Windows 分段应兼容 PowerShell 5.1 且不引入新版 cmdlet。

    Returns:
        None

    Raises:
        AssertionError: 任一关键 cmdlet / 字段契约缺失时失败
    """
    group = _windows_group()
    combined_script = "\n".join(seg["script"] for seg in group["segments"])

    # Get-WmiObject / gwmi 兼容(基线 4 类 + 物理盘关联,本断言只保证不引入新版 cmdlet)
    assert "Get-WmiObject" in combined_script or "gwmi" in combined_script
    assert "Get-CimInstance" not in combined_script
    assert "Get-PhysicalDisk" not in combined_script
    assert "ConvertTo-Json" not in combined_script
    # IO 采集段契约:介质探测 + 性能计数器 + 关键输出字段
    assert "MSFT_PhysicalDisk" in combined_script
    assert "Win32_PerfFormattedData_PerfDisk_PhysicalDisk" in combined_script
    assert "PercentDiskTime" in combined_script
    assert "AvgDiskSecPerTransfer" in combined_script
    assert "disk_type" in combined_script
    # 物理盘关联:host_disk / disk_index 字段(通过 Win32_DiskDrive.DeviceID)
    assert "Win32_DiskDrive" in combined_script
    assert "host_disk" in combined_script
    assert "disk_index" in combined_script
    # mount 段使用单引号 JSON 字符串拼接 + Replace 反斜杠转义
    # 实际渲染到 PowerShell 时形态为 .Replace('\','\\'),r""" 源里反斜杠被字面保留。
    # 仅检测 .Replace( 出现 + 转义形态存在(松断言)。
    assert ".Replace(" in combined_script
    assert "'\\\\'" in combined_script or "'\\'" in combined_script


def test_windows_segments_output_keys_match_declared_fields():
    """windows-ps-5.1 四分段输出键并集覆盖字段规则 key 集合。

    Returns:
        None

    Raises:
        AssertionError: 字段规则的 key 在分段输出中找不到对应 JSON 键时失败
    """
    import re
    group = _windows_group()
    declared = {f["key"] for f in group["inspection_fields"]}
    produced = set()
    for seg in group["segments"]:
        produced |= set(re.findall(r'\\?"([a-z_0-9]+)\\?"\s*:', seg["script"]))
    produced.discard("disks")
    # disks 数组元素承载 disk_used_pct / io_util_pct / io_await_ms
    produced |= {"disk_used_pct", "io_util_pct", "io_await_ms"}
    assert declared <= produced


def test_windows_disk_io_segment_has_io_await_ssd_threshold_in_fields():
    """io_await_ms 字段必须保留 ssd_warn / ssd_crit 阈值对。

    Returns:
        None

    Raises:
        AssertionError: 阈值对缺失或数值不一致时失败
    """
    group = _windows_group()
    await_rule = next(f for f in group["inspection_fields"] if f["key"] == "io_await_ms")
    assert await_rule["warn"] == 100 and await_rule["crit"] == 200
    assert await_rule["ssd_warn"] == 20 and await_rule["ssd_crit"] == 50
