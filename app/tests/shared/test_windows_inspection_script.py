# -*- coding:utf-8 -*-
"""Windows PowerShell 巡检脚本兼容性回归测试。"""

from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_windows_inspection_scripts_support_legacy_powershell():
    """公开配置中的 Windows 脚本应兼容旧版 PowerShell 并保持 JSON 字段契约。"""
    script_paths = [
        PROJECT_ROOT / "data" / "devops" / "servers.yaml",
        PROJECT_ROOT / "data" / "devops" / "servers.yaml.example",
    ]

    for path in script_paths:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        windows = next(
            item for item in document["servers"] if item["server_type"] == "windows"
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
