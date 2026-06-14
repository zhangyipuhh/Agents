/**
 * MessageBubble 组件测试（2026-06-14 新增）
 *
 * 覆盖 2026-06-14 改造：
 *   - sandboxExecution prop 已移除（与 SubAgentCard 合并）
 *   - 子智能体卡片按 toolCallId 匹配，渲染在 timeline.tool 内（按事件时序）
 *   - 不再在 timeline 之外渲染 subagent-cards 列表
 *   - timeline.tool 内 SubAgentCard 点击触发 open-subagent-drawer 事件
 *
 * 2026-06-14 再改造：subagent 类工具调用不在「工具调用」块内重复展示
 *   - 当 group.items 全是 subagent：tools-header / tools-body 完全不渲染，仅保留 SubAgentCard
 *   - 当 group.items 混合 subagent 与普通工具：count 与 body 仅展示普通工具
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MessageBubble from '../MessageBubble.vue'

const makeToolEvent = (toolCallId, tool = 'sandbox') => ({
  type: 'custom',
  data: {
    type: 'tool_start',
    tool,
    tool_call_id: toolCallId,
    data: { parent_prompt: 'p' }
  }
})

const makeNonSubAgentEvent = (toolCallId, tool = 'read_file') => ({
  type: 'custom',
  data: {
    type: 'tool_start',
    tool,
    tool_call_id: toolCallId,
    data: { path: '/tmp/foo' }
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

// ========== 2026-06-14 再改造：subagent 不在工具调用块内重复展示 ==========

describe('MessageBubble 工具调用块过滤子智能体（2026-06-14 改造）', () => {
  it('group.items 全是 subagent 时不渲染 tools-header / tools-body', () => {
    const subAgents = [
      { toolCallId: 'tc_1', threadId: 'tc_1', tool: 'sandbox', parentPrompt: 'p1', messages: [], events: [], status: 'success', startTime: 0, endTime: 100, error: null },
      { toolCallId: 'tc_2', threadId: 'tc_2', tool: 'sandbox', parentPrompt: 'p2', messages: [], events: [], status: 'success', startTime: 0, endTime: 100, error: null }
    ]
    const wrapper = mount(MessageBubble, {
      props: {
        type: 'ai',
        timeline: [
          { type: 'tool', content: makeToolEvent('tc_1') },
          { type: 'tool', content: makeToolEvent('tc_2') }
        ],
        subAgents
      }
    })
    // tools-header / tools-body 不应出现（全是 subagent）
    expect(wrapper.find('.tools-header').exists()).toBe(false)
    expect(wrapper.find('.tools-body').exists()).toBe(false)
    // 但 SubAgentCard 应渲染
    expect(wrapper.findAll('.subagent-card').length).toBe(2)
  })

  it('group.items 混合 subagent + 普通工具时，count 与 body 仅展示普通工具', async () => {
    const subAgents = [
      { toolCallId: 'tc_sa', threadId: 'tc_sa', tool: 'sandbox', parentPrompt: 'p_sa', messages: [], events: [], status: 'success', startTime: 0, endTime: 100, error: null }
    ]
    const wrapper = mount(MessageBubble, {
      props: {
        type: 'ai',
        timeline: [
          { type: 'tool', content: makeToolEvent('tc_sa', 'sandbox') },
          { type: 'tool', content: makeNonSubAgentEvent('tc_fs1', 'read_file') },
          { type: 'tool', content: makeNonSubAgentEvent('tc_fs2', 'write_file') }
        ],
        subAgents
      }
    })
    // tools-header 应渲染，计数为 2（不含 subagent）
    const label = wrapper.find('.tools-label')
    expect(label.exists()).toBe(true)
    expect(label.text()).toContain('(2)')
    // 点击 tools-header 展开后再断言 body
    await wrapper.find('.tools-header').trigger('click')
    // tools-body 内仅 2 个 tool-item（不含 subagent）
    const items = wrapper.findAll('.tools-body .tool-item')
    expect(items.length).toBe(2)
    // 1 个 subAgentCard
    expect(wrapper.findAll('.subagent-card').length).toBe(1)
  })

  it('group.items 全是普通工具时维持旧行为（count == items.length）', async () => {
    const wrapper = mount(MessageBubble, {
      props: {
        type: 'ai',
        timeline: [
          { type: 'tool', content: makeNonSubAgentEvent('tc_a', 'read_file') },
          { type: 'tool', content: makeNonSubAgentEvent('tc_b', 'write_file') }
        ],
        subAgents: []
      }
    })
    const label = wrapper.find('.tools-label')
    expect(label.exists()).toBe(true)
    expect(label.text()).toContain('(2)')
    // 展开后再断言 body
    await wrapper.find('.tools-header').trigger('click')
    const items = wrapper.findAll('.tools-body .tool-item')
    expect(items.length).toBe(2)
  })
})

// ========== 2026-06-14 第三次去重：同一 toolCallId 跨多个 tool group 只渲染一张 SubAgentCard ==========
// 场景：同一次沙箱执行的 custom 事件（tool_start / tool_progress×N / tool_stop）
//      被 thinking / text 事件隔开后，mergedTimeline 会拆为多个独立 tool group。
//      旧行为：每个 group 都渲染一张 SubAgentCard → 重复
//      新行为：只渲染第一张，后续 group 内的同 id 卡片直接跳过

const makeThinkingEvent = () => ({
  type: 'thinking',
  content: '思考中…'
})

const makeTextEvent = (text) => ({
  type: 'text',
  content: text
})

describe('MessageBubble SubAgentCard 跨 group 去重（2026-06-14 新增）', () => {
  it('同一 toolCallId 跨多个 tool group 时只渲染一张 SubAgentCard', () => {
    const subAgents = [
      {
        toolCallId: 'tc_1',
        threadId: 'tc_1',
        tool: 'sandbox',
        parentPrompt: 'p1',
        messages: [],
        events: [],
        status: 'running',
        startTime: 0,
        endTime: null,
        error: null
      }
    ]
    // timeline: [tool(tc_1), thinking, tool(tc_1), text, tool(tc_1)]
    const wrapper = mount(MessageBubble, {
      props: {
        type: 'ai',
        timeline: [
          { type: 'tool', content: makeToolEvent('tc_1') },
          makeThinkingEvent(),
          { type: 'tool', content: makeToolEvent('tc_1') },
          makeTextEvent('中间说明'),
          { type: 'tool', content: makeToolEvent('tc_1') }
        ],
        subAgents
      }
    })
    // 全文应只有 1 张 SubAgentCard
    expect(wrapper.findAll('.subagent-card').length).toBe(1)
    // timeline-subagent-list 也应只有 1 个（首次 group 渲染，后续 group 跳过）
    expect(wrapper.findAll('.timeline-subagent-list').length).toBe(1)
  })

  it('不同 toolCallId 各自独立去重（互不影响）', () => {
    const subAgents = [
      { toolCallId: 'tc_1', threadId: 'tc_1', tool: 'sandbox', parentPrompt: 'p1', messages: [], events: [], status: 'running', startTime: 0, endTime: null, error: null },
      { toolCallId: 'tc_2', threadId: 'tc_2', tool: 'sandbox', parentPrompt: 'p2', messages: [], events: [], status: 'running', startTime: 0, endTime: null, error: null }
    ]
    // timeline: [tool(tc_1), thinking, tool(tc_2), thinking, tool(tc_1)]
    //   → tc_1 出现 2 次（应去重到 1），tc_2 出现 1 次
    //   → 预期 2 张 SubAgentCard
    const wrapper = mount(MessageBubble, {
      props: {
        type: 'ai',
        timeline: [
          { type: 'tool', content: makeToolEvent('tc_1') },
          makeThinkingEvent(),
          { type: 'tool', content: makeToolEvent('tc_2') },
          makeThinkingEvent(),
          { type: 'tool', content: makeToolEvent('tc_1') }
        ],
        subAgents
      }
    })
    expect(wrapper.findAll('.subagent-card').length).toBe(2)
    // 2 个不同的 subAgent 各自独立渲染
    expect(wrapper.findAll('.timeline-subagent-list').length).toBe(2)
  })

  it('同 toolCallId 全部去重后，后续 group 的 timeline-subagent-list 不渲染', () => {
    const subAgents = [
      {
        toolCallId: 'tc_1',
        threadId: 'tc_1',
        tool: 'sandbox',
        parentPrompt: 'p1',
        messages: [],
        events: [],
        status: 'running',
        startTime: 0,
        endTime: null,
        error: null
      }
    ]
    // timeline: [tool(tc_1), thinking, tool(tc_1)]
    //   → 第一个 group 渲染 1 张卡片
    //   → 第二个 group 内 tc_1 已被去重，getSubAgentsForGroup 返回 []
    //   → v-if 不成立，timeline-subagent-list 不渲染
    const wrapper = mount(MessageBubble, {
      props: {
        type: 'ai',
        timeline: [
          { type: 'tool', content: makeToolEvent('tc_1') },
          makeThinkingEvent(),
          { type: 'tool', content: makeToolEvent('tc_1') }
        ],
        subAgents
      }
    })
    expect(wrapper.findAll('.subagent-card').length).toBe(1)
    // 第二个 group 中没有剩余 subAgent → timeline-subagent-list 只有 1 个
    expect(wrapper.findAll('.timeline-subagent-list').length).toBe(1)
  })
})

