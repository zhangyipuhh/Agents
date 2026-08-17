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

  // 2026-08-17 新增：智能检测 chat override 契约需要 business_name 精确反查
  it('test_map_snapshot_passes_business_name mapSnapshotToServer 透传 businessName', async () => {
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
    // 第一行 node_name='MyA' 与 business_name='biz-A' 不同：
    // 卡片显示名 name='MyA'，但 query_inspection_records 必须按 business_name 精确反查
    expect(servers[0].name).toBe('MyA')
    expect(servers[0].businessName).toBe('biz-A')
    expect(servers[1].businessName).toBe('biz-B')
    wrapper.unmount()
  })

  // 2026-08-16 改造：详情页 OS 关键指标（iowait/swap/inode）从 parsed_values 映射；
  // os/cpuModel/uptime 死字段已移除（详情页不再消费，「操作系统」改展示 server_type 原值）。
  it('test_map_snapshot_reads_os_metrics mapping 从 parsed_values 读取 cpu_iowait_pct / swap_used_pct / inode_used_pct', async () => {
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
    expect(servers[0].iowait).toBeNull()   // 默认 mock 的 parsed_values 无三字段 → null
    expect(servers[0].swap).toBeNull()
    expect(servers[0].inode).toBeNull()
    // 死字段已移除
    expect(servers[0]).not.toHaveProperty('os')
    expect(servers[0]).not.toHaveProperty('cpuModel')
    expect(servers[0]).not.toHaveProperty('uptime')
    wrapper.unmount()
  })

  it('test_map_snapshot_consumes_real_db_os_metrics mapping 消费真实 DB 字段（linux 全指标形状）', async () => {
    // 形状对齐 2026-08-16 server_latest_snapshot 真实行（server_id=100）
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
          collected_at: '2026-08-16T13:51:49.201Z',
          duration_ms: 42,
          metrics: { cpu: 4.6, mem: 79, disk: 28, load: 1.36 },
          disks: [],
          parsed_values: {
            disks: [],
            mem_used_pct: 79,
            cpu_idle_pct: 95.4,
            cpu_iowait_pct: 0.1,
            swap_used_pct: 0,
            inode_used_pct: 1,
            load_1m: 1.36,
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
    expect(servers[0].serverType).toBe('linux')
    expect(servers[0].iowait).toBe(0.1)
    expect(servers[0].swap).toBe(0)
    expect(servers[0].inode).toBe(1)
    wrapper.unmount()
  })

  it('test_map_snapshot_os_metrics_null_when_missing mapping 防御性兜底：windows parsed_values 缺三字段 → null', async () => {
    const api = await import('../../utils/api.js')
    api.fetchServerInspectionLatest.mockResolvedValueOnce({
      items: [
        {
          node_id: 12,
          node_name: 'MyW',
          server_id: 3,
          business_name: 'biz-W',
          server_type: 'windows',
          status: 'ok',
          inspection_status: 'pass',
          collected_at: '2026-08-16T12:23:28.329Z',
          duration_ms: 30,
          metrics: { cpu: 83, mem: 45.4, disk: 77.9, load: null },
          disks: [],
          parsed_values: { disks: [], mem_used_pct: 45.4, cpu_used_pct: 83 },
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
    expect(servers[0].iowait).toBeNull()
    expect(servers[0].swap).toBeNull()
    expect(servers[0].inode).toBeNull()
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

  // 2026-08-16: 物理盘分组 - 映射透传 host_disk / disk_index / partition
  it('test_map_snapshot_passes_host_disk_disk_index_partition mapSnapshotToServer 透传 host_disk/disk_index/partition', async () => {
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
          collected_at: '2026-08-16T00:46:35',
          duration_ms: 10,
          metrics: { cpu: 10, mem: 38.1, disk: 50, load: 0.5 },
          parsed_values: {
            disks: [
              { mount: '/', disk_used_pct: 50, host_disk: 'sda', disk_index: 0, partition: 'sda1' },
              { mount: '/data', disk_used_pct: 80, host_disk: 'sdb', disk_index: 1, partition: 'sdb1' },
              { mount: 'sda[HDD]', io_util_pct: 12.0, io_await_ms: 5.0, disk_type: 'hdd',
                host_disk: 'sda', disk_index: 0, partition: '' },
            ],
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
    expect(servers[0].disks).toHaveLength(3)
    // 分区记录: host_disk / partition 透传
    expect(servers[0].disks[0].hostDisk).toBe('sda')
    expect(servers[0].disks[0].diskIndex).toBe(0)
    expect(servers[0].disks[0].partition).toBe('sda1')
    expect(servers[0].disks[1].hostDisk).toBe('sdb')
    expect(servers[0].disks[1].diskIndex).toBe(1)
    expect(servers[0].disks[1].partition).toBe('sdb1')
    // 整盘 IO 记录: partition 空
    expect(servers[0].disks[2].hostDisk).toBe('sda')
    expect(servers[0].disks[2].diskIndex).toBe(0)
    expect(servers[0].disks[2].partition).toBe('')
    wrapper.unmount()
  })

  // 2026-08-16: 兼容老 snapshot - 缺 host_disk / disk_index 时前端字段降级为空
  it('test_map_snapshot_falls_back_when_host_disk_missing 旧 snapshot 缺 host_disk 时前端降级为空', async () => {
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
          duration_ms: 10,
          metrics: { cpu: 10, mem: 38.1, disk: 50, load: null },
          // 旧 snapshot 缺 host_disk / disk_index / partition
          parsed_values: {
            disks: [
              { mount: 'C:\\', disk_used_pct: 50 },
              { mount: '0 C: D:[SSD]', io_util_pct: 12.0, io_await_ms: 5.0, disk_type: 'ssd' },
            ],
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
    expect(servers[0].disks).toHaveLength(2)
    // 旧 snapshot 缺字段: 前端降级为空串 / null, 不抛错
    expect(servers[0].disks[0].hostDisk).toBe('')
    expect(servers[0].disks[0].diskIndex).toBeNull()
    expect(servers[0].disks[0].partition).toBe('')
    expect(servers[0].disks[1].hostDisk).toBe('')
    expect(servers[0].disks[1].diskIndex).toBeNull()
    expect(servers[0].disks[1].partition).toBe('')
    wrapper.unmount()
  })
})