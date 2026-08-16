// -*- coding:utf-8 -*-
/**
 * OpsDetailWindow 详情页改造测试（2026-08-16 用户需求）。
 *
 * 覆盖：
 *   - 头部 sub 改为「最新检测时间:」+ 绝对时间（与卡片 srv-card-time 文案一致）；
 *   - 4 联指标条：linux 4 项 / windows 3 项（隐藏负载）；
 *   - 指标值 ≥ 阈值时标红（CPU/内存 ≥ 80 红 / 负载 ≥ 4 红）；
 *   - 服务器负载显示原始数值不带 %（load_1m 非百分比指标）；
 *   - kv 区 4 项：操作系统（serverType 原值 linux/windows）/ CPU IOWait /
 *     Swap 使用率 / Inode 使用率；OS 三指标按 YAML warn 阈值标红（iowait 20
 *     / swap 30 / inode 80），低于阈值标绿，null 标灰；
 *   - 物理磁盘纵向分组：每块物理盘一行；磁盘头只显示「排队 / IO 利用率」；
 *     分区卡只显示「使用率」；IO 整盘记录（含 mount="sda[SSD]"）不渲染为分区卡；
 *   - 未知归属（缺 host_disk）单独成组，红绿灰灯与 metricColor 80 规则保留；
 *   - 「智能检测」按钮已删除。
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
    serverType: '',
    cpu: 27,
    mem: 31.4,
    disk: 50,
    load: null,
    iowait: null,
    swap: null,
    inode: null,
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

  it('test_load_value_without_percent_sign linux 负载显示原始数值不带 %', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({ serverType: 'linux', load: 1.36 }),
      },
    })
    const items = wrapper.findAll('.detail-metric-bar .dm-item')
    const loadValue = items[items.length - 1].find('.dm-value')
    expect(loadValue.text()).toBe('1.36')
    expect(loadValue.text()).not.toContain('%')
  })

  it('test_load_value_dash_when_null 负载为 null 显示 -', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({ serverType: 'linux', load: null }),
      },
    })
    const items = wrapper.findAll('.detail-metric-bar .dm-item')
    const loadValue = items[items.length - 1].find('.dm-value')
    expect(loadValue.text()).toBe('-')
  })

  // -------- kv 区精简（2026-08-16 用户需求：4 项 OS 关键指标） --------
  it('test_kv_no_legacy_fields kv 不含「内存总量 / 存储总量 / 网络流入 / CPU 型号 / 运行时长」', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: { win: baseWin, server: makeServer() },
    })
    const keys = wrapper.findAll('.kv .k').map(n => n.text())
    expect(keys).not.toContain('内存总量')
    expect(keys).not.toContain('存储总量')
    expect(keys).not.toContain('网络流入')
    expect(keys).not.toContain('CPU 型号')
    expect(keys).not.toContain('运行时长')
  })

  it('test_kv_four_items kv 仅 4 项（操作系统 / CPU IOWait / Swap 使用率 / Inode 使用率）', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: { win: baseWin, server: makeServer() },
    })
    const keys = wrapper.findAll('.kv .k').map(n => n.text())
    expect(keys).toEqual(['操作系统', 'CPU IOWait', 'Swap 使用率', 'Inode 使用率'])
  })

  it('test_kv_os_displays_server_type kv「操作系统」渲染 server.serverType 原值', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: { win: baseWin, server: makeServer({ serverType: 'linux' }) },
    })
    const osRow = wrapper.findAll('.kv > div')[0]
    expect(osRow.find('span:last-child').text()).toBe('linux')
  })

  it('test_kv_os_displays_windows_server_type kv「操作系统」windows 原值', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: { win: baseWin, server: makeServer({ serverType: 'windows' }) },
    })
    const osRow = wrapper.findAll('.kv > div')[0]
    expect(osRow.find('span:last-child').text()).toBe('windows')
  })

  it('test_kv_os_dash_when_server_type_empty serverType 为空串时操作系统降级为 -', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: { win: baseWin, server: makeServer({ serverType: '' }) },
    })
    const osRow = wrapper.findAll('.kv > div')[0]
    expect(osRow.find('span:last-child').text()).toBe('-')
  })

  it('test_kv_os_metrics_render_percent kv 三项 OS 指标渲染百分比', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({ serverType: 'linux', iowait: 12.5, swap: 21, inode: 1 }),
      },
    })
    const rows = wrapper.findAll('.kv > div')
    expect(rows[1].find('span:last-child').text()).toBe('12.5%')
    expect(rows[2].find('span:last-child').text()).toBe('21%')
    expect(rows[3].find('span:last-child').text()).toBe('1%')
  })

  it('test_kv_os_metrics_dash_when_null kv 三项 OS 指标 null 显示 - 且灰', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: { win: baseWin, server: makeServer() },
    })
    const rows = wrapper.findAll('.kv > div')
    for (const i of [1, 2, 3]) {
      const val = rows[i].find('span:last-child')
      expect(val.text()).toBe('-')
      expect(val.attributes('style') || '').toContain('#9aa3af')
    }
  })

  it('test_kv_iowait_red_at_yaml_warn_20 iowait ≥ 20 标红（对齐 YAML warn）', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: { win: baseWin, server: makeServer({ iowait: 20 }) },
    })
    const val = wrapper.findAll('.kv > div')[1].find('span:last-child')
    expect(val.attributes('style') || '').toContain('#ff453a')
  })

  it('test_kv_iowait_green_below_warn iowait < 20 标绿', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: { win: baseWin, server: makeServer({ iowait: 19.9 }) },
    })
    const val = wrapper.findAll('.kv > div')[1].find('span:last-child')
    expect(val.attributes('style') || '').toContain('#1d9a40')
  })

  it('test_kv_swap_red_at_yaml_warn_30 swap ≥ 30 标红（对齐 YAML warn）', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: { win: baseWin, server: makeServer({ swap: 30 }) },
    })
    const val = wrapper.findAll('.kv > div')[2].find('span:last-child')
    expect(val.attributes('style') || '').toContain('#ff453a')
  })

  it('test_kv_inode_red_at_yaml_warn_80 inode ≥ 80 标红（对齐 YAML warn）', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: { win: baseWin, server: makeServer({ inode: 80 }) },
    })
    const val = wrapper.findAll('.kv > div')[3].find('span:last-child')
    expect(val.attributes('style') || '').toContain('#ff453a')
  })

  it('test_kv_swap_green_below_warn swap < 30 标绿', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: { win: baseWin, server: makeServer({ swap: 29 }) },
    })
    const val = wrapper.findAll('.kv > div')[2].find('span:last-child')
    expect(val.attributes('style') || '').toContain('#1d9a40')
  })

  it('test_kv_inode_green_below_warn inode < 80 标绿', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: { win: baseWin, server: makeServer({ inode: 79 }) },
    })
    const val = wrapper.findAll('.kv > div')[3].find('span:last-child')
    expect(val.attributes('style') || '').toContain('#1d9a40')
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
})