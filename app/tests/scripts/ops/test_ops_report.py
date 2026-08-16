# -*- coding:utf-8 -*-
"""``app.scripts.ops.ops_report`` 单元测试。"""
from datetime import datetime

from app.shared.utils.report.word.config import (
    ReportConfig, SectionConfig, TableSectionConfig,
)
from app.scripts.ops.ops_report import OpsSummary, OpsAlerts, OpsAlertItem, compute_ops_summary
from app.scripts.ops.ops_report import compute_ops_alerts
from app.scripts.ops.ops_report import resolve_server_ip_map
from app.scripts.ops.ops_report import build_ops_report_config
from app.scripts.ops.ops_report import build_ops_email_body
from app.scripts.api_check import ApiCheckItem, ApiCheckReport
from app.scripts.server_ops import ServerOpsItem, ServerOpsReport


def _server(biz, status="pass", success=True, skipped=False):
    return ServerOpsItem(
        business_name=biz, success=success, inspection_status=status, skipped=skipped,
    )


def _api(node_id, name, check_passed=True):
    return ApiCheckItem(node_id=node_id, name=name, path="/x", check_passed=check_passed)


def test_ops_summary_dataclass_basic():
    s = OpsSummary(
        total=5, passed=3, problem=2,
        server_total=3, server_passed=2, server_problem=1,
        server_failed_count=1, server_warn_count=1, server_crit_count=0,
        api_total=2, api_passed=1, api_problem=1,
    )
    assert s.total == 5
    assert s.passed == 3
    assert s.problem == 2


def test_ops_alerts_is_empty():
    assert OpsAlerts(server_warn_crit=[], api_failed=[]).is_empty is True
    a = OpsAlerts(
        server_warn_crit=[OpsAlertItem(business="x", metric="y", value="z",
                                       threshold="-", status="WARN", detail="")],
        api_failed=[],
    )
    assert a.is_empty is False


def test_compute_summary_all_passed():
    srv = ServerOpsReport(items=[_server("A"), _server("B")])
    api = ApiCheckReport(items=[_api("1", "X"), _api("2", "Y")])
    s = compute_ops_summary(srv, api)
    assert s.total == 4 and s.passed == 4 and s.problem == 0
    assert s.server_total == 2 and s.server_passed == 2 and s.server_problem == 0
    assert s.api_total == 2 and s.api_passed == 2 and s.api_problem == 0


def test_compute_summary_with_failures():
    srv = ServerOpsReport(items=[
        _server("A", "pass", True),
        _server("B", "crit", False),
        _server("C", "skipped", None, skipped=True),
    ])
    api = ApiCheckReport(items=[
        _api("1", "X", check_passed=True),
        _api("2", "Y", check_passed=False),
        _api("3", "Z", check_passed=None),
    ])
    s = compute_ops_summary(srv, api)
    assert s.total == 6
    assert s.server_passed == 1 and s.server_problem == 2
    assert s.server_failed_count == 2  # B(crit,fail) + C(skipped)
    assert s.server_crit_count == 1
    assert s.api_passed == 1 and s.api_problem == 2


def test_compute_summary_empty():
    s = compute_ops_summary(ServerOpsReport(), ApiCheckReport())
    assert s.total == 0 and s.passed == 0 and s.problem == 0


def test_compute_alerts_warn_crit_only():
    srv = ServerOpsReport(items=[
        ServerOpsItem(
            business_name="A", success=True, inspection_status="pass",
            field_results=[
                {"key": "cpu", "name_zh": "CPU 使用率", "unit": "%",
                 "value": 75.2, "warn": 80, "crit": 90,
                 "status": "warn", "message": ""},
                {"key": "disk", "name_zh": "磁盘使用率", "unit": "%",
                 "value": 92.0, "warn": 80, "crit": 90,
                 "status": "crit", "message": "磁盘 /data"},
            ],
        ),
        ServerOpsItem(
            business_name="B", success=True, inspection_status="pass",
            field_results=[
                {"key": "cpu", "name_zh": "CPU 使用率", "unit": "%",
                 "value": 30.0, "warn": 80, "crit": 90,
                 "status": "pass", "message": ""},
            ],
        ),
    ])
    api = ApiCheckReport(items=[
        ApiCheckItem(node_id="1", name="OK", path="/ok", check_passed=True),
        ApiCheckItem(node_id="2", name="FAIL", path="/x", check_passed=False,
                     http_status=500, duration_ms=30),
    ])
    alerts = compute_ops_alerts(srv, api)
    assert len(alerts.server_warn_crit) == 2
    assert alerts.server_warn_crit[0].business == "A"
    assert alerts.server_warn_crit[0].status == "WARN"
    assert alerts.server_warn_crit[1].status == "CRIT"
    assert len(alerts.api_failed) == 1
    assert alerts.api_failed[0].business == "FAIL"
    assert alerts.api_failed[0].status == "FAIL"
    # value 与 detail 现在包含 URL + 耗时,便于排障
    assert "HTTP 500" in alerts.api_failed[0].value
    assert "/x" in alerts.api_failed[0].value
    assert "接口地址" in alerts.api_failed[0].detail
    assert "/x" in alerts.api_failed[0].detail
    assert "30ms" in alerts.api_failed[0].detail
    assert alerts.is_empty is False


