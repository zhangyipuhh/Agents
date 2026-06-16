/**
 * sseParser.js 子智能体历史恢复辅助函数测试（2026-06-16 新增）
 *
 * 覆盖：
 *   - isSubAgentHistoryItem 识别后端 history 元素
 *   - convertSubAgentHistoryToAiSubAgent 转换为前端 subAgent 格式
 *   - 字段映射（thread_id / tool / parent_message_id / messages）
 *   - 边界（缺字段、非 subagent type、空 thread_id）
 */
import { describe, it, expect } from 'vitest'
import {
  isSubAgentHistoryItem,
  convertSubAgentHistoryToAiSubAgent
} from '../sseParser.js'

describe('isSubAgentHistoryItem（2026-06-16 新增）', () => {
  it('识别 { type: "subagent", thread_id: "..." }', () => {
    expect(
      isSubAgentHistoryItem({ type: 'subagent', thread_id: 'call_001' })
    ).toBe(true)
  })

  it('含 messages 字段时仍识别', () => {
    expect(
      isSubAgentHistoryItem({
        type: 'subagent',
        thread_id: 'call_001',
        messages: []
      })
    ).toBe(true)
  })

  it('type 缺失时不识别', () => {
    expect(isSubAgentHistoryItem({ thread_id: 'call_001' })).toBe(false)
  })

  it('type 非 subagent 时不识别（user/ai/tool 均不识别）', () => {
    expect(isSubAgentHistoryItem({ type: 'user', content: 'hi' })).toBe(false)
    expect(isSubAgentHistoryItem({ type: 'ai', content: 'hi' })).toBe(false)
    expect(isSubAgentHistoryItem({ type: 'tool', content: '...' })).toBe(false)
  })

  it('thread_id 缺失时不识别', () => {
    expect(isSubAgentHistoryItem({ type: 'subagent' })).toBe(false)
    expect(isSubAgentHistoryItem({ type: 'subagent', thread_id: '' })).toBe(
      false
    )
  })

  it('null/undefined/非对象输入安全降级', () => {
    expect(isSubAgentHistoryItem(null)).toBe(false)
    expect(isSubAgentHistoryItem(undefined)).toBe(false)
    expect(isSubAgentHistoryItem('not an object')).toBe(false)
    expect(isSubAgentHistoryItem(123)).toBe(false)
  })
})

describe('convertSubAgentHistoryToAiSubAgent（2026-06-16 新增）', () => {
  it('完整字段映射', () => {
    const msg = {
      type: 'subagent',
      thread_id: 'call_001',
      tool: 'sandbox',
      parent_message_id: 'ai-msg-1',
      parent_prompt: '执行沙箱',
      messages: [
        { type: 'HumanMessage', role: 'user', content: 'sub prompt' },
        { type: 'AIMessage', role: 'ai', content: 'sub reply' }
      ],
      status: 'success',
      start_time: 1700000000000,
      end_time: 1700000001000
    }
    const result = convertSubAgentHistoryToAiSubAgent(msg)
    expect(result).toEqual({
      toolCallId: 'call_001',
      threadId: 'call_001',
      tool: 'sandbox',
      parentPrompt: '执行沙箱',
      parentMessageId: 'ai-msg-1',
      messages: [
        { type: 'HumanMessage', role: 'user', content: 'sub prompt' },
        { type: 'AIMessage', role: 'ai', content: 'sub reply' }
      ],
      events: [],
      summary: null,
      status: 'success',
      startTime: 1700000000000,
      endTime: 1700000001000,
      error: null,
      isHistory: true
    })
  })

  it('status 缺失时默认 success（向后兼容）', () => {
    const result = convertSubAgentHistoryToAiSubAgent({
      type: 'subagent',
      thread_id: 'call_x',
      tool: 'explore',
      messages: []
    })
    expect(result.status).toBe('success')
  })

  it('messages 缺失时默认为空数组', () => {
    const result = convertSubAgentHistoryToAiSubAgent({
      type: 'subagent',
      thread_id: 'call_x',
      tool: 'sandbox'
    })
    expect(result.messages).toEqual([])
  })

  it('兼容 tool_call_id 作为 thread_id 回退（防御性）', () => {
    // 如果后端某天改用 tool_call_id 字段，保持兼容
    const result = convertSubAgentHistoryToAiSubAgent({
      type: 'subagent',
      tool_call_id: 'call_legacy',
      tool: 'sandbox'
    })
    expect(result.toolCallId).toBe('call_legacy')
    expect(result.threadId).toBe('call_legacy')
  })

  it('type 非 subagent 时返回 null', () => {
    expect(
      convertSubAgentHistoryToAiSubAgent({ type: 'user', content: 'x' })
    ).toBeNull()
  })

  it('thread_id 与 tool_call_id 均缺失时返回 null', () => {
    expect(
      convertSubAgentHistoryToAiSubAgent({ type: 'subagent', tool: 'sandbox' })
    ).toBeNull()
  })

  it('isHistory 字段恒为 true 便于前端识别来源', () => {
    const result = convertSubAgentHistoryToAiSubAgent({
      type: 'subagent',
      thread_id: 'a',
      tool: 'sandbox'
    })
    expect(result.isHistory).toBe(true)
  })

  it('向 MessageBubble 提供可被 toolCallId 索引的字段', () => {
    // 关键：转换结果必须含 toolCallId 字段，以便 MessageBubble.subAgentMap
    // 在 timeline.tool 块内按 toolCallId O(1) 匹配
    const result = convertSubAgentHistoryToAiSubAgent({
      type: 'subagent',
      thread_id: 'tc_xyz',
      tool: 'sandbox'
    })
    expect(result.toolCallId).toBe('tc_xyz')
  })
})

describe('与现有 isSubAgentTool 集成（2026-06-16 新增）', () => {
  it('convertSubAgentHistoryToAiSubAgent 输出的 tool 名可被 isSubAgentTool 识别', async () => {
    const { isSubAgentTool } = await import('../sseParser.js')
    const result = convertSubAgentHistoryToAiSubAgent({
      type: 'subagent',
      thread_id: 'a',
      tool: 'sandbox'
    })
    expect(isSubAgentTool(result.tool)).toBe(true)
  })
})
