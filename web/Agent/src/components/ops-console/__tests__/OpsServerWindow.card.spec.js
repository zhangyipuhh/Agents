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
import OpsServerWindow, { pickDisplayDisk, metricColor } from '../OpsServerWindow.vue'

const baseWin = { x: 0, y: 0, z: 1, max: false }

function makeServer(overrides = {}) {
  return {
    id: 1,
    name: '本机',
    status: 'ok',
    cpu: 30,
    mem: 40,
    disk: 50,
    disks: [{ name: '/', used: 50 }],
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
    expect(wrapper.find('.srv-metric-disk').text()).toBe('-')
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