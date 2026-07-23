/**
 * EmailSettingsManager 子 tab ACL 过滤测试（2026-07-23）
 *
 * 覆盖：
 * - admin 全量显示 3 个 tab
 * - 普通用户只显示被 visibleMenus 授权的 tab（policies 而非 server/test）
 * - 全空 ACL 显示「此功能对您未开放」占位
 * - 单 tab 授权（只有 server）也只显示 server
 * - activeTab 默认值改为第一个被授权的 tab（不是 TAB_SERVER）
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// 拦截 utils/api 让组件挂载时不拉真实数据
vi.mock('../../utils/api.js', () => ({
  fetchEmailServerConfig: vi.fn().mockResolvedValue({}),
  updateEmailServerConfig: vi.fn(),
  testEmailServerConfig: vi.fn(),
  fetchEmailableUsers: vi.fn().mockResolvedValue([]),
  fetchEmailPolicies: vi.fn().mockResolvedValue([]),
  createEmailPolicy: vi.fn(),
  updateEmailPolicy: vi.fn(),
  deleteEmailPolicy: vi.fn(),
  sendTestEmail: vi.fn()
}))

import EmailSettingsManager from '../EmailSettingsManager.vue'

describe('EmailSettingsManager 子 tab ACL 过滤', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('test_admin_shows_all_three_tabs admin 看全部 3 个 tab', async () => {
    const wrapper = mount(EmailSettingsManager, {
      props: { isAdmin: true }
    })
    await flushPromises()
    const tabs = wrapper.findAll('[data-testid^="email-tab-"]')
    expect(tabs.length).toBe(3)
    expect(tabs[0].attributes('data-testid')).toBe('email-tab-server')
    expect(tabs[1].attributes('data-testid')).toBe('email-tab-policies')
    expect(tabs[2].attributes('data-testid')).toBe('email-tab-test')
  })

  it('test_normal_user_only_shows_granted_subtabs 普通用户仅显示授权 tab（policies）', async () => {
    const wrapper = mount(EmailSettingsManager, {
      props: {
        visibleMenus: ['profile', 'task-scheduler.email-settings', 'task-scheduler.email-settings.policies']
      }
    })
    await flushPromises()
    const tabs = wrapper.findAll('[data-testid^="email-tab-"]')
    // 应只显示 policies（policies 被授权，server 和 test 没有）
    expect(tabs.length).toBe(1)
    expect(tabs[0].attributes('data-testid')).toBe('email-tab-policies')
  })

  it('test_normal_user_only_server 只授 server tab 时只显示 server', async () => {
    const wrapper = mount(EmailSettingsManager, {
      props: {
        visibleMenus: ['profile', 'task-scheduler.email-settings', 'task-scheduler.email-settings.server']
      }
    })
    await flushPromises()
    const tabs = wrapper.findAll('[data-testid^="email-tab-"]')
    expect(tabs.length).toBe(1)
    expect(tabs[0].attributes('data-testid')).toBe('email-tab-server')
  })

  it('test_all_subtabs_granted 普通用户授权全部 3 个子 tab 也都显示', async () => {
    const wrapper = mount(EmailSettingsManager, {
      props: {
        visibleMenus: [
          'profile', 'task-scheduler.email-settings',
          'task-scheduler.email-settings.server',
          'task-scheduler.email-settings.policies',
          'task-scheduler.email-settings.test'
        ]
      }
    })
    await flushPromises()
    const tabs = wrapper.findAll('[data-testid^="email-tab-"]')
    expect(tabs.length).toBe(3)
  })

  it('test_empty_acl_shows_no_permission_placeholder ACL 为空时显示占位', async () => {
    const wrapper = mount(EmailSettingsManager, {
      props: {
        visibleMenus: ['profile']  // 只有 profile，无 email-settings 子 tab
      }
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="email-settings-no-permission"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-testid^="email-tab-"]').length).toBe(0)
  })

  it('test_activeTab_defaults_to_first_granted activeTab 默认值改为第一个被授权 tab', async () => {
    const wrapper = mount(EmailSettingsManager, {
      props: {
        visibleMenus: [
          'profile', 'task-scheduler.email-settings',
          'task-scheduler.email-settings.test'  // 注意：只有 test 授权，没有 server/policies
        ]
      }
    })
    await flushPromises()
    // activeTab 应自动改为 'test'（不是默认 'server'）
    // 通过查看 data-testid 选中状态推断：activeTab === 'test' 对应 email-tab-test 有 active 类
    const tab = wrapper.find('[data-testid="email-tab-test"]')
    expect(tab.exists()).toBe(true)
    expect(tab.classes()).toContain('active')
  })

  it('test_admin_empty_visible_menus_still_shows_all admin 即便 ACL 空也直通', async () => {
    const wrapper = mount(EmailSettingsManager, {
      props: {
        visibleMenus: [],
        isAdmin: true
      }
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="email-settings-no-permission"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid^="email-tab-"]').length).toBe(3)
  })
})