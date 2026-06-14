import { describe, it, expect } from 'vitest'
import {
  isThinkingBlock,
  tryParsePythonLiteral,
  extractTextFromBlock,
  processContentBlocks,
  parseMessageContent,
  processSSEEvent,
  createAiMessage,
  isSubAgentMessage,
} from '../sseParser.js'

function createTestAiMsg() {
  return {
    id: 1,
    type: 'ai',
    timeline: [],
    thinking: [],
    tools: [],
    text: '',
    ended: false,
    error: '',
  }
}

describe('isThinkingBlock', () => {
  it('returns true for thinking type', () => {
    expect(isThinkingBlock({ type: 'thinking' })).toBe(true)
  })

  it('returns true for block with thinking field', () => {
    expect(isThinkingBlock({ thinking: 'hmm' })).toBe(true)
  })

  it('returns false for text type', () => {
    expect(isThinkingBlock({ type: 'text', text: 'hello' })).toBe(false)
  })

  it('returns false for null', () => {
    expect(isThinkingBlock(null)).toBe(false)
  })

  it('returns false for undefined', () => {
    expect(isThinkingBlock(undefined)).toBe(false)
  })

  it('returns false for empty object', () => {
    expect(isThinkingBlock({})).toBe(false)
  })
})

describe('tryParsePythonLiteral', () => {
  it('returns null for non-string', () => {
    expect(tryParsePythonLiteral(42)).toBe(null)
  })

  it('returns null for string not starting with [', () => {
    expect(tryParsePythonLiteral('hello')).toBe(null)
  })

  it('parses valid JSON array', () => {
    const result = tryParsePythonLiteral('[{"type":"text","text":"hello"}]')
    expect(result).toEqual([{ type: 'text', text: 'hello' }])
  })

  it('parses Python-style boolean literals', () => {
    const result = tryParsePythonLiteral("[{'flag': True}]")
    expect(result[0].flag).toBe(true)
  })

  it('parses Python-style None', () => {
    const result = tryParsePythonLiteral("[{'val': None}]")
    expect(result[0].val).toBe(null)
  })

  it('extracts thinking blocks from Python literal', () => {
    const content = "[{'thinking': 'deep thought', 'type': 'thinking'}]"
    const result = tryParsePythonLiteral(content)
    expect(result).toEqual([{ type: 'thinking', thinking: 'deep thought' }])
  })

  it('extracts text blocks from Python literal', () => {
    const content = "[{'text': 'hello world', 'type': 'text'}]"
    const result = tryParsePythonLiteral(content)
    expect(result).toEqual([{ type: 'text', text: 'hello world' }])
  })

  it('returns null for unparseable content', () => {
    expect(tryParsePythonLiteral('[]')).toEqual([])
  })
})

describe('extractTextFromBlock', () => {
  it('returns string as-is', () => {
    expect(extractTextFromBlock('hello')).toBe('hello')
  })

  it('returns empty string for null', () => {
    expect(extractTextFromBlock(null)).toBe('')
  })

  it('extracts text field', () => {
    expect(extractTextFromBlock({ text: 'hello' })).toBe('hello')
  })

  it('extracts content field', () => {
    expect(extractTextFromBlock({ content: 'world' })).toBe('world')
  })

  it('prefers text over content', () => {
    expect(extractTextFromBlock({ text: 'a', content: 'b' })).toBe('a')
  })
})

describe('processContentBlocks', () => {
  it('processes string blocks', () => {
    const msg = createTestAiMsg()
    processContentBlocks(msg, ['hello'])
    expect(msg.text).toBe('hello')
    expect(msg.timeline).toEqual([{ type: 'text', content: 'hello' }])
  })

  it('processes thinking blocks', () => {
    const msg = createTestAiMsg()
    processContentBlocks(msg, [{ type: 'thinking', thinking: 'hmm' }])
    expect(msg.thinking).toEqual(['hmm'])
    expect(msg.timeline[0].type).toBe('thinking')
  })

  it('skips empty thinking', () => {
    const msg = createTestAiMsg()
    processContentBlocks(msg, [{ type: 'thinking', thinking: '' }])
    expect(msg.thinking).toEqual([])
    expect(msg.timeline).toEqual([])
  })

  it('processes text blocks', () => {
    const msg = createTestAiMsg()
    processContentBlocks(msg, [{ type: 'text', text: 'hello' }])
    expect(msg.text).toBe('hello')
  })

  it('processes mixed blocks', () => {
    const msg = createTestAiMsg()
    processContentBlocks(msg, [
      { type: 'thinking', thinking: 'hmm' },
      { type: 'text', text: 'answer' },
    ])
    expect(msg.thinking).toEqual(['hmm'])
    expect(msg.text).toBe('answer')
    expect(msg.timeline).toHaveLength(2)
  })
})