def test_compute_alerts_excludes_skipped_and_missing():
    srv = ServerOpsReport(items=[
        ServerOpsItem(business_name="A", success=False, skipped=True,
                      inspection_status="skipped"),
    ])
    api = ApiCheckReport(items=[
        ApiCheckItem(node_id="1", name="M", path="/x", check_passed=None),
    ])
    alerts = compute_ops_alerts(srv, api)
    assert alerts.server_warn_crit == []
    assert alerts.api_failed == []
    assert alerts.is_empty is True


# --------------------------------------------------------------------------
# resolve_server_ip_map 反查 IP
# --------------------------------------------------------------------------

class _FakeService:
    """最小桩:模拟 DevOpsServerService.get_connection_config。"""

    def __init__(self, mapping):
        self._mapping = mapping

    def get_connection_config(self, biz):
        if biz in self._mapping:
            return {"host": self._mapping[biz]}
        raise KeyError(biz)


def test_resolve_ip_map_returns_hosts():
    srv = ServerOpsReport(items=[
        ServerOpsItem(business_name="A"),
        ServerOpsItem(business_name="B"),
    ])
    svc = _FakeService({"A": "10.0.0.1", "B": "10.0.0.2"})
    m = resolve_server_ip_map(svc, srv)
    assert m == {"A": "10.0.0.1", "B": "10.0.0.2"}


def test_resolve_ip_map_handles_missing_service():
    srv = ServerOpsReport(items=[ServerOpsItem(business_name="A")])
    m = resolve_server_ip_map(None, srv)
    assert m == {"A": None}


def test_resolve_ip_map_handles_key_error():
    srv = ServerOpsReport(items=[ServerOpsItem(business_name="X")])
    svc = _FakeService({})
    m = resolve_server_ip_map(svc, srv)
    assert m == {"X": None}


def test_resolve_ip_map_handles_exception():
    class _Boom:
        def get_connection_config(self, biz):
            raise RuntimeError("boom")
    srv = ServerOpsReport(items=[ServerOpsItem(business_name="X")])
    m = resolve_server_ip_map(_Boom(), srv)
    assert m == {"X": None}


def test_resolve_ip_map_reads_ip_field():
    """真实 DevOpsServerService 返回 ip 字段,非 host。

    参见 ``app/shared/utils/devops_server_service.py:357``:`get_connection_config`
    返回的 dict 包含 ``ip`` 键,旧版代码只读 ``host`` 会导致所有 IP 都为 None。
    """
    class _RealLikeService:
        def get_connection_config(self, biz):
            return {"ip": "10.0.0.5", "port": 22, "username": "u"}

    srv = ServerOpsReport(items=[ServerOpsItem(business_name="A")])
    m = resolve_server_ip_map(_RealLikeService(), srv)
    assert m == {"A": "10.0.0.5"}


def test_resolve_ip_map_prefers_ip_over_host_alias():
    """``ip`` 字段优先于 ``host`` 别名,避免被历史别名字段误导。"""
    class _MixedService:
        def get_connection_config(self, biz):
            return {"ip": "10.0.0.7", "host": "192.168.0.1", "port": 22}

    srv = ServerOpsReport(items=[ServerOpsItem(business_name="A")])
    m = resolve_server_ip_map(_MixedService(), srv)
    assert m == {"A": "10.0.0.7"}


# --------------------------------------------------------------------------
# build_ops_report_config 报告配置构造
# --------------------------------------------------------------------------

def _build_summary():
    return compute_ops_summary(ServerOpsReport(items=[
        ServerOpsItem(business_name="A", success=True, inspection_status="pass"),
    ]), ApiCheckReport())


def test_build_report_config_structure():
    summary = _build_summary()
    alerts = compute_ops_alerts(ServerOpsReport(), ApiCheckReport())
    cfg = build_ops_report_config(
        summary=summary,
        alerts=alerts,
        server_report=ServerOpsReport(items=[
            ServerOpsItem(business_name="A", success=True, inspection_status="pass"),
        ]),
        api_report=ApiCheckReport(),
        ip_map={"A": "10.0.0.1"},
        schedule_name="运维巡检",
        started_at=datetime(2026, 7, 22, 15, 0, 0),
    )
    assert isinstance(cfg, ReportConfig)
    titles = [s.content for s in cfg.sections if s.section_type == "heading"]
    assert "一、综述" in titles
    assert "二、网络检查" in titles
    assert "三、服务器基本情况" in titles
    assert "四、接口健康检查" in titles
    # 业务名作为二级标题
    assert "A" in titles
    # 表格 SectionConfig
    tables = [s for s in cfg.sections if s.section_type == "table"]
    assert len(tables) >= 1
    # 封面标题
    assert cfg.cover is not None
    assert cfg.cover.title.text == "沈阳不动产运维报告"


