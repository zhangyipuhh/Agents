/**
 * TaskSchedulerManager 子 tab ACL 过滤测试（2026-07-23）
 *
 * 覆盖：
 * - admin 全量显示 4 个 tab（含脚本扫描入库）
 * - 普通用户只显示被 visibleMenus 授权的 tab
 * - 顶层 isAdmin 拦截已替换为 hasAnyAccess 拦截
 * - 多个子 tab 授权都可见
 * - 脚本扫描入库 tab（task-scheduler.script-inventory）需独立授权才显示
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// 拦截 utils/api 让组件挂载时不拉真实数据
vi.mock('../../utils/api.js', () => ({
  fetchAdminAgentList: vi.fn().mockResolvedValue([]),
  fetchTaskSchedules: vi.fn().mockResolvedValue([]),
  fetchTaskSchedule: vi.fn().mockResolvedValue(null),
  fetchTaskScheduleRuns: vi.fn().mockResolvedValue([]),
  createTaskSchedule: vi.fn(),
  updateTaskSchedule: vi.fn(),
  deleteTaskSchedule: vi.fn(),
  setTaskScheduleEnabled: vi.fn(),
  triggerTaskSchedule: vi.fn(),
  fetchDevopsServers: vi.fn().mockResolvedValue([]),
  scanDevopsServers: vi.fn(),
  fetchAdminScripts: vi.fn().mockResolvedValue([]),
  scanScripts: vi.fn(),
  fetchApiConfigTree: vi.fn().mockResolvedValue({ nodes: [], api_configs: [] }),
  createApiConfigNode: vi.fn(),
  updateApiConfigNode: vi.fn(),
  deleteApiConfigNode: vi.fn(),
  fetchApiConfig: vi.fn().mockResolvedValue(null),
  saveApiConfig: vi.fn(),
  sendApiConfig: vi.fn(),
  fetchApiConfigRuns: vi.fn().mockResolvedValue([])
}))

import TaskSchedulerManager from '../TaskSchedulerManager.vue'

describe('TaskSchedulerManager 子 tab ACL 过滤', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('test_admin_shows_all_three_tabs admin 看 4 个 task tab（含脚本扫描入库）', async () => {
    const wrapper = mount(TaskSchedulerManager, {
      props: { isAdmin: true }
    })
    await flushPromises()
    const tabs = wrapper.findAll('[role="tab"]')
    const tabTexts = tabs.map(t => t.text().trim())
    expect(tabTexts).toContain('编辑任务')
    expect(tabTexts).toContain('服务器扫描入库')
    expect(tabTexts).toContain('脚本扫描入库')
    expect(tabTexts).toContain('API接口配置')
  })

  it('test_admin_no_visible_menus_still_shows admin 即便 ACL 空也直通', async () => {
    const wrapper = mount(TaskSchedulerManager, {
      props: {
        visibleMenus: [],
        isAdmin: true
      }
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="task-scheduler-no-permission"]').exists()).toBe(false)
  })

  it('test_normal_user_visible_scheduled_subtab 只授 .scheduled 时显示 "编辑任务"', async () => {
    const wrapper = mount(TaskSchedulerManager, {
      props: {
        visibleMenus: ['profile', 'task-scheduler', 'task-scheduler.scheduled']
      }
    })
    await flushPromises()
    const tabs = wrapper.findAll('[role="tab"]')
    const tabTexts = tabs.map(t => t.text().trim())
    expect(tabTexts).toContain('编辑任务')
    expect(tabTexts).not.toContain('服务器扫描入库')
    expect(tabTexts).not.toContain('脚本扫描入库')
    expect(tabTexts).not.toContain('API接口配置')
  })

  it('test_normal_user_multiple_subtabs_granted 3 个 tab 都授权都显示', async () => {
    const wrapper = mount(TaskSchedulerManager, {
      props: {
        visibleMenus: [
          'profile', 'task-scheduler',
          'task-scheduler.scheduled',
          'task-scheduler.script-scan',
          'task-scheduler.api-config'
        ]
      }
    })
    await flushPromises()
    const tabs = wrapper.findAll('[role="tab"]')
    const tabTexts = tabs.map(t => t.text().trim())
    expect(tabTexts).toContain('编辑任务')
    expect(tabTexts).toContain('服务器扫描入库')
    expect(tabTexts).toContain('API接口配置')
    expect(tabTexts).not.toContain('脚本扫描入库')  // 未授 task-scheduler.script-inventory
  })

  it('test_normal_user_granted_script_inventory_sees_script_tab 普通用户授权 .script-inventory 后可见"脚本扫描入库"', async () => {
    const wrapper = mount(TaskSchedulerManager, {
      props: {
        visibleMenus: [
          'profile', 'task-scheduler',
          'task-scheduler.script-inventory'
        ]
      }
    })
    await flushPromises()
    const tabs = wrapper.findAll('[role="tab"]')
    const tabTexts = tabs.map(t => t.text().trim())
    expect(tabTexts).toContain('脚本扫描入库')
    // 其他未授权 tab 不应出现
    expect(tabTexts).not.toContain('编辑任务')
    expect(tabTexts).not.toContain('服务器扫描入库')
    expect(tabTexts).not.toContain('API接口配置')
  })

  it('test_normal_user_no_subtabs_shows_placeholder 普通用户无任何 task-scheduler 授权时显示占位', async () => {
    const wrapper = mount(TaskSchedulerManager, {
      props: {
        visibleMenus: ['profile']  // 只 profile，没 task-scheduler 任何 tab
      }
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="task-scheduler-no-permission"]').exists()).toBe(true)
  })
})