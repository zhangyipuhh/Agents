// -*- coding:utf-8 -*-
/**
 * LoginView MFA 两阶段登录测试（2026-08-07 落地）
 *
 * 覆盖契约：
 * - 密码+图形验证码提交后，若响应 auth_stage=mfa_required/mfa_enrollment_required，
 *   组件不能写 localStorage（auth_token/user_role/username），不能 emit login-success。
 * - mfa_required 阶段：支持 TOTP / 恢复码切换；challenge_token 仅保留在组件 ref 内存；
 *   verify 成功后 emit login-success；Access Token 由后端 Set-Cookie 下发（HttpOnly, JS 不可读），
 *   role / username / user_id 等展示态字段缓存到 localStorage，前端不再写 auth_token。
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

    // 普通成功路径必须 emit login-success 并写 localStorage（auth_token 由后端 Set-Cookie 下发，不入 localStorage）
    expect(localStorage.getItem('auth_token')).toBeNull()
    expect(localStorage.getItem('user_role')).toBe('user')
    expect(localStorage.getItem('username')).toBe('alice')
    const events = wrapper.emitted('login-success')
    expect(events).toBeTruthy()
    expect(events.length).toBe(1)
    expect(events[0][0].access_token).toBeUndefined() // access_token 由后端 Set-Cookie 下发（HttpOnly, JS 不可读），不再通过 emit 传递
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
    // auth_token 由后端 Set-Cookie 下发（HttpOnly, JS 不可读），前端不再写 localStorage
    expect(localStorage.getItem('auth_token')).toBeNull()
    const events = wrapper.emitted('login-success')
    expect(events).toBeTruthy()
    expect(events[0][0].access_token).toBeUndefined() // access_token 由后端 Set-Cookie 下发（HttpOnly, JS 不可读），不再通过 emit 传递
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
    // 关键断言：confirm 成功后，组件必须停在"恢复码展示"阶段等用户点击"我已抄写并继续"
    // 才能写 localStorage + emit login-success —— 否则父级 window.location.href 跳走,
    // 恢复码"一闪而过",用户根本看不到。
    expect(localStorage.getItem('auth_token')).toBeNull()
    expect(wrapper.emitted('login-success')).toBeUndefined()
    // 恢复码必须已经渲染到 DOM
    const recoveryList = wrapper.find('[data-testid="mfa-recovery-codes-list"]')
    expect(recoveryList.exists()).toBe(true)
    expect(recoveryList.text()).toContain('AAAA-BBBB')
    expect(recoveryList.text()).toContain('CCCC-DDDD')
    // "我已抄写并继续"按钮必须渲染
    const ackBtn = wrapper.find('[data-testid="mfa-recovery-ack-btn"]')
    expect(ackBtn.exists()).toBe(true)
    // 恢复码不应写入 localStorage 或 sessionStorage
    const storageDump = JSON.stringify({
      ls: { ...localStorage },
      ss: { ...sessionStorage }
    })
    expect(storageDump.includes('AAAA-BBBB')).toBe(false)
    expect(storageDump.includes('CCCC-DDDD')).toBe(false)

    // 用户点击"我已抄写并继续"后才完成登录
    await ackBtn.trigger('click')
    await flushPromises()

    // auth_token 由后端 Set-Cookie 下发（HttpOnly, JS 不可读），前端不再写 localStorage
    expect(localStorage.getItem('auth_token')).toBeNull()
    const events = wrapper.emitted('login-success')
    expect(events).toBeTruthy()
    expect(events.length).toBe(1)
    expect(events[0][0].access_token).toBeUndefined() // access_token 由后端 Set-Cookie 下发（HttpOnly, JS 不可读），不再通过 emit 传递
  })

  it('test_mfa_enrollment_recovery_codes_not_flashed_before_acknowledge 恢复码不会在用户确认前触发 finalize', async () => {
    // 2026-08-08 bug 复现测试：原 bug 是 confirm 成功后同步 finalizeLogin，
    // 导致父级立刻 window.location.href 跳走，恢复码"一闪而过"。
    // 本测试断言 confirm 成功后、用户未点 ack 按钮前，绝不能写 localStorage 或 emit。
    apiMocks.login.mockResolvedValue({
      auth_stage: 'mfa_enrollment_required',
      challenge_token: 'enroll-challenge-flash',
      challenge_expires_in: 300,
      mfa_methods: [],
      username: 'admin'
    })
    apiMocks.startLoginMfaEnrollment.mockResolvedValue({
      enrollment_token: 'enroll-token-flash',
      otpauth_uri: 'otpauth://totp/Test:admin?secret=CCC',
      qr_png_base64: 'data:image/png;base64,DDDD',
      expires_in: 300
    })
    apiMocks.confirmLoginMfaEnrollment.mockResolvedValue({
      auth: {
        access_token: 'token-flash',
        token_type: 'Bearer',
        expires_in: 30,
        role: 'admin',
        username: 'admin',
        user_id: 1,
        visible_menus: [],
        allowed_agents: []
      },
      recovery_codes: ['RECO-A1', 'RECO-B2']
    })

    const wrapper = makeWrapper()
    await flushPromises()

    await wrapper.find('#login-username').setValue('admin')
    await wrapper.find('#login-password').setValue('adminpw')
    await wrapper.find('#login-captcha').setValue('abcd')
    await wrapper.find('form.login-form').trigger('submit.prevent')
    await flushPromises()

    await wrapper.find('[data-testid="mfa-enroll-code-input"]').setValue('123456')
    await wrapper.find('[data-testid="mfa-enroll-form"]').trigger('submit.prevent')
    await flushPromises()

    // 核心断言：confirm 已成功，但未点 ack 前，绝不能写 token、绝不能 emit
    expect(localStorage.getItem('auth_token')).toBeNull()
    expect(localStorage.getItem('user_role')).toBeNull()
    expect(wrapper.emitted('login-success')).toBeUndefined()
    // 恢复码列表必须可见（不在 DOM 中就完全没有抄写机会）
    expect(wrapper.find('[data-testid="mfa-recovery-codes-list"]').exists()).toBe(true)
    // ack 按钮必须可见
    expect(wrapper.find('[data-testid="mfa-recovery-ack-btn"]').exists()).toBe(true)
  })

  it('test_mfa_enrollment_acknowledge_emits_login_success 点击 ack 后才完成登录', async () => {
    // 与上一条互补：覆盖 ack 路径 —— 点击后写 localStorage + emit login-success
    apiMocks.login.mockResolvedValue({
      auth_stage: 'mfa_enrollment_required',
      challenge_token: 'enroll-challenge-ack',
      challenge_expires_in: 300,
      mfa_methods: [],
      username: 'admin'
    })
    apiMocks.startLoginMfaEnrollment.mockResolvedValue({
      enrollment_token: 'enroll-token-ack',
      otpauth_uri: 'otpauth://totp/Test:admin?secret=EEE',
      qr_png_base64: 'data:image/png;base64,FFFF',
      expires_in: 300
    })
    apiMocks.confirmLoginMfaEnrollment.mockResolvedValue({
      auth: {
        access_token: 'token-ack',
        token_type: 'Bearer',
        expires_in: 30,
        role: 'admin',
        username: 'admin',
        user_id: 7,
        visible_menus: ['profile'],
        allowed_agents: []
      },
      recovery_codes: ['ACK-AA11', 'ACK-BB22']
    })

    const wrapper = makeWrapper()
    await flushPromises()

    await wrapper.find('#login-username').setValue('admin')
    await wrapper.find('#login-password').setValue('adminpw')
    await wrapper.find('#login-captcha').setValue('abcd')
    await wrapper.find('form.login-form').trigger('submit.prevent')
    await flushPromises()

    await wrapper.find('[data-testid="mfa-enroll-code-input"]').setValue('111111')
    await wrapper.find('[data-testid="mfa-enroll-form"]').trigger('submit.prevent')
    await flushPromises()

    const ackBtn = wrapper.find('[data-testid="mfa-recovery-ack-btn"]')
    expect(ackBtn.exists()).toBe(true)
    // 点击 ack 按钮
    await ackBtn.trigger('click')
    await flushPromises()

    // localStorage 应写入 3 个展示态字段；auth_token 由后端 Set-Cookie 下发（HttpOnly, JS 不可读）
    expect(localStorage.getItem('auth_token')).toBeNull()
    expect(localStorage.getItem('user_role')).toBe('admin')
    expect(localStorage.getItem('username')).toBe('admin')
    expect(localStorage.getItem('user_id')).toBe('7')
    // login-success 应 emit，且 payload 不再包含 access_token（改由后端 Set-Cookie HttpOnly 下发）
    const events = wrapper.emitted('login-success')
    expect(events).toBeTruthy()
    expect(events.length).toBe(1)
    expect(events[0][0].access_token).toBeUndefined() // access_token 由后端 Set-Cookie 下发（HttpOnly, JS 不可读），不再通过 emit 传递
    // 恢复码绝不能写入 localStorage / sessionStorage
    const storageDump = JSON.stringify({
      ls: { ...localStorage },
      ss: { ...sessionStorage }
    })
    expect(storageDump.includes('ACK-AA11')).toBe(false)
    expect(storageDump.includes('ACK-BB22')).toBe(false)
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