def test_build_report_includes_disk_inventory_table():
    """parsed_values 含异构 disks 数组时生成磁盘介质清单表（6 列, 按 host_disk 分组）。

    2026-08-16 改造: 按 ``host_disk`` 分组渲染, 每组 1 行 sub-header + N 行
    partition/IO 数据。本用例覆盖:
        * 4 元素分属 2 个 host_disk（vda / sda）→ 2 组, 共 2 sub-header + 4 数据行 = 6 行
        * df 元素（无 disk_type）介质列 = '-'
        * io 元素 mount 尾部 [SSD] 标签剥离, 介质列显示 SSD
        * 非 Mapping 噪音元素跳过
        * sub-header 行介质列: 单介质 → "SSD" / "-"; 介质汇总独立在 col 2
        * sub-header 行 col 3~6 全为 "-"

    Returns:
        None
    """
    item = ServerOpsItem(
        business_name="A", success=True, inspection_status="pass",
        parsed_values={"disks": [
            {"mount": "/", "disk_used_pct": 42, "host_disk": "vda",
             "disk_index": 0, "partition": ""},
            {"mount": "sda[SSD]", "io_util_pct": 12.3, "io_await_ms": 4.5,
             "disk_type": "ssd", "host_disk": "sda", "disk_index": 0,
             "partition": ""},
            "noise",
        ]},
    )
    config = build_ops_report_config(
        summary=OpsSummary(), alerts=OpsAlerts(),
        server_report=ServerOpsReport(items=[item]),
        api_report=ApiCheckReport(),
        ip_map={}, schedule_name="t", started_at=datetime(2026, 8, 15),
    )
    inventory = [
        s.table for s in config.sections
        if s.section_type == "table"
        and s.table.headers == [
            "物理盘", "设备/挂载点", "介质", "磁盘使用率", "IO 利用率", "IO 平均等待"
        ]
    ]
    assert len(inventory) == 1
    rows = inventory[0].rows
    # 2 组（vda / sda）→ 2 sub-header + 2 数据行 = 4 行
    assert len(rows) == 4
    # 第 1 组 vda: sub-header + 1 数据行
    assert rows[0] == ["vda", "-", "-", "-", "-", "-"]   # sub-header
    assert rows[1] == ["vda", "/", "-", "42%", "-", "-"]  # df 元素
    # 第 2 组 sda: sub-header + 1 数据行
    assert rows[2] == ["sda", "SSD", "-", "-", "-", "-"]  # sub-header (组内介质汇总)
    assert rows[3] == ["sda", "sda", "SSD", "-", "12.3%", "4.5 ms"]  # io 元素


def test_build_report_disk_inventory_groups_same_host_disk():
    """同 host_disk 多元素（多 partition + IO）合并到同一组, sub-header 只出现一次。

    验证分组语义核心: 同一 host_disk 下的 df / io 元素归到同一 sub-header 之下,
    介质汇总 "SSD+HDD" 拼接两种介质（脚本未提供 HDD 场景, 改用仅一种介质验证单值）;
    disk_index 升序: disk_index=0 排在 disk_index=2 之前。

    Returns:
        None
    """
    item = ServerOpsItem(
        business_name="A", success=True, inspection_status="pass",
        parsed_values={"disks": [
            {"mount": "/", "disk_used_pct": 42, "host_disk": "sda",
             "disk_index": 0, "partition": "sda1"},
            {"mount": "/data", "disk_used_pct": 78, "host_disk": "sda",
             "disk_index": 0, "partition": "sda2"},
            {"mount": "sda[SSD]", "io_util_pct": 12.3, "io_await_ms": 4.5,
             "disk_type": "ssd", "host_disk": "sda", "disk_index": 0,
             "partition": ""},
        ]},
    )
    config = build_ops_report_config(
        summary=OpsSummary(), alerts=OpsAlerts(),
        server_report=ServerOpsReport(items=[item]),
        api_report=ApiCheckReport(),
        ip_map={}, schedule_name="t", started_at=datetime(2026, 8, 16),
    )
    inventory = [
        s.table for s in config.sections
        if s.section_type == "table"
        and s.table.headers == [
            "物理盘", "设备/挂载点", "介质", "磁盘使用率", "IO 利用率", "IO 平均等待"
        ]
    ]
    rows = inventory[0].rows
    # 1 组 → 1 sub-header + 3 数据行 = 4 行
    assert len(rows) == 4
    # sub-header: 介质汇总 "SSD" (单介质)
    assert rows[0] == ["sda", "SSD", "-", "-", "-", "-"]
    # 数据行: mount 字典序? mount 升序; 但脚本按出现顺序保留; 同 disk_index=0 按 mount 字典序
    # 排序键为 (0, "/"), (0, "/data"), (0, "sda[SSD]" 剥离后 "sda")
    # 字典序: "/" < "/data" < "sda"
    data_rows = rows[1:]
    assert data_rows[0] == ["sda1", "/", "-", "42%", "-", "-"]
    assert data_rows[1] == ["sda2", "/data", "-", "78%", "-", "-"]
    assert data_rows[2] == ["sda", "sda", "SSD", "-", "12.3%", "4.5 ms"]


