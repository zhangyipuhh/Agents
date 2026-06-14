/**
 * MessageBubble 组件测试（2026-06-14 新增）
 *
 * 覆盖 2026-06-14 改造：
 *   - sandboxExecution prop 已移除（与 SubAgentCard 合并）
 *   - 子智能体卡片按 toolCallId 匹配，渲染在 timeline.tool 内（按事件时序）
 *   - 不再在 timeline 之外渲染 subagent-cards 列表
 *   - timeline.tool 内 SubAgentCard 点击触发 open-subagent-drawer 事件
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MessageBubble from '../MessageBubble.vue'

const makeToolEvent = (toolCallId) => ({
  type: 'custom',
  data: {
    type: 'tool_start',
    tool: 'sandbox',
    tool_call_id: toolCallId,
    data: { parent_prompt: 'p' }
  }
})

describe('MessageBubble 子智能体卡片渲染（2026-06-14 改造）', () => {
  it('timeline.tool 内按 toolCallId 匹配并渲染 SubAgentCard', () => {
    const subAgents = [
      {
        toolCallId: 'tc_1',
        threadId: 'tc_1',
        tool: 'sandbox',
        parentPrompt: '执行沙箱任务',
        messages: [],
        events: [],
        status: 'running',
        startTime: Date.now() - 1500,
        endTime: null,
        error: null
      }
    ]
    const wrapper = mount(MessageBubble, {
      props: {
        type: 'ai',
        timeline: [
          { type: 'tool', content: makeToolEvent('tc_1') }
        ],
        subAgents
      }
    })
    // timeline.tool 内应出现 SubAgentCard
    const cards = wrapper.findAll('.subagent-card')
    expect(cards.length).toBeGreaterThanOrEqual(1)
    expect(wrapper.find('.timeline-subagent-list').exists()).toBe(true)
  })

  it('timeline 之外不再渲染 subagent-cards 容器', () => {
    const subAgents = [
      {
        toolCallId: 'tc_1',
        threadId: 'tc_1',
        tool: 'sandbox',
        parentPrompt: 'p',
        messages: [],
        events: [],
        status: 'success',
        startTime: 0,
        endTime: 100,
        error: null
      }
    ]
    const wrapper = mount(MessageBubble, {
      props: {
        type: 'ai',
        ended: true,
        timeline: [],
        subAgents
      }
    })
    // 旧的 .subagent-cards 容器不应再出现
    expect(wrapper.find('.subagent-cards').exists()).toBe(false)
  })

  it('timeline.tool 块内 SubAgentCard 点击触发 open-subagent-drawer 事件', async () => {
    const sa = {
      toolCallId: 'tc_1',
      threadId: 'tc_1',
      tool: 'sandbox',
      parentPrompt: 'p',
      messages: [],
      events: [],
      status: 'running',
      startTime: Date.now() - 1000,
      endTime: null,
      error: null
    }
    const wrapper = mount(MessageBubble, {
      props: {
        type: 'ai',
        timeline: [
          { type: 'tool', content: makeToolEvent('tc_1') }
        ],
        subAgents: [sa]
      }
    })
    // 点击 timeline.tool 块内的 SubAgentCard
    const card = wrapper.find('.timeline-subagent-list .subagent-card')
    expect(card.exists()).toBe(true)
    await card.trigger('click')
    // 应触发 open-subagent-drawer 事件
    expect(wrapper.emitted('open-subagent-drawer')).toBeTruthy()
    expect(wrapper.emitted('open-subagent-drawer')[0][0]).toEqual(sa)
  })

  it('timeline.tool 内无匹配 subAgent 时不渲染卡片（按 toolCallId 严格匹配）', () => {
    const subAgents = [
      {
        toolCallId: 'tc_other',
        threadId: 'tc_other',
        tool: 'sandbox',
        parentPrompt: 'p',
        messages: [],
        events: [],
        status: 'running',
        startTime: 0,
        endTime: null,
        error: null
      }
    ]
    const wrapper = mount(MessageBubble, {
      props: {
        type: 'ai',
        timeline: [
          { type: 'tool', content: makeToolEvent('tc_1') }  // 不匹配 tc_other
        ],
        subAgents
      }
    })
    // 不应渲染 SubAgentCard
    expect(wrapper.find('.timeline-subagent-list').exists()).toBe(false)
  })

  it('多 subAgent 数据驱动：每个匹配 toolCallId 在对应 tool 块内出现', () => {
    const subAgents = [
      { toolCallId: 'tc_1', threadId: 'tc_1', tool: 'sandbox', parentPrompt: 'p1', messages: [], events: [], status: 'success', startTime: 0, endTime: 100, error: null },
      { toolCallId: 'tc_2', threadId: 'tc_2', tool: 'sandbox', parentPrompt: 'p2', messages: [], events: [], status: 'success', startTime: 0, endTime: 100, error: null }
    ]
    const wrapper = mount(MessageBubble, {
      props: {
        type: 'ai',
        timeline: [
          { type: 'text', content: 'hello' },
          { type: 'tool', content: makeToolEvent('tc_1') },
          { type: 'text', content: 'middle' },
          { type: 'tool', content: makeToolEvent('tc_2') }
        ],
        subAgents
      }
    })
    // 两个 subAgentCard 都应渲染
    const cards = wrapper.findAll('.subagent-card')
    expect(cards.length).toBe(2)
  })
})
