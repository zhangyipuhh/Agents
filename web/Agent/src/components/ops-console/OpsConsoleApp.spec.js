// -*- coding:utf-8 -*-
/**
 * OpsConsoleApp 组件冒烟测试（2026-08-05 新增）。
 *
 * 覆盖：
 *   - 组件可被 import；
 *   - 挂载时不抛异常（mock fetchWithAuth）；
 *   - 加载成功后 servers 列表渲染（映射函数 / loadLatest 链路）。
 *
 * 2026-08-08 等保三级改造更新：
 *   - onMounted 增加 validateToken() 主动引导 refresh（防止父窗口超时后页面拉不到数据），
 *     mock 中补 validateToken，否则测试会 await 一个未导出的 undefined；
 *   - 组件从独立 HTML 入口根组件改为 App.vue 内嵌子页面，组件语义保持不变，
 *     测试无需重构（仍以 mount(OpsConsoleApp) 验证根状态机即可）。
 *
 * 2026-08-14 菜单栏重构：移除 OpsDockBar stub（组件已彻底删除）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// mock api.js：fetchServerInspectionLatest 返回 2 行（1 ok + 1 unknown）；
// 2026-08-08 等保三级改造：补 validateToken（onMounted 主动引导 refresh）
vi.mock('../../utils/api.js', () => ({
  fetchServerInspectionLatest: vi.fn(async () => ({
    items: [
      {
        node_id: 11,
        node_name: 'MyA',
        server_id: 1,
        business_name: 'biz-A',
        server_type: 'linux',
        status: 'ok',
        inspection_status: 'pass',
        collected_at: '2026-08-05T10:00:00',
        duration_ms: 42,
        metrics: { cpu: 23.5, mem: 45.0, disk: 58.0 },
        disks: [{ mount: '/', disk_used_pct: 58 }],
        parsed_values: { disks: [{ mount: '/', disk_used_pct: 58 }],
                          mem_used_pct: 45.0, cpu_idle_pct: 76.5,
                          uptime_hours: 36 },
        error_message: null,
      },
      {
        node_id: null,
        node_name: 'biz-B',
        server_id: 2,
        business_name: 'biz-B',
        server_type: 'windows',
        status: 'unknown',
        inspection_status: null,
        collected_at: null,
        duration_ms: null,
        metrics: { cpu: null, mem: null, disk: null },
        disks: [],
        parsed_values: {},
        error_message: null,
      },
    ],
  })),
  validateToken: vi.fn(async () => ({ username: 'tester', role: 'admin', allowed_agents: [] })),
}))

import OpsConsoleApp from './OpsConsoleApp.vue'

describe('OpsConsoleApp 运维控制台根组件', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('test_ops_console_app_importable 组件可被 import', () => {
    expect(OpsConsoleApp).toBeTruthy()
  })

  it('test_ops_console_app_mounts_without_error 组件挂载不抛异常', async () => {
    // stub 子组件：避免引入更多依赖；只验证根组件能挂载并触发 loadLatest
    const wrapper = mount(OpsConsoleApp, {
      global: {
        stubs: {
          OpsMenuBar: true,
          OpsServerWindow: true,
          OpsDetailWindow: true,
          OpsLogManager: true,
          OpsLogViewer: true,
        },
      },
    })
    await flushPromises()
    // loadLatest 调过一次
    const api = await import('../../utils/api.js')
    expect(api.fetchServerInspectionLatest).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('test_ops_console_app_uses_map_snapshot_to_server mapping 验证映射：ip='-'、name=node_name', async () => {
    // 通过 mount 后访问内部 servers 数据（通过 wrapper.vm）
    const wrapper = mount(OpsConsoleApp, {
      global: {
        stubs: {
          OpsMenuBar: true,
          OpsServerWindow: true,
          OpsDetailWindow: true,
          OpsLogManager: true,
          OpsLogViewer: true,
        },
      },
    })
    await flushPromises()
    // servers 应为 2 行
    const servers = wrapper.vm.servers
    expect(servers).toHaveLength(2)
    expect(servers[0].id).toBe(1)
    expect(servers[0].name).toBe('MyA')           // node_name 优先
    expect(servers[0].ip).toBe('-')               // 不返 ip
    expect(servers[0].status).toBe('ok')
    expect(servers[0].cpu).toBe(23.5)
    expect(servers[1].status).toBe('unknown')     // 无快照 → unknown
    expect(servers[1].cpu).toBeNull()
    wrapper.unmount()
  })

  // 2026-08-16 修复：之前硬编码 os/cpuModel='-'，导致详情页 kv 三项始终为占位符。
  // 修复后 mapSnapshotToServer 必须从 parsed_values 读取 os/cpu_model/uptime_hours。
  it('test_map_snapshot_reads_os_cpu_model_uptime mapping 从 parsed_values 读取 os / cpu_model / uptime_hours', async () => {
    const wrapper = mount(OpsConsoleApp, {
      global: {
        stubs: {
          OpsMenuBar: true,
          OpsServerWindow: true,
          OpsDetailWindow: true,
          OpsLogManager: true,
          OpsLogViewer: true,
        },
      },
    })
    await flushPromises()
    const servers = wrapper.vm.servers
    expect(servers[0].os).toBe('-')            // mock 中 parsed_values 没 os → 降级
    expect(servers[0].cpuModel).toBe('-')      // mock 中 parsed_values 没 cpu_model → 降级
    expect(servers[0].uptime).toBe('36 小时')  // mock 中 parsed_values.uptime_hours=36
    wrapper.unmount()
  })

  // 2026-08-16：mock 增加 os / cpu_model 字段，验证前端能消费真实 DB 数据。
  it('test_map_snapshot_consumes_real_db_os_cpu_model mapping 消费真实 DB 字段（os="Microsoft Windows 11"）', async () => {
    // 重置 mock 让 fetchServerInspectionLatest 返回带 os/cpu_model 的数据
    const api = await import('../../utils/api.js')
    api.fetchServerInspectionLatest.mockResolvedValueOnce({
      items: [
        {
          node_id: 11,
          node_name: 'MyA',
          server_id: 1,
          business_name: 'biz-A',
          server_type: 'windows',
          status: 'ok',
          inspection_status: 'pass',
          collected_at: '2026-08-15T18:00:14.283Z',
          duration_ms: 42,
          metrics: { cpu: 10, mem: 38.1, disk: 78.1, load: null },
          disks: [{ mount: 'C:\\', disk_used_pct: 78.1 }],
          parsed_values: {
            disks: [{ mount: 'C:\\', disk_used_pct: 78.1 }],
            mem_used_pct: 38.1,
            cpu_used_pct: 10,
            uptime_hours: 3.4,
            os: 'Microsoft Windows 11',
            cpu_model: '13th Gen Intel(R) Core(TM) i7-13620H',
          },
          field_results: [],
          error_message: null,
        },
      ],
    })
    const wrapper = mount(OpsConsoleApp, {
      global: {
        stubs: {
          OpsMenuBar: true,
          OpsServerWindow: true,
          OpsDetailWindow: true,
          OpsLogManager: true,
          OpsLogViewer: true,
        },
      },
    })
    await flushPromises()
    const servers = wrapper.vm.servers
    expect(servers).toHaveLength(1)
    expect(servers[0].os).toBe('Microsoft Windows 11')
    expect(servers[0].cpuModel).toBe('13th Gen Intel(R) Core(TM) i7-13620H')
    expect(servers[0].uptime).toBe('3.4 小时')
    wrapper.unmount()
  })

  // 2026-08-16：DB 空字符串 fallback（防御性）
  it('test_map_snapshot_dash_when_os_empty mapping 防御性兜底：os 空串 → '-'', async () => {
    const api = await import('../../utils/api.js')
    api.fetchServerInspectionLatest.mockResolvedValueOnce({
      items: [
        {
          node_id: 11,
          node_name: 'MyA',
          server_id: 1,
          business_name: 'biz-A',
          server_type: 'linux',
          status: 'ok',
          inspection_status: 'pass',
          collected_at: '2026-08-15T18:00:14.283Z',
          duration_ms: 42,
          metrics: { cpu: 10, mem: 38.1, disk: 50, load: 0.5 },
          disks: [],
          parsed_values: { os: '', cpu_model: '   ' },  // 空串 / 空白 → '-'
          field_results: [],
          error_message: null,
        },
      ],
    })
    const wrapper = mount(OpsConsoleApp, {
      global: {
        stubs: {
          OpsMenuBar: true,
          OpsServerWindow: true,
          OpsDetailWindow: true,
          OpsLogManager: true,
          OpsLogViewer: true,
        },
      },
    })
    await flushPromises()
    const servers = wrapper.vm.servers
    expect(servers[0].os).toBe('-')         // 空串 → '-'
    expect(servers[0].cpuModel).toBe('-')    // 纯空白 → '-'
    wrapper.unmount()
  })

  // 2026-08-08 等保三级改造：onMounted 应主动调 validateToken 引导 Cookie 鉴权链路
  it('test_ops_console_app_on_mounted_calls_validate_token onMounted 主动引导 validateToken', async () => {
    const wrapper = mount(OpsConsoleApp, {
      global: {
        stubs: {
          OpsMenuBar: true,
          OpsServerWindow: true,
          OpsDetailWindow: true,
          OpsLogManager: true,
          OpsLogViewer: true,
          OpsDockBar: true,
        },
      },
    })
    await flushPromises()
    const api = await import('../../utils/api.js')
    // validateToken 在 onMounted 中调一次（即使失败也吞掉，不阻断 loadLatest）
    expect(api.validateToken).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
})