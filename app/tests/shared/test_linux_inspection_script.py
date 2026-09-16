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
    produced.discard("web_apps")
    # disks 数组元素承载 disk_used_pct / io_util_pct / io_await_ms
    # 2026-09-16 晚:web_apps 数组元素承载 web_app_cpu_pct / web_app_mem_mb /
    # web_app_qps / web_app_avg_response_ms(均与 inspection_fields 规则 key 一致)
    produced |= {
        "disk_used_pct", "io_util_pct", "io_await_ms",
        "web_app_cpu_pct", "web_app_mem_mb", "web_app_qps", "web_app_avg_response_ms",
    }
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


# ============================== 2026-09-16 新增 host_disk 推导测试 ==============================

import json
import os
import shutil
import subprocess


def _run_disk_usage_awk(df_input: str) -> list[dict]:
    """从 disk-usage 分段提取 awk 程序,在合成 df 输入下运行,返回解析出的 disks 元素列表。

    参数:
        df_input: 合成的 `df -P` 标准输出文本(包含表头行)

    返回:
        list[dict]: `disks` 数组元素列表,每个元素含 mount / host_disk / disk_used_pct 等

    异常:
        pytest.skip: 当前环境无 Git Bash / awk 时跳过(Windows 无 Git Bash 时 fallback)
    """
    script = _segment(_linux_group(), "disk-usage")["script"]
    # 提取 df -P | awk '...' 之间的 awk 程序(支持多行)
    match = re.search(r"df -P \| awk '(.*?)'\n", script, flags=re.DOTALL)
    if not match:
        match = re.search(r"awk '(.*?)'", script, flags=re.DOTALL)
    assert match, "disk-usage 分段中未找到 awk 程序"
    awk_program = match.group(1)
    # 通过 Git Bash + herestring 喂 awk(直接 awk.exe 在 Windows 下 stdin 行为不可靠;
    # shutil.which("bash") 在 Windows 上会优先返回 system32\bash.EXE — 那不是 Git Bash,跳过)
    bash_candidates = [
        shutil.which("bash"),
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        "/usr/bin/bash",
        "/bin/bash",
    ]
    bash_bin = None
    for cand in bash_candidates:
        if not cand:
            continue
        # 排除 system32\bash.EXE(Win10 Ubuntu on Windows,不是 Git Bash)
        if "system32" in cand.lower():
            continue
        if os.path.isfile(cand):
            bash_bin = cand
            break
    if not bash_bin:
        import pytest
        pytest.skip("当前环境无 Git Bash,跳过 host_disk 推导解析测试")
    bash_script = (
        "/usr/bin/awk '" + awk_program.replace("'", "'\\''") + "' <<'EOF'\n"
        + df_input + "\nEOF\n"
    )
    proc = subprocess.run(
        [bash_bin, "-c", bash_script],
        capture_output=True, text=True, timeout=10,
        env={**os.environ, "PATH": r"C:\Program Files\Git\usr\bin;C:\Program Files\Git\mingw64\bin"},
    )
    assert proc.returncode == 0, f"awk 失败: stderr={proc.stderr}"
    raw = proc.stdout.strip()
    if not raw:
        return []
    wrapped = "[" + raw + "]"
    return json.loads(wrapped)


