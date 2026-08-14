// -*- coding:utf-8 -*-
/**
 * LoginView 密码显示/隐藏切换测试（2026-08-14 新增）
 *
 * 覆盖契约：
 * - 渲染后 #login-password 默认 type=password；
 * - 点击眼睛图标后变 type=text；
 * - 再次点击还原；
 * - 不破坏密码提交逻辑（输入密码 + 提交仍走 handleLogin → login API）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const apiMocks = vi.hoisted(() => ({
  login: vi.fn(),
  getCaptcha: vi.fn(),
  loginMfaVerify: vi.fn(),
  startLoginMfaEnrollment: vi.fn(),
  confirmLoginMfaEnrollment: vi.fn()
}))

vi.mock('../../utils/api.js', () => apiMocks)

vi.mock('../../config/portal.js', () => ({
  appConfig: {
    brandTitle: 'Test Brand',
    brandDesc: 'Test Desc',
    loginThemes: {
      default: {
        brandTitle: 'Test Brand',
        brandDesc: 'Test Desc',
        loginTitle: '欢迎登录',
        loginSubtitle: '请输入您的账号信息',
        registerSubtitle: '请填写以下信息完成注册',
        footerText: '没有账号？',
        footerLink: '去注册',
        copyright: ''
      }
    },
    currentThemeKey: 'default'
  },
  getCurrentLoginTheme: () => ({
    brandTitle: 'Test Brand',
    brandDesc: 'Test Desc',
    loginTitle: '欢迎登录',
    loginSubtitle: '请输入您的账号信息',
    registerSubtitle: '请填写以下信息完成注册',
    footerText: '没有账号？',
    footerLink: '去注册',
    copyright: ''
  })
}))

import LoginView from '../LoginView.vue'

describe('LoginView 密码显示切换', () => {
  beforeEach(() => {
    apiMocks.getCaptcha.mockResolvedValue({ captcha_key: 'cap-id', captcha_image: '' })
    apiMocks.login.mockReset()
  })

  it('默认渲染 #login-password 为 type=password，眼睛按钮 aria-pressed=false', async () => {
    const w = mount(LoginView)
    await flushPromises()
    const input = w.find('#login-password')
    expect(input.exists()).toBe(true)
    expect(input.attributes('type')).toBe('password')
    const btn = w.find('[data-testid="password-toggle"]')
    expect(btn.exists()).toBe(true)
    expect(btn.attributes('aria-pressed')).toBe('false')
  })

  it('点击眼睛后 #login-password 变为 type=text', async () => {
    const w = mount(LoginView)
    await flushPromises()
    const btn = w.find('[data-testid="password-toggle"]')
    await btn.trigger('click')
    expect(w.find('#login-password').attributes('type')).toBe('text')
    expect(btn.attributes('aria-pressed')).toBe('true')
  })

  it('再次点击还原 type=password', async () => {
    const w = mount(LoginView)
    await flushPromises()
    const btn = w.find('[data-testid="password-toggle"]')
    await btn.trigger('click')
    await btn.trigger('click')
    expect(w.find('#login-password').attributes('type')).toBe('password')
  })

  it('不影响密码提交：handleLogin 仍正确传递当前密码值', async () => {
    apiMocks.login.mockResolvedValue({ role: 'user', username: 'u', user_id: 1 })
    const w = mount(LoginView)
    await flushPromises()
    await w.find('#login-username').setValue('u')
    await w.find('#login-password').setValue('mypwd')
    await w.find('#login-captcha').setValue('1234')
    await w.find('form').trigger('submit.prevent')
    await flushPromises()
    expect(apiMocks.login).toHaveBeenCalledWith('u', 'mypwd', 'cap-id', '1234')
  })
})