def test_build_report_disk_inventory_groups_multiple_host_disks():
    """多 host_disk 分组: 验证组间排序 (disk_index 升序) + 介质汇总。

    2 个 host_disk（nvme0n1 排前, sda 排后; 都含 SSD 元素）→ 2 sub-header + 4 数据行 = 6 行;
    sub-header 介质列单介质 → "SSD"; disk_index 验证组间排序。

    Returns:
        None
    """
    item = ServerOpsItem(
        business_name="A", success=True, inspection_status="pass",
        parsed_values={"disks": [
            {"mount": "sda[SSD]", "io_util_pct": 12.3, "io_await_ms": 4.5,
             "disk_type": "ssd", "host_disk": "sda", "disk_index": 1,
             "partition": ""},
            {"mount": "/", "disk_used_pct": 42, "host_disk": "sda",
             "disk_index": 1, "partition": "sda1"},
            {"mount": "nvme0n1[SSD]", "io_util_pct": 8.1, "io_await_ms": 2.3,
             "disk_type": "ssd", "host_disk": "nvme0n1", "disk_index": 0,
             "partition": ""},
            {"mount": "/", "disk_used_pct": 30, "host_disk": "nvme0n1",
             "disk_index": 0, "partition": "nvme0n1p1"},
        ]},
    )
    config = build_ops_report_config(
        summary=OpsSummary(), alerts=OpsAlerts(),
        server_report=ServerOpsReport(items=[item]),
        api_report=ApiCheckReport(),
        ip_map={}, schedule_name="t", started_at=datetime(2026, 8, 16),
    )
    inventory = [
        s.table for s in config.sections
        if s.section_type == "table"
        and s.table.headers == [
            "物理盘", "设备/挂载点", "介质", "磁盘使用率", "IO 利用率", "IO 平均等待"
        ]
    ]
    rows = inventory[0].rows
    # 2 组 → 2 sub-header + 4 数据行 = 6 行
    assert len(rows) == 6
    # 组间按 disk_index 升序: nvme0n1 (idx=0) 在前, sda (idx=1) 在后
    assert rows[0] == ["nvme0n1", "SSD", "-", "-", "-", "-"]  # sub-header
    # nvme0n1 组数据行: disk_index=0 内 (0, "/"), (0, "nvme0n1[SSD]" 剥离后 "nvme0n1")
    assert rows[1] == ["nvme0n1p1", "/", "-", "30%", "-", "-"]
    assert rows[2] == ["nvme0n1", "nvme0n1", "SSD", "-", "8.1%", "2.3 ms"]
    # sda 组
    assert rows[3] == ["sda", "SSD", "-", "-", "-", "-"]  # sub-header
    assert rows[4] == ["sda1", "/", "-", "42%", "-", "-"]
    assert rows[5] == ["sda", "sda", "SSD", "-", "12.3%", "4.5 ms"]


def test_build_report_disk_inventory_orphan_group_for_missing_host_disk():
    """部分元素缺 host_disk → 归入 _orphan_ 虚拟组, 排在最后, 不与有 host_disk 元素混组。

    Returns:
        None
    """
    item = ServerOpsItem(
        business_name="A", success=True, inspection_status="pass",
        parsed_values={"disks": [
            {"mount": "/", "disk_used_pct": 42, "host_disk": "sda",
             "disk_index": 0, "partition": ""},
            {"mount": "sda[SSD]", "io_util_pct": 12.3, "io_await_ms": 4.5,
             "disk_type": "ssd", "host_disk": "sda", "disk_index": 0,
             "partition": ""},
            # 缺 host_disk 元素
            {"mount": "/legacy", "disk_used_pct": 80},
            {"mount": "loop0[HDD]", "io_util_pct": 5, "io_await_ms": 1,
             "disk_type": "hdd"},
        ]},
    )
    config = build_ops_report_config(
        summary=OpsSummary(), alerts=OpsAlerts(),
        server_report=ServerOpsReport(items=[item]),
        api_report=ApiCheckReport(),
        ip_map={}, schedule_name="t", started_at=datetime(2026, 8, 16),
    )
    inventory = [
        s.table for s in config.sections
        if s.section_type == "table"
        and s.table.headers == [
            "物理盘", "设备/挂载点", "介质", "磁盘使用率", "IO 利用率", "IO 平均等待"
        ]
    ]
    rows = inventory[0].rows
    # sda 组 (1 sub-header + 2 数据行) + _orphan_ 组 (1 sub-header + 2 数据行) = 6 行
    assert len(rows) == 6
    # sda 组在前 (disk_index=0)
    assert rows[0] == ["sda", "SSD", "-", "-", "-", "-"]
    assert rows[1] == ["sda", "/", "-", "42%", "-", "-"]
    assert rows[2] == ["sda", "sda", "SSD", "-", "12.3%", "4.5 ms"]
    # _orphan_ 组在后; 介质汇总 "HDD" (loop0 有 disk_type=hdd, /legacy 无)
    assert rows[3] == ["_orphan_", "HDD", "-", "-", "-", "-"]
    # /legacy 元素无 host_disk / partition → _format_host_disk 返回 "-"
    assert rows[4] == ["-", "/legacy", "-", "80%", "-", "-"]
    assert rows[5] == ["-", "loop0", "HDD", "-", "5%", "1 ms"]


