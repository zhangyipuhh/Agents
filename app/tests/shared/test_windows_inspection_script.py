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
    windows-ps-5.1 条目；输出键集合仍与 ``inspection_fields`` 一致。
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
            "uptime_hours",
        }
        configured_keys = {field["key"] for field in windows["inspection_fields"]}

        assert script.count("Get-WmiObject") == 2
        assert "Get-CimInstance" not in script
        assert "ConvertTo-Json" not in script
        assert "ConvertToDateTime" in script
        assert "JavaScriptSerializer" in script
        assert output_keys == configured_keys