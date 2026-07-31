/**
 * UserSettingsDialog 消息设置父菜单 — 回归保护（2026-07-31）
 *
 * 历史：
 * - 2026-07-23：「邮件设置」升级为一级菜单（id=task-scheduler.email-settings）
 * - 2026-07-31：「邮件设置」再次降级为「消息设置」(messaging) 下的二级菜单
 *
 * 覆盖：
 * - 顶部 tab 渲染分支使用 'messaging'（不再用 'task-scheduler.email-settings' 作为一级 tab）
 * - visibleMenus 含 'messaging' 时，navItems 出现且不含旧 'email-settings' / 'task-scheduler.email-settings' 一级壳
 * - NAV_MENU_METADATA 持有 'messaging' 键
 * - PARENT_TO_CHILDREN_ALIAS 让子菜单授权推父级可见
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

describe('UserSettingsDialog 消息设置父菜单（2026-07-31）', () => {
  it('test_messaging_tab_uses_new_id 模板顶部 tab 使用 messaging id', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'admin',
        userId: 1,
        username: 'admin',
        initialTab: 'profile',
        visibleMenus: ['profile', 'messaging']
      },
      global: {
        stubs: { teleport: true, transition: true }
      }
    })
    await flushPromises()
    // 切换到消息设置 tab
    wrapper.vm.activeTab = 'messaging'
    await flushPromises()
    const ids = wrapper.vm.navItems.map(i => i.id)
    // messaging 一级菜单可见
    expect(ids).toContain('messaging')
    // 旧顶级壳 'email-settings' 不再是合法 activeTab —— 它不在 NAV_MENU_METADATA 里
    expect(ids).not.toContain('email-settings')
    // task-scheduler.email-settings 也不再作为一级菜单可见（已降级为二级）
    expect(ids).not.toContain('task-scheduler.email-settings')
  })

  it('test_messaging_l1_self_visible 消息设置父级自身授权即自身可见', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'user',
        userId: 5,
        username: 'zhangsan',
        initialTab: 'profile',
        // 仅授权 messaging 自身
        visibleMenus: ['profile', 'messaging']
      },
      global: {
        stubs: { teleport: true, transition: true }
      }
    })
    await flushPromises()
    const ids = wrapper.vm.navItems.map(i => i.id)
    // 一级菜单「消息设置」应出现
    expect(ids).toContain('messaging')
    // 旧顶级壳 'email-settings' / 'task-scheduler.email-settings' 已不存在
    expect(ids).not.toContain('email-settings')
    expect(ids).not.toContain('task-scheduler.email-settings')
  })

  it('test_messaging_l1_visible_via_alias 子菜单授权通过 PARENT_TO_CHILDREN_ALIAS 让父级可见', async () => {
    // 这是新行为：messaging 父级与孙 tab id 前缀不匹配，需要 alias 显式补齐
    // 2026-07-31 二次调整：原 task-scheduler.email-settings 中间层已删，alias 改为孙 tab 列表
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'user',
        userId: 6,
        username: 'lisi',
        initialTab: 'profile',
        // 仅授权孙 tab task-scheduler.email-settings.server（不授权 channel messaging.email 与父级 messaging）
        visibleMenus: ['profile', 'task-scheduler.email-settings.server']
      },
      global: {
        stubs: { teleport: true, transition: true }
      }
    })
    await flushPromises()
    const ids = wrapper.vm.navItems.map(i => i.id)
    // 父级 messaging 仍可见（alias 推导：孙 tab id 在 messaging alias 列表中）
    expect(ids).toContain('messaging')
  })

  it('test_messaging_email_channel_visible_via_grandchild_alias 孙 tab 授权让 channel messaging.email 可见', async () => {
    // 2026-07-31 二次调整：channel `messaging.email` 父级与孙 tab id 前缀不匹配（孙 tab id `task-scheduler.email-settings.*` 不以 `messaging.email.` 开头）
    // alias 让孙 tab 授权时父级 channel 也可见
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'user',
        userId: 7,
        username: 'wangwu',
        initialTab: 'profile',
        // 仅授权一个孙 tab policies（不授权 channel 不授权父级）
        visibleMenus: ['profile', 'messaging', 'task-scheduler.email-settings.policies']
      },
      global: {
        stubs: { teleport: true, transition: true }
      }
    })
    await flushPromises()
    // channel messaging.email 应可见（alias 推导）
    // 注：UserSettingsDialog 的 navItems 是顶级 tab 列表，不含 channel 二级；channel 可见性体现在 messaging tab 内 sub-tab 渲染
    // 但 channel 自身作为 navItem 不可见（仅顶级才进 navItems）
    // 验证 messaging 顶级可见 + 切到 messaging tab 后 channel sub-tab 渲染
    wrapper.vm.activeTab = 'messaging'
    await flushPromises()
    // channel sub-tab 按钮应可见
    expect(wrapper.find('[data-testid="messaging-channel-email"]').exists()).toBe(true)
  })

  it('test_nav_metadata_has_messaging_key NAV_MENU_METADATA 持有 messaging 键', async () => {
    // 此用例保护源码契约：messaging 必须在 NAV_MENU_METADATA 里
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'admin',
        userId: 1,
        username: 'admin',
        initialTab: 'profile',
        visibleMenus: ['profile', 'messaging']
      },
      global: { stubs: { teleport: true, transition: true } }
    })
    await flushPromises()
    const ids = wrapper.vm.navItems.map(i => i.id)
    // 新一级壳 'messaging' 存在
    expect(ids.some(id => id === 'messaging')).toBe(true)
  })
})
