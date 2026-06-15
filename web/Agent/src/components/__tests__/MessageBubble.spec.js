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

// ========== 2026-06-14 第四次：子智能体 message 不进入主气泡的 thinking 区域 ==========
// 场景：经过 sseParser 过滤后，timeline 中应不出现子智能体内部的
//      thinking / text 片段（已通过 custom 事件累积到 subAgents[i].messages）。
//      此处使用 sseParser 处理一组 SSE 事件，验证输出的 timeline 干净无子智能体内容。

import { processSSEEvent, createAiMessage } from '../../utils/sseParser.js'

describe('MessageBubble 子智能体 message 过滤（2026-06-14 端到端）', () => {
  it('sseParser 过滤后，timeline 不含子智能体的 thinking 文本', () => {
    const aiMsg = createAiMessage()
    // 1) 注册 sandbox 子智能体
    processSSEEvent({
      type: 'custom',
      thread_id: 'tc_workspace',
      data: {
        type: 'tool_start',
        tool: 'sandbox',
        tool_call_id: 'tc_workspace',
        data: { parent_prompt: '生成 C# Hello World' }
      }
    }, aiMsg)
    // 2) 父线程 message
    processSSEEvent({
      type: 'message',
      content: [{ type: 'text', text: '我来帮你生成 C# Hello World' }],
      metadata: { thread_id: 'main_thread' }
    }, aiMsg)
    // 3) 子智能体 LLM 增量输出（模拟实际场景中的流式 thinking）
    processSSEEvent({
      type: 'message',
      content: [{ type: 'thinking', thinking: '工作目录是 /workspace，让我在这里创建' }],
      metadata: { thread_id: 'tc_workspace', lc_agent_name: 'sandbox' }
    }, aiMsg)
    processSSEEvent({
      type: 'message',
      content: [{ type: 'thinking', thinking: 'Let me try with the current working directory or check what path to use' }],
      metadata: { thread_id: 'tc_workspace', lc_agent_name: 'sandbox' }
    }, aiMsg)

    // 父气泡的 thinking / text 区域应只含父线程内容
    expect(aiMsg.text).toBe('我来帮你生成 C# Hello World')
    expect(aiMsg.thinking).toEqual([])
    // timeline 中不应出现子智能体的 thinking 文本
    const subAgentLeak = aiMsg.timeline.some(t => {
      if (typeof t.content === 'string') {
        return t.content.includes('工作目录是 /workspace') || t.content.includes('Let me try with the current working directory')
      }
      return false
    })
    expect(subAgentLeak).toBe(false)

    // 渲染 MessageBubble
    const wrapper = mount(MessageBubble, {
      props: {
        type: 'ai',
        ended: true,
        timeline: aiMsg.timeline,
        text: aiMsg.text,
        thinking: aiMsg.thinking,
        subAgents: aiMsg.subAgents
      }
    })
    // 主体文本应展示父线程的"我来帮你生成..."
    expect(wrapper.html()).toContain('我来帮你生成 C# Hello World')
    // 不应出现子智能体 thinking 字符串
    expect(wrapper.html()).not.toContain('工作目录是 /workspace')
    expect(wrapper.html()).not.toContain('Let me try with the current working directory')
  })

  it('子智能体 child_messages 仍完整保留在 subAgents[i].messages 中', () => {
    const aiMsg = createAiMessage()
    processSSEEvent({
      type: 'custom', thread_id: 'tc_keep', data: {
        type: 'tool_start', tool: 'sandbox', tool_call_id: 'tc_keep',
        data: { parent_prompt: 'p' }
      }
    }, aiMsg)
    // 通过 custom 事件累积 child_messages
    processSSEEvent({
      type: 'custom', thread_id: 'tc_keep', data: {
        type: 'tool_progress', tool: 'sandbox', tool_call_id: 'tc_keep',
        data: {
          child_messages: [
            { type: 'AIMessage', role: 'ai', content: [{ thinking: '工作目录是 /workspace', type: 'thinking' }] },
            { type: 'AIMessage', role: 'ai', content: [{ thinking: 'Let me try with the current working directory', type: 'thinking' }] }
          ]
        }
      }
    }, aiMsg)

    // 子智能体 messages 应保留两条 child_messages
    const sa = aiMsg.subAgents[0]
    expect(sa.messages).toHaveLength(2)
    // 这些内容在子智能体抽屉内仍可展示
    expect(JSON.stringify(sa.messages)).toContain('工作目录是 /workspace')
    expect(JSON.stringify(sa.messages)).toContain('Let me try with the current working directory')
  })
})

