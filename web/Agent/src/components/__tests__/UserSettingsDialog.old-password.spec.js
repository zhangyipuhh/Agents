/**
 * 2026-07-19 回归测试:旧密码输入框视觉脱敏
 *
 * 根因记录:type=password 在 Chrome/Edge 等浏览器中,即使 value 为空也会渲染
 * 默认的 6 个占位圆点,造成"密码框已填"错觉。用户反馈:旧密码完全为空即可,
 * 不需要符号替代。修复:type=text + CSS -webkit-text-security / text-security,
 * 输入字符仍以圆点形式保护隐私,但空值时只显示 placeholder。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import UserSettingsDialog from '../UserSettingsDialog.vue'

describe('旧密码输入框视觉脱敏', () => {
  let originalFetch, originalLocalStorage

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
    global.fetch = vi.fn(async (url) => {
      const u = typeof url === 'string' ? url : url.url
      if (u.includes('/api/users/1/profile')) {
        return { ok: true, json: async () => ({
          id: 1, username: 'admin', role: 'admin',
          real_name: '', phone: '', email: '542995981@qq.com',
          department: '', position: '', allowed_agents: [],
          created_at: '2026-07-19', updated_at: '2026-07-19',
        }) }
      }
      return { ok: true, json: async () => [] }
    })
    global.localStorage = {
      getItem: vi.fn((key) => {
        if (key === 'user_id') return '1'
        if (key === 'auth_token') return 'fake-token'
        if (key === 'session_id') return 'fake-session'
        return null
      }),
      setItem: vi.fn(), removeItem: vi.fn(), clear: vi.fn(),
    }
  })

  afterEach(() => {
    global.fetch = originalFetch
    global.localStorage = originalLocalStorage
    document.body.innerHTML = ''
  })

  it('test_old_password_input_not_type_password 旧密码输入框不应是 type=password', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: { visible: true, role: 'admin', userId: 1, username: 'admin', initialTab: 'profile' },
      attachTo: document.body,
    })
    await flushPromises()
    await flushPromises()

    const oldPwdInput = document.body.querySelector('#settings-old-password')
    expect(oldPwdInput).not.toBeNull()
    // 关键:不能是 type=password(避免 Chrome/Edge 默认显示 6 个占位圆点)
    expect(oldPwdInput.type).toBe('text')
    // 必须应用 password-mask 类(让输入字符以圆点形式保护隐私)
    expect(oldPwdInput.classList.contains('password-mask')).toBe(true)
    // 初始 value 必须为空(避免显示占位符圆点)
    expect(oldPwdInput.value).toBe('')
    // placeholder 应正常显示
    expect(oldPwdInput.placeholder).toBe('请输入旧密码')
  })

  it('test_old_password_input_value_reflects_user_input 用户输入旧密码应正确保存到 oldPassword ref', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: { visible: true, role: 'admin', userId: 1, username: 'admin', initialTab: 'profile' },
      attachTo: document.body,
    })
    await flushPromises()
    await flushPromises()

    const oldPwdInput = document.body.querySelector('#settings-old-password')
    oldPwdInput.value = 'mypassword'
    oldPwdInput.dispatchEvent(new Event('input', { bubbles: true }))
    await flushPromises()

    // 验证 v-model 正确生效:wrapper.vm.oldPassword 应等于 'mypassword'
    expect(wrapper.vm.oldPassword).toBe('mypassword')
  })
})