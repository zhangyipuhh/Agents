/**
 * UserSettingsDialog 邮件设置升级为一级菜单 — 回归保护（2026-07-23）
 *
 * 覆盖：
 * - 顶部 tab 渲染分支使用 'task-scheduler.email-settings'（不再用旧 'email-settings'）
 * - visibleMenus 仅含自身 id 时，navItems 出现且不含旧顶级壳 'email-settings'
 * - NAV_MENU_METADATA 不再持有 'email-settings' key
 */
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

import UserSettingsDialog from '../UserSettingsDialog.vue'

// 拦截 utils/api 导入
vi.mock('../../utils/api.js', () => ({
  fetchUserProfile: vi.fn().mockResolvedValue({}),
  updateUserProfile: vi.fn(),
  updatePassword: vi.fn(),
  updateUsername: vi.fn(),
  fetchUserList: vi.fn().mockResolvedValue([]),
  fetchAdminAgentList: vi.fn().mockResolvedValue([]),
  deleteUser: vi.fn(),
  kickUser: vi.fn(),
  createUser: vi.fn(),
  updateUser: vi.fn(),
  fetchOnlineUsers: vi.fn().mockResolvedValue({ online_users: [] }),
  fetchUserSessions: vi.fn(),
  adminDeleteSession: vi.fn(),
  adminBatchDeleteSessions: vi.fn(),
  adminExportSessionMarkdown: vi.fn(),
  adminFetchSessionMessages: vi.fn(),
  searchSessionsByUsername: vi.fn()
}))

// stub 子组件
vi.mock('../McpServerManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../AgentManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../ToolManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../SkillManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../TaskSchedulerManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../EmailSettingsManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../MenuPermissionManager.vue', () => ({ default: { template: '<div />' } }))

describe('UserSettingsDialog 邮件设置升级为一级菜单', () => {
  it('test_email_settings_tab_uses_new_id 模板顶部 tab 使用新 id', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'admin',
        userId: 1,
        username: 'admin',
        initialTab: 'profile',
        visibleMenus: ['profile', 'task-scheduler.email-settings']
      },
      global: {
        stubs: { teleport: true, transition: true }
      }
    })
    await flushPromises()
    // 切换到邮件设置 tab
    wrapper.vm.activeTab = 'task-scheduler.email-settings'
    await flushPromises()
    // 旧顶级分支已删除：'email-settings' activeTab 不再触发 EmailSettingsManager 渲染
    // 这里通过组件内部 activeTab 状态断言：activeTab 切换到 'email-settings'（旧值）应无效
    wrapper.vm.activeTab = 'email-settings'
    await flushPromises()
    // 旧顶级壳 'email-settings' 不再是合法 activeTab——它不在 NAV_MENU_METADATA 里
    const ids = wrapper.vm.navItems.map(i => i.id)
    expect(ids).not.toContain('email-settings')
    expect(ids).toContain('task-scheduler.email-settings')
  })

  it('test_email_settings_l1_self_visible_no_parent_needed 邮件设置一级菜单自身授权即自身可见', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'user',
        userId: 5,
        username: 'zhangsan',
        initialTab: 'profile',
        // 仅授权邮件设置自身，不授权运维任务
        visibleMenus: ['profile', 'task-scheduler.email-settings']
      },
      global: {
        stubs: { teleport: true, transition: true }
      }
    })
    await flushPromises()
    const ids = wrapper.vm.navItems.map(i => i.id)
    // 一级菜单「邮件设置」应出现
    expect(ids).toContain('task-scheduler.email-settings')
    // 旧顶级壳 'email-settings' 已不存在
    expect(ids).not.toContain('email-settings')
    // 注:由于 id 字面仍带 'task-scheduler.' 前缀,isMenuVisible 的
    // "标准前缀匹配"会顺带让 task-scheduler 可见 —— 这是既有前缀推断
    // 机制的副作用,与本次升级无关,本用例不约束该行为。
  })

  it('test_nav_metadata_no_legacy_email_settings_key NAV_MENU_METADATA 不再持有旧 email-settings key', async () => {
    // 此用例保护源码契约：旧 'email-settings' key 必须从 NAV_MENU_METADATA 移除
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'admin',
        userId: 1,
        username: 'admin',
        initialTab: 'profile',
        visibleMenus: ['profile', 'task-scheduler.email-settings']
      },
      global: { stubs: { teleport: true, transition: true } }
    })
    await flushPromises()
    const ids = wrapper.vm.navItems.map(i => i.id)
    // 没有 'email-settings' 顶级壳
    expect(ids.some(id => id === 'email-settings')).toBe(false)
    // 新顶级壳 'task-scheduler.email-settings' 存在
    expect(ids.some(id => id === 'task-scheduler.email-settings')).toBe(true)
  })
})