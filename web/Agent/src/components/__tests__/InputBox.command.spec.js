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
      props: { sessionId: 'sid_1', isStreaming: false, allowedAgents: ['map_agent'] },
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
      props: { sessionId: 'sid_1', isStreaming: false, allowedAgents: ['map_agent'] },
    })
    const textarea = wrapper.find('textarea')
    await textarea.setValue('/agent map_agent')
    // 命令模式下应显示命令提示（.command-hint 元素存在且文本含「命令」）
    expect(wrapper.find('.command-hint').exists()).toBe(true)
    expect(wrapper.text()).toContain('命令')
  })

  it('test_agent_command_emits_agent_switched /agent 命令触发切换事件', async () => {
    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_1', isStreaming: false, allowedAgents: ['map_agent'] },
    })
    const textarea = wrapper.find('textarea')
    await textarea.setValue('/agent map_agent')
    const sendBtn = wrapper.find('.send-btn')
    await sendBtn.trigger('click')
    await flushPromises()
    // /agent 命令成功时应 emit('agent-switched', { name, display_name })
    // 2026-07-01 同步：2026-06-26 改造后 InputBox 把字符串包装成 { name, display_name } 对象；
    // 当前 InputBox.vue:247 在 result.switchAgent 为字符串时直接用该字符串作为 display_name 兜底，
    // 故 payload.display_name === 'map_agent'（与 fixture 的 display_name '地图' 不同，属正常封装行为）
    expect(wrapper.emitted('agent-switched')).toBeTruthy()
    expect(wrapper.emitted('agent-switched')[0][0]).toMatchObject({ name: 'map_agent' })
  })

  it('test_unknown_command_shows_hint 未知命令显示未知命令提示', async () => {
    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_1', isStreaming: false, allowedAgents: ['map_agent'] },
    })
    const textarea = wrapper.find('textarea')
    await textarea.setValue('/foo bar')
    // 未知命令应在 commandHint 中显示「未知命令：/foo」
    expect(wrapper.text()).toContain('未知命令：/foo')
  })

  it('test_agent_command_not_found /agent 不存在时不触发切换', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [{ name: 'map_agent', display_name: '地图' }],
    })
    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_1', isStreaming: false, allowedAgents: ['map_agent'] },
    })
    const textarea = wrapper.find('textarea')
    await textarea.setValue('/agent non_exist')
    const sendBtn = wrapper.find('.send-btn')
    await sendBtn.trigger('click')
    await flushPromises()
    // 目标 agent 不存在时不应触发 agent-switched
    expect(wrapper.emitted('agent-switched')).toBeFalsy()
    // 应通过 send 事件返回包含「不存在」的提示文本
    expect(wrapper.emitted('send')).toBeTruthy()
    expect(wrapper.emitted('send')[0][0]).toContain('不存在')
  })

  it('test_command_network_error_emits_failure 命令网络错误时 emit 失败提示', async () => {
    global.fetch = vi.fn((url) => {
      if (url === '/api/agent/list') {
        return Promise.resolve({ ok: false, status: 500, json: async () => ({ detail: '服务器错误' }) })
      }
      return Promise.resolve({ ok: true, json: async () => ({ access_token: 'token' }) })
    })
    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_1', isStreaming: false, allowedAgents: ['map_agent'] },
    })
    const textarea = wrapper.find('textarea')
    await textarea.setValue('/agent map_agent')
    const sendBtn = wrapper.find('.send-btn')
    await sendBtn.trigger('click')
    await flushPromises()
    // /api/agent/list 返回非 ok 时应通过 send 事件返回「命令执行失败」提示
    expect(wrapper.emitted('send')).toBeTruthy()
    expect(wrapper.emitted('send')[0][0]).toContain('命令执行失败')
  })

  it('test_agents_command_emits_send /agents 命令触发 send 事件', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [{ name: 'map_agent', display_name: '地图' }],
    })
    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_1', isStreaming: false, allowedAgents: ['map_agent'] },
    })
    const textarea = wrapper.find('textarea')
    await textarea.setValue('/agents')
    const sendBtn = wrapper.find('.send-btn')
    await sendBtn.trigger('click')
    await flushPromises()
    // /agents 命令应通过 send 事件返回智能体列表文本
    expect(wrapper.emitted('send')).toBeTruthy()
    expect(wrapper.emitted('send')[0][0]).toContain('map_agent')
  })

  // 2026-06-24 新增：智能体快速选择下拉菜单测试
  it('test_slash_shows_agent_dropdown 输入 "/" 显示智能体下拉菜单', async () => {
    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_1', isStreaming: false, allowedAgents: ['map_agent'] },
    })
    const textarea = wrapper.find('textarea')
    await textarea.setValue('/')
    await flushPromises()
    // 下拉菜单应存在
    expect(wrapper.find('.agent-dropdown').exists()).toBe(true)
    // 应显示智能体列表项
    expect(wrapper.find('.agent-dropdown-item').exists()).toBe(true)
    expect(wrapper.text()).toContain('地图')
  })

  it('test_select_agent_from_dropdown 从下拉菜单选中智能体后显示标签', async () => {
    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_1', isStreaming: false, allowedAgents: ['map_agent'] },
    })
    const textarea = wrapper.find('textarea')
    await textarea.setValue('/')
    await flushPromises()
    // 点击第一个智能体项
    const firstItem = wrapper.find('.agent-dropdown-item')
    await firstItem.trigger('mousedown')
    await flushPromises()
    // 应显示已选智能体标签
    expect(wrapper.find('.selected-agent-tag').exists()).toBe(true)
    expect(wrapper.text()).toContain('地图')
    // 输入框应被清空
    expect(textarea.element.value).toBe('')
  })

  it('test_selected_agent_emits_switch_on_send 选中智能体后发送触发 agent-switched', async () => {
    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_1', isStreaming: false, allowedAgents: ['map_agent'] },
    })
    const textarea = wrapper.find('textarea')
    await textarea.setValue('/')
    await flushPromises()
    // 选中智能体
    const firstItem = wrapper.find('.agent-dropdown-item')
    await firstItem.trigger('mousedown')
    await flushPromises()
    // 输入消息并发送
    await textarea.setValue('hello')
    const sendBtn = wrapper.find('.send-btn')
    await sendBtn.trigger('click')
    await flushPromises()
    // 应先触发 agent-switched，再触发 send
    // 2026-07-01 同步：2026-06-26 改造后 InputBox 发送对象（含 display_name）而不是字符串
    expect(wrapper.emitted('agent-switched')).toBeTruthy()
    expect(wrapper.emitted('agent-switched')[0]).toEqual([{ name: 'map_agent', display_name: '地图' }])
    expect(wrapper.emitted('send')).toBeTruthy()
    expect(wrapper.emitted('send')[0][0]).toBe('hello')
  })

  it('test_remove_selected_agent_tag 点击移除按钮可移除已选智能体标签', async () => {
    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_1', isStreaming: false, allowedAgents: ['map_agent'] },
    })
    const textarea = wrapper.find('textarea')
    await textarea.setValue('/')
    await flushPromises()
    // 选中智能体
    const firstItem = wrapper.find('.agent-dropdown-item')
    await firstItem.trigger('mousedown')
    await flushPromises()
    expect(wrapper.find('.selected-agent-tag').exists()).toBe(true)
    // 点击移除按钮
    const removeBtn = wrapper.find('.agent-remove-btn')
    await removeBtn.trigger('click')
    await flushPromises()
    // 标签应被移除
    expect(wrapper.find('.selected-agent-tag').exists()).toBe(false)
  })

  // 2026-06-24 新增：验证组件挂载时自动加载智能体列表
  it('test_load_agents_on_mount 组件挂载时自动加载智能体列表', async () => {
    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_1', isStreaming: false, allowedAgents: ['map_agent'] }
    })
    await flushPromises()
    // 下拉菜单未显示，但 agentList 应在挂载时已填充
    expect(wrapper.find('.agent-dropdown').exists()).toBe(false)
    // 输入 / 后应直接展示已加载的列表（无加载中状态）
    const textarea = wrapper.find('textarea')
    await textarea.setValue('/')
    await flushPromises()
    expect(wrapper.find('.agent-dropdown-item').exists()).toBe(true)
    expect(wrapper.text()).toContain('地图')
  })

  // 2026-07-01 新增：allowedAgents 权限过滤测试
  it('test_allowed_agents_filters_dropdown allowedAgents 过滤下拉列表', async () => {
    global.fetch = vi.fn((url) => {
      if (url === '/api/auth/refresh') {
        return Promise.resolve({ ok: true, json: async () => ({ access_token: 'new-fake-token' }) })
      }
      if (url === '/api/agent/list') {
        return Promise.resolve({
          ok: true,
          json: async () => [
            { name: 'map_agent', display_name: '地图' },
            { name: 'audit_agent', display_name: '审计' }
          ]
        })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })

    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_1', isStreaming: false, allowedAgents: ['map_agent'] }
    })
    const textarea = wrapper.find('textarea')
    await textarea.setValue('/')
    await flushPromises()

    expect(wrapper.find('.agent-dropdown-item').exists()).toBe(true)
    expect(wrapper.text()).toContain('地图')
    expect(wrapper.text()).not.toContain('审计')
  })

  it('test_empty_allowed_agents_shows_no_agents allowedAgents 为空时显示暂无可用智能体', async () => {
    global.fetch = vi.fn((url) => {
      if (url === '/api/auth/refresh') {
        return Promise.resolve({ ok: true, json: async () => ({ access_token: 'new-fake-token' }) })
      }
      if (url === '/api/agent/list') {
        return Promise.resolve({
          ok: true,
          json: async () => [{ name: 'map_agent', display_name: '地图' }]
        })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })

    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_1', isStreaming: false, allowedAgents: [] }
    })
    const textarea = wrapper.find('textarea')
    await textarea.setValue('/')
    await flushPromises()

    expect(wrapper.find('.agent-dropdown-item').exists()).toBe(false)
    expect(wrapper.text()).toContain('暂无可用智能体')
  })
})
