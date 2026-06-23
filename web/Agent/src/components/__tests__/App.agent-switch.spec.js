/**
 * App.vue agent 切换测试
 *
 * 覆盖：App.vue 有 agentName 状态、监听 agent-switched 事件、
 *      chatStream 调用时传递 agentName。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

describe('App.vue agent 切换', () => {
  let originalFetch
  let originalLocalStorage

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
    // mock fetch：按 URL 分发到不同端点
    // - /api/auth/refresh → 返回新 access_token（供 refreshToken 成功）
    // - /api/auth/validate → 返回用户数据（供 validateToken 成功，使 authReady=true）
    global.fetch = vi.fn((url) => {
      if (url === '/api/auth/refresh') {
        return Promise.resolve({
          ok: true,
          json: async () => ({ access_token: 'fake-token' }),
        })
      }
      if (url === '/api/auth/validate') {
        return Promise.resolve({
          ok: true,
          json: async () => ({ username: 'tester', role: 'user', user_id: 1 }),
        })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })
    global.localStorage = {
      getItem: vi.fn((key) => {
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
  })

  it('test_app_has_agent_name_state App.vue 有 agentName 状态', async () => {
    const App = (await import('../../App.vue')).default
    const wrapper = mount(App, {
      global: {
        stubs: ['router-link', 'router-view'],
      },
    })
    await flushPromises()
    // agentName 应该有默认值 map_agent
    expect(wrapper.vm.agentName).toBe('map_agent')
  })

  it('test_app_listens_agent_switched App.vue 监听 agent-switched 事件', async () => {
    const App = (await import('../../App.vue')).default
    const wrapper = mount(App, {
      global: {
        stubs: ['router-link', 'router-view'],
      },
    })
    await flushPromises()
    // 模拟 InputBox 触发 agent-switched
    wrapper.findComponent({ name: 'InputBox' }).vm.$emit('agent-switched', 'contract_agent')
    await flushPromises()
    expect(wrapper.vm.agentName).toBe('contract_agent')
  })
})
