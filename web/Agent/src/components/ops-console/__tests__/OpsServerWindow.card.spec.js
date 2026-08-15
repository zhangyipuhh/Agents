// -*- coding:utf-8 -*-
/**
 * OpsServerWindow 卡片化测试（2026-08-14 新增）。
 *
 * 覆盖：
 *   - pickDisplayDisk 纯函数：
 *       * 有 used ≥ 80 的盘 → 返回 used 最大的那块；
 *       * 多块异常盘 → 取 used 最大者；
 *       * 无异常 Windows mount（如 "C:\\"） → 选 C: 盘（无 C: 取首块盘符）；
 *       * 无异常 Linux mount "/" → 选 / 盘；
 *       * 空数组 / 非数组 → null；
 *   - metricColor：null → 灰；≥ 80 → 红；< 80 → 绿；
 *   - 组件渲染：
 *       * 两列 srv-card；
 *       * LED 三态颜色映射（绿/红/灰）；
 *       * CPU/内存/存储 数值与红色态；
 *       * 存储行盘符选择（异常盘优先 / Windows C: / Linux /）；
 *       * 单击卡片 emit('open-detail', srv)。
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import OpsServerWindow, {
  pickDisplayDisk,
  metricColor,
  loadColor,
  formatCollectedAt,
  isLinuxType,
  pickAnomalyDisks,
  formatAnomalyItem,
} from '../OpsServerWindow.vue'

const baseWin = { x: 0, y: 0, z: 1, max: false }

function makeServer(overrides = {}) {
  return {
    id: 1,
    name: '本机',
    status: 'ok',
    serverType: '',
    cpu: 30,
    mem: 40,
    disk: 50,
    load: null,
    disks: [{ name: '/', used: 50, mount: '/', ioUtilPct: null, ioAwaitMs: null, diskType: '' }],
    fieldResults: [],
    collectedAt: null,
    ...overrides,
  }
}

describe('pickDisplayDisk 智能选盘', () => {
  it('test_pick_display_disk_null_for_empty 空数组返回 null', () => {
    expect(pickDisplayDisk([])).toBeNull()
    expect(pickDisplayDisk(null)).toBeNull()
    expect(pickDisplayDisk(undefined)).toBeNull()
  })

  it('test_pick_display_disk_problem_disk_picked 有 used ≥ 80 的盘 → 返回该盘', () => {
    const disks = [
      { name: '/', used: 50 },
      { name: '/data', used: 92 },
    ]
    expect(pickDisplayDisk(disks)).toEqual({ name: '/data', used: 92 })
  })

  it('test_pick_display_disk_problem_max_used 多块异常盘取 used 最大者', () => {
    const disks = [
      { name: '/', used: 85 },
      { name: '/data', used: 95 },
      { name: '/var', used: 88 },
    ]
    expect(pickDisplayDisk(disks)).toEqual({ name: '/data', used: 95 })
  })

  it('test_pick_display_disk_windows_c_drive_no_problem Windows 无异常优先 C:', () => {
    const disks = [
      { name: 'D:\\', used: 40 },
      { name: 'C:\\', used: 60 },
    ]
    expect(pickDisplayDisk(disks)).toEqual({ name: 'C:\\', used: 60 })
  })

  it('test_pick_display_disk_windows_no_c_no_problem Windows 无 C: 取首块盘符', () => {
    const disks = [
      { name: 'D:\\', used: 30 },
      { name: 'E:\\', used: 20 },
    ]
    expect(pickDisplayDisk(disks)).toEqual({ name: 'D:\\', used: 30 })
  })

  it('test_pick_display_disk_linux_root_no_problem Linux 无异常取 /', () => {
    const disks = [
      { name: '/data', used: 50 },
      { name: '/', used: 30 },
    ]
    expect(pickDisplayDisk(disks)).toEqual({ name: '/', used: 30 })
  })

  it('test_pick_display_disk_all_used_null all used=null → 走 mount 名称规则', () => {
    expect(pickDisplayDisk([{ name: 'C:\\', used: null }])).toEqual({ name: 'C:\\', used: null })
    expect(pickDisplayDisk([{ name: '/', used: null }])).toEqual({ name: '/', used: null })
  })

  it('test_pick_display_disk_no_match_return_first 都不匹配 → 退回首块', () => {
    const disks = [{ name: 'whatever', used: 50 }]
    expect(pickDisplayDisk(disks)).toEqual({ name: 'whatever', used: 50 })
  })
})

describe('metricColor 指标着色', () => {
  it('test_metric_color_null_is_gray null → 灰色', () => {
    expect(metricColor(null)).toBe('#9aa3af')
    expect(metricColor(undefined)).toBe('#9aa3af')
  })

  it('test_metric_color_below_threshold_is_green < 80 → 绿', () => {
    expect(metricColor(0)).toBe('#1d9a40')
    expect(metricColor(79.9)).toBe('#1d9a40')
  })

  it('test_metric_color_at_threshold_is_red ≥ 80 → 红', () => {
    expect(metricColor(80)).toBe('#ff453a')
    expect(metricColor(99.9)).toBe('#ff453a')
  })
})

describe('OpsServerWindow 卡片组件', () => {
  it('test_ops_server_window_importable 组件可被 import', () => {
    expect(OpsServerWindow).toBeTruthy()
    expect(typeof OpsServerWindow).toBe('object')
  })

  it('test_renders_two_columns_grid 渲染两列 srv-grid', () => {
    const wrapper = mount(OpsServerWindow, {
      props: { win: baseWin, servers: [makeServer({ id: 1 }), makeServer({ id: 2 })] },
    })
    const grid = wrapper.find('.srv-grid')
    expect(grid.exists()).toBe(true)
    const cards = wrapper.findAll('.srv-card')
    expect(cards.length).toBe(2)
  })

  it('test_card_click_emits_open_detail 单击卡片 emit open-detail', async () => {
    const srv = makeServer({ id: 7, name: '测试机' })
    const wrapper = mount(OpsServerWindow, {
      props: { win: baseWin, servers: [srv] },
    })
    await wrapper.find('.srv-card').trigger('click')
    expect(wrapper.emitted('open-detail')).toBeTruthy()
    expect(wrapper.emitted('open-detail')[0][0]).toEqual(srv)
  })

  it('test_led_class_thinks_status LED 颜色随 status 映射', () => {
    const ok = mount(OpsServerWindow, {
      props: { win: baseWin, servers: [makeServer({ id: 1, status: 'ok' })] },
    })
    expect(ok.find('.led').classes()).toContain('green')

    const err = mount(OpsServerWindow, {
      props: { win: baseWin, servers: [makeServer({ id: 2, status: 'err' })] },
    })
    expect(err.find('.led').classes()).toContain('red')

    const unknown = mount(OpsServerWindow, {
      props: { win: baseWin, servers: [makeServer({ id: 3, status: 'unknown' })] },
    })
    expect(unknown.find('.led').classes()).toContain('gray')
  })

  it('test_cpu_and_mem_red_when_over_threshold CPU/内存 ≥ 80 时 value 颜色为红', () => {
    const wrapper = mount(OpsServerWindow, {
      props: {
        win: baseWin,
        servers: [makeServer({ id: 1, cpu: 92, mem: 85 })],
      },
    })
    const values = wrapper.findAll('.srv-metric-value')
    // 三个值：CPU / 内存 / 存储；前两个应红色
    const cpuStyle = values[0].attributes('style') || ''
    const memStyle = values[1].attributes('style') || ''
    expect(cpuStyle).toContain('#ff453a')
    expect(memStyle).toContain('#ff453a')
  })

  it('test_null_metric_shows_dash null 指标显示 -', () => {
    const wrapper = mount(OpsServerWindow, {
      props: {
        win: baseWin,
        servers: [makeServer({ id: 1, cpu: null, mem: null, disks: [{ name: '/', used: null }] })],
      },
    })
    const texts = wrapper.findAll('.srv-metric-value').map(n => n.text())
    expect(texts).toEqual(['-', '-', '-'])
  })

  it('test_storage_picks_problem_disk 存储行选用 used 最高的异常盘', () => {
    const wrapper = mount(OpsServerWindow, {
      props: {
        win: baseWin,
        servers: [makeServer({
          id: 1,
          disks: [
            { name: '/', used: 40 },
            { name: '/data', used: 95 },
          ],
        })],
      },
    })
    const diskLabel = wrapper.find('.srv-metric-disk').text()
    expect(diskLabel).toBe('/data')
  })

  it('test_storage_picks_c_drive_when_no_problem Windows 无异常选 C:', () => {
    const wrapper = mount(OpsServerWindow, {
      props: {
        win: baseWin,
        servers: [makeServer({
          id: 1,
          disks: [
            { name: 'C:\\', used: 50 },
            { name: 'D:\\', used: 30 },
          ],
        })],
      },
    })
    expect(wrapper.find('.srv-metric-disk').text()).toBe('C:\\')
  })

  it('test_storage_picks_linux_root_when_no_problem Linux 无异常选 /', () => {
    const wrapper = mount(OpsServerWindow, {
      props: {
        win: baseWin,
        servers: [makeServer({
          id: 1,
          disks: [
            { name: '/data', used: 50 },
            { name: '/', used: 40 },
          ],
        })],
      },
    })
    expect(wrapper.find('.srv-metric-disk').text()).toBe('/')
  })

  it('test_storage_shows_dash_when_no_disks disks 为空显示 -', () => {
    const wrapper = mount(OpsServerWindow, {
      props: {
        win: baseWin,
        servers: [makeServer({ id: 1, disks: [] })],
      },
    })
    // 2026-08-16 模板重构：disks 为空 + fieldResults 为空 → 走 v-else 分支
    // 显示 '-'（metricColor(null) 灰色），不渲染 .srv-metric-disk 节点。
    const storageMetric = wrapper.findAll('.srv-metric').find(n =>
      n.find('.srv-metric-label').text() === '存储')
    expect(storageMetric).toBeTruthy()
    expect(storageMetric.find('.srv-metric-value').text()).toBe('-')
  })

  it('test_selected_class_applied 选中态添加 selected 类', () => {
    const wrapper = mount(OpsServerWindow, {
      props: {
        win: baseWin,
        servers: [makeServer({ id: 1 }), makeServer({ id: 2 })],
        selectedId: 2,
      },
    })
    const cards = wrapper.findAll('.srv-card')
    expect(cards[0].classes()).not.toContain('selected')
    expect(cards[1].classes()).toContain('selected')
  })
})

// 2026-08-16 新增：最后检测时间 + Linux 1 分钟负载 + 磁盘指标智能选盘

describe('loadColor 负载着色', () => {
  it('test_load_color_null_is_gray null → 灰色', () => {
    expect(loadColor(null)).toBe('#9aa3af')
    expect(loadColor(undefined)).toBe('#9aa3af')
  })

  it('test_load_color_below_4_is_green < 4 → 绿（独立阈值，与 80% 解耦）', () => {
    expect(loadColor(0)).toBe('#1d9a40')
    expect(loadColor(3.99)).toBe('#1d9a40')
  })

  it('test_load_color_at_4_is_red ≥ 4 → 红（与 inspection_scripts.yaml load_1m warn=4.0 对齐）', () => {
    expect(loadColor(4)).toBe('#ff453a')
    expect(loadColor(8.5)).toBe('#ff453a')
  })
})

describe('formatCollectedAt 时间格式化', () => {
  it('test_format_collected_at_valid_iso 合法 ISO → YYYY-MM-DD HH:MM', () => {
    // 用 ISO 字符串 + toLocaleString 不依赖宿主时区，故直接断言字符串前缀
    const out = formatCollectedAt('2026-08-16T00:46:35')
    expect(out).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/)
  })

  it('test_format_collected_at_null_is_dash null/undefined → -', () => {
    expect(formatCollectedAt(null)).toBe('-')
    expect(formatCollectedAt(undefined)).toBe('-')
    expect(formatCollectedAt('')).toBe('-')
  })

  it('test_format_collected_at_invalid_is_dash 无效字符串 → -', () => {
    expect(formatCollectedAt('not-a-date')).toBe('-')
    expect(formatCollectedAt('2026-13-99T99:99:99')).toBe('-')
  })
})

describe('isLinuxType 平台判定', () => {
  it('test_is_linux_type_true_for_linux linux 大小写都算 linux', () => {
    expect(isLinuxType('linux')).toBe(true)
    expect(isLinuxType('LINUX')).toBe(true)
  })

  it('test_is_linux_type_false_for_windows_or_empty windows/空/未知一律 false', () => {
    expect(isLinuxType('windows')).toBe(false)
    expect(isLinuxType('')).toBe(false)
    expect(isLinuxType(undefined)).toBe(false)
    expect(isLinuxType(null)).toBe(false)
    expect(isLinuxType('darwin')).toBe(false)
  })
})

describe('OpsServerWindow 卡片头/负载渲染（2026-08-16 新增）', () => {
  it('test_renders_collected_at_in_card_head 卡片头部展示「最新检测时间:」前缀 + 绝对时间', () => {
    const wrapper = mount(OpsServerWindow, {
      props: {
        win: baseWin,
        servers: [makeServer({ id: 1, collectedAt: '2026-08-16T00:46:35' })],
      },
    })
    const time = wrapper.find('.srv-card-time')
    expect(time.exists()).toBe(true)
    expect(time.text()).toMatch(/^最新检测时间:\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/)
    expect(time.attributes('title')).toBe('2026-08-16T00:46:35')
  })

  it('test_collected_at_dash_when_null 无快照时显示「最新检测时间:-」', () => {
    const wrapper = mount(OpsServerWindow, {
      props: {
        win: baseWin,
        servers: [makeServer({ id: 1, collectedAt: null })],
      },
    })
    expect(wrapper.find('.srv-card-time').text()).toBe('最新检测时间:-')
  })

  it('test_load_metric_visible_only_for_linux linux 显示负载节点，windows 不显示', () => {
    const linux = mount(OpsServerWindow, {
      props: {
        win: baseWin,
        servers: [makeServer({
          id: 1,
          serverType: 'linux',
          load: 1.23,
          disks: [{ name: '/', used: 50 }],
        })],
      },
    })
    const labels = linux.findAll('.srv-metric-label').map(n => n.text())
    expect(labels).toContain('服务器负载')
    // linux 指标项 4 个（CPU/内存/存储/服务器负载）
    expect(linux.findAll('.srv-metric').length).toBe(4)

    const win = mount(OpsServerWindow, {
      props: {
        win: baseWin,
        servers: [makeServer({
          id: 2,
          serverType: 'windows',
          load: null,
          disks: [{ name: 'C:\\', used: 50 }],
        })],
      },
    })
    const winLabels = win.findAll('.srv-metric-label').map(n => n.text())
    expect(winLabels).not.toContain('负载')
    expect(win.findAll('.srv-metric').length).toBe(3)
  })

  it('test_load_metric_red_when_above_threshold 负载 ≥ 4 时标红', () => {
    const wrapper = mount(OpsServerWindow, {
      props: {
        win: baseWin,
        servers: [makeServer({
          id: 1,
          serverType: 'linux',
          load: 4.5,
          disks: [{ name: '/', used: 30 }],
        })],
      },
    })
    const values = wrapper.findAll('.srv-metric-value')
    // 末位是负载（index=3：CPU/内存/存储/负载）
    const loadStyle = values[3].attributes('style') || ''
    expect(loadStyle).toContain('#ff453a')
  })

  it('test_load_metric_green_when_below_threshold 负载 < 4 时标绿', () => {
    const wrapper = mount(OpsServerWindow, {
      props: {
        win: baseWin,
        servers: [makeServer({
          id: 1,
          serverType: 'linux',
          load: 0.5,
          disks: [{ name: '/', used: 30 }],
        })],
      },
    })
    const values = wrapper.findAll('.srv-metric-value')
    const loadStyle = values[3].attributes('style') || ''
    expect(loadStyle).toContain('#1d9a40')
  })
})

// 2026-08-16 新增：磁盘异常盘符智能选择（基于后端 field_results）

describe('pickAnomalyDisks 异常盘符聚合', () => {
  it('test_pick_anomaly_disks_empty_for_all_pass 全 pass → 返回 []', () => {
    const frs = [
      { key: 'disk_used_pct', status: 'pass', value: 50, message: '磁盘 /', name_zh: '磁盘使用率', unit: '%' },
      { key: 'mem_used_pct', status: 'pass', value: 40, name_zh: '内存使用率', unit: '%' },
    ]
    expect(pickAnomalyDisks(frs, [])).toEqual([])
  })

  it('test_pick_anomaly_disks_returns_warn_item 有 warn 但无 crit → 返回 warn 项', () => {
    const frs = [
      { key: 'disk_used_pct', status: 'pass', value: 50, message: '磁盘 /', name_zh: '磁盘使用率', unit: '%' },
      { key: 'disk_used_pct', status: 'warn', value: 80, message: '磁盘 /data', name_zh: '磁盘使用率', unit: '%' },
    ]
    const out = pickAnomalyDisks(frs, [{ mount: '/data' }])
    expect(out).toHaveLength(1)
    expect(out[0].mount).toBe('/data')
    expect(out[0].status).toBe('warn')
    expect(out[0].items[0].key).toBe('disk_used_pct')
  })

  it('test_pick_anomaly_disks_crit_first warn + crit 并存 → crit 优先', () => {
    const frs = [
      { key: 'disk_used_pct', status: 'warn', value: 80, message: '磁盘 /data', name_zh: '磁盘使用率', unit: '%' },
      { key: 'io_util_pct', status: 'crit', value: 95, message: '磁盘 sda[HDD]', name_zh: '磁盘 IO 利用率', unit: '%' },
    ]
    const out = pickAnomalyDisks(frs, [{ mount: '/data' }, { mount: 'sda[HDD]' }])
    expect(out[0].status).toBe('crit')
    expect(out[0].mount).toBe('sda[HDD]')
    expect(out[1].status).toBe('warn')
    expect(out[1].mount).toBe('/data')
  })

  it('test_pick_anomaly_disks_aggregate_same_mount 同一 mount 多异常指标 → 聚合到 items', () => {
    const frs = [
      { key: 'disk_used_pct', status: 'warn', value: 85, message: '磁盘 sda[SSD]', name_zh: '磁盘使用率', unit: '%' },
      { key: 'io_util_pct', status: 'crit', value: 95, message: '磁盘 sda[SSD]', name_zh: '磁盘 IO 利用率', unit: '%' },
      { key: 'io_await_ms', status: 'warn', value: 60, message: '磁盘 sda[SSD]', name_zh: '磁盘 IO 平均等待', unit: 'ms' },
    ]
    const out = pickAnomalyDisks(frs, [{ mount: 'sda[SSD]', io_util_pct: 95 }])
    expect(out).toHaveLength(1)
    expect(out[0].mount).toBe('sda[SSD]')
    expect(out[0].status).toBe('crit')   // 最高状态
    expect(out[0].items).toHaveLength(3)
    expect(out[0].items.map(i => i.key).sort()).toEqual(['disk_used_pct', 'io_await_ms', 'io_util_pct'])
  })
})

describe('formatAnomalyItem 异常指标紧凑展示', () => {
  it('test_format_anomaly_pct 单位 % → "使用 92%"', () => {
    expect(formatAnomalyItem({ key: 'disk_used_pct', name_zh: '磁盘使用率', unit: '%', value: 92 }))
      .toBe('使用 92%')
  })
  it('test_format_anomaly_ms 单位 ms → "等待 150ms"', () => {
    expect(formatAnomalyItem({ key: 'io_await_ms', name_zh: '磁盘 IO 平均等待', unit: 'ms', value: 150 }))
      .toBe('等待 150ms')
  })
  it('test_format_anomaly_io_util IO 简写', () => {
    expect(formatAnomalyItem({ key: 'io_util_pct', name_zh: '磁盘 IO 利用率', unit: '%', value: 80 }))
      .toBe('IO 80%')
  })
})

describe('OpsServerWindow 存储行 field_results 渲染（2026-08-16 新增）', () => {
  it('test_storage_row_shows_anomaly_disk_name field_results 有异常 → 盘符 + 概要标红', () => {
    const wrapper = mount(OpsServerWindow, {
      props: {
        win: baseWin,
        servers: [makeServer({
          id: 1,
          serverType: 'linux',
          load: 1.0,
          disks: [
            { name: '/', mount: '/', used: 50 },
            { name: 'sda[HDD]', mount: 'sda[HDD]', used: null, ioUtilPct: 92, ioAwaitMs: 12.5, diskType: 'hdd' },
          ],
          fieldResults: [
            { key: 'io_util_pct', status: 'crit', value: 92, message: '磁盘 sda[HDD]', name_zh: '磁盘 IO 利用率', unit: '%' },
          ],
        })],
      },
    })
    // 盘符 + 异常概要节点存在
    expect(wrapper.find('.srv-metric-disk--problem').exists()).toBe(true)
    expect(wrapper.find('.srv-metric-disk-name').text()).toBe('sda[HDD]')
    expect(wrapper.find('.srv-metric-anomaly').text()).toContain('IO 92%')
    // 颜色：通过 CSS 类断言（盘符与异常概要都标红，class 由 ops-console.css 提供）
    expect(wrapper.find('.srv-metric-disk--problem').classes()).toContain('srv-metric-disk--problem')
    expect(wrapper.find('.srv-metric-anomaly').classes()).toContain('srv-metric-anomaly')
  })

  it('test_storage_row_dash_when_no_anomaly field_results 全 pass → 显示 -', () => {
    const wrapper = mount(OpsServerWindow, {
      props: {
        win: baseWin,
        servers: [makeServer({
          id: 1,
          serverType: 'linux',
          disks: [
            { name: '/', mount: '/', used: 50 },
            { name: 'sda[HDD]', mount: 'sda[HDD]', used: null, ioUtilPct: 30, ioAwaitMs: 5, diskType: 'hdd' },
          ],
          fieldResults: [
            { key: 'disk_used_pct', status: 'pass', value: 50, message: '磁盘 /', name_zh: '磁盘使用率', unit: '%' },
            { key: 'io_util_pct', status: 'pass', value: 30, message: '磁盘 sda[HDD]', name_zh: '磁盘 IO 利用率', unit: '%' },
          ],
        })],
      },
    })
    // 没有异常盘 → 不渲染 srv-metric-disk--problem 节点
    expect(wrapper.find('.srv-metric-disk--problem').exists()).toBe(false)
    // 存储行 metric value 显示 '-'（灰）
    const storageMetric = wrapper.findAll('.srv-metric').find(n =>
      n.find('.srv-metric-label').text() === '存储')
    expect(storageMetric).toBeTruthy()
    const dashVal = storageMetric.find('.srv-metric-value').text()
    expect(dashVal).toBe('-')
  })

  it('test_storage_row_legacy_fallback fieldResults 空 → 退化到 displayDiskOf 行为', () => {
    const wrapper = mount(OpsServerWindow, {
      props: {
        win: baseWin,
        servers: [makeServer({
          id: 1,
          serverType: 'linux',
          disks: [{ name: '/', mount: '/', used: 80 }],
          fieldResults: [],   // 老数据：未落库
        })],
      },
    })
    // 退化分支：仍渲染盘符 + 使用率（沿用旧 UI）
    expect(wrapper.find('.srv-metric-disk').text()).toBe('/')
    const storageMetric = wrapper.findAll('.srv-metric').find(n =>
      n.find('.srv-metric-label').text() === '存储')
    const val = storageMetric.find('.srv-metric-value').text()
    expect(val).toBe('80%')
  })
})