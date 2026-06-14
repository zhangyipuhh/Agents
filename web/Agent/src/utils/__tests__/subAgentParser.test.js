/**
 * sseParser subagent 解析单测（2026-06-13 新增，2026-06-14 改造）
 *
 * 覆盖：
 *   - createAiMessage 初始化 subAgents: []（2026-06-14 移除 sandboxExecution 字段）
 *   - processSSEEvent 处理 custom 事件时维护 subAgents 列表
 *   - updateSubAgentFromCustomEvent 内部工具的状态推进
 *   - getSubAgentById / formatSubAgentDuration / getSubAgentMeta 工具函数
 *   - 2026-06-14 改造：sandbox_summary 持久化到 subAgent.summary
 *   - 2026-06-14 改造：final_summary 在 tool_stop 时合并到 subAgent.summary
 */
import { describe, it, expect, beforeEach } from 'vitest'
import {
  processSSEEvent,
  createAiMessage,
  getSubAgentById,
  formatSubAgentDuration,
  getSubAgentMeta
} from '../sseParser.js'

describe('sseParser subagent 解析', () => {
  let aiMsg

  beforeEach(() => {
    aiMsg = createAiMessage()
  })

  it('createAiMessage 初始化 subAgents 为空数组且不包含 sandboxExecution', () => {
    expect(Array.isArray(aiMsg.subAgents)).toBe(true)
    expect(aiMsg.subAgents).toEqual([])
    // 2026-06-14 改造：sandboxExecution 字段已移除
    expect(aiMsg.sandboxExecution).toBeUndefined()
  })

  it('tool_start 自定义事件应创建 subagent 条目', () => {
    processSSEEvent({
      type: 'custom',
      thread_id: 'call_123',
      data: {
        type: 'tool_start',
        tool: 'sandbox',
        tool_call_id: 'call_123',
        data: {
          parent_prompt: '在沙箱里计算 1+1'
        }
      }
    }, aiMsg)

    expect(aiMsg.subAgents).toHaveLength(1)
    const sa = aiMsg.subAgents[0]
    expect(sa.toolCallId).toBe('call_123')
    expect(sa.threadId).toBe('call_123')
    expect(sa.tool).toBe('sandbox')
    expect(sa.parentPrompt).toBe('在沙箱里计算 1+1')
    expect(sa.status).toBe('running')
    expect(Array.isArray(sa.messages)).toBe(true)
  })

  it('tool_progress 自定义事件应累计 child_messages', () => {
    // 先 start
    processSSEEvent({
      type: 'custom',
      thread_id: 'call_1',
      data: {
        type: 'tool_start',
        tool: 'sandbox',
        tool_call_id: 'call_1',
        data: { parent_prompt: 'test' }
      }
    }, aiMsg)

    // 再 progress
    processSSEEvent({
      type: 'custom',
      thread_id: 'call_1',
      data: {
        type: 'tool_progress',
        tool: 'sandbox',
        tool_call_id: 'call_1',
        data: {
          child_messages: [
            { type: 'HumanMessage', role: 'user', content: 'calc 1+1' },
            { type: 'AIMessage', role: 'ai', content: 'thinking...' }
          ]
        }
      }
    }, aiMsg)

    const sa = aiMsg.subAgents[0]
    expect(sa.messages).toHaveLength(2)
    expect(sa.messages[0].role).toBe('user')
    expect(sa.messages[1].role).toBe('ai')
  })

  it('tool_stop 自定义事件应标记 success 并覆盖 messages', () => {
    processSSEEvent({
      type: 'custom',
      thread_id: 'call_2',
      data: {
        type: 'tool_start',
        tool: 'explore',
        tool_call_id: 'call_2',
        data: { parent_prompt: 'find readme' }
      }
    }, aiMsg)

    processSSEEvent({
      type: 'custom',
      thread_id: 'call_2',
      data: {
        type: 'tool_stop',
        tool: 'explore',
        tool_call_id: 'call_2',
        data: {
          final_messages: [
            { type: 'HumanMessage', role: 'user', content: 'q' },
            { type: 'AIMessage', role: 'ai', content: 'a' }
          ]
        }
      }
    }, aiMsg)

    const sa = aiMsg.subAgents[0]
    expect(sa.status).toBe('success')
    expect(sa.endTime).toBeGreaterThan(0)
    expect(sa.messages).toHaveLength(2)
  })

  it('tool_error 自定义事件应标记 error 并记录错误信息', () => {
    processSSEEvent({
      type: 'custom',
      thread_id: 'call_3',
      data: {
        type: 'tool_start',
        tool: 'sandbox',
        tool_call_id: 'call_3',
        data: { parent_prompt: 'broken' }
      }
    }, aiMsg)

    processSSEEvent({
      type: 'custom',
      thread_id: 'call_3',
      data: {
        type: 'tool_error',
        tool: 'sandbox',
        tool_call_id: 'call_3',
        data: {
          error_type: 'RuntimeError',
          error_message: 'docker not running'
        }
      }
    }, aiMsg)

    const sa = aiMsg.subAgents[0]
    expect(sa.status).toBe('error')
    expect(sa.error).toContain('RuntimeError')
    expect(sa.error).toContain('docker not running')
  })

  it('tool_call_id 缺失但顶层 thread_id 存在时仍可建立条目', () => {
    processSSEEvent({
      type: 'custom',
      thread_id: 'top_thread_x',
      data: {
        type: 'tool_start',
        tool: 'sandbox',
        data: { parent_prompt: 'p' }
      }
    }, aiMsg)

    expect(aiMsg.subAgents).toHaveLength(1)
    expect(aiMsg.subAgents[0].toolCallId).toBe('top_thread_x')
  })

  it('多次 subagent 调用应并存为多条目', () => {
    processSSEEvent({
      type: 'custom', thread_id: 'c1', data: {
        type: 'tool_start', tool: 'sandbox', tool_call_id: 'c1',
        data: { parent_prompt: 'p1' }
      }
    }, aiMsg)
    processSSEEvent({
      type: 'custom', thread_id: 'c2', data: {
        type: 'tool_start', tool: 'explore', tool_call_id: 'c2',
        data: { parent_prompt: 'p2' }
      }
    }, aiMsg)

    expect(aiMsg.subAgents).toHaveLength(2)
    expect(aiMsg.subAgents.map(s => s.tool).sort()).toEqual(['explore', 'sandbox'])
  })

  // ========== 2026-06-14 改造：summary 字段持久化 ==========

  it('tool_progress 携带 sandbox_summary 时合并到 subAgent.summary', () => {
    processSSEEvent({
      type: 'custom', thread_id: 's1', data: {
        type: 'tool_start', tool: 'sandbox', tool_call_id: 's1',
        data: { parent_prompt: 'p' }
      }
    }, aiMsg)

    processSSEEvent({
      type: 'custom', thread_id: 's1', data: {
        type: 'tool_progress', tool: 'sandbox', tool_call_id: 's1',
        data: {
          sandbox_summary: {
            progress_pct: 40,
            current_step: 2,
            total_steps: 5,
            elapsed_ms: 3000
          }
        }
      }
    }, aiMsg)

    const sa = aiMsg.subAgents[0]
    expect(sa.summary).toBeTruthy()
    expect(sa.summary.progress_pct).toBe(40)
    expect(sa.summary.current_step).toBe(2)
    expect(sa.summary.total_steps).toBe(5)
  })

  it('tool_stop 携带 final_summary 时合并到 subAgent.summary（最终态）', () => {
    processSSEEvent({
      type: 'custom', thread_id: 's2', data: {
        type: 'tool_start', tool: 'sandbox', tool_call_id: 's2',
        data: { parent_prompt: 'p' }
      }
    }, aiMsg)

    // 进度阶段先来一次
    processSSEEvent({
      type: 'custom', thread_id: 's2', data: {
        type: 'tool_progress', tool: 'sandbox', tool_call_id: 's2',
        data: {
          sandbox_summary: {
            progress_pct: 60,
            current_step: 3,
            total_steps: 5,
            elapsed_ms: 5000
          }
        }
      }
    }, aiMsg)

    // 结束时带 final_summary
    processSSEEvent({
      type: 'custom', thread_id: 's2', data: {
        type: 'tool_stop', tool: 'sandbox', tool_call_id: 's2',
        data: {
          status: 'success',
          final_summary: {
            progress_pct: 100,
            current_step: 5,
            elapsed_ms: 10000,
            status_message: '执行完成'
          }
        }
      }
    }, aiMsg)

    const sa = aiMsg.subAgents[0]
    expect(sa.status).toBe('success')
    expect(sa.summary.progress_pct).toBe(100)
    expect(sa.summary.current_step).toBe(5)
    expect(sa.summary.total_steps).toBe(5)  // 保留 progress 阶段的字段
    expect(sa.summary.status_message).toBe('执行完成')
  })
})

