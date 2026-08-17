// -*- coding:utf-8 -*-
/**
 * OpsInspectionLogWindow 组件测试（2026-08-17 新增）。
 *
 * 覆盖：
 *   - 组件可被 import；
 *   - 左栏列表渲染：默认选中首条 / 状态徽章颜色映射 / 错误摘要非空展示；
 *   - 点击不同记录切换选中态；
 *   - 空态展示（records=[] / loading=true）；
 *   - 右栏（详情区）展示指标卡（CPU / 内存 / 存储）；
 *   - 窗口 max / close 按钮触发对应事件；
 *   - mapRecordToServer 纯函数：parsed_values → metrics / disks / load 等映射。
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import OpsInspectionLogWindow, {
  mapRecordToServer,
} from '../OpsInspectionLogWindow.vue'

const baseWin = { x: 0, y: 0, z: 1, max: false }

function makeBaseServer(overrides = {}) {
  return {
    id: 1,
    name: '本机',
    status: 'ok',
    serverType: 'linux',
    cpu: 30,
    mem: 40,
    disk: 50,
    load: 0.5,
    disks: [{ name: '/', mount: '/', used: 50, ioUtilPct: 10, ioAwaitMs: 1, partition: '/' }],
    fieldResults: [],
    collectedAt: '2026-08-17T10:00:00',
    ...overrides,
  }
}

function makeRecord(overrides = {}) {
  return {
    id: 100,
    server_id: 1,
    business_name: '本机',
    collected_at: '2026-08-17T10:00:00',
    success: true,
    inspection_status: 'pass',
    duration_ms: 1234,
    exit_code: 0,
    error_message: null,
    parsed_values: {
      cpu_used_pct: 45,
      mem_used_pct: 60,
      load_1m: 0.8,
      disks: [{ mount: '/', disk_used_pct: 70, io_util_pct: 30, io_await_ms: 5, partition: '/' }],
    },
    field_results: [],
    ...overrides,
  }
}

describe('mapRecordToServer 纯函数', () => {
  it('test_map_record_to_server_basic_fields parsed_values → metrics/disks/load 映射', () => {
    const base = makeBaseServer()
    const rec = makeRecord()
    const out = mapRecordToServer(rec, base)
    expect(out.id).toBe(base.id)
    expect(out.name).toBe(base.name)
    expect(out.serverType).toBe('linux')
    expect(out.cpu).toBe(45)
    expect(out.mem).toBe(60)
    expect(out.disk).toBe(70)    // system root mount '/'
    expect(out.load).toBe(0.8)
    expect(out.collectedAt).toBe(rec.collected_at)
    expect(out.disks).toHaveLength(1)
    expect(out.disks[0].mount).toBe('/')
    expect(out.disks[0].used).toBe(70)
  })

  it('test_map_record_status_pass_to_ok inspection_status=pass → status=ok', () => {
    const out = mapRecordToServer(makeRecord({ inspection_status: 'pass', success: true }), makeBaseServer())
    expect(out.status).toBe('ok')
  })

  it('test_map_record_status_warn_to_err inspection_status=warn → status=err', () => {
    const out = mapRecordToServer(makeRecord({ inspection_status: 'warn', success: true }), makeBaseServer())
    expect(out.status).toBe('err')
  })

  it('test_map_record_success_false_to_err success=false → status=err', () => {
    const out = mapRecordToServer(makeRecord({ success: false, inspection_status: 'pass' }), makeBaseServer())
    expect(out.status).toBe('err')
  })

  it('test_map_record_no_parsed_values 缺 parsed_values → 字段为 null 不报错', () => {
    const out = mapRecordToServer({ id: 1, server_id: 1, business_name: 'x' }, makeBaseServer())
    expect(out.cpu).toBeNull()
    expect(out.mem).toBeNull()
    expect(out.disk).toBeNull()
    expect(out.load).toBeNull()
    expect(out.disks).toEqual([])
    expect(out.fieldResults).toEqual([])
  })

  it('test_map_record_null_input null record → 返回 baseServer', () => {
    const base = makeBaseServer({ id: 99 })
    const out = mapRecordToServer(null, base)
    expect(out).toBe(base)
  })
})

describe('OpsInspectionLogWindow 组件', () => {
  it('test_window_importable 组件可被 import', () => {
    expect(OpsInspectionLogWindow).toBeTruthy()
    expect(typeof OpsInspectionLogWindow).toBe('object')
  })

  it('test_renders_left_list_with_records 传入 records 后左栏渲染对应条目 + 默认选中首条', () => {
    const records = [
      makeRecord({ id: 1, collected_at: '2026-08-17T10:00:00' }),
      makeRecord({ id: 2, collected_at: '2026-08-17T09:00:00' }),
      makeRecord({ id: 3, collected_at: '2026-08-17T08:00:00' }),
    ]
    const wrapper = mount(OpsInspectionLogWindow, {
      props: { win: baseWin, server: makeBaseServer(), records },
    })
    const items = wrapper.findAll('.inslog-item')
    expect(items.length).toBe(3)
    // 默认选中首条
    expect(items[0].classes()).toContain('active')
    expect(items[1].classes()).not.toContain('active')
  })

  it('test_renders_record_status_badge 状态徽章颜色映射（pass/warn/crit）', () => {
    const records = [
      makeRecord({ id: 1, inspection_status: 'pass' }),
      makeRecord({ id: 2, inspection_status: 'warn' }),
      makeRecord({ id: 3, inspection_status: 'crit' }),
    ]
    const wrapper = mount(OpsInspectionLogWindow, {
      props: { win: baseWin, server: makeBaseServer(), records },
    })
    const badges = wrapper.findAll('.inslog-badge')
    expect(badges[0].classes()).toContain('pass')
    expect(badges[1].classes()).toContain('warn')
    expect(badges[2].classes()).toContain('crit')
  })

  it('test_click_record_updates_selection 点击记录切换选中态', async () => {
    const records = [
      makeRecord({ id: 1, collected_at: '2026-08-17T10:00:00' }),
      makeRecord({ id: 2, collected_at: '2026-08-17T09:00:00' }),
    ]
    const wrapper = mount(OpsInspectionLogWindow, {
      props: { win: baseWin, server: makeBaseServer(), records },
    })
    // 初始首条 active
    expect(wrapper.findAll('.inslog-item')[0].classes()).toContain('active')
    // 点击第二条
    await wrapper.findAll('.inslog-item')[1].trigger('click')
    expect(wrapper.findAll('.inslog-item')[0].classes()).not.toContain('active')
    expect(wrapper.findAll('.inslog-item')[1].classes()).toContain('active')
  })

  it('test_empty_state_no_records records=[] → 显示「暂无采集记录」', () => {
    const wrapper = mount(OpsInspectionLogWindow, {
      props: { win: baseWin, server: makeBaseServer(), records: [] },
    })
    expect(wrapper.find('.inslog-empty').exists()).toBe(true)
    expect(wrapper.find('.inslog-empty').text()).toBe('暂无采集记录')
  })

  it('test_loading_state_shows_loading_text loading=true → 显示「加载中…」', () => {
    const wrapper = mount(OpsInspectionLogWindow, {
      props: { win: baseWin, server: makeBaseServer(), records: [], loading: true },
    })
    expect(wrapper.find('.inslog-empty').exists()).toBe(true)
    expect(wrapper.find('.inslog-empty').text()).toBe('加载中…')
  })

  it('test_right_pane_renders_record_metrics 右栏展示选中记录的指标卡', () => {
    const records = [makeRecord()]
    const wrapper = mount(OpsInspectionLogWindow, {
      props: { win: baseWin, server: makeBaseServer(), records },
    })
    // .detail-metric-bar 至少 3 个 dm-item（CPU/内存/存储）
    const items = wrapper.findAll('.detail-metric-bar .dm-item')
    expect(items.length).toBeGreaterThanOrEqual(3)
    // 第一项 = CPU 使用率
    expect(items[0].find('.dm-label').text()).toBe('CPU 使用率')
  })

  it('test_record_with_error_message_shows_err_summary error_message 非空 → 列表展示红字摘要', () => {
    const records = [
      makeRecord({ id: 1, success: false, error_message: 'SSH 连接超时', inspection_status: 'crit' }),
    ]
    const wrapper = mount(OpsInspectionLogWindow, {
      props: { win: baseWin, server: makeBaseServer(), records },
    })
    const errEl = wrapper.find('.inslog-err')
    expect(errEl.exists()).toBe(true)
    expect(errEl.text()).toBe('SSH 连接超时')
  })

  it('test_emits_close_via_close_button 窗口 close 按钮触发 close 事件', async () => {
    const wrapper = mount(OpsInspectionLogWindow, {
      props: { win: baseWin, server: makeBaseServer(), records: [] },
    })
    await wrapper.find('.win-control--close').trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()
    expect(wrapper.emitted('close').length).toBe(1)
  })

  it('test_emits_max_via_max_button 窗口 max 按钮触发 max 事件', async () => {
    const wrapper = mount(OpsInspectionLogWindow, {
      props: { win: baseWin, server: makeBaseServer(), records: [] },
    })
    await wrapper.find('.win-control--max').trigger('click')
    expect(wrapper.emitted('max')).toBeTruthy()
    expect(wrapper.emitted('max').length).toBe(1)
  })

  it('test_window_title_contains_server_name 窗口标题包含服务器名称', () => {
    const wrapper = mount(OpsInspectionLogWindow, {
      props: { win: baseWin, server: makeBaseServer({ name: '生产机-01' }), records: [] },
    })
    expect(wrapper.find('.win-title').text()).toContain('生产机-01')
    expect(wrapper.find('.win-title').text()).toContain('采集记录')
  })
})
