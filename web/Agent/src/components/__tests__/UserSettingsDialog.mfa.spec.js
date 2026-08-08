// -*- coding:utf-8 -*-
/**
 * UserSettingsDialog 个人 MFA 管理测试（2026-08-07 落地）
 *
 * 覆盖契约：
 * - 个人设置 profile tab 渲染 MFA 区域（state='enabled'|'disabled'|'required'）。
 * - 普通用户可启用 / 轮换 / 禁用 / 重置恢复码。
 * - admin 角色：状态为 required，不显示「禁用 MFA」按钮。
 * - 二维码 / secret / recovery_codes 仅内存；dialog close 时清空。
 *
 * 现有 utils/api.js 已扩展 fetchMfaStatus / startMfaEnrollment / confirmMfaEnrollment /
 * disableMfa / regenerateMfaRecoveryCodes（在本 spec 内 mock）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const apiMocks = vi.hoisted(() => ({
  fetchUserProfile: vi.fn(),
  updateUserProfile: vi.fn(),
  updatePassword: vi.fn(),
  updateUsername: vi.fn(),
  fetchUserList: vi.fn().mockResolvedValue([]),
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
  searchSessionsByUsername: vi.fn(),
  fetchAgentPermissionCatalog: vi.fn().mockResolvedValue({ items: [] }),
  fetchUserAgentGrants: vi.fn().mockResolvedValue({ agent_names: [] }),
  replaceUserAgentGrants: vi.fn().mockResolvedValue({ agent_names: [] }),
  fetchMenuCatalog: vi.fn().mockResolvedValue({ items: [] }),
  fetchUserMenuGrants: vi.fn().mockResolvedValue({ menu_ids: [] }),
  saveUserMenuGrants: vi.fn().mockResolvedValue({ menu_ids: [] }),
  fetchUploadConfig: vi.fn().mockResolvedValue({ max_file_size_mb: 3 }),
  // MFA API（2026-08-07 新增）
  fetchMfaStatus: vi.fn(),
  startMfaEnrollment: vi.fn(),
  confirmMfaEnrollment: vi.fn(),
  disableMfa: vi.fn(),
  regenerateMfaRecoveryCodes: vi.fn(),
}))

vi.mock('../../utils/api.js', () => apiMocks)

vi.mock('../McpServerManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../AgentManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../ToolManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../SkillManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../TaskSchedulerManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../EmailSettingsManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../MenuPermissionManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../AgentAccessManager.vue', () => ({ default: { template: '<div />' } }))

import UserSettingsDialog from '../UserSettingsDialog.vue'

function makeWrapper(role = 'user', username = 'alice') {
  return mount(UserSettingsDialog, {
    props: {
      visible: true,
      role,
      username,
      userId: 1,
      visibleMenus: ['profile']
    },
    global: {
      stubs: {
        teleport: true,
        transition: true
      }
    }
  })
}

describe('UserSettingsDialog 个人 MFA 管理', () => {
  beforeEach(() => {
    Object.values(apiMocks).forEach(m => { if (typeof m === 'function' && m.mockReset) m.mockReset() })
    apiMocks.fetchUserProfile.mockResolvedValue({
      id: 1, username: 'alice', role: 'user',
      real_name: '', phone: '', email: '', department: '', position: '',
      allowed_agents: []
    })
    apiMocks.fetchUserList.mockResolvedValue([])
    apiMocks.fetchOnlineUsers.mockResolvedValue({ online_users: [] })
    apiMocks.fetchAgentPermissionCatalog.mockResolvedValue({ items: [] })
    apiMocks.fetchUserAgentGrants.mockResolvedValue({ agent_names: [] })
    apiMocks.replaceUserAgentGrants.mockResolvedValue({ agent_names: [] })
    apiMocks.fetchMenuCatalog.mockResolvedValue({ items: [] })
    apiMocks.fetchUserMenuGrants.mockResolvedValue({ menu_ids: [] })
    apiMocks.saveUserMenuGrants.mockResolvedValue({ menu_ids: [] })
    apiMocks.fetchUploadConfig.mockResolvedValue({ max_file_size_mb: 3 })
    // 默认 MFA 状态：未启用（普通 user）
    apiMocks.fetchMfaStatus.mockResolvedValue({
      enabled: false,
      required: false,
      methods: [],
      enabled_at: null,
      issuer: 'TestIssuer'
    })
    localStorage.clear()
  })

  it('test_mfa_section_renders_disabled_state 普通用户未启用时显示启用入口', async () => {
    const wrapper = makeWrapper('user', 'alice')
    await flushPromises()

    expect(wrapper.find('[data-testid="mfa-section"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="mfa-enable-btn"]').exists()).toBe(true)
    // 未启用 → 不应出现禁用按钮
    expect(wrapper.find('[data-testid="mfa-disable-btn"]').exists()).toBe(false)
  })

  it('test_mfa_enable_flow_for_regular_user 普通用户启用流程', async () => {
    apiMocks.fetchMfaStatus.mockResolvedValue({
      enabled: false,
      required: false,
      methods: [],
      enabled_at: null,
      issuer: 'TestIssuer'
    })
    apiMocks.startMfaEnrollment.mockResolvedValue({
      secret: 'JBSWY3DPEHPK3PXP',
      enrollment_token: 'enroll-token-1',
      otpauth_uri: 'otpauth://totp/Test:alice',
      qr_png_base64: 'data:image/png;base64,ENROLLQR',
      expires_in: 300
    })
    apiMocks.confirmMfaEnrollment.mockResolvedValue({
      recovery_codes: ['RC-1', 'RC-2', 'RC-3']
    })

    const wrapper = makeWrapper('user', 'alice')
    await flushPromises()

    // 进入启用向导：输入当前密码后点 start 按钮（UI 上 mfa-enable-btn 就是「生成二维码」）
    await wrapper.find('[data-testid="mfa-enroll-current-password"]').setValue('pw')
    await wrapper.find('[data-testid="mfa-enable-btn"]').trigger('click')
    await flushPromises()

    expect(apiMocks.startMfaEnrollment).toHaveBeenCalledWith('pw')
    // 二维码与 secret 必须只内存展示
    const qrImg = wrapper.find('[data-testid="mfa-enroll-qr"]')
    expect(qrImg.exists()).toBe(true)
    expect(qrImg.attributes('src')).toBe('data:image/png;base64,ENROLLQR')

    // 输入 6 位码完成确认
    await wrapper.find('[data-testid="mfa-enroll-code-input"]').setValue('123456')
    await wrapper.find('[data-testid="mfa-enroll-confirm-btn"]').trigger('click')
    await flushPromises()

    expect(apiMocks.confirmMfaEnrollment).toHaveBeenCalledWith('enroll-token-1', '123456')
    // 恢复码必须只内存展示（恢复码区域渲染）
    expect(wrapper.find('[data-testid="mfa-recovery-codes-list"]').exists()).toBe(true)
    // 不写入 localStorage / sessionStorage
    const storageDump = JSON.stringify({ ls: { ...localStorage }, ss: { ...sessionStorage } })
    expect(storageDump.includes('RC-1')).toBe(false)
    expect(storageDump.includes('JBSWY3DPEHPK3PXP')).toBe(false)
  })

  it('test_admin_required_hides_disable admin 强制策略下不显示禁用按钮', async () => {
    apiMocks.fetchMfaStatus.mockResolvedValue({
      enabled: true,
      required: true,
      methods: ['totp', 'recovery_code'],
      enabled_at: '2026-08-01T00:00:00',
      issuer: 'TestIssuer'
    })

    const wrapper = makeWrapper('admin', 'admin')
    await flushPromises()

    // admin + required → 必须有禁用按钮不存在
    expect(wrapper.find('[data-testid="mfa-disable-btn"]').exists()).toBe(false)
    // 但可以重置恢复码
    expect(wrapper.find('[data-testid="mfa-regen-recovery-btn"]').exists()).toBe(true)
  })

  it('test_close_dialog_clears_qr_and_recovery_codes 关闭 dialog 清空二维码/恢复码', async () => {
    apiMocks.startMfaEnrollment.mockResolvedValue({
      secret: 'SECRETSECRET',
      enrollment_token: 'enroll-token-2',
      otpauth_uri: 'otpauth://totp/Test:bob',
      qr_png_base64: 'data:image/png;base64,QR2',
      expires_in: 300
    })

    const wrapper = makeWrapper('user', 'bob')
    await flushPromises()

    await wrapper.find('[data-testid="mfa-enroll-current-password"]').setValue('pw')
    await wrapper.find('[data-testid="mfa-enable-btn"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="mfa-enroll-qr"]').exists()).toBe(true)

    // 模拟 close（更新 visible=false）
    await wrapper.setProps({ visible: false })
    await flushPromises()

    // 再次打开后，二维码 / 恢复码不应残留
    await wrapper.setProps({ visible: true })
    await flushPromises()
    // 此时应回到启用向导初始态（未填密码、二维码未生成）
    const qrBeforeStart = wrapper.find('[data-testid="mfa-enroll-qr"]')
    expect(qrBeforeStart.exists()).toBe(false)
    // 重新进入启用向导：点 start 后才会出现新二维码
    await wrapper.find('[data-testid="mfa-enroll-current-password"]').setValue('pw')
    await wrapper.find('[data-testid="mfa-enable-btn"]').trigger('click')
    await flushPromises()
    const qrAfterReStart = wrapper.find('[data-testid="mfa-enroll-qr"]')
    expect(qrAfterReStart.exists()).toBe(true)
  })
})