# -*- coding:utf-8 -*-
"""Windows PowerShell 巡检脚本兼容性回归测试（2026-08-03 改造）。

2026-07-22：原测试通过遍历 ``data/devops/servers.yaml`` 的 Windows 节点读取
inspection_script / inspection_fields 字段；2026-08-03 巡检脚本库改造后：
- servers.yaml / servers.yaml.example 不再携带 inspection_script 原文，
  改为 inspection_script_name 引用脚本库条目；
- inspection_scripts.yaml.example 是脚本库模板，包含 windows-ps-5.1 节点
  的 inspection_script / inspection_fields 字段。
因此本测试改读 inspection_scripts.yaml.example，验证脚本库条目契约。
"""

from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_windows_inspection_scripts_support_legacy_powershell():
    """公开配置中的 Windows 脚本应兼容旧版 PowerShell 并保持 JSON 字段契约。

    2026-08-03 改造：检查项从 servers.yaml 迁移到 inspection_scripts.yaml.example 的
    windows-ps-5.1 条目；2026-08-15 扩展：新增磁盘 IO 采集段
    （Win32_PerfFormattedData_PerfDisk_PhysicalDisk 熟数据 + MSFT_PhysicalDisk
    介质探测），仍保持 Get-WmiObject-only，不引入 Get-CimInstance /
    Get-PhysicalDisk / ConvertTo-Json。

    2026-08-16 扩展：单个磁盘 IO 段必须额外输出 ``host_disk`` / ``disk_index``
    字段（按 Win32_DiskDrive.DeviceID 索引），兼容旧快照（缺字段时前端允许为空）。
    分区记录（Get-PSDrive 的 mount 段）也带 ``host_disk`` / ``disk_index`` /
    ``partition``，依据 WMI mount 关联（``0 C: D:[SSD]`` 文本解析）归入物理盘。
    """
    script_paths = [
        PROJECT_ROOT / "data" / "devops" / "inspection_scripts.yaml.example",
    ]

    for path in script_paths:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        windows = next(
            item for item in document["inspection_scripts"]
            if item.get("name") == "windows-ps-5.1"
        )
        script = windows["inspection_script"]
        output_keys = {
            "disk_used_pct",
            "mem_used_pct",
            "cpu_used_pct",
            "cpu_iowait_pct",
            "swap_used_pct",
            "inode_used_pct",
            "io_util_pct",
            "io_await_ms",
        }
        configured_keys = {field["key"] for field in windows["inspection_fields"]}

        # Get-WmiObject 调用次数动态匹配：基线 4 个类（OS / Processor / PhysicalDisk /
        # PerfDisk_PhysicalDisk）+ 2026-08-16 新增 Win32_DiskDrive（host_disk 索引），
        # 不能再硬编码 = 4。
        assert script.count("Get-WmiObject") >= 5
        assert "Get-CimInstance" not in script
        assert "Get-PhysicalDisk" not in script
        assert "ConvertTo-Json" not in script
        assert "ConvertToDateTime" in script
        assert "JavaScriptSerializer" in script
        # IO 采集段契约
        assert "MSFT_PhysicalDisk" in script
        assert "Win32_PerfFormattedData_PerfDisk_PhysicalDisk" in script
        assert "PercentDiskTime" in script
        assert "AvgDiskSecPerTransfer" in script
        assert "disk_type" in script
        # 2026-08-16 物理磁盘关联：新增 Win32_DiskDrive 索引 + host_disk / disk_index 字段
        assert "Win32_DiskDrive" in script
        assert "host_disk" in script
        assert "disk_index" in script
        assert output_keys == configured_keys
        await_rule = next(
            f for f in windows["inspection_fields"] if f["key"] == "io_await_ms"
        )
        assert await_rule["warn"] == 100 and await_rule["crit"] == 200
        assert await_rule["ssd_warn"] == 20 and await_rule["ssd_crit"] == 50