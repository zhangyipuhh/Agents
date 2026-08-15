// -*- coding:utf-8 -*-
/**
 * OpsDetailWindow 详情页改造测试（2026-08-16 用户需求）。
 *
 * 覆盖：
 *   - 头部 sub 改为「最新检测时间:」+ 绝对时间（与卡片 srv-card-time 文案一致）；
 *   - 4 联指标条：linux 4 项 / windows 3 项（隐藏负载）；
 *   - 指标值 ≥ 阈值时标红（CPU/内存 ≥ 80 红 / 负载 ≥ 4 红）；
 *   - kv 表格精简：保留 OS/CPU型号/运行时长；删除 内存总量/存储总量/网络流入；
 *   - 磁盘多列网格：每列盘符 + 三指标（使用率/排队(ms)/IO利用率）；
 *   - 磁盘列无进度条样式；
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

  // -------- 磁盘多列网格 --------
  it('test_disk_grid_renders_per_disk 每个 disk 一列', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({
          disks: [
            { name: 'C:\\', mount: 'C:\\', used: 91.5, ioUtilPct: 30, ioAwaitMs: 5 },
            { name: 'D:\\', mount: 'D:\\', used: 57.8, ioUtilPct: 20, ioAwaitMs: 8 },
            { name: 'E:\\', mount: 'E:\\', used: 39.9, ioUtilPct: 10, ioAwaitMs: 4 },
          ],
        }),
      },
    })
    const cells = wrapper.findAll('.disk-cell')
    expect(cells.length).toBe(3)
  })

  it('test_disk_cell_shows_three_metrics 每列展示使用率 / 排队 / IO 利用率', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({
          disks: [{ name: 'C:\\', mount: 'C:\\', used: 91.5, ioUtilPct: 30, ioAwaitMs: 5 }],
        }),
      },
    })
    const labels = wrapper.findAll('.disk-cell .dc-m-label').map(n => n.text())
    expect(labels).toEqual(['使用率', '排队', 'IO 利用率'])
    const values = wrapper.findAll('.disk-cell .dc-m-value').map(n => n.text())
    expect(values).toEqual(['91.5%', '5ms', '30%'])
  })

  it('test_disk_metric_red_when_above_threshold 单个磁盘指标 ≥ 80 时标红', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({
          disks: [{ name: 'C:\\', mount: 'C:\\', used: 91.5, ioUtilPct: 30, ioAwaitMs: 5 }],
        }),
      },
    })
    // 第一列（使用率 91.5）应红色
    const usedStyle = wrapper.findAll('.disk-cell .dc-m-value')[0].attributes('style') || ''
    expect(usedStyle).toContain('#ff453a')
    // 第二列（排队 5）应绿色
    const awaitStyle = wrapper.findAll('.disk-cell .dc-m-value')[1].attributes('style') || ''
    expect(awaitStyle).toContain('#1d9a40')
  })

  it('test_disk_metric_dash_when_null 磁盘字段为 null 时显示 -', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({
          disks: [{ name: '/', mount: '/', used: null, ioUtilPct: null, ioAwaitMs: null }],
        }),
      },
    })
    const values = wrapper.findAll('.disk-cell .dc-m-value').map(n => n.text())
    expect(values).toEqual(['-', '-', '-'])
    // 颜色应都是灰色
    const styles = wrapper.findAll('.disk-cell .dc-m-value').map(n => n.attributes('style') || '')
    styles.forEach(s => expect(s).toContain('#9aa3af'))
  })

  it('test_disk_cell_no_progress_bar 磁盘列无进度条样式', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: {
        win: baseWin,
        server: makeServer({
          disks: [{ name: 'C:\\', mount: 'C:\\', used: 50 }],
        }),
      },
    })
    // .disk-cell 内不能含 .bar
    expect(wrapper.find('.disk-cell .bar').exists()).toBe(false)
    // 整页也不能含老的 .bar 类（防止遗漏）
    expect(wrapper.find('.bar').exists()).toBe(false)
  })

  it('test_disk_grid_empty_when_no_disks 无 disks 时显示空态文案', () => {
    const wrapper = mount(OpsDetailWindow, {
      props: { win: baseWin, server: makeServer({ disks: [] }) },
    })
    expect(wrapper.find('.disk-grid').exists()).toBe(false)
    expect(wrapper.find('.disk-empty').text()).toBe('无磁盘数据')
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
  it('test_kv_os_displays_from_server_os kv「操作系统」渲染 server.os（非 '-'）', () => {
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