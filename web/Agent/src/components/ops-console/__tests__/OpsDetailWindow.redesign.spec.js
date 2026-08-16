// -*- coding:utf-8 -*-
/**
 * OpsDetailWindow 详情页改造测试（2026-08-16 用户需求）。
 *
 * 覆盖：
 *   - 头部 sub 改为「最新检测时间:」+ 绝对时间（与卡片 srv-card-time 文案一致）；
 *   - 4 联指标条：linux 4 项 / windows 3 项（隐藏负载）；
 *   - 指标值 ≥ 阈值时标红（CPU/内存 ≥ 80 红 / 负载 ≥ 4 红）；
 *   - kv 表格精简：保留 OS/CPU型号/运行时长；删除 内存总量/存储总量/网络流入；
 *   - 物理磁盘纵向分组：每块物理盘一行；磁盘头只显示「排队 / IO 利用率」；
 *     分区卡只显示「使用率」；IO 整盘记录（含 mount="sda[SSD]"）不渲染为分区卡；
 *   - 未知归属（缺 host_disk）单独成组，红绿灰灯与 metricColor 80 规则保留；
 *   - 「智能检测」按钮已删除。
 *
 * 2026-08-16: 物理盘纵向分组 (Linux / Windows 双平台)。
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import OpsDetailWindow from '../OpsDetailWindow.vue'

const baseWin = { x: 0, y: 0, z: 1, max: false }

function makeServer(overrides = {}) {
  return {
    id: 1,
    name: '本机',
    status: 'ok',
    ip: '-',
    os: '-',
    serverType: '',
    cpu: 27,
    mem: 31.4,
    disk: 50,
    load: null,
    cpuModel: '-',
    memTotal: '-',
    diskTotal: '-',
    netIn: '-',
    uptime: '0.7 小时',
    disks: [],
    fieldResults: [],
    collectedAt: '2026-08-09T11:35:28.487343+00:00',
    errorMessage: null,
    ...overrides,
  }
}

describe('OpsDetailWindow 详情页改造（2026-08-16）', () => {
  it('test_detail_window_importable 组件可被 import', () => {
    expect(OpsDetailWindow).toBeTruthy()
  })

  // -------- 头部 sub：最新检测时间 --------
  it('test_collected_at_in_srv_head 头部 sub 展示「最新检测时间:」+ 绝对时间', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: { win: baseWin, server: makeServer({ collectedAt: '2026-08-16T00:46:35' }) },
    })
    const sub = wrapper.find('.srv-head .sub')
    expect(sub.exists()).toBe(true)
    expect(sub.text()).toMatch(/^最新检测时间:\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/)
    expect(sub.attributes('title')).toBe('2026-08-16T00:46:35')
  })

  it('test_collected_at_dash_when_null 无快照时显示「最新检测时间:-」', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: { win: baseWin, server: makeServer({ collectedAt: null }) },
    })
    expect(wrapper.find('.srv-head .sub').text()).toBe('最新检测时间:-')
  })

  // -------- 长方形 4 联指标条 --------
  it('test_metric_bar_has_4_items_for_linux linux 显示 4 联指标', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({
          serverType: 'linux',
          cpu: 30, mem: 40, disk: 50, load: 1.5,
          disks: [{ name: '/', used: 50, ioUtilPct: null, ioAwaitMs: null }],
        }),
      },
    })
    const labels = wrapper.findAll('.detail-metric-bar .dm-label').map(n => n.text())
    expect(labels).toEqual(['CPU 使用率', '内存占用', '存储使用', '服务器负载'])
    expect(wrapper.findAll('.detail-metric-bar .dm-item').length).toBe(4)
  })

  it('test_metric_bar_has_3_items_for_windows windows 隐藏负载', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({
          serverType: 'windows',
          cpu: 30, mem: 40, disk: 50, load: null,
          disks: [{ name: 'C:\\', used: 50 }],
        }),
      },
    })
    const labels = wrapper.findAll('.detail-metric-bar .dm-label').map(n => n.text())
    expect(labels).not.toContain('服务器负载')
    expect(labels).toEqual(['CPU 使用率', '内存占用', '存储使用'])
    expect(wrapper.findAll('.detail-metric-bar .dm-item').length).toBe(3)
  })

  it('test_metric_value_red_when_above_threshold CPU/内存 ≥ 80 时标红', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({ serverType: 'windows', cpu: 92, mem: 85 }),
      },
    })
    const values = wrapper.findAll('.detail-metric-bar .dm-value')
    expect(values[0].attributes('style') || '').toContain('#ff453a')   // CPU
    expect(values[1].attributes('style') || '').toContain('#ff453a')   // 内存
  })

  it('test_metric_value_green_when_normal CPU/内存 < 80 时标绿', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({ serverType: 'windows', cpu: 27, mem: 31.4 }),
      },
    })
    const values = wrapper.findAll('.detail-metric-bar .dm-value')
    expect(values[0].attributes('style') || '').toContain('#1d9a40')
    expect(values[1].attributes('style') || '').toContain('#1d9a40')
  })

  it('test_load_metric_red_when_above_4 linux 负载 ≥ 4 时标红', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({ serverType: 'linux', load: 4.5 }),
      },
    })
    const values = wrapper.findAll('.detail-metric-bar .dm-value')
    // 末位是负载（index=3：CPU/内存/存储/负载）
    expect(values[3].attributes('style') || '').toContain('#ff453a')
  })

  // -------- kv 表格精简 --------
  it('test_kv_includes_runtime kv 含「运行时长」', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: { win: baseWin, server: makeServer() },
    })
    const keys = wrapper.findAll('.kv .k').map(n => n.text())
    expect(keys).toContain('运行时长')
  })

  it('test_kv_no_mem_total_disk_total_net_in kv 不含「内存总量 / 存储总量 / 网络流入」', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: { win: baseWin, server: makeServer() },
    })
    const keys = wrapper.findAll('.kv .k').map(n => n.text())
    expect(keys).not.toContain('内存总量')
    expect(keys).not.toContain('存储总量')
    expect(keys).not.toContain('网络流入')
  })

  it('test_kv_three_items kv 仅 3 项（OS / CPU 型号 / 运行时长）', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: { win: baseWin, server: makeServer() },
    })
    expect(wrapper.findAll('.kv > div').length).toBe(3)
  })

  // -------- 物理磁盘分组展示（2026-08-16 用户需求） --------
  it('test_disk_groups_rendered_per_physical_disk Linux sda 同盘多个分区归入一个节点', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({
          disks: [
            { mount: '/', used: 78.1, hostDisk: 'sda', diskIndex: 0, partition: 'sda2' },
            { mount: '/data', used: 54.1, hostDisk: 'sda', diskIndex: 0, partition: 'sda3' },
            // 整盘 IO 记录: used=null, io 指标在磁盘头呈现, 不渲染为分区卡
            { mount: 'sda[SSD]', used: null, ioUtilPct: 4, ioAwaitMs: 0, hostDisk: 'sda', diskIndex: 0, partition: '' },
          ],
        }),
      },
    })
    const groups = wrapper.findAll('.disk-groups .disk-group')
    expect(groups).toHaveLength(1)
    expect(groups[0].text()).toContain('磁盘 0')
    expect(groups[0].findAll('.disk-pcard')).toHaveLength(2)
  })

  it('test_disk_groups_rendered_per_physical_disk_windows Windows C:/D: 归入 PHYSICALDRIVE0', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({
          serverType: 'windows',
          disks: [
            { mount: 'C:\\', used: 71.4, hostDisk: 'PHYSICALDRIVE0', diskIndex: 0, partition: 'C:' },
            { mount: 'D:\\', used: 64.9, hostDisk: 'PHYSICALDRIVE0', diskIndex: 0, partition: 'D:' },
            { mount: 'E:\\', used: 91.5, hostDisk: 'PHYSICALDRIVE1', diskIndex: 1, partition: 'E:' },
          ],
        }),
      },
    })
    const groups = wrapper.findAll('.disk-groups .disk-group')
    expect(groups).toHaveLength(2)
    // 按 diskIndex 升序, 第 1 行是 PHYSICALDRIVE0 (C:/D:), 第 2 行是 PHYSICALDRIVE1 (E:)
    expect(groups[0].text()).toContain('磁盘 0')
    expect(groups[0].findAll('.disk-pcard')).toHaveLength(2)
    expect(groups[1].text()).toContain('磁盘 1')
    expect(groups[1].findAll('.disk-pcard')).toHaveLength(1)
  })

  it('test_disk_group_head_only_shows_queue_and_io_utilization 磁盘头只显示排队和 IO 利用率', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({
          disks: [
            { mount: '/', used: 50, hostDisk: 'sda', diskIndex: 0, partition: 'sda2' },
            { mount: 'sda[SSD]', used: null, ioUtilPct: 12, ioAwaitMs: 5, hostDisk: 'sda', diskIndex: 0, partition: '' },
          ],
        }),
      },
    })
    const head = wrapper.find('.disk-group-head')
    expect(head.exists()).toBe(true)
    expect(head.text()).toContain('sda')
    expect(head.findAll('.dg-m-label').map(n => n.text())).toEqual(['排队', 'IO 利用率'])
    expect(head.text()).not.toContain('使用率')
  })

  it('test_disk_partition_cards_only_show_usage 分区卡片只显示使用率', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({
          disks: [{ mount: 'C:\\', used: 91.5, hostDisk: 'PHYSICALDRIVE0', diskIndex: 0, partition: 'C:' }],
        }),
      },
    })
    const labels = wrapper.findAll('.disk-pcard .dg-m-label').map(n => n.text())
    expect(labels).toEqual(['使用率'])
    const values = wrapper.findAll('.disk-pcard .dg-m-value').map(n => n.text())
    expect(values).toEqual(['91.5%'])
  })

  it('test_disk_partition_metric_red_when_above_threshold 分区使用率 ≥ 80 时标红', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({
          disks: [{ mount: 'C:\\', used: 91.5, hostDisk: 'PHYSICALDRIVE0', diskIndex: 0, partition: 'C:' }],
        }),
      },
    })
    const usedStyle = wrapper.find('.disk-pcard .dg-m-value').attributes('style') || ''
    expect(usedStyle).toContain('#ff453a')
  })

  it('test_disk_partition_metric_dash_when_null 缺失分区使用率显示 - 和灰灯', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({
          disks: [{ mount: '/', used: null, hostDisk: 'sda', diskIndex: 0, partition: 'sda1' }],
        }),
      },
    })
    // 分区记录 (partition="sda1") 渲染为分区卡; used=null 显示 "-", 灰灯
    const value = wrapper.find('.disk-pcard .dg-m-value')
    expect(value.text()).toBe('-')
    expect(value.attributes('style') || '').toContain('#9aa3af')
  })

  it('test_disk_groups_empty_when_no_disks 无 disks 时显示空态文案', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: { win: baseWin, server: makeServer({ disks: [] }) },
    })
    expect(wrapper.find('.disk-groups').exists()).toBe(false)
    expect(wrapper.find('.disk-empty').text()).toBe('无磁盘数据')
  })

  it('test_disk_group_preserves_party_colors_and_unknown_partitioning 保留红绿灰灯，未知归属单独成组', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({
          disks: [
            // 已知归属: sda 盘 (分区 + IO)
            { mount: '/', used: 91, hostDisk: 'sda', diskIndex: 0, partition: 'sda1' },
            { mount: 'sda[HDD]', used: null, ioUtilPct: 30, ioAwaitMs: 50, hostDisk: 'sda', diskIndex: 0, partition: '' },
            // 未知归属: 旧 snapshot 缺 host_disk, 不能与 sda 合并
            { mount: 'C:\\', used: null, hostDisk: '', diskIndex: null, partition: 'C:' },
          ],
        }),
      },
    })
    const groups = wrapper.findAll('.disk-group')
    // 2 个分组: sda / 未知(C:\\)
    expect(groups.length).toBe(2)
    // 已知分区使用率 91 → 红色
    const usedStyle = wrapper.find('.disk-pcard .dg-m-value').attributes('style') || ''
    expect(usedStyle).toContain('#ff453a')
    // 旧 snapshot 缺 host_disk 但 partition="C:" 仍然渲染为分区卡; used=null → "-", 灰
    const allUsedNodes = wrapper.findAll('.disk-pcard .dg-m-value')
    const lastUsed = allUsedNodes[allUsedNodes.length - 1]
    expect(lastUsed.text()).toBe('-')
    expect(lastUsed.attributes('style') || '').toContain('#9aa3af')
  })

  it('test_disk_group_io_record_not_rendered_as_partition_card IO 整盘记录不渲染为分区卡', () => {
    // 数据形状来自真实 inspection_scripts.yaml::linux-bash:
    //   分区记录 (used != null) + 整盘 IO 记录 (used == null, mount 形如 "sda[SSD]")
    // 应只渲染分区卡, IO 记录只在磁盘头参与排队/IO 利用率聚合。
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({
          disks: [
            { mount: '/', used: 50, hostDisk: 'sda', diskIndex: 0, partition: 'sda2' },
            { mount: '/data', used: 80, hostDisk: 'sda', diskIndex: 0, partition: 'sda3' },
            { mount: 'sda[SSD]', used: null, ioUtilPct: 12, ioAwaitMs: 5, hostDisk: 'sda', diskIndex: 0, partition: '' },
          ],
        }),
      },
    })
    const partitions = wrapper.findAll('.disk-group-partitions .disk-pcard')
    expect(partitions.length).toBe(2)
    // 每个分区卡只显示使用率
    for (const p of partitions) {
      const labels = p.findAll('.dg-m-label').map(n => n.text())
      expect(labels).toEqual(['使用率'])
    }
    // 磁盘头包含 IO 记录贡献的排队/IO 利用率
    const head = wrapper.find('.disk-group-head')
    const headValues = head.findAll('.dg-m-value').map(n => n.text())
    expect(headValues).toEqual(['5ms', '12%'])
  })

  it('test_no_legacy_disk_grid_class 新模板不再渲染旧 .disk-grid', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({
          disks: [
            { mount: '/', used: 50, hostDisk: 'sda', diskIndex: 0, partition: 'sda1' },
          ],
        }),
      },
    })
    expect(wrapper.find('.disk-grid').exists()).toBe(false)
    expect(wrapper.find('.disk-section').exists()).toBe(true)
    expect(wrapper.find('.disk-groups').exists()).toBe(true)
  })

  // -------- 智能检测按钮已删除 --------
  it('test_smart_detect_button_removed 智能检测按钮已移除', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: { win: baseWin, server: makeServer() },
    })
    expect(wrapper.find('.gov-btn').exists()).toBe(false)
    expect(wrapper.find('.detect-panel').exists()).toBe(false)
  })

  // -------- 窗口宽度 --------
  it('test_win_detail_narrow_width 详情窗口宽度缩小为 460px', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: { win: baseWin, server: makeServer() },
    })
    // .win-detail 类存在即可（具体宽度由 CSS 控制，本测试确保模板类名仍正确）
    expect(wrapper.find('.win-detail').exists()).toBe(true)
    expect(wrapper.find('.win.win-detail').exists()).toBe(true)
  })

  // -------- 展示字段从 DB 读取（2026-08-16 修复：之前硬编码 '-'） --------
  it('test_kv_os_displays_from_server_os kv「操作系统」渲染 server.os（非 \'-\'）', () => {
    // 模拟 OpsConsoleApp.mapSnapshotToServer 已从 parsed_values.os 读到值
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({ os: 'Microsoft Windows 11' }),
      },
    })
    // kv 第 1 行（操作系统）的值 span
    const osRow = wrapper.findAll('.kv > div')[0]
    const val = osRow.find('span:last-child').text()
    expect(val).toBe('Microsoft Windows 11')
    expect(val).not.toBe('-')
  })

  it('test_kv_cpu_model_displays_from_server_cpu_model kv「CPU 型号」渲染 server.cpuModel', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({ cpuModel: '13th Gen Intel(R) Core(TM) i7-13620H' }),
      },
    })
    const cpuRow = wrapper.findAll('.kv > div')[1]
    const val = cpuRow.find('span:last-child').text()
    expect(val).toBe('13th Gen Intel(R) Core(TM) i7-13620H')
  })

  it('test_kv_uptime_displays_runtime kv「运行时长」渲染 server.uptime', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({ uptime: '3.4 小时' }),
      },
    })
    const upRow = wrapper.findAll('.kv > div')[2]
    const val = upRow.find('span:last-child').text()
    expect(val).toBe('3.4 小时')
    expect(val).not.toBe('-')
  })

  it('test_kv_os_dash_when_empty_string server.os 为空串时降级为 -', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({ os: '' }),
      },
    })
    const osRow = wrapper.findAll('.kv > div')[0]
    expect(osRow.find('span:last-child').text()).toBe('-')
  })
})