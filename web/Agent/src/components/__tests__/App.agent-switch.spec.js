/**
 * App.vue agent 切换测试
 *
 * 覆盖：App.vue 有 agentName 状态、监听 agent-switched 事件、
 *      chatStream 调用时传递 agentName、handleAgentSwitched 边界分支
 *      （空值/非字符串/同值）。
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

  it('test_chat_stream_passes_agent_name chatStream 调用时传递 agentName', async () => {
    // 使用 spy 替换 chatStream，避免真实网络请求并捕获调用参数
    const apiModule = await import('../../utils/api.js')
    const chatStreamSpy = vi.spyOn(apiModule, 'chatStream').mockResolvedValue({
      getReader: () => ({
        read: async () => ({ done: true, value: undefined })
      })
    })

    const App = (await import('../../App.vue')).default
    const wrapper = mount(App, {
      global: {
        stubs: ['router-link', 'router-view'],
      },
    })
    await flushPromises()

    // 模拟用户发送消息，触发 handleSendMessage → chatStream 调用链
    const inputBox = wrapper.findComponent({ name: 'InputBox' })
    inputBox.vm.$emit('send', 'hello', [])
    await flushPromises()

    // 验证 chatStream 被调用且第 5 个参数是 agentName.value（默认 map_agent）
    expect(chatStreamSpy).toHaveBeenCalled()
    const callArgs = chatStreamSpy.mock.calls[0]
    expect(callArgs[4]).toBe('map_agent')

    chatStreamSpy.mockRestore()
  })

  it('test_agent_switched_ignores_empty_value 空值不触发切换', async () => {
    const App = (await import('../../App.vue')).default
    const wrapper = mount(App, {
      global: {
        stubs: ['router-link', 'router-view'],
      },
    })
    await flushPromises()

    // emit 空字符串，应触发 handleAgentSwitched 的 !name 分支提前 return
    const inputBox = wrapper.findComponent({ name: 'InputBox' })
    inputBox.vm.$emit('agent-switched', '')
    await flushPromises()

    // agentName 应保持默认值 map_agent
    expect(wrapper.vm.agentName).toBe('map_agent')
  })

  it('test_agent_switched_ignores_non_string 非字符串不触发切换', async () => {
    const App = (await import('../../App.vue')).default
    const wrapper = mount(App, {
      global: {
        stubs: ['router-link', 'router-view'],
      },
    })
    await flushPromises()

    // emit 数字，应触发 typeof name !== 'string' 分支提前 return
    const inputBox = wrapper.findComponent({ name: 'InputBox' })
    inputBox.vm.$emit('agent-switched', 123)
    await flushPromises()

    expect(wrapper.vm.agentName).toBe('map_agent')
  })

  it('test_agent_switched_ignores_same_value 同值不触发重复设置', async () => {
    const App = (await import('../../App.vue')).default
    const wrapper = mount(App, {
      global: {
        stubs: ['router-link', 'router-view'],
      },
    })
    await flushPromises()

    // 先切换到 contract_agent（触发正常赋值分支）
    const inputBox = wrapper.findComponent({ name: 'InputBox' })
    inputBox.vm.$emit('agent-switched', 'contract_agent')
    await flushPromises()
    expect(wrapper.vm.agentName).toBe('contract_agent')

    // 再次 emit 同值，应触发 agentName.value === name 分支提前 return
    inputBox.vm.$emit('agent-switched', 'contract_agent')
    await flushPromises()
    expect(wrapper.vm.agentName).toBe('contract_agent')
  })
})
