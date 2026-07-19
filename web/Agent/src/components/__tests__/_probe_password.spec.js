/**
 * 探针测试:旧密码输入框初始状态
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import UserSettingsDialog from '../UserSettingsDialog.vue'

describe('PROBE: 旧密码输入框', () => {
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
          department: '沈阳', position: '', allowed_agents: [],
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

  it('probe_old_password_input 初始空字符串状态下不应显示任何字符', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: { visible: true, role: 'admin', userId: 1, username: 'admin', initialTab: 'profile' },
      attachTo: document.body,
    })
    await flushPromises()
    await flushPromises()

    const oldPwdInput = document.body.querySelector('#settings-old-password')
    const info = {
      type: oldPwdInput?.type,
      value: JSON.stringify(oldPwdInput?.value),
      valueLength: oldPwdInput?.value?.length,
      placeholder: oldPwdInput?.placeholder,
      outerHTML: oldPwdInput?.outerHTML,
    }
    throw new Error('[PROBE] ' + JSON.stringify(info, null, 2))
  })
})