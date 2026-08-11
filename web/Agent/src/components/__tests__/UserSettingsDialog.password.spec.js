/* -*- coding:utf-8 -*- */
/**
 * UserSettingsDialog 修改密码复杂度校验测试（2026-08-09 新增）。
 *
 * 验证 validatePasswordForm 在新密码 7 位时被拦截、8 位四类齐全时通过。
 * 仅与个人设置「修改密码」表单（validatePasswordForm）相关，不涉及后端。
 */

import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
vi.mock('../../utils/api.js', () => ({
  updatePassword: vi.fn(),
  fetchUserProfile: vi.fn().mockResolvedValue({}),
  fetchUserList: vi.fn().mockResolvedValue([]),
  fetchOnlineUsers: vi.fn().mockResolvedValue({ online_users: [] }),
  fetchUploadConfig: vi.fn().mockResolvedValue({ max_file_size_mb: 3 })
}))
vi.mock('../McpServerManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../AgentManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../ToolManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../SkillManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../TaskSchedulerManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../EmailSettingsManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../MenuPermissionManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../AgentAccessManager.vue', () => ({ default: { template: '<div />' } }))
import UserSettingsDialog from '../UserSettingsDialog.vue'

describe('UserSettingsDialog 修改密码复杂度', () => {
  it('新密码 7 位被拦截', async () => {
    const w = mount(UserSettingsDialog, {
      props: { visible: true, role: 'user', userId: 1, username: 'u', initialTab: 'profile' }
    })
    await flushPromises()
    w.vm.oldPassword = 'P@ssword1!'
    w.vm.newPassword = 'Aa1!aaa'
    w.vm.confirmNewPassword = 'Aa1!aaa'
    expect(w.vm.validatePasswordForm()).toBe(false)
    expect(w.vm.passwordError).toMatch(/至少8位/)
  })
  it('新密码 8 位四类齐全通过', async () => {
    const w = mount(UserSettingsDialog, {
      props: { visible: true, role: 'user', userId: 1, username: 'u', initialTab: 'profile' }
    })
    await flushPromises()
    w.vm.oldPassword = 'P@ssword1!'
    w.vm.newPassword = 'P@ssword2@'
    w.vm.confirmNewPassword = 'P@ssword2@'
    expect(w.vm.validatePasswordForm()).toBe(true)
  })
})
