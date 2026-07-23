/**
 * TaskSchedulerManager 部分失败容错测试（2026-07-23 ACL 双重门）
 *
 * 覆盖：
 * - fetchAdminAgentList 失败时 task-schedules 仍加载 + 不显示 banner
 * - fetchTaskSchedules 失败时 banner 显示（核心数据失败）
 * - 两个都失败时组件不崩溃
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// 拦截 utils/api 让组件挂载时不拉真实数据
vi.mock('../../utils/api.js', () => ({
  fetchAdminAgentList: vi.fn(),
  fetchTaskSchedules: vi.fn(),
  fetchTaskSchedule: vi.fn(),
  fetchTaskScheduleRuns: vi.fn(),
  createTaskSchedule: vi.fn(),
  updateTaskSchedule: vi.fn(),
  deleteTaskSchedule: vi.fn(),
  setTaskScheduleEnabled: vi.fn(),
  triggerTaskSchedule: vi.fn(),
  fetchDevopsServers: vi.fn().mockResolvedValue([]),
  scanDevopsServers: vi.fn(),
  fetchAdminScripts: vi.fn().mockResolvedValue([]),
  scanScripts: vi.fn(),
  fetchApiConfigTree: vi.fn().mockResolvedValue({ nodes: [] }),
  createApiConfigNode: vi.fn(),
  updateApiConfigNode: vi.fn(),
  deleteApiConfigNode: vi.fn(),
  fetchApiConfig: vi.fn().mockResolvedValue(null),
  saveApiConfig: vi.fn(),
  sendApiConfig: vi.fn(),
  fetchApiConfigRuns: vi.fn().mockResolvedValue([])
}))

import TaskSchedulerManager from '../TaskSchedulerManager.vue'
import * as api from '../../utils/api.js'

describe('TaskSchedulerManager 部分失败容错（ACL 双重门）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('test_admin_agents_fail_task_still_loads_no_banner 普通用户：fetchAdminAgentList 失败 + task 仍加载 + 无 banner', async () => {
    // 模拟 scenario：admin-agents 必失败（admin-only），task 成功
    api.fetchTaskSchedules.mockResolvedValue([
      { id: 1, name: 'task1', cron_expression: '0 * * * *', enabled: true }
    ])
    api.fetchAdminAgentList.mockRejectedValue(new Error('403 会话无效，请重试'))

    const wrapper = mount(TaskSchedulerManager, {
      props: {
        isAdmin: false,
        // 普通用户被授权 task-scheduler.scheduled（但 .script-scan/.api-config 没授）
        visibleMenus: ['task-scheduler', 'task-scheduler.scheduled']
      }
    })
    await flushPromises()
    await flushPromises()
    await flushPromises()

    // 任务列表仍渲染（任务名出现在 DOM）
    expect(wrapper.text()).toContain('task1')
    // 红色 banner 不应出现（关键：fail-safe 吞掉 admin-agents 403）
    const errorAlerts = wrapper.findAll('.alert.error')
    expect(errorAlerts.length).toBe(0)
    wrapper.unmount()
  })

  it('test_task_schedules_fail_shows_banner 核心数据失败显示 banner（合理）', async () => {
    api.fetchTaskSchedules.mockRejectedValue(new Error('503 不可用'))
    api.fetchAdminAgentList.mockResolvedValue([])

    const wrapper = mount(TaskSchedulerManager, {
      props: {
        isAdmin: false,
        visibleMenus: ['task-scheduler', 'task-scheduler.scheduled']
      }
    })
    // 等所有异步操作完成
    for (let i = 0; i < 5; i++) {
      await flushPromises()
      await new Promise(r => setTimeout(r, 30))
    }

    // 检查 vm 内部状态
    const vm = wrapper.vm
    console.log('[debug] errorMessage:', JSON.stringify(vm.errorMessage))
    console.log('[debug] isLoading:', vm.isLoading)
    console.log('[debug] activeTab:', vm.activeTab)
    console.log('[debug] taskRes fail swallow 完成, schedules.length:', vm.schedules.length)

    // task-schedules 是核心，失败 → banner 显示
    const alerts = wrapper.findAll('.alert.error')
    if (alerts.length === 0) {
      console.log('[debug] failed: no .alert.error found')
      console.log('[debug] wrapper html length:', wrapper.html().length)
      console.log('[debug] wrapper.text() length:', wrapper.text().length)
      console.log('[debug] has 503 in html?', wrapper.html().includes('503'))
    }
    expect(alerts.length).toBeGreaterThanOrEqual(1)
    expect(alerts[0].text()).toContain('503')
    wrapper.unmount()
  })

  it('test_all_fail_component_not_thrown 两个核心 fetch 都失败时组件仍渲染', async () => {
    // 不能 throw 到全局 unhandled promise
    api.fetchTaskSchedules.mockRejectedValue(new Error('boom1'))
    api.fetchAdminAgentList.mockRejectedValue(new Error('boom2'))

    const wrapper = mount(TaskSchedulerManager, {
      props: {
        isAdmin: false,
        visibleMenus: ['task-scheduler', 'task-scheduler.scheduled']
      }
    })
    await flushPromises()
    await flushPromises()

    // 组件仍存在（不被 unmounted）
    expect(wrapper.exists()).toBe(true)
    // task-schedules 是核心，写到 banner
    const alerts = wrapper.findAll('.alert.error')
    expect(alerts.length).toBeGreaterThanOrEqual(1)
    wrapper.unmount()
  })

  it('test_admin_role_full_success_no_banner admin：所有 fetch 成功，不显示 banner', async () => {
    api.fetchTaskSchedules.mockResolvedValue([{ id: 1, name: 'admin-task', cron_expression: '0 * * * *', enabled: true }])
    api.fetchAdminAgentList.mockResolvedValue([{ name: 'agent1' }])

    const wrapper = mount(TaskSchedulerManager, {
      props: {
        isAdmin: true,
        visibleMenus: []
      }
    })
    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('admin-task')
    // 无 banner
    const alerts = wrapper.findAll('.alert.error')
    expect(alerts.length).toBe(0)
    wrapper.unmount()
  })
})