// ========== 2026-06-15：thinking-header 宽度对齐 subagent-card ==========
// 场景：MessageBubble 中存在两处 .thinking-header（timeline 模式 + 降级模式），
//      都需要从「内容自适应」改为「与 .subagent-card 等宽、右对齐」。
//
// 测试策略：直接读取 MessageBubble.vue 源文件，用 regex 验证 CSS 规则。
// 原因：happy-dom 不解析 Vue SFC <style scoped> 的 stylesheet.cssRules，
//       无法在运行时获取 scoped CSS 规则。源文件读取是最可靠的离线验证方式。

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const messageBubbleSource = readFileSync(
  join(__dirname, '../MessageBubble.vue'),
  'utf-8'
)

/**
 * 从 SFC 源文件中提取指定 class 选择器的 CSS 规则体
 * 入参：className（不带前导点）
 * 返回：CSS 规则体字符串（如 `display: flex; width: 100%; ...`），未找到返回 null
 */
const extractCssRule = (source, className) => {
  // 匹配 ".className {" 开头，到对应的 "}" 结束（简单匹配，非嵌套）
  const re = new RegExp(`\\.${className}\\s*\\{([^}]*)\\}`, 'm')
  const match = re.exec(source)
  return match ? match[1] : null
}

describe('MessageBubble 思考头部宽度（2026-06-15 新增）', () => {
  it('.thinking-header 使用 display:flex + width:100%（两处共用）', () => {
    const body = extractCssRule(messageBubbleSource, 'thinking-header')
    expect(body).not.toBeNull()
    // display 应为 flex（匹配以分号结尾的属性值，避免误匹配注释中的 inline-flex 字样）
    expect(body).toMatch(/display\s*:\s*flex\s*;/)
    expect(body).not.toMatch(/display\s*:\s*inline-flex/)
    // width 应为 100%
    expect(body).toMatch(/width\s*:\s*100%/)
    // box-sizing 应为 border-box
    expect(body).toMatch(/box-sizing\s*:\s*border-box/)
  })

  it('.timeline-thinking 容器：width:100% + align-self:flex-end（与 subagent-list 右对齐）', () => {
    const body = extractCssRule(messageBubbleSource, 'timeline-thinking')
    expect(body).not.toBeNull()
    // width 应为 100%（与 subagent-card 容器同宽）
    expect(body).toMatch(/width\s*:\s*100%/)
    // 右对齐
    expect(body).toMatch(/align-self\s*:\s*flex-end/)
    // 2026-06-15 二改：移除 max-width: 85% 兜底，让左右两边都与 subagent-card 对齐
    expect(body).not.toMatch(/max-width\s*:\s*85%/)
  })

  it('.thinking-section 容器（降级模式）：width:100% + align-self:flex-end', () => {
    const body = extractCssRule(messageBubbleSource, 'thinking-section')
    expect(body).not.toBeNull()
    // width 应为 100%（与 subagent-card 容器同宽）
    expect(body).toMatch(/width\s*:\s*100%/)
    // 右对齐（与 timeline 模式保持一致）
    expect(body).toMatch(/align-self\s*:\s*flex-end/)
    // 2026-06-15 二改：移除 max-width: 85% 兜底
    expect(body).not.toMatch(/max-width\s*:\s*85%/)
  })

  it('.thinking-header（width:100%）与 .subagent-card（width:100%）宽度规则一致', () => {
    const headerBody = extractCssRule(messageBubbleSource, 'thinking-header')
    const cardSourcePath = join(__dirname, '../SubAgentCard.vue')
    const cardSource = readFileSync(cardSourcePath, 'utf-8')
    const cardBody = extractCssRule(cardSource, 'subagent-card')
    expect(headerBody).not.toBeNull()
    expect(cardBody).not.toBeNull()
    // 两个元素都应设置 width: 100%（与父容器同宽）
    expect(headerBody).toMatch(/width\s*:\s*100%/)
    expect(cardBody).toMatch(/width\s*:\s*100%/)
  })
})

