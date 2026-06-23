/**
 * InputBox 命令检测测试（2026-06-23 新增，Task 17）
 *
 * 覆盖：输入 / 开头时识别为命令、/agent 命令触发 agent-switched 事件、
 *      普通文本不触发命令而走正常 send 流程。
 *
 * 测试策略：mount InputBox + mock global.fetch（同时处理 /api/auth/refresh
 *           与 /api/agent/list 两个端点）+ mock global.localStorage。
 *           通过 textarea.setValue 注入输入，点击 .send-btn 触发 handleSend。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import InputBox from '../InputBox.vue'

describe('InputBox 命令检测', () => {
  let originalFetch
  let originalLocalStorage

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
    // mock fetch：按 URL 分发到不同端点
    // - /api/auth/refresh → 返回新 access_token（供 refreshToken 成功）
    // - /api/agent/list → 返回 map_agent（供 /agent 命令匹配）
    global.fetch = vi.fn((url) => {
      if (url === '/api/auth/refresh') {
        return Promise.resolve({
          ok: true,
          json: async () => ({ access_token: 'new-fake-token' }),
        })
      }
      if (url === '/api/agent/list') {
        return Promise.resolve({
          ok: true,
          json: async () => [{ name: 'map_agent', display_name: '地图' }],
        })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })
    global.localStorage = {
      getItem: vi.fn(() => 'fake-token'),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    }
    // happy-dom 不提供 alert，注入 noop 避免 unhandled error
    if (typeof window !== 'undefined' && !window.alert) {
      window.alert = () => {}
    }
  })

  afterEach(() => {
    global.fetch = originalFetch
    global.localStorage = originalLocalStorage
  })

  it('test_normal_text_emits_send 普通文本触发 send 事件', async () => {
    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_1', isStreaming: false },
    })
    const textarea = wrapper.find('textarea')
    await textarea.setValue('hello world')
    const sendBtn = wrapper.find('.send-btn')
    await sendBtn.trigger('click')
    await flushPromises()
    // 普通文本应走正常发送流程，emit('send', text, files)
    expect(wrapper.emitted('send')).toBeTruthy()
    // 不应触发 agent-switched
    expect(wrapper.emitted('agent-switched')).toBeFalsy()
  })

  it('test_slash_input_identified_as_command / 开头识别为命令', async () => {
    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_1', isStreaming: false },
    })
    const textarea = wrapper.find('textarea')
    await textarea.setValue('/agent map_agent')
    // 命令模式下应显示命令提示（.command-hint 元素存在且文本含「命令」）
    expect(wrapper.find('.command-hint').exists()).toBe(true)
    expect(wrapper.text()).toContain('命令')
  })

  it('test_agent_command_emits_agent_switched /agent 命令触发切换事件', async () => {
    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_1', isStreaming: false },
    })
    const textarea = wrapper.find('textarea')
    await textarea.setValue('/agent map_agent')
    const sendBtn = wrapper.find('.send-btn')
    await sendBtn.trigger('click')
    await flushPromises()
    // /agent 命令成功时应 emit('agent-switched', 'map_agent')
    expect(wrapper.emitted('agent-switched')).toBeTruthy()
    expect(wrapper.emitted('agent-switched')[0]).toEqual(['map_agent'])
  })
})
