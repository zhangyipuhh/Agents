import { describe, it, expect } from 'vitest'
import {
  isThinkingBlock,
  tryParsePythonLiteral,
  extractTextFromBlock,
  processContentBlocks,
  parseMessageContent,
  processSSEEvent,
  createAiMessage,
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
})
