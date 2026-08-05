// -*- coding:utf-8 -*-
/**
 * OpsConsoleApp 组件冒烟测试（2026-08-05 新增）。
 *
 * 覆盖：
 *   - 组件可被 import；
 *   - 挂载时不抛异常（mock fetchWithAuth）；
 *   - 加载成功后 servers 列表渲染（映射函数 / loadLatest 链路）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// mock api.js：fetchServerInspectionLatest 返回 2 行（1 ok + 1 unknown）
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
          OpsDockBar: true,
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
          OpsDockBar: true,
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
})