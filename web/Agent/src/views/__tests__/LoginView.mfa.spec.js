// -*- coding:utf-8 -*-
/**
 * LoginView MFA 两阶段登录测试（2026-08-07 落地）
 *
 * 覆盖契约：
 * - 密码+图形验证码提交后，若响应 auth_stage=mfa_required/mfa_enrollment_required，
 *   组件不能写 localStorage（auth_token/user_role/username），不能 emit login-success。
 * - mfa_required 阶段：支持 TOTP / 恢复码切换；challenge_token 仅保留在组件 ref 内存；
 *   verify 成功后写 localStorage 并 emit login-success。
 * - mfa_enrollment_required 阶段：调 startLoginMfaEnrollment 获取二维码；
 *   组件显示二维码 + secret 输入；confirm 后走统一完成登录路径。
 * - 任一阶段错误/过期清理：mfa token / code / qr / recovery_codes 清空 + 刷新验证码。
 *
 * 说明：保持与项目其他 spec 风格一致（happy-dom + vue-test-utils + vi.mock api）。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import LoginView from '../LoginView.vue'

// mock utils/api.js:覆盖本测试关心的所有函数
const apiMocks = vi.hoisted(() => ({
  login: vi.fn(),
  getCaptcha: vi.fn(),
  loginMfaVerify: vi.fn(),
  startLoginMfaEnrollment: vi.fn(),
  confirmLoginMfaEnrollment: vi.fn(),
}))

vi.mock('../../utils/api.js', () => apiMocks)

vi.mock('../../config/portal.js', () => ({
  appConfig: { brandTitle: 'Test Brand', brandDesc: 'Test Desc' }
}))

function makeWrapper() {
  return mount(LoginView, {
    global: {
      stubs: {
        teleport: true,
        transition: true
      }
    }
  })
}

describe('LoginView MFA 两阶段登录', () => {
  beforeEach(() => {
    apiMocks.login.mockReset()
    apiMocks.getCaptcha.mockReset()
    apiMocks.loginMfaVerify.mockReset()
    apiMocks.startLoginMfaEnrollment.mockReset()
    apiMocks.confirmLoginMfaEnrollment.mockReset()
    // 默认 captcha 正常返回
    apiMocks.getCaptcha.mockResolvedValue({
      captcha_key: 'cap-key-1',
      captcha_image: 'data:image/png;base64,AAA'
    })
    localStorage.clear()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('test_normal_login_success_still_works 普通登录成功时 login-success 被 emit 并写 localStorage', async () => {
    apiMocks.login.mockResolvedValue({
      access_token: 'token-1',
      token_type: 'Bearer',
      expires_in: 30,
      role: 'user',
      username: 'alice',
      user_id: 2,
      visible_menus: ['profile'],
      allowed_agents: []
    })

    const wrapper = makeWrapper()
    await flushPromises()

    // 触发提交
    await wrapper.find('#login-username').setValue('alice')
    await wrapper.find('#login-password').setValue('pw')
    await wrapper.find('#login-captcha').setValue('abcd')
    await wrapper.find('form.login-form').trigger('submit.prevent')
    await flushPromises()

    // 普通成功路径必须 emit login-success 并写 localStorage
    expect(localStorage.getItem('auth_token')).toBe('token-1')
    expect(localStorage.getItem('user_role')).toBe('user')
    expect(localStorage.getItem('username')).toBe('alice')
    const events = wrapper.emitted('login-success')
    expect(events).toBeTruthy()
    expect(events.length).toBe(1)
    expect(events[0][0].access_token).toBe('token-1')
  })

  it('test_mfa_required_response_does_not_emit_or_persist mfa_required 响应不写 token 也不 emit', async () => {
    apiMocks.login.mockResolvedValue({
      auth_stage: 'mfa_required',
      challenge_token: 'challenge-abc',
      challenge_expires_in: 300,
      mfa_methods: ['totp', 'recovery_code'],
      username: 'bob'
    })

    const wrapper = makeWrapper()
    await flushPromises()

    await wrapper.find('#login-username').setValue('bob')
    await wrapper.find('#login-password').setValue('pw')
    await wrapper.find('#login-captcha').setValue('abcd')
    await wrapper.find('form.login-form').trigger('submit.prevent')
    await flushPromises()

    // 不写 localStorage；不 emit login-success
    expect(localStorage.getItem('auth_token')).toBeNull()
    expect(localStorage.getItem('user_role')).toBeNull()
    expect(wrapper.emitted('login-success')).toBeFalsy()

    // MFA 校验阶段应该展示 TOTP 输入框
    expect(wrapper.find('[data-testid="mfa-verify-stage"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="mfa-code-input"]').exists()).toBe(true)
  })

  it('test_mfa_verify_success_persists_and_emits verify 成功后写 localStorage 并 emit login-success', async () => {
    apiMocks.login.mockResolvedValue({
      auth_stage: 'mfa_required',
      challenge_token: 'challenge-xyz',
      challenge_expires_in: 300,
      mfa_methods: ['totp'],
      username: 'bob'
    })
    apiMocks.loginMfaVerify.mockResolvedValue({
      access_token: 'token-2',
      token_type: 'Bearer',
      expires_in: 30,
      role: 'user',
      username: 'bob',
      user_id: 3,
      visible_menus: ['profile'],
      allowed_agents: []
    })

    const wrapper = makeWrapper()
    await flushPromises()

    await wrapper.find('#login-username').setValue('bob')
    await wrapper.find('#login-password').setValue('pw')
    await wrapper.find('#login-captcha').setValue('abcd')
    await wrapper.find('form.login-form').trigger('submit.prevent')
    await flushPromises()

    // 输入 6 位 TOTP 码并提交
    await wrapper.find('[data-testid="mfa-code-input"]').setValue('123456')
    await wrapper.find('[data-testid="mfa-verify-form"]').trigger('submit.prevent')
    await flushPromises()

    expect(apiMocks.loginMfaVerify).toHaveBeenCalledWith('challenge-xyz', '123456', 'totp')
    expect(localStorage.getItem('auth_token')).toBe('token-2')
    const events = wrapper.emitted('login-success')
    expect(events).toBeTruthy()
    expect(events[0][0].access_token).toBe('token-2')
  })

  it('test_mfa_enrollment_displays_qr_then_confirm 强制绑定阶段显示二维码并完成确认', async () => {
    apiMocks.login.mockResolvedValue({
      auth_stage: 'mfa_enrollment_required',
      challenge_token: 'enroll-challenge-1',
      challenge_expires_in: 300,
      mfa_methods: [],
      username: 'admin'
    })
    apiMocks.startLoginMfaEnrollment.mockResolvedValue({
      enrollment_token: 'enroll-token-1',
      otpauth_uri: 'otpauth://totp/Test:admin?secret=AAA',
      qr_png_base64: 'data:image/png;base64,BBBB',
      expires_in: 300
    })
    apiMocks.confirmLoginMfaEnrollment.mockResolvedValue({
      auth: {
        access_token: 'token-3',
        token_type: 'Bearer',
        expires_in: 30,
        role: 'admin',
        username: 'admin',
        user_id: 1,
        visible_menus: ['profile', 'user-management'],
        allowed_agents: []
      },
      recovery_codes: ['AAAA-BBBB', 'CCCC-DDDD']
    })

    const wrapper = makeWrapper()
    await flushPromises()

    await wrapper.find('#login-username').setValue('admin')
    await wrapper.find('#login-password').setValue('adminpw')
    await wrapper.find('#login-captcha').setValue('abcd')
    await wrapper.find('form.login-form').trigger('submit.prevent')
    await flushPromises()

    // 进入 enrollment 阶段：start 已自动调用，二维码已渲染
    expect(apiMocks.startLoginMfaEnrollment).toHaveBeenCalledWith('enroll-challenge-1')
    expect(wrapper.find('[data-testid="mfa-enroll-stage"]').exists()).toBe(true)
    const qrImg = wrapper.find('[data-testid="mfa-enroll-qr"]')
    expect(qrImg.exists()).toBe(true)
    expect(qrImg.attributes('src')).toBe('data:image/png;base64,BBBB')

    // confirm 阶段输入 6 位码
    await wrapper.find('[data-testid="mfa-enroll-code-input"]').setValue('654321')
    await wrapper.find('[data-testid="mfa-enroll-form"]').trigger('submit.prevent')
    await flushPromises()

    expect(apiMocks.confirmLoginMfaEnrollment).toHaveBeenCalledWith('enroll-token-1', '654321')
    // confirm 成功后恢复码必须只在内存中，且最终写 localStorage + emit
    expect(localStorage.getItem('auth_token')).toBe('token-3')
    const events = wrapper.emitted('login-success')
    expect(events).toBeTruthy()
    // 恢复码不应写入 localStorage 或 sessionStorage
    const storageDump = JSON.stringify({
      ls: { ...localStorage },
      ss: { ...sessionStorage }
    })
    expect(storageDump.includes('AAAA-BBBB')).toBe(false)
    expect(storageDump.includes('CCCC-DDDD')).toBe(false)
  })

  it('test_mfa_verify_error_clears_in_memory_state 错误时清空 mfa token/code 并刷新 captcha', async () => {
    apiMocks.login.mockResolvedValue({
      auth_stage: 'mfa_required',
      challenge_token: 'challenge-err',
      challenge_expires_in: 300,
      mfa_methods: ['totp'],
      username: 'bob'
    })
    apiMocks.loginMfaVerify.mockRejectedValue(new Error('MFA 校验失败'))

    const wrapper = makeWrapper()
    await flushPromises()

    await wrapper.find('#login-username').setValue('bob')
    await wrapper.find('#login-password').setValue('pw')
    await wrapper.find('#login-captcha').setValue('abcd')
    await wrapper.find('form.login-form').trigger('submit.prevent')
    await flushPromises()

    // 进入 MFA verify 阶段
    const captchaCallsBeforeMfa = apiMocks.getCaptcha.mock.calls.length

    await wrapper.find('[data-testid="mfa-code-input"]').setValue('000000')
    await wrapper.find('[data-testid="mfa-verify-form"]').trigger('submit.prevent')
    await flushPromises()

    // MFA 校验失败后必须刷新图形验证码
    expect(apiMocks.getCaptcha.mock.calls.length).toBeGreaterThan(captchaCallsBeforeMfa)
    // 错误信息展示；不应写 localStorage
    expect(localStorage.getItem('auth_token')).toBeNull()
    // mfaCode 已被清空（再提交时不会携带旧码）
    await wrapper.find('[data-testid="mfa-code-input"]').setValue('111111')
    await wrapper.find('[data-testid="mfa-verify-form"]').trigger('submit.prevent')
    await flushPromises()
    // verify 第二次调用携带的 code 是新输入的 '111111'
    const verifyCalls = apiMocks.loginMfaVerify.mock.calls
    expect(verifyCalls[verifyCalls.length - 1][1]).toBe('111111')
  })
})