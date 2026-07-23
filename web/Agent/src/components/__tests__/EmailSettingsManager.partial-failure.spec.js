/**
 * EmailSettingsManager 部分失败容错测试（2026-07-23 ACL 双重门）
 *
 * 覆盖：
 * - emailable-users 失败时 policies tab 不显示红色 banner（错误隔离）
 * - policies 失败时显示 banner
 * - server tab 用户：emailable-users 失败不影响 server 渲染
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../../utils/api.js', () => ({
  fetchEmailServerConfig: vi.fn().mockResolvedValue({}),
  updateEmailServerConfig: vi.fn(),
  testEmailServerConfig: vi.fn(),
  fetchEmailableUsers: vi.fn(),
  fetchEmailPolicies: vi.fn(),
  createEmailPolicy: vi.fn(),
  updateEmailPolicy: vi.fn(),
  deleteEmailPolicy: vi.fn(),
  sendTestEmail: vi.fn()
}))

import EmailSettingsManager from '../EmailSettingsManager.vue'
import * as api from '../../utils/api.js'

describe('EmailSettingsManager 部分失败错误隔离（ACL 双重门）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('test_emailable_users_fail_policies_no_red_banner emailable-users 失败 + policies 成功 → 无红 banner', async () => {
    // 场景：用户被授权 .policies 但 emailable-users 失败（无权访问父级）。
    // 旧版本：policyError 被写入，显示「403 红色 banner」。
    // 新版本：仅独立 ref 显示小警示，不污染 policies tab。
    api.fetchEmailableUsers.mockRejectedValue(new Error('403 会话无效，请重试'))
    api.fetchEmailPolicies.mockResolvedValue([
      { id: 1, name: '策略A', description: '', recipient_user_ids: [], subject_template: '', body_template: '' }
    ])

    const wrapper = mount(EmailSettingsManager, {
      props: {
        isAdmin: false,
        visibleMenus: ['profile', 'task-scheduler.email-settings', 'task-scheduler.email-settings.policies']
      }
    })
    await flushPromises()
    await flushPromises()

    // 切到 policies tab 看策略列表
    const policiesTab = wrapper.find('[data-testid="email-tab-policies"]')
    expect(policiesTab.exists()).toBe(true)
    await policiesTab.trigger('click')
    await flushPromises()

    // 策略列表渲染
    expect(wrapper.text()).toContain('策略A')
    // 关键：无 .alert.error（红 banner），只有 .alert.warn（小警示）
    const errorAlerts = wrapper.findAll('.alert.error')
    expect(errorAlerts.length).toBe(0)
    // 但有 .alert.warn 提示 emailable-users 失败
    const warnAlerts = wrapper.findAll('[data-testid="emailable-users-warning"]')
    expect(warnAlerts.length).toBe(1)
    wrapper.unmount()
  })

  it('test_policies_fail_shows_red_banner policies 失败显示 banner', async () => {
    api.fetchEmailableUsers.mockResolvedValue([])
    api.fetchEmailPolicies.mockRejectedValue(new Error('403 会话无效，请重试'))

    const wrapper = mount(EmailSettingsManager, {
      props: {
        isAdmin: false,
        visibleMenus: ['profile', 'task-scheduler.email-settings', 'task-scheduler.email-settings.policies']
      }
    })
    await flushPromises()
    await flushPromises()

    // policies 失败 → 显示 .alert.error
    const errorAlerts = wrapper.findAll('.alert.error')
    expect(errorAlerts.length).toBeGreaterThanOrEqual(1)
    wrapper.unmount()
  })

  it('test_server_tab_emailable_fail_no_banner server tab 用户：emailable 失败不影响', async () => {
    // 用户只被授权 server tab，emailable 失败不该有 banner（emailable 也跟着加载）
    api.fetchEmailableUsers.mockRejectedValue(new Error('403 会话无效，请重试'))
    api.fetchEmailServerConfig.mockResolvedValue({
      host: 'smtp.qq.com', port: 465, use_ssl: true, username: '',
      password: '', sender_name: '', enabled: true, force_plain: false,
      verify_ssl: true
    })

    const wrapper = mount(EmailSettingsManager, {
      props: {
        isAdmin: false,
        visibleMenus: ['profile', 'task-scheduler.email-settings', 'task-scheduler.email-settings.server']
      }
    })
    await flushPromises()
    await flushPromises()

    // 无红 banner
    const errorAlerts = wrapper.findAll('.alert.error')
    expect(errorAlerts.length).toBe(0)
    // server tab 仍渲染（host 出现）
    expect(wrapper.text()).toContain('smtp.qq.com')
    wrapper.unmount()
  })

  it('test_admin_role_all_success_no_banner admin：所有 fetch 成功无 banner', async () => {
    api.fetchEmailableUsers.mockResolvedValue([{ id: 1, username: 'u1' }])
    api.fetchEmailPolicies.mockResolvedValue([
      { id: 1, name: '策略X', description: '', recipient_user_ids: [], subject_template: '', body_template: '' }
    ])
    api.fetchEmailServerConfig.mockResolvedValue({
      host: 'smtp.qq.com', port: 465, use_ssl: true, username: '',
      password: '', sender_name: '', enabled: true, force_plain: false,
      verify_ssl: true
    })

    const wrapper = mount(EmailSettingsManager, {
      props: {
        isAdmin: true,
        visibleMenus: []
      }
    })
    await flushPromises()
    await flushPromises()

    // admin 看 server tab 默认页：smtp 出现
    expect(wrapper.text()).toContain('smtp.qq.com')

    // 切到 policies tab 看策略
    const policiesTab = wrapper.find('[data-testid="email-tab-policies"]')
    expect(policiesTab.exists()).toBe(true)
    await policiesTab.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('策略X')

    expect(wrapper.findAll('.alert.error').length).toBe(0)
    wrapper.unmount()
  })
})