def test_disk_usage_recognizes_raid_lvm_zram():
    """扩展识别覆盖 zram / dm- / loop / md / drbd 五种虚拟 / 软件 RAID 设备。

    Returns:
        None

    Raises:
        AssertionError: 任一设备 host_disk 推导不符合预期时失败
    """
    # 注意:Capacity 列采用「数字 + 可选 %」形式(兼容 Git Bash 与 Linux df -P)
    df_input = (
        "Filesystem      1024-blocks    Used Available Capacity Mounted on\n"
        "/dev/sda1           100000   50000     50000      50 /\n"
        "/dev/nvme0n1p1      200000  100000    100000      50 /data\n"
        "/dev/mmcblk0p1       30000   10000     20000      33 /boot\n"
        "/dev/zram0           16384    4096     12288      25 /swap0\n"
        "/dev/dm-0           500000  200000    300000      40 /lvm0\n"
        "/dev/loop0            8192    1024      7168      13 /snap0\n"
        "/dev/md0            800000  400000    400000      50 /raid0\n"
        "/dev/drbd0          900000  450000    450000      50 /drbd0\n"
    )
    disks = _run_disk_usage_awk(df_input)
    by_mount = {d["mount"]: d for d in disks}
    # 标准物理盘(回归基线)
    assert by_mount["/"]["host_disk"] == "sda"
    assert by_mount["/"]["partition"] == "sda1"
    assert by_mount["/data"]["host_disk"] == "nvme0n1"
    assert by_mount["/data"]["partition"] == "nvme0n1p1"
    assert by_mount["/boot"]["host_disk"] == "mmcblk0"
    assert by_mount["/boot"]["partition"] == "mmcblk0p1"
    # 新增识别:zram / dm- / loop / md / drbd 整盘
    assert by_mount["/swap0"]["host_disk"] == "zram"
    assert by_mount["/swap0"]["partition"] == "zram0"
    assert by_mount["/lvm0"]["host_disk"] == "dm-0"
    assert by_mount["/lvm0"]["partition"] == ""
    assert by_mount["/snap0"]["host_disk"] == "loop0"
    assert by_mount["/snap0"]["partition"] == ""
    assert by_mount["/raid0"]["host_disk"] == "md0"
    assert by_mount["/raid0"]["partition"] == ""
    assert by_mount["/drbd0"]["host_disk"] == "drbd0"
    assert by_mount["/drbd0"]["partition"] == ""


def test_disk_usage_orphan_for_virtual_devices():
    """虚拟 / 网络 / 容器设备 → host_disk 主动入 _orphan_ 虚拟组。

    Returns:
        None

    Raises:
        AssertionError: 虚拟设备未主动入 _orphan_ 时失败
    """
    df_input = (
        "Filesystem      1024-blocks    Used Available Capacity Mounted on\n"
        "overlay           100000   50000     50000      50 /var/lib/container\n"
        "fuse.mergerfs     200000  100000    100000      50 /mnt/merge\n"
        "127.0.0.1:/vol    300000  150000    150000      50 /mnt/nfs\n"
        "none                 100       50        50      50 /sys/fs/cgroup\n"
    )
    # 注:tmpfs 会被 line 34 的正则前缀过滤掉,不进入 awk 主逻辑;
    # 本测试只覆盖「能走到主分支的虚拟设备」——overlay / fuse / 127.0.0.1 / none
    disks = _run_disk_usage_awk(df_input)
    by_mount = {d["mount"]: d for d in disks}
    assert by_mount["/var/lib/container"]["host_disk"] == "_orphan_"
    assert by_mount["/var/lib/container"]["partition"] == "/var/lib/container"
    assert by_mount["/mnt/merge"]["host_disk"] == "_orphan_"
    assert by_mount["/mnt/merge"]["partition"] == "/mnt/merge"
    assert by_mount["/mnt/nfs"]["host_disk"] == "_orphan_"
    assert by_mount["/mnt/nfs"]["partition"] == "/mnt/nfs"
    assert by_mount["/sys/fs/cgroup"]["host_disk"] == "_orphan_"
    assert by_mount["/sys/fs/cgroup"]["partition"] == "/sys/fs/cgroup"