def test_build_report_disk_inventory_keeps_flat_when_all_missing_host_disk():
    """全部元素都缺 host_disk → 退化为平铺渲染, 不生成 sub-header。

    兼容 2026-08-15 旧契约: 历史快照 (disks 元素不含 host_disk) 的报告再生时
    仍按平铺行为, 不引入额外 sub-header 行 (避免行数膨胀 + 视觉割裂)。

    Returns:
        None
    """
    item = ServerOpsItem(
        business_name="A", success=True, inspection_status="pass",
        parsed_values={"disks": [
            {"mount": "/", "disk_used_pct": 42},
            {"mount": "/data", "disk_used_pct": 78},
            {"mount": "loop0[HDD]", "io_util_pct": 5, "io_await_ms": 1,
             "disk_type": "hdd"},
        ]},
    )
    config = build_ops_report_config(
        summary=OpsSummary(), alerts=OpsAlerts(),
        server_report=ServerOpsReport(items=[item]),
        api_report=ApiCheckReport(),
        ip_map={}, schedule_name="t", started_at=datetime(2026, 8, 16),
    )
    inventory = [
        s.table for s in config.sections
        if s.section_type == "table"
        and s.table.headers == [
            "物理盘", "设备/挂载点", "介质", "磁盘使用率", "IO 利用率", "IO 平均等待"
        ]
    ]
    rows = inventory[0].rows
    # 平铺: 3 元素 → 3 行, 无 sub-header
    assert len(rows) == 3
    # 无 host_disk → _format_host_disk 返回 "-" (partition 也空)
    assert rows[0] == ["-", "/", "-", "42%", "-", "-"]
    assert rows[1] == ["-", "/data", "-", "78%", "-", "-"]
    assert rows[2] == ["-", "loop0", "HDD", "-", "5%", "1 ms"]


def test_build_report_skips_inventory_table_without_disks():
    """parsed_values 为 None / 无 disks 键时不生成清单表（优雅降级，兼容旧脚本）。

    Returns:
        None
    """
    item = _server("A")
    config = build_ops_report_config(
        summary=OpsSummary(), alerts=OpsAlerts(),
        server_report=ServerOpsReport(items=[item]),
        api_report=ApiCheckReport(),
        ip_map={}, schedule_name="t", started_at=datetime(2026, 8, 15),
    )
    assert all(
        not (s.section_type == "table" and s.table.headers
             and s.table.headers[0] == "设备/挂载点")
        for s in config.sections
    )


# --------------------------------------------------------------------------
# 元信息表渲染: 跟随 2026-08-16 脚本契约撤回 ``os`` / ``cpu_model`` 字段后,
# 不再渲染「操作系统」「CPU 型号」两行, 元信息表固定 5 行。
# --------------------------------------------------------------------------


def _meta_rows_of(config, business_name):
    """从 ReportConfig 中按业务名提取「项目/值」元信息表行。"""
    titles = [s.content for s in config.sections if s.section_type == "heading"]
    assert business_name in titles, f"业务名 {business_name} 未作为二级标题出现"
    tables = [s.table for s in config.sections if s.section_type == "table"]
    meta_table = next(
        (t for t in tables if t.headers == ["项目", "值"]),
        None,
    )
    assert meta_table is not None, "未找到元信息表(项目/值)"
    return meta_table.rows