describe('parseMessageContent', () => {
  it('handles null/undefined', () => {
    const msg = createTestAiMsg()
    parseMessageContent(null, msg)
    expect(msg.text).toBe('')
  })

  it('handles array content', () => {
    const msg = createTestAiMsg()
    parseMessageContent([{ type: 'text', text: 'hi' }], msg)
    expect(msg.text).toBe('hi')
  })

  it('handles object thinking block', () => {
    const msg = createTestAiMsg()
    parseMessageContent({ type: 'thinking', thinking: 'deep' }, msg)
    expect(msg.thinking).toEqual(['deep'])
  })

  it('handles object with text', () => {
    const msg = createTestAiMsg()
    parseMessageContent({ type: 'text', text: 'hello' }, msg)
    expect(msg.text).toBe('hello')
  })

  it('handles plain string', () => {
    const msg = createTestAiMsg()
    parseMessageContent('hello world', msg)
    expect(msg.text).toBe('hello world')
  })

  it('handles Python literal string', () => {
    const msg = createTestAiMsg()
    parseMessageContent("[{'type': 'text', 'text': 'parsed'}]", msg)
    expect(msg.text).toBe('parsed')
  })

  it('handles numeric content', () => {
    const msg = createTestAiMsg()
    parseMessageContent(42, msg)
    expect(msg.text).toBe('42')
  })
})

describe('processSSEEvent', () => {
  it('processes message event with string content', () => {
    const msg = createTestAiMsg()
    processSSEEvent({ type: 'message', content: 'Hello AI' }, msg)
    expect(msg.text).toBe('Hello AI')
  })

  it('processes message event with data field', () => {
    const msg = createTestAiMsg()
    processSSEEvent({ type: 'message', data: 'from data' }, msg)
    expect(msg.text).toBe('from data')
  })

  it('processes message event with array content', () => {
    const msg = createTestAiMsg()
    processSSEEvent({ type: 'message', content: [{ type: 'text', text: 'hello' }] }, msg)
    expect(msg.text).toBe('hello')
  })

  it('processes thinking content in message', () => {
    const msg = createTestAiMsg()
    processSSEEvent(
      { type: 'message', content: [{ type: 'thinking', thinking: 'hmm' }, { type: 'text', text: 'answer' }] },
      msg
    )
    expect(msg.thinking).toEqual(['hmm'])
    expect(msg.text).toBe('answer')
  })

  it('processes update event with llm_call', () => {
    const msg = createTestAiMsg()
    processSSEEvent(
      {
        type: 'update',
        data: {
          llm_call: {
            messages: ["[{'type': 'text', 'text': 'response'}]"],
          },
        },
      },
      msg
    )
    expect(msg.text).toBe('response')
  })

  it('skips update event with summarize node', () => {
    const msg = createTestAiMsg()
    processSSEEvent(
      { type: 'update', data: { summarize: { messages: [] } } },
      msg
    )
    expect(msg.text).toBe('')
    expect(msg.thinking).toEqual([])
  })

  it('processes update event as thinking when no llm_call', () => {
    const msg = createTestAiMsg()
    processSSEEvent({ type: 'update', data: { progress: 'loading' } }, msg)
    expect(msg.thinking.length).toBe(1)
  })

  it('processes custom event', () => {
    const msg = createTestAiMsg()
    processSSEEvent({ type: 'custom', tool: 'search', result: 'found' }, msg)
    expect(msg.tools.length).toBe(1)
    expect(msg.tools[0].tool).toBe('search')
  })

  it('processes end event', () => {
    const msg = createTestAiMsg()
    processSSEEvent({ type: 'end' }, msg)
    expect(msg.ended).toBe(true)
  })

  it('processes error event', () => {
    const msg = createTestAiMsg()
    processSSEEvent({ type: 'error', message: 'timeout' }, msg)
    expect(msg.error).toBe('不好意思，刚刚出了点小故障，可以晚点再问我一遍。')
  })
})