def test_disk_usage_regression_std_dev():
    """回归基线:标准 /dev/sda1 / /dev/nvme0n1p1 / /dev/mmcblk0p1 推导与老行为完全一致。

    Returns:
        None

    Raises:
        AssertionError: 标准设备 host_disk / partition 推导与老行为不一致时失败
    """
    df_input = (
        "Filesystem      1024-blocks    Used Available Capacity Mounted on\n"
        "/dev/sda1           100000   50000     50000      50 /\n"
        "/dev/sda2           100000   10000     90000      10 /var\n"
        "/dev/nvme0n1p1      200000  100000    100000      50 /data\n"
        "/dev/nvme0n1p2      200000   20000    180000      10 /data2\n"
        "/dev/mmcblk0p1       30000   10000     20000      33 /boot\n"
    )
    disks = _run_disk_usage_awk(df_input)
    by_mount = {d["mount"]: d for d in disks}
    # 回归:hd=物理盘裸名(不带 /dev/),part=分区全名
    assert by_mount["/"]["host_disk"] == "sda"
    assert by_mount["/"]["partition"] == "sda1"
    assert by_mount["/"]["disk_index"] == 0
    assert by_mount["/"]["disk_used_pct"] == 50
    assert by_mount["/var"]["host_disk"] == "sda"
    assert by_mount["/var"]["partition"] == "sda2"
    assert by_mount["/data"]["host_disk"] == "nvme0n1"
    assert by_mount["/data"]["partition"] == "nvme0n1p1"
    assert by_mount["/data2"]["host_disk"] == "nvme0n1"
    assert by_mount["/data2"]["partition"] == "nvme0n1p2"
    assert by_mount["/boot"]["host_disk"] == "mmcblk0"
    assert by_mount["/boot"]["partition"] == "mmcblk0p1"


# ============================== 2026-09-16 晚:web-server 分段契约测试 ==============================


def test_web_server_segment_scans_tomcat_paths():
    """web-server 分段应扫描常见 Tomcat 安装路径并解析 server.xml / webapps。

    Returns:
        None

    Raises:
        AssertionError: 关键路径 / 关键词缺失时失败
    """
    script = _segment(_linux_group(), "web-server")["script"]
    assert "catalina.sh" in script
    assert "server.xml" in script
    assert "webapps" in script
    assert "/opt" in script
    assert "/usr/local" in script


def test_web_server_segment_outputs_web_apps_array_with_required_keys():
    """web-server 分段输出 JSON 应含 web_apps 数组 + 必备字段。

    2026-09-16 晚:元素键名与 inspection_fields 规则 key 对齐
    (web_app_cpu_pct / web_app_mem_mb / web_app_qps / web_app_avg_response_ms),
    便于评估器 _expand_array 路径按数组展开评估。

    Returns:
        None

    Raises:
        AssertionError: 输出键缺失时失败
    """
    script = _segment(_linux_group(), "web-server")["script"]
    assert "web_apps" in script
    # 必备元数据字段
    for required in (
        "app_name",
        "server_type",
        "host",
        "port",
        "status",
        "worker_count",
        "jvm_heap_used_pct",
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
    assert '"server_type":"tomcat"' in script


def test_web_server_segment_posix_only_no_bash4_process_substitution():
    """web-server 分段必须保持 POSIX 兼容,禁止 bash4+ 进程替换 ``<(``。

    Returns:
        None

    Raises:
        AssertionError: 出现 bash4+ 语法时失败(沿用既有约束)
    """
    script = _segment(_linux_group(), "web-server")["script"]
    assert "<(" not in script


def test_web_server_segment_declares_segment_key_and_order():
    """web-server 段必须在 linux-bash 组中以 segment_key=web-server 形式声明。

    Returns:
        None

    Raises:
        AssertionError: 段键缺失或未加入组时失败
    """
    group = _linux_group()
    keys = [s["segment_key"] for s in group["segments"]]
    assert "web-server" in keys
    seg = _segment(group, "web-server")
    assert seg["sort_order"] >= 40  # cpu 段是 40,web-server 排后面


def test_linux_inspection_fields_includes_web_app_rules():
    """linux-bash inspection_fields 必须含 4 条 web_app_* 规则。

    Returns:
        None

    Raises:
        AssertionError: 规则缺失时失败
    """
    group = _linux_group()
    keys = {f["key"] for f in group["inspection_fields"]}
    expected = {
        "web_app_cpu_pct",
        "web_app_mem_mb",
        "web_app_qps",
        "web_app_avg_response_ms",
    }
    assert expected <= keys
    cpu_rule = next(f for f in group["inspection_fields"] if f["key"] == "web_app_cpu_pct")
    assert cpu_rule["warn"] == 60
    assert cpu_rule["crit"] == 85
    assert cpu_rule["direction"] == "high"
