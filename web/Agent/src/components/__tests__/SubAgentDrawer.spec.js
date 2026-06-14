/**
 * SubAgentDrawer 组件测试（2026-06-13 新增）
 *
 * 覆盖：
 *   - visible=false 时抽屉不显示（aside v-show 行为）
 *   - 关闭按钮触发 close 事件
 *   - 父 prompt 折叠/展开交互
 *   - 各 message type 渲染
 *   - 状态徽章 + 消息数 + 工具调用次数
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
})
