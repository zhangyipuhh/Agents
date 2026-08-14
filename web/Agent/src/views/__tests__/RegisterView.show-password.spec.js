// -*- coding:utf-8 -*-
/**
 * RegisterView 密码显示/隐藏切换测试（2026-08-14 新增）
 *
 * 覆盖契约：
 * - #register-password 与 #register-confirm-password 默认均为 type=password；
 * - 点击各自的眼睛按钮可独立切换 type=password ↔ type=text；
 * - 两个输入框的可见性状态独立（互不影响）；
 * - 不破坏密码复杂度提示（passwordValidation 仍工作）。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../../utils/api.js', () => ({
  register: vi.fn(),
  getCaptcha: vi.fn().mockResolvedValue({ captcha_key: 'k', captcha_image: '' })
}))

import RegisterView from '../RegisterView.vue'

describe('RegisterView 密码显示切换', () => {
  it('默认两个密码框 type=password', async () => {
    const w = mount(RegisterView)
    await flushPromises()
    expect(w.find('#register-password').attributes('type')).toBe('password')
    expect(w.find('#register-confirm-password').attributes('type')).toBe('password')
  })

  it('点击 #register-password 眼睛 → 切 type=text，其它框不变', async () => {
    const w = mount(RegisterView)
    await flushPromises()
    const toggles = w.findAll('[data-testid="password-toggle"]')
    // 顺序：注册页 password 在前、confirm 在后
    await toggles[0].trigger('click')
    expect(w.find('#register-password').attributes('type')).toBe('text')
    expect(w.find('#register-confirm-password').attributes('type')).toBe('password')
  })

  it('点击 #register-confirm-password 眼睛 → 切 type=text，其它框不变', async () => {
    const w = mount(RegisterView)
    await flushPromises()
    const toggles = w.findAll('[data-testid="password-toggle"]')
    await toggles[1].trigger('click')
    expect(w.find('#register-confirm-password').attributes('type')).toBe('text')
    expect(w.find('#register-password').attributes('type')).toBe('password')
  })

  it('再次点击还原 type=password', async () => {
    const w = mount(RegisterView)
    await flushPromises()
    const toggles = w.findAll('[data-testid="password-toggle"]')
    await toggles[0].trigger('click')
    await toggles[0].trigger('click')
    expect(w.find('#register-password').attributes('type')).toBe('password')
  })

  it('不影响密码复杂度提示：passwordValidation.isValid 仍正确计算', async () => {
    const w = mount(RegisterView)
    await flushPromises()
    // 输入 7 位（不满足 minLength=8）
    await w.find('#register-password').setValue('Aa1!aaa')
    expect(w.vm.passwordValidation.minLength).toBe(false)
    expect(w.vm.passwordValidation.isValid).toBe(false)
    // 输入 8 位四类齐全
    await w.find('#register-password').setValue('Aa1!aaaa')
    expect(w.vm.passwordValidation.minLength).toBe(true)
    expect(w.vm.passwordValidation.isValid).toBe(true)
  })
})
