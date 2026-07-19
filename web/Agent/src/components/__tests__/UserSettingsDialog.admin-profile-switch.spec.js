/**
 * 2026-07-19 探针 v4:复现 admin 真实场景 → 已转为回归测试
 *
 * 根因记录:之前 watch 只在 props.visible 变化时触发 loadUserProfile,
 * 当 admin 用户先点"管理后台"(activeTab='user-management')再在 dialog 内切换到
 * "个人设置"时,switchTab 没有调用 loadUserProfile,导致邮箱等字段保持空字符串,
 * 渲染时显示 placeholder。修复:switchTab 增加 profile 分支调用 loadUserProfile。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import UserSettingsDialog from '../UserSettingsDialog.vue'

describe('admin 场景:管理后台→个人设置切换', () => {
  let originalFetch
  let originalLocalStorage

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
    global.fetch = vi.fn(async (url, opts = {}) => {
      const u = typeof url === 'string' ? url : url.url
      if (u.includes('/api/users/1/profile')) {
        return {
          ok: true,
          json: async () => ({
            id: 1, username: 'admin', role: 'admin',
            real_name: '', phone: '', email: '542995981@qq.com',
            department: '', position: '', allowed_agents: [],
            created_at: '2026-07-19', updated_at: '2026-07-19',
          })
        }
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
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    }
  })

  afterEach(() => {
    global.fetch = originalFetch
    global.localStorage = originalLocalStorage
    document.body.innerHTML = ''
  })

  it('test_admin_switch_to_profile_loads_email admin 在 dialog 内切换到"个人设置"必须重新加载用户资料', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: { visible: false, role: 'admin', userId: 1, username: 'admin', initialTab: 'user-management' },
      attachTo: document.body,
    })
    await flushPromises()

    // 模拟点击"管理后台" → visible=true
    await wrapper.setProps({ visible: true })
    await flushPromises()
    await flushPromises()

    // 模拟用户在 dialog 内点击"个人设置" → 调用 switchTab('profile')
    wrapper.vm.switchTab('profile')
    await flushPromises()
    await flushPromises()

    const emailInput = document.body.querySelector('#settings-email')
    expect(emailInput).not.toBeNull()
    expect(emailInput.value).toBe('542995981@qq.com')
  })
})