def test_build_report_meta_table_omits_os_and_cpu_rows():
    """2026-08-16 撤回: 脚本不再输出 ``os`` / ``cpu_model`` 后, 元信息表不再
    渲染「操作系统」「CPU 型号」两行, 固定 5 行。

    历史 JSONB 中残留的两键仍可存在, 但报告侧吞值不渲染, 不抛异常
    (兼容旧记录)。

    验证 3 类场景:
        1. ``parsed_values`` 完全不含 OS / CPU 键 → 不渲染；
        2. ``parsed_values`` 含两键 + 字符串值 → 不渲染（吞值）；
        3. ``parsed_values`` 含两键 + 字符串值且 IP 走真实反查 → 仍不渲染。

    Returns:
        None
    """
    scenarios = [
        ("不含 OS/CPU 键", {"mem_used_pct": 50, "load_1m": 0.5}),
        ("含 OS/CPU 字符串值(吞值)",
         {"mem_used_pct": 50, "os": "Ubuntu 22.04.3 LTS",
          "cpu_model": "Intel Xeon E5-2680 v4"}),
        ("OS 值为空字符串 + CPU 值为 None",
         {"os": "", "cpu_model": None}),
    ]
    for label, parsed in scenarios:
        item = ServerOpsItem(
            business_name="A", success=True, inspection_status="pass",
            parsed_values=parsed,
        )
        config = build_ops_report_config(
            summary=OpsSummary(), alerts=OpsAlerts(),
            server_report=ServerOpsReport(items=[item]),
            api_report=ApiCheckReport(),
            ip_map={"A": "10.0.0.1"},
            schedule_name="t", started_at=datetime(2026, 8, 16),
        )
        rows = _meta_rows_of(config, "A")
        # 元信息表固定 5 行
        assert len(rows) == 5, (
            f"场景 {label}: 元信息表应为 5 行, 实际 {len(rows)} 行 ({rows!r})"
        )
        # 各项数据来源
        row_keys = {r[0] for r in rows}
        assert row_keys == {"业务名", "服务器 IP", "SSH 退出码", "耗时", "巡检状态"}, (
            f"场景 {label}: 行集合不符, 实际 {row_keys!r}"
        )
        assert ["业务名", "A"] in rows
        assert ["服务器 IP", "10.0.0.1"] in rows
        assert ["巡检状态", "通过"] in rows
        # 不渲染 OS / CPU 行（无论是否含值）
        assert not any(r[0] == "操作系统" for r in rows), (
            f"场景 {label}: 应不渲染「操作系统」行"
        )
        assert not any(r[0] == "CPU 型号" for r in rows), (
            f"场景 {label}: 应不渲染「CPU 型号」行"
        )


def test_build_report_meta_table_does_not_render_os_cpu_with_real_values():
    """``parsed_values`` 含真实 OS / CPU 字符串值时, 元信息表仍然不渲染这两行。

    单独提取一个用例防止 ``test_build_report_meta_table_omits_os_and_cpu_rows``
    被框架 fixture 误用掩盖「字符串值触发渲染」的回归。

    Returns:
        None
    """
    item = ServerOpsItem(
        business_name="A", success=True, inspection_status="pass",
        parsed_values={
            "mem_used_pct": 50,
            "cpu_idle_pct": 80,
            "load_1m": 1.5,
            "os": "Ubuntu 22.04.3 LTS",
            "cpu_model": "Intel(R) Xeon(R) CPU E5-2680 v4 @ 2.40GHz",
        },
    )
    config = build_ops_report_config(
        summary=OpsSummary(), alerts=OpsAlerts(),
        server_report=ServerOpsReport(items=[item]),
        api_report=ApiCheckReport(),
        ip_map={"A": "10.0.0.1"},
        schedule_name="t", started_at=datetime(2026, 8, 16),
    )
    rows = _meta_rows_of(config, "A")
    keys = {r[0] for r in rows}
    assert "操作系统" not in keys
    assert "CPU 型号" not in keys
    # 业务名行不受影响, OS / CPU 字符串值被吞, 不进任何表行
    assert len(rows) == 5


def test_build_report_config_table_section_headers():
    summary = _build_summary()
    alerts = compute_ops_alerts(ServerOpsReport(), ApiCheckReport())
    cfg = build_ops_report_config(
        summary=summary, alerts=alerts,
        server_report=ServerOpsReport(items=[
            ServerOpsItem(business_name="A", success=True, inspection_status="pass"),
        ]),
        api_report=ApiCheckReport(),
        ip_map={"A": "10.0.0.1"},
        schedule_name="x", started_at=datetime(2026, 7, 22),
    )
    tables = [s for s in cfg.sections if s.section_type == "table"]
    # 元信息表 + 字段明细表 = 至少 1 个
    headers_combined = []
    for t in tables:
        headers_combined.append(t.table.headers[0])
    # 字段表首列应为「指标」或「项目」之一
    assert any(h in ["指标", "项目"] for h in headers_combined)


# --------------------------------------------------------------------------
# build_ops_email_body 邮件正文构造
# --------------------------------------------------------------------------

def test_build_email_body_includes_alerts():
    summary = OpsSummary(
        total=3, passed=2, problem=1,
        server_total=2, server_passed=2, server_problem=0,
        server_failed_count=0, server_warn_count=0, server_crit_count=0,
        api_total=1, api_passed=0, api_problem=1,
    )
    alerts = OpsAlerts(
        server_warn_crit=[],
        api_failed=[OpsAlertItem(business="X", metric="HTTP 检查",
                                  value="HTTP 500", threshold="-", status="FAIL", detail="")],
    )
    body = build_ops_email_body(
        summary=summary, alerts=alerts,
        schedule_name="运维巡检", schedule_id=1, run_id=42,
        trigger_type="scheduled",
        started_at=datetime(2026, 7, 22, 15, 0, 0),
        finished_at=datetime(2026, 7, 22, 15, 1, 0),
        report_file_name="report.docx",
    )
    assert "[运维巡检]" in body
    assert "运行 ID：42" in body
    assert "本次运维巡检共检查 3 大项" in body
    assert "【接口 · 检查失败】" in body
    assert "X · HTTP 检查 · HTTP 500" in body
    assert "report.docx" in body