describe('sseParser subagent 工具函数', () => {
  it('getSubAgentById 返回匹配的 subagent', () => {
    const aiMsg = {
      subAgents: [
        { toolCallId: 'a', tool: 'sandbox' },
        { toolCallId: 'b', tool: 'explore' }
      ]
    }
    expect(getSubAgentById(aiMsg, 'a').tool).toBe('sandbox')
    expect(getSubAgentById(aiMsg, 'b').tool).toBe('explore')
    expect(getSubAgentById(aiMsg, 'c')).toBeNull()
    expect(getSubAgentById(null, 'a')).toBeNull()
  })

  it('formatSubAgentDuration 格式化毫秒', () => {
    expect(formatSubAgentDuration(500)).toBe('500ms')
    expect(formatSubAgentDuration(1500)).toBe('1.5s')
    expect(formatSubAgentDuration(65000)).toBe('1分5秒')
    expect(formatSubAgentDuration(0)).toBe('')
    expect(formatSubAgentDuration(-1)).toBe('')
  })

  it('getSubAgentMeta 返回已知/未知工具的元信息', () => {
    expect(getSubAgentMeta('sandbox')).toEqual({ icon: '📦', label: '沙箱执行' })
    expect(getSubAgentMeta('explore')).toEqual({ icon: '🔍', label: '文件探索' })
    expect(getSubAgentMeta('unknown_tool').label).toBe('unknown_tool')
    expect(getSubAgentMeta(null).icon).toBe('🤖')
  })
})
