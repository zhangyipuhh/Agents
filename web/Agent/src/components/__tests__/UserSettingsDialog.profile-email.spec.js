/**
 * 2026-07-19 探针测试 → 回归测试:UserSettingsDialog 个人设置邮箱字段加载
 *
 * 根因记录:之前未对 GET /api/users/{id}/profile 的前端加载链路做端到端回归测试,
 * 一旦后端响应模型或前端赋值逻辑出错,无法被 CI 捕获。本次新增测试覆盖:
 * - 后端响应含 email 时,前端 #settings-email 输入框必须显示该值
 * - 模拟浏览器真实交互:visible:false → true 切换
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import UserSettingsDialog from '../UserSettingsDialog.vue'

describe('个人设置邮箱字段回归测试', () => {
  let originalFetch
  let originalLocalStorage

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
    global.fetch = vi.fn(async (url, opts = {}) => {
      const u = typeof url === 'string' ? url : url.url
      // 2026-07-19 关键契约:/api/users/{id}/profile 必须返回 email 字段
      if (u.includes('/api/users/1/profile')) {
        return {
          ok: true,
          json: async () => ({
            id: 1,
            username: 'admin',
            role: 'admin',
            real_name: '',
            phone: '',
            email: '542995981@qq.com',
            department: '',
            position: '',
            allowed_agents: [],
            created_at: '2026-07-19T00:00:00',
            updated_at: '2026-07-19T00:00:00',
          })
        }
      }
      // 阻断其他无关请求
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

  it('test_profile_email_input_reflects_backend_value 后端返回 email 时,输入框必须显示该值', async () => {
    // 阶段 1:visible=false mount(对应 Sidebar 初始)
    const wrapper = mount(UserSettingsDialog, {
      props: { visible: false, role: 'admin', userId: 1, username: 'admin', initialTab: 'profile' },
      attachTo: document.body,
    })
    await flushPromises()

    // 阶段 2:模拟用户点击「个人设置」,visible:false → true
    await wrapper.setProps({ visible: true })
    await flushPromises()
    await flushPromises()

    // 由于 <Teleport to="body">,输入框渲染到 document.body 而非 wrapper.element
    const emailInput = document.body.querySelector('#settings-email')
    expect(emailInput).not.toBeNull()
    expect(emailInput.value).toBe('542995981@qq.com')
  })
})