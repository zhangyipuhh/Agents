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
    produced.discard("web_apps")
    # disks 数组元素承载 disk_used_pct / io_util_pct / io_await_ms
    # 2026-09-16 晚:web_apps 数组元素承载 web_app_cpu_pct / web_app_mem_mb /
    # web_app_qps / web_app_avg_response_ms(均与 inspection_fields 规则 key 一致)
    produced |= {
        "disk_used_pct", "io_util_pct", "io_await_ms",
        "web_app_cpu_pct", "web_app_mem_mb", "web_app_qps", "web_app_avg_response_ms",
    }
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


# ============================== 2026-09-16 晚:web-server 分段契约测试 ==============================


def test_windows_web_server_segment_queries_iis():
    """windows-ps-5.1 web-server 分段必须用 Get-Website / WebAdministration 拿 IIS 信息。

    Returns:
        None

    Raises:
        AssertionError: 关键 IIS cmdlet 缺失时失败
    """
    script = _segment(_windows_group(), "web-server")["script"]
    assert "Get-Website" in script
    assert "Get-WebApplication" in script
    assert "WebAdministration" in script
    assert "Get-Counter" in script
    # 性能计数器路径(IIS Web Service 全局)
    assert "Web Service" in script


def test_windows_web_server_segment_queries_tomcat():
    """windows-ps-5.1 web-server 分段必须通过 Get-WmiObject Win32_Service 找 Tomcat。

    Returns:
        None

    Raises:
        AssertionError: Tomcat 服务发现 / 路径解析关键词缺失时失败
    """
    script = _segment(_windows_group(), "web-server")["script"]
    assert "Win32_Service" in script
    assert "Tomcat" in script
    # 路径 / webapps / server.xml
    assert "webapps" in script
    assert "server.xml" in script
    assert "catalina.bat" in script


def test_windows_web_server_segment_outputs_web_apps_array():
    """windows-ps-5.1 web-server 分段输出 JSON 必须含 web_apps 数组与必备字段。

    2026-09-16 晚:元素键名与 inspection_fields 规则 key 对齐
    (web_app_cpu_pct / web_app_mem_mb / web_app_qps / web_app_avg_response_ms),
    便于评估器 _expand_array 路径按数组展开评估。

    Returns:
        None

    Raises:
        AssertionError: 输出键 / server_type 缺失时失败
    """
    script = _segment(_windows_group(), "web-server")["script"]
    assert "web_apps" in script
    # 元数据字段
    for required in (
        "app_name",
        "server_type",
        "host",
        "port",
        "status",
        "worker_count",
    ):
        assert required in script, f"web-server 段输出缺元数据字段: {required}"
    # 评估器契约:4 个 web_app_* 键名与 inspection_fields 规则 key 一致
    for required in (
        "web_app_cpu_pct",
        "web_app_mem_mb",
        "web_app_qps",
        "web_app_avg_response_ms",
    ):
        assert required in script, f"web-server 段输出缺评估键: {required}"
    # 至少声明 iis 与 tomcat 两种 server_type
    assert '"server_type":"iis"' in script
    assert '"server_type":"tomcat"' in script


def test_windows_web_server_segment_keeps_ps51_compatibility():
    """windows-ps-5.1 web-server 段不能引入新版 cmdlet(ConvertTo-Json / Get-CimInstance)。

    Returns:
        None

    Raises:
        AssertionError: 出现 PowerShell 6+ 专属 cmdlet 时失败(沿用既有约束)
    """
    script = _segment(_windows_group(), "web-server")["script"]
    assert "ConvertTo-Json" not in script
    assert "Get-CimInstance" not in script


def test_windows_inspection_fields_includes_web_app_rules():
    """windows-ps-5.1 inspection_fields 必须含 4 条 web_app_* 规则。

    Returns:
        None

    Raises:
        AssertionError: 规则缺失或阈值不一致时失败
    """
    group = _windows_group()
    keys = {f["key"] for f in group["inspection_fields"]}
    expected = {
        "web_app_cpu_pct",
        "web_app_mem_mb",
        "web_app_qps",
        "web_app_avg_response_ms",
    }
    assert expected <= keys
    mem_rule = next(f for f in group["inspection_fields"] if f["key"] == "web_app_mem_mb")
    assert mem_rule["warn"] == 2048
    assert mem_rule["crit"] == 4096
    resp_rule = next(
        f for f in group["inspection_fields"] if f["key"] == "web_app_avg_response_ms"
    )
    assert resp_rule["warn"] == 500
    assert resp_rule["crit"] == 2000