describe('createAiMessage', () => {
  it('creates message with correct structure', () => {
    const msg = createAiMessage()
    expect(msg.type).toBe('ai')
    expect(msg.timeline).toEqual([])
    expect(msg.thinking).toEqual([])
    expect(msg.tools).toEqual([])
    expect(msg.text).toBe('')
    expect(msg.ended).toBe(false)
    expect(msg.error).toBe('')
  })

  it('creates unique ids', async () => {
    const msg1 = createAiMessage()
    await new Promise(r => setTimeout(r, 2))
    const msg2 = createAiMessage()
    expect(msg1.id).not.toBe(msg2.id)
  })
})

describe('SSE regression: event type contract', () => {
  it('handles all 5 SSE event types', () => {
    const eventTypes = ['update', 'message', 'custom', 'end', 'error']
    for (const type of eventTypes) {
      const msg = createTestAiMsg()
      processSSEEvent({ type }, msg)
    }
  })

  it('message event with thinking+text array preserves both', () => {
    const msg = createTestAiMsg()
    processSSEEvent(
      {
        type: 'message',
        content: [
          { type: 'thinking', thinking: 'Let me think...' },
          { type: 'text', text: 'Here is the answer' },
        ],
      },
      msg
    )
    expect(msg.thinking).toEqual(['Let me think...'])
    expect(msg.text).toBe('Here is the answer')
    expect(msg.timeline).toHaveLength(2)
    expect(msg.timeline[0].type).toBe('thinking')
    expect(msg.timeline[1].type).toBe('text')
  })

  it('update event with llm_call containing Python literal', () => {
    const msg = createTestAiMsg()
    processSSEEvent(
      {
        type: 'update',
        data: {
          llm_call: {
            messages: [
              "[{'thinking': 'analyzing', 'type': 'thinking'}, {'text': 'result', 'type': 'text'}]",
            ],
          },
        },
      },
      msg
    )
    expect(msg.thinking).toEqual(['analyzing'])
    expect(msg.text).toBe('result')
  })

  // ========== 2026-06-14 改造：子智能体 message 跳过与 threadId 防污染 ==========

  it('2026-06-14: message event from registered subagent thread is skipped', () => {
    const msg = createAiMessage()
    // 先注册 sandbox 子智能体
    processSSEEvent({
      type: 'custom',
      thread_id: 'call_sandbox_1',
      data: {
        type: 'tool_start',
        tool: 'sandbox',
        tool_call_id: 'call_sandbox_1',
        data: { parent_prompt: '执行沙箱任务' }
      }
    }, msg)
    expect(msg.subAgents).toHaveLength(1)
    const saThreadId = msg.subAgents[0].threadId
    // 记录 tool_start 累积的 timeline 长度（按设计它会推一条 tool 项到 timeline）
    const timelineLenBefore = msg.timeline.length

    // 模拟子智能体 LLM 流式输出（metadata.thread_id === subagent.threadId）
    processSSEEvent({
      type: 'message',
      content: [{ type: 'thinking', thinking: '工作目录是 /workspace，让我在这里创建' }],
      metadata: { thread_id: saThreadId, lc_agent_name: 'sandbox' }
    }, msg)

    // 不应写入父气泡的 thinking / text
    expect(msg.thinking).toEqual([])
    expect(msg.text).toBe('')
    // timeline 长度不变（message 事件被跳过，不会新增 timeline 项）
    expect(msg.timeline.length).toBe(timelineLenBefore)
    // timeline 内不应出现子智能体 thinking 文本
    const subAgentLeak = msg.timeline.some(t => {
      if (typeof t.content === 'string') {
        return t.content.includes('工作目录是 /workspace')
      }
      return false
    })
    expect(subAgentLeak).toBe(false)
    expect(msg.isThinkingActive).toBe(false)
  })

  it('2026-06-14: message event from main thread still gets processed', () => {
    const msg = createAiMessage()
    // 父线程 message
    processSSEEvent({
      type: 'message',
      content: [{ type: 'text', text: '父线程输出' }],
      metadata: { thread_id: 'main_thread_xyz' }
    }, msg)

    expect(msg.threadId).toBe('main_thread_xyz')
    expect(msg.text).toBe('父线程输出')
    expect(msg.timeline.some(t => t.type === 'text')).toBe(true)
  })

  it('2026-06-14: aiMsg.threadId not polluted by subagent message arriving first', () => {
    const msg = createAiMessage()
    // 先注册 sandbox 子智能体
    processSSEEvent({
      type: 'custom',
      thread_id: 'call_sandbox_2',
      data: {
        type: 'tool_start',
        tool: 'sandbox',
        tool_call_id: 'call_sandbox_2',
        data: { parent_prompt: 'p' }
      }
    }, msg)

    // 子智能体先发 message（threadId 仍为空）
    processSSEEvent({
      type: 'message',
      content: [{ type: 'thinking', thinking: '子智能体 thinking' }],
      metadata: { thread_id: 'call_sandbox_2' }
    }, msg)

    // 父气泡 threadId 不应被子智能体的 threadId 污染
    expect(msg.threadId).toBe('')

    // 真正的父线程 message 到达时正确设置
    processSSEEvent({
      type: 'message',
      content: [{ type: 'text', text: '父线程' }],
      metadata: { thread_id: 'real_main' }
    }, msg)
    expect(msg.threadId).toBe('real_main')
    expect(msg.text).toBe('父线程')
  })

  it('2026-06-14: subagent message does not affect other subagents messages', () => {
    const msg = createAiMessage()
    // 注册两个子智能体
    processSSEEvent({
      type: 'custom', thread_id: 'sa_A', data: {
        type: 'tool_start', tool: 'sandbox', tool_call_id: 'sa_A',
        data: { parent_prompt: 'A 任务' }
      }
    }, msg)
    processSSEEvent({
      type: 'custom', thread_id: 'sa_B', data: {
        type: 'tool_start', tool: 'explore', tool_call_id: 'sa_B',
        data: { parent_prompt: 'B 任务' }
      }
    }, msg)
    // 给 A 累积一些子消息
    processSSEEvent({
      type: 'custom', thread_id: 'sa_A', data: {
        type: 'tool_progress', tool: 'sandbox', tool_call_id: 'sa_A',
        data: { child_messages: [
          { type: 'AIMessage', role: 'ai', content: [{ thinking: 'A 内部思考', type: 'thinking' }] }
        ] }
      }
    }, msg)

    const messagesBefore = msg.subAgents.find(s => s.toolCallId === 'sa_B').messages.length

    // A 子智能体发 message 事件
    processSSEEvent({
      type: 'message',
      content: [{ type: 'thinking', thinking: 'A 的 LLM 增量输出' }],
      metadata: { thread_id: 'sa_A' }
    }, msg)

    // 父气泡不应写入
    expect(msg.thinking).toEqual([])
    expect(msg.text).toBe('')
    // B 子智能体的 messages 不应被 A 的 message 影响
    const messagesAfter = msg.subAgents.find(s => s.toolCallId === 'sa_B').messages.length
    expect(messagesAfter).toBe(messagesBefore)
  })
})

