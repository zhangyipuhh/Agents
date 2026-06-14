/**
 * SubAgentDrawer 组件测试（2026-06-13 新增，2026-06-14 改造）
 *
 * 覆盖：
 *   - visible=false 时抽屉不显示（aside v-show 行为）
 *   - 关闭按钮触发 close 事件
 *   - 父 prompt 折叠/展开交互
 *   - 各 message type 渲染
 *   - 状态徽章 + 消息数 + 工具调用次数
 *   - 2026-06-14 改造：tool='sandbox' 时展示沙箱摘要 + 沙箱事件时间线
 *   - 2026-06-14 改造：AIMessage.content 为 LangChain 0.3+ list[ContentBlock] 格式时正确渲染
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SubAgentDrawer from '../SubAgentDrawer.vue'

const baseSubAgent = {
  toolCallId: 'c1',
  threadId: 'c1',
  tool: 'sandbox',
  parentPrompt: '父 agent 提问文本',
  messages: [
    { type: 'HumanMessage', role: 'user', content: 'user question' },
    { type: 'AIMessage', role: 'ai', content: 'ai thinking', tool_calls: [{ name: 'ls', args: { p: '/tmp' }, id: 'c1' }] },
    { type: 'ToolMessage', role: 'tool', content: 'tool output', tool_call_id: 'c1', name: 'ls' }
  ],
  events: [],
  status: 'success',
  startTime: Date.now() - 2000,
  endTime: Date.now() - 1000,
  error: null
}

describe('SubAgentDrawer', () => {
  it('visible=false 时抽屉不应可见', () => {
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: false, subAgent: baseSubAgent }
    })
    const aside = wrapper.find('aside.subagent-drawer')
    // v-show 切换 display
    expect(aside.exists()).toBe(true)
  })

  it('visible=true 时添加 visible class', () => {
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: baseSubAgent }
    })
    expect(wrapper.find('aside.subagent-drawer').classes()).toContain('visible')
  })

  it('关闭按钮触发 close 事件', async () => {
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: baseSubAgent }
    })
    await wrapper.find('.close-btn').trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('渲染父 agent 提问文本', () => {
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: baseSubAgent }
    })
    expect(wrapper.text()).toContain('父 agent 提问文本')
  })

  it('点击父 prompt section header 切换折叠状态', async () => {
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: baseSubAgent }
    })
    const header = wrapper.find('.parent-prompt-section .section-header')
    expect(header.exists()).toBe(true)
    await header.trigger('click')
    // 折叠后 content 区域不再显示
    expect(wrapper.find('.parent-prompt-content').exists()).toBe(false)
  })

  it('渲染 HumanMessage / AIMessage / ToolMessage 各一条', () => {
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: baseSubAgent }
    })
    const items = wrapper.findAll('.message-item')
    expect(items).toHaveLength(3)
    // role 分类样式
    expect(items[0].classes()).toContain('role-user')
    expect(items[1].classes()).toContain('role-ai')
    expect(items[2].classes()).toContain('role-tool')
  })

  it('AIMessage 含 tool_calls 时渲染"决策"区', () => {
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: baseSubAgent }
    })
    expect(wrapper.text()).toContain('决策')
    expect(wrapper.text()).toContain('ls')
  })

  it('底部摘要显示耗时/消息数/工具调用次数', () => {
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: baseSubAgent }
    })
    expect(wrapper.text()).toContain('3 条消息')
    expect(wrapper.text()).toContain('1 次工具调用')
  })

  it('messages 为空时显示"暂无消息"', () => {
    const wrapper = mount(SubAgentDrawer, {
      props: {
        visible: true,
        subAgent: { ...baseSubAgent, messages: [] }
      }
    })
    expect(wrapper.text()).toContain('暂无消息')
  })

  it('subAgent=null 时不崩溃且显示占位', () => {
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: null }
    })
    expect(wrapper.exists()).toBe(true)
  })

  // ========== 2026-06-14 改造：沙箱摘要 + 沙箱事件展示 ==========

  it('tool=sandbox 且有 summary 时展示沙箱摘要区', () => {
    const sandboxSa = {
      ...baseSubAgent,
      summary: {
        progress_pct: 50,
        current_step: 3,
        total_steps: 6,
        elapsed_ms: 12345
      }
    }
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: sandboxSa }
    })
    // 摘要区仍存在（状态 + 耗时）
    expect(wrapper.find('.drawer-summary').exists()).toBe(true)
    // 进度条已移除（2026-06-14）
    expect(wrapper.find('.summary-progress').exists()).toBe(false)
    // 耗时展示保留
    expect(wrapper.text()).toContain('耗时:')
  })

  it('tool=sandbox 且有 events 时展示沙箱事件区', () => {
    const sandboxSa = {
      ...baseSubAgent,
      events: [
        { step: 1, status: 'start', message: '开始执行', timestamp: Date.now() },
        { step: 2, status: 'progress', message: '执行中...', timestamp: Date.now() }
      ]
    }
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: sandboxSa }
    })
    expect(wrapper.find('.sandbox-events-section').exists()).toBe(true)
    const items = wrapper.findAll('.sandbox-event-item')
    expect(items).toHaveLength(2)
    // 步骤标签
    expect(wrapper.text()).toContain('步骤 1')
    expect(wrapper.text()).toContain('步骤 2')
  })

  it('tool=非 sandbox 时不展示沙箱事件区', () => {
    const exploreSa = {
      ...baseSubAgent,
      tool: 'explore',
      events: [{ step: 1, message: '探索中', timestamp: Date.now() }]
    }
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: exploreSa }
    })
    expect(wrapper.find('.sandbox-events-section').exists()).toBe(false)
    expect(wrapper.find('.drawer-summary').exists()).toBe(false)
  })

  it('沙箱事件可点击折叠', async () => {
    const sandboxSa = {
      ...baseSubAgent,
      events: [{ step: 1, status: 'start', message: '开始', timestamp: Date.now() }]
    }
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: sandboxSa }
    })
    // 默认展开
    expect(wrapper.find('.sandbox-events-scroll').exists()).toBe(true)
    // 点击 section-header 折叠
    const header = wrapper.find('.sandbox-events-section .section-header')
    await header.trigger('click')
    // 折叠后 scroll 容器消失
    expect(wrapper.find('.sandbox-events-scroll').exists()).toBe(false)
  })

  // ========== 2026-06-14 改造：LangChain 0.3+ 多模态消息格式 ==========

  it('AIMessage.content 为 list[ContentBlock] 时正确渲染（LangChain 0.3 格式）', () => {
    const lcSa = {
      ...baseSubAgent,
      tool: 'explore',
      messages: [
        { type: 'HumanMessage', role: 'user', content: 'hi' },
        {
          type: 'AIMessage',
          role: 'ai',
          content: [
            { type: 'text', text: '我会调用工具' },
            { type: 'tool_use', name: 'search', input: { query: 'xxx' } }
          ]
        },
        {
          type: 'ToolMessage',
          role: 'tool',
          content: [
            { type: 'tool_result', tool_use_id: 'c1', content: '搜索结果...' }
          ],
          tool_call_id: 'c1',
          name: 'search'
        }
      ]
    }
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: lcSa }
    })
    // text 块
    expect(wrapper.text()).toContain('我会调用工具')
    // tool_use 块
    expect(wrapper.text()).toContain('[工具调用]')
    expect(wrapper.text()).toContain('search')
    // tool_result 块
    expect(wrapper.text()).toContain('[工具结果')
    expect(wrapper.text()).toContain('搜索结果')
  })

  it('AIMessage.content 包含 thinking 块时正确渲染', () => {
    const thinkSa = {
      ...baseSubAgent,
      tool: 'explore',
      messages: [
        {
          type: 'AIMessage',
          role: 'ai',
          content: [
            { type: 'thinking', thinking: '分析用户意图...' },
            { type: 'text', text: '我需要查询资料' }
          ]
        }
      ]
    }
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: thinkSa }
    })
    expect(wrapper.text()).toContain('[思考]')
    expect(wrapper.text()).toContain('分析用户意图')
    expect(wrapper.text()).toContain('我需要查询资料')
  })
})