def test_build_email_body_no_alerts_omits_section():
    body = build_ops_email_body(
        summary=OpsSummary(), alerts=OpsAlerts(),
        schedule_name="x", schedule_id=1, run_id=1,
        trigger_type="manual",
        started_at=datetime(2026, 7, 22, 15, 0, 0),
        finished_at=datetime(2026, 7, 22, 15, 0, 30),
        report_file_name=None,
    )
    assert "—— 综述 ——" in body
    assert "—— 关键告警 ——" not in body
    assert "—— 附件 ——" not in body


# --------------------------------------------------------------------------
# 2026-08-16 新增: 物理盘列渲染 3 场景 + OS 关键指标告警归类与报告小节
# --------------------------------------------------------------------------


def test_inventory_rows_host_disk_with_disk_index():
    """``host_disk`` + ``disk_index > 0`` → ``host_disk[index]`` 拼接形式。

    覆盖 ``_format_host_disk`` 的最高优先级分支;以 Linux 分区
    ``sda`` + ``disk_index=1`` 为例,期望 ``sda[1]``;Windows
    ``PHYSICALDRIVE0`` + ``disk_index=2`` → ``PHYSICALDRIVE0[2]``。

    Returns:
        None
    """
    from app.scripts.ops.ops_report import _format_host_disk

    assert _format_host_disk({
        "host_disk": "sda", "disk_index": 1, "partition": "sda1",
    }) == "sda[1]"
    assert _format_host_disk({
        "host_disk": "PHYSICALDRIVE0", "disk_index": 2,
        "partition": "D:",
    }) == "PHYSICALDRIVE0[2]"
    # disk_index=0 → 不拼接,仅 host_disk（避免「sda[0]」噪音）
    assert _format_host_disk({
        "host_disk": "sda", "disk_index": 0, "partition": "",
    }) == "sda"


def test_inventory_rows_host_disk_only_without_index():
    """``host_disk`` 非空但 ``disk_index`` 缺失 / 非整数 → 仅渲染 ``host_disk``。"""
    from app.scripts.ops.ops_report import _format_host_disk

    # disk_index 缺失
    assert _format_host_disk({"host_disk": "nvme0n1"}) == "nvme0n1"
    # disk_index 为 None
    assert _format_host_disk({
        "host_disk": "sda", "disk_index": None,
    }) == "sda"
    # disk_index 为 bool（Python 中 int 子类,应被拦截）
    assert _format_host_disk({
        "host_disk": "sda", "disk_index": True,
    }) == "sda"
    # disk_index 为字符串（应被拒绝,退回 host_disk）
    assert _format_host_disk({
        "host_disk": "sda", "disk_index": "1",
    }) == "sda"


def test_inventory_rows_fallback_to_partition_or_dash():
    """``host_disk`` 空时降级:有 ``partition`` → 仅 partition;均空 → ``-``。"""
    from app.scripts.ops.ops_report import _format_host_disk

    # 仅 partition(Windows 盘符场景)
    assert _format_host_disk({"host_disk": "", "partition": "C:"}) == "C:"
    assert _format_host_disk({"partition": "sda2"}) == "sda2"
    # partition 含前后空白 → strip
    assert _format_host_disk({"partition": "  D:  "}) == "D:"
    # 两者均空 → '-'
    assert _format_host_disk({}) == "-"
    assert _format_host_disk({"host_disk": "", "partition": ""}) == "-"
    # 非字符串类型 → '-'
    assert _format_host_disk({"host_disk": None, "partition": 123}) == "-"


def test_compute_alerts_os_metric_keys_get_suffix():
    """``cpu_iowait_pct`` / ``swap_used_pct`` / ``inode_used_pct`` 命中告警时,
    ``OpsAlertItem.metric`` 自动追加「(OS 指标)」后缀;其他字段不受影响。

    Returns:
        None
    """
    srv = ServerOpsReport(items=[
        ServerOpsItem(
            business_name="A", success=True, inspection_status="crit",
            field_results=[
                {"key": "cpu_iowait_pct", "name_zh": "CPU iowait 占比",
                 "unit": "%", "value": 45.0, "direction": "high",
                 "warn": 20.0, "crit": 40.0,
                 "status": "crit", "message": ""},
                {"key": "swap_used_pct", "name_zh": "交换分区使用率",
                 "unit": "%", "value": 35.0, "direction": "high",
                 "warn": 30.0, "crit": 60.0,
                 "status": "warn", "message": ""},
                {"key": "mem_used_pct", "name_zh": "内存使用率",
                 "unit": "%", "value": 92.0, "direction": "high",
                 "warn": 80.0, "crit": 90.0,
                 "status": "crit", "message": ""},
            ],
        ),
    ])
    alerts = compute_ops_alerts(srv, ApiCheckReport())
    assert len(alerts.server_warn_crit) == 3

    metric_by_key = {item.metric: item for item in alerts.server_warn_crit}
    # OS 指标 2 条：带「（OS 指标）」后缀(全角中文括号,与代码实现一致)
    os_metric_keys = [m for m in metric_by_key if "（OS 指标）" in m]
    assert len(os_metric_keys) == 2
    assert "CPU iowait 占比（OS 指标）" in metric_by_key
    assert "交换分区使用率（OS 指标）" in metric_by_key
    # 内存使用率（非 OS 指标）不带后缀
    assert "内存使用率" in metric_by_key
    mem_alert = metric_by_key["内存使用率"]
    assert "（OS 指标）" not in mem_alert.metric


def test_build_report_includes_os_metric_section_on_warn_crit():
    """``field_results`` 含新 3 字段 warn/crit → 报告追加「OS 关键指标」小节。

    触发条件: ``key in {cpu_iowait_pct, swap_used_pct, inode_used_pct}``
    且 ``status in {warn, crit}``。新增三级标题 + 5 列小表格。

    Returns:
        None
    """
    item = ServerOpsItem(
        business_name="A", success=True, inspection_status="crit",
        field_results=[
            {"key": "mem_used_pct", "name_zh": "内存使用率", "unit": "%",
             "value": 50.0, "warn": 80.0, "crit": 90.0,
             "status": "pass", "message": ""},
            {"key": "cpu_iowait_pct", "name_zh": "CPU iowait 占比",
             "unit": "%", "value": 45.0, "warn": 20.0, "crit": 40.0,
             "status": "crit", "message": ""},
            {"key": "swap_used_pct", "name_zh": "交换分区使用率",
             "unit": "%", "value": 35.0, "warn": 30.0, "crit": 60.0,
             "status": "warn", "message": ""},
        ],
    )
    config = build_ops_report_config(
        summary=OpsSummary(), alerts=OpsAlerts(),
        server_report=ServerOpsReport(items=[item]),
        api_report=ApiCheckReport(),
        ip_map={}, schedule_name="t", started_at=datetime(2026, 8, 16),
    )
    # 三级标题断言
    headings = [s.content for s in config.sections if s.section_type == "heading"]
    assert "A · OS 关键指标" in headings
    # 5 列表格在 docs 中按出现顺序排列: 先字段明细表(3 行含 mem_used_pct)、
    # 后 OS 关键指标表(2 行不含 mem_used_pct)。通过"不含 mem_used_pct"
    # + "行数 == 2" 双重条件精确识别 OS 指标表。
    five_col_tables = [
        s.table for s in config.sections
        if s.section_type == "table"
        and s.table.headers == ["指标", "当前值", "阈值", "状态", "说明"]
    ]
    assert len(five_col_tables) == 2, f"应出现 2 个 5 列表格,实际 {len(five_col_tables)}"
    os_table = next(
        tbl for tbl in five_col_tables
        if "内存使用率" not in [r[0] for r in tbl.rows]
    )
    assert len(os_table.rows) == 2
    # 状态列中文
    status_by_metric = {r[0]: r[3] for r in os_table.rows}
    assert status_by_metric["CPU iowait 占比"] == "严重"
    assert status_by_metric["交换分区使用率"] == "告警"


def test_build_report_omits_os_metric_section_when_no_alerts():
    """``field_results`` 中新 3 字段全部 pass / unassessed → 不渲染 OS 关键指标小节。

    Returns:
        None
    """
    item = ServerOpsItem(
        business_name="A", success=True, inspection_status="pass",
        field_results=[
            {"key": "mem_used_pct", "name_zh": "内存使用率", "unit": "%",
             "value": 50.0, "warn": 80.0, "crit": 90.0,
             "status": "pass", "message": ""},
            {"key": "cpu_iowait_pct", "name_zh": "CPU iowait 占比",
             "unit": "%", "value": 5.0, "warn": 20.0, "crit": 40.0,
             "status": "pass", "message": ""},
            {"key": "swap_used_pct", "name_zh": "交换分区使用率",
             "unit": "%", "value": 5.0, "warn": 30.0, "crit": 60.0,
             "status": "pass", "message": ""},
            {"key": "inode_used_pct", "name_zh": "inode 使用率",
             "unit": "%", "value": 10.0, "warn": 80.0, "crit": 90.0,
             "status": "pass", "message": ""},
        ],
    )
    config = build_ops_report_config(
        summary=OpsSummary(), alerts=OpsAlerts(),
        server_report=ServerOpsReport(items=[item]),
        api_report=ApiCheckReport(),
        ip_map={}, schedule_name="t", started_at=datetime(2026, 8, 16),
    )
    # 三级标题断言:不应出现「OS 关键指标」
    headings = [s.content for s in config.sections if s.section_type == "heading"]
    assert not any("OS 关键指标" in h for h in headings)
    # 5 列 OS 指标小表格不应存在（仅字段明细表含 5 列 4 行）
    five_col_tables = [
        s.table for s in config.sections
        if s.section_type == "table"
        and s.table.headers == ["指标", "当前值", "阈值", "状态", "说明"]
    ]
    assert len(five_col_tables) == 1  # 仅字段明细表