describe('isSubAgentMessage 工具函数（2026-06-14 新增）', () => {
  it('returns true when eventThreadId matches any subAgent.threadId', () => {
    const aiMsg = {
      subAgents: [
        { toolCallId: 'a', threadId: 'thread_a' },
        { toolCallId: 'b', threadId: 'thread_b' }
      ]
    }
    expect(isSubAgentMessage(aiMsg, 'thread_a')).toBe(true)
    expect(isSubAgentMessage(aiMsg, 'thread_b')).toBe(true)
  })

  it('returns false when eventThreadId does not match', () => {
    const aiMsg = { subAgents: [{ toolCallId: 'a', threadId: 'thread_a' }] }
    expect(isSubAgentMessage(aiMsg, 'thread_other')).toBe(false)
  })

  it('returns false for null/undefined aiMsg', () => {
    expect(isSubAgentMessage(null, 'thread_a')).toBe(false)
    expect(isSubAgentMessage(undefined, 'thread_a')).toBe(false)
  })

  it('returns false when aiMsg.subAgents is not an array', () => {
    expect(isSubAgentMessage({}, 'thread_a')).toBe(false)
    expect(isSubAgentMessage({ subAgents: null }, 'thread_a')).toBe(false)
  })

  it('returns false for empty eventThreadId', () => {
    const aiMsg = { subAgents: [{ toolCallId: 'a', threadId: 'thread_a' }] }
    expect(isSubAgentMessage(aiMsg, '')).toBe(false)
    expect(isSubAgentMessage(aiMsg, null)).toBe(false)
    expect(isSubAgentMessage(aiMsg, undefined)).toBe(false)
  })

  it('returns false for empty subAgents', () => {
    expect(isSubAgentMessage({ subAgents: [] }, 'any')).toBe(false)
  })

  it('handles malformed subAgents entries gracefully', () => {
    const aiMsg = {
      subAgents: [null, undefined, { toolCallId: 'a', threadId: 'thread_a' }]
    }
    expect(isSubAgentMessage(aiMsg, 'thread_a')).toBe(true)
    expect(isSubAgentMessage(aiMsg, 'thread_b')).toBe(false)
  })
})
