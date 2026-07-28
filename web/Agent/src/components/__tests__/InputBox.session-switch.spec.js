/**
 * InputBox 会话切换清理测试（2026-07-28 新增）
 *
 * 覆盖：用户在当前会话"已选智能体但未发送"或"已选待上传文件"时切换到历史会话，
 *       InputBox 应清空这些"待发送的本地态"，避免前一会话残留标签与新会话的
 *       boundAgent 标签同时出现（"两个运维项目智能体"重复显示）。
 *
 * 测试策略：mount InputBox + props.sessionId 变化触发 watch。
 *           通过 input + 模拟 selectAgent 注入"已选"状态，再切换 sessionId。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import InputBox from '../InputBox.vue'

describe('InputBox 会话切换清理本地态（2026-07-28）', () => {
  let originalFetch
  let originalLocalStorage

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
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
          json: async () => [
            { name: 'ops_agent', display_name: '运维项目智能体' },
            { name: 'map_agent', display_name: '地图智能体' },
          ],
        })
      }
      if (typeof url === 'string' && url.includes('/api/core/upload-config')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ max_file_size_mb: 3 }),
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
    if (typeof window !== 'undefined' && !window.alert) {
      window.alert = () => {}
    }
  })

  afterEach(() => {
    global.fetch = originalFetch
    global.localStorage = originalLocalStorage
  })

  it('test_selected_agent_cleared_on_session_switch 切换 session 时清空已选智能体标签', async () => {
    const wrapper = mount(InputBox, {
      props: {
        sessionId: 'sid_new',
        isStreaming: false,
        boundAgentName: '',
        boundAgentDisplayName: '',
        allowedAgents: ['ops_agent', 'map_agent'],
        isAdmin: true,
      },
    })
    await flushPromises()

    // 触发智能体下拉：输入 /
    const editor = wrapper.find('[data-testid="input-editor"]')
    editor.element.replaceChildren(document.createTextNode('/'))
    await editor.trigger('input')
    await flushPromises()

    // 模拟 selectAgent：直接调用组件内方法或通过事件触发
    // 这里通过模板路径：找 .agent-dropdown-item 触发 mousedown 选中
    const items = wrapper.findAll('.agent-dropdown-item')
    expect(items.length).toBeGreaterThan(0)
    // 找到「运维项目智能体」并点击
    const opsItem = items.find((i) => i.text().includes('运维项目智能体'))
    expect(opsItem).toBeTruthy()
    await opsItem.trigger('mousedown')
    await flushPromises()

    // 切换前：selected-agent-tag 应存在
    expect(wrapper.find('.selected-agent-tag').exists()).toBe(true)

    // 切换到历史会话（该会话绑定了 map_agent）
    await wrapper.setProps({
      sessionId: 'sid_history',
      boundAgentName: 'map_agent',
      boundAgentDisplayName: '地图智能体',
    })
    await flushPromises()

    // 切换后：selectedAgent 状态已被清空（无 .selected-agent-tag 但不带 .bound-agent-tag 的元素）
    const allTags = wrapper.findAll('.selected-agent-tag')
    // 仅 1 个 bound-agent-tag（不带 × 移除按钮）
    expect(allTags.length).toBe(1)
    expect(allTags[0].classes()).toContain('bound-agent-tag')
    // bound-agent-tag 应显示新会话绑定的智能体
    expect(allTags[0].text()).toContain('地图智能体')
    // bound-agent-tag 上不应有 agent-remove-btn（只有 selectedAgent 标签有）
    expect(allTags[0].find('.agent-remove-btn').exists()).toBe(false)
  })

  it('test_no_duplicate_agent_label_after_session_switch 切换后无重复的智能体标签', async () => {
    const wrapper = mount(InputBox, {
      props: {
        sessionId: 'sid_new',
        isStreaming: false,
        boundAgentName: '',
        boundAgentDisplayName: '',
        allowedAgents: ['ops_agent', 'map_agent'],
        isAdmin: true,
      },
    })
    await flushPromises()

    // 触发下拉并选中
    const editor = wrapper.find('[data-testid="input-editor"]')
    editor.element.replaceChildren(document.createTextNode('/'))
    await editor.trigger('input')
    await flushPromises()
    const items = wrapper.findAll('.agent-dropdown-item')
    const opsItem = items.find((i) => i.text().includes('运维项目智能体'))
    await opsItem.trigger('mousedown')
    await flushPromises()

    // 切到历史会话（也绑定了 ops_agent，验证只是 selectedAgent 被清空，不依赖 boundAgent 是否同名）
    await wrapper.setProps({
      sessionId: 'sid_history',
      boundAgentName: 'ops_agent',
      boundAgentDisplayName: '运维项目智能体',
    })
    await flushPromises()

    // 应只显示 1 个智能体标签（bound-agent-tag），而非 2 个
    const allAgentTags = wrapper.findAll('.selected-agent-tag')
    expect(allAgentTags.length).toBe(1)
    expect(allAgentTags[0].classes()).toContain('bound-agent-tag')
  })

  it('test_dropdown_closes_on_session_switch 切换时收起下拉菜单', async () => {
    const wrapper = mount(InputBox, {
      props: {
        sessionId: 'sid_new',
        isStreaming: false,
        allowedAgents: ['ops_agent'],
        isAdmin: true,
      },
    })
    await flushPromises()

    // 打开下拉
    const editor = wrapper.find('[data-testid="input-editor"]')
    editor.element.replaceChildren(document.createTextNode('/'))
    await editor.trigger('input')
    await flushPromises()
    expect(wrapper.find('.agent-dropdown').exists()).toBe(true)

    // 切换 session
    await wrapper.setProps({ sessionId: 'sid_history' })
    await flushPromises()

    // 下拉应关闭
    expect(wrapper.find('.agent-dropdown').exists()).toBe(false)
  })

  it('test_editor_dom_cleared_on_session_switch 切换时清空编辑器 DOM', async () => {
    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_a', isStreaming: false, allowedAgents: ['map_agent'] },
    })
    await flushPromises()

    // 在编辑器输入一些文本
    const editor = wrapper.find('[data-testid="input-editor"]')
    editor.element.replaceChildren(document.createTextNode('hello world'))
    await editor.trigger('input')
    await flushPromises()

    // 切到新 session（无快照）
    await wrapper.setProps({ sessionId: 'sid_b_unseen' })
    await flushPromises()

    // 编辑器应清空（无快照时新 session 初始化为空）
    expect(editor.element.innerHTML).toBe('')
  })

  it('test_immediate_watch_does_not_clear_initial_state immediate 阶段不清空初始态', async () => {
    // 验证：第一次 mount 时（immediate 触发）sid === oldSidKey，不应清空
    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_initial', isStreaming: false, allowedAgents: ['map_agent'] },
    })
    await flushPromises()

    const editor = wrapper.find('[data-testid="input-editor"]')
    editor.element.replaceChildren(document.createTextNode('initial text'))
    await editor.trigger('input')
    await flushPromises()
    expect(editor.element.textContent).toContain('initial text')

    // 重新设回同一个 sessionId（不应触发清空）
    await wrapper.setProps({ sessionId: 'sid_initial' })
    await flushPromises()
    expect(editor.element.textContent).toContain('initial text')
  })
})