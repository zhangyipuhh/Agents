/**
 * App.vue 中断待生效（toolStopPending）测试（2026-07-06 新增）
 *
 * 复刻 App.vue 的 toolStopPending 状态机 + handleStopMessage + SSE 白名单复位 + finally 兜底复位
 * 为纯函数版本，便于在隔离环境下验证关键逻辑。
 *
 * 设计要点：
 *   - 与 App.stop.spec.js 互补：stop.spec.js 验证旧行为（reset isStreaming 立即生效），
 *     本文件验证新行为（toolStopPending 锁定 + SSE 事件白名单复位 + catch/finally 兜底）
 *   - 状态机：
 *     置 true：handleStopMessage（重复点击短路）
 *     置 false（白名单）：SSE end/error/interrupt 事件；SSE 流自然走完（done=true）
 *     置 false（兜底）：catch（异常）、finally（任何路径兜底）、newSession/handleSessionSwitch/handleApprovalCancel/handleStopMessage 入口前置
 *
 * Date: 2026-07-06
 */
import { describe, it, expect, vi } from 'vitest'

/**
 * 复刻 App.vue 的 handleStopMessage 行为（纯函数版）
 *
 * 与旧版（App.stop.spec.js）差异：
 *   - 加锁 toolStopPending = true（重复点击短路）
 *   - 不重置 isStreaming —— 由 SSE 事件流自然走完时复位
 *   - 文本标记从「[生成已被用户中止]」改为「[中断中，等待工具完成...]」
 *   - 不再清空 currentStreamReader（保留引用让 SSE 继续推完 tools 节点 chunk）
 *
 * Args:
 *   state: { isStreaming, toolStopPending, currentStreamReader, messages }
 *
 * Returns: 修改后的 state
 */
async function handleStopMessage(state) {
  if (!state.isStreaming) return state
  // 重复点击短路（核心新逻辑）
  if (state.toolStopPending) return state

  // 加锁
  state.toolStopPending = true

  // 取消 SSE reader（不置 null）
  if (state.currentStreamReader) {
    try {
      await state.currentStreamReader.cancel()
    } catch (err) {
      // 静默忽略
    }
  }

  // 标记 AI 消息为「中断中」状态
  const aiMsg = state.messages[state.messages.length - 1]
  if (aiMsg && aiMsg.type === 'ai') {
    aiMsg.ended = true
    aiMsg.isThinkingActive = false
    if (typeof aiMsg.text === 'string' && !aiMsg.text.includes('[中断中')) {
      aiMsg.text = (aiMsg.text || '') + '\n\n[中断中，等待工具完成...]'
    }
  }

  // 不重置 isStreaming —— 由 SSE 流自然走完时复位
  return state
}

/**
 * 复刻 App.vue::clearToolStopPending 纯函数版
 * @param {object} state
 */
function clearToolStopPending(state) {
  state.toolStopPending = false
}

/**
 * 复刻 App.vue SSE while 循环白名单复位逻辑（纯函数版）
 * 接收单个 SSE 事件，返回是否应该清锁
 *
 * @param {object} data - SSE 事件数据 { type: 'end' | 'error' | 'interrupt' | ... }
 * @returns {boolean}
 */
function shouldClearToolStopPending(data) {
  return !!(data && (data.type === 'end' || data.type === 'error' || data.type === 'interrupt'))
}

describe('App.vue toolStopPending 状态机（2026-07-06 新增）', () => {
  it('test_handleStopMessage_locks_toolStopPending 流式时点击 stop 加锁 toolStopPending', async () => {
    const cancelFn = vi.fn().mockResolvedValue(undefined)
    const state = {
      isStreaming: true,
      toolStopPending: false,
      currentStreamReader: { cancel: cancelFn },
      messages: [
        { id: 1, type: 'ai', text: 'partial', ended: false, isThinkingActive: true }
      ]
    }

    await handleStopMessage(state)

    // 加锁
    expect(state.toolStopPending).toBe(true)
    // cancel 被调用
    expect(cancelFn).toHaveBeenCalledTimes(1)
    // currentStreamReader 不被立即清空（保留引用）
    expect(state.currentStreamReader).not.toBeNull()
    // isStreaming 不被立即重置（保留 stop-pending 期间 true）
    expect(state.isStreaming).toBe(true)
    // AI 消息 ended = true
    expect(state.messages[0].ended).toBe(true)
    expect(state.messages[0].isThinkingActive).toBe(false)
    // 文本标记改为「[中断中，等待工具完成...]」
    expect(state.messages[0].text).toContain('[中断中，等待工具完成...]')
    expect(state.messages[0].text).not.toContain('[生成已被用户中止]')
  })

  it('test_handleStopMessage_short_circuit_when_already_pending 重复点击短路', async () => {
    const cancelFn = vi.fn().mockResolvedValue(undefined)
    const state = {
      isStreaming: true,
      toolStopPending: false,
      currentStreamReader: { cancel: cancelFn },
      messages: [
        { id: 1, type: 'ai', text: 'partial', ended: false, isThinkingActive: true }
      ]
    }

    // 第一次点击：加锁
    await handleStopMessage(state)
    expect(cancelFn).toHaveBeenCalledTimes(1)
    expect(state.toolStopPending).toBe(true)

    // 第二次点击：短路
    await handleStopMessage(state)
    expect(cancelFn).toHaveBeenCalledTimes(1)  // cancel 仍只被调用一次
    expect(state.toolStopPending).toBe(true)
  })

  it('test_handleStopMessage_noop_when_not_streaming 非流式时为 noop', async () => {
    const cancelFn = vi.fn().mockResolvedValue(undefined)
    const state = {
      isStreaming: false,
      toolStopPending: false,
      currentStreamReader: { cancel: cancelFn },
      messages: []
    }

    await handleStopMessage(state)

    expect(cancelFn).not.toHaveBeenCalled()
    expect(state.toolStopPending).toBe(false)
  })

  it('test_handleStopMessage_does_not_duplicate_marker 已有中断中标记时不重复追加', async () => {
    const cancelFn = vi.fn().mockResolvedValue(undefined)
    const state = {
      isStreaming: true,
      toolStopPending: false,
      currentStreamReader: { cancel: cancelFn },
      messages: [
        { id: 1, type: 'ai', text: 'partial\n\n[中断中，等待工具完成...]', ended: false, isThinkingActive: true }
      ]
    }

    await handleStopMessage(state)

    // [中断中 标记应只出现一次
    const occurrences = (state.messages[0].text.match(/\[中断中/g) || []).length
    expect(occurrences).toBe(1)
  })

  it('test_handleStopMessage_swallows_cancel_error cancel 抛错时不影响加锁主流程', async () => {
    const cancelFn = vi.fn().mockRejectedValue(new Error('cancel failed'))
    const state = {
      isStreaming: true,
      toolStopPending: false,
      currentStreamReader: { cancel: cancelFn },
      messages: [
        { id: 1, type: 'ai', text: 'partial', ended: false, isThinkingActive: true }
      ]
    }

    await expect(handleStopMessage(state)).resolves.toBeTruthy()
    expect(state.toolStopPending).toBe(true)
    expect(state.messages[0].ended).toBe(true)
  })

  it('test_handleStopMessage_handles_no_ai_message messages 为空时不报错', async () => {
    const cancelFn = vi.fn().mockResolvedValue(undefined)
    const state = {
      isStreaming: true,
      toolStopPending: false,
      currentStreamReader: { cancel: cancelFn },
      messages: []
    }

    await expect(handleStopMessage(state)).resolves.toBeTruthy()
    expect(cancelFn).toHaveBeenCalledTimes(1)
    expect(state.toolStopPending).toBe(true)
    // isStreaming 保持
    expect(state.isStreaming).toBe(true)
  })

  it('test_handleStopMessage_handles_no_reader currentStreamReader=null 时不抛错', async () => {
    const state = {
      isStreaming: true,
      toolStopPending: false,
      currentStreamReader: null,
      messages: [
        { id: 1, type: 'ai', text: 'partial', ended: false, isThinkingActive: true }
      ]
    }

    await expect(handleStopMessage(state)).resolves.toBeTruthy()
    // AI 消息仍被标记 + 加锁
    expect(state.messages[0].ended).toBe(true)
    expect(state.toolStopPending).toBe(true)
  })
})

describe('App.vue toolStopPending 白名单复位（2026-07-06 新增）', () => {
  it('test_shouldClearToolStopPending_end_event SSE end 事件清锁', () => {
    expect(shouldClearToolStopPending({ type: 'end' })).toBe(true)
  })

  it('test_shouldClearToolStopPending_error_event SSE error 事件清锁', () => {
    expect(shouldClearToolStopPending({ type: 'error', message: 'oops' })).toBe(true)
  })

  it('test_shouldClearToolStopPending_interrupt_event SSE interrupt 事件清锁', () => {
    expect(shouldClearToolStopPending({ type: 'interrupt', data: { requests: [] } })).toBe(true)
  })

  it('test_shouldClearToolStopPending_message_event SSE message 事件不清锁', () => {
    expect(shouldClearToolStopPending({ type: 'message', content: 'token' })).toBe(false)
  })

  it('test_shouldClearToolStopPending_update_event SSE update 事件不清锁（只 update 本身）', () => {
    expect(shouldClearToolStopPending({ type: 'update', data: {} })).toBe(false)
  })

  it('test_shouldClearToolStopPending_custom_event SSE custom 事件不清锁', () => {
    expect(shouldClearToolStopPending({ type: 'custom', data: { tool: 'sandbox' } })).toBe(false)
  })

  it('test_shouldClearToolStopPending_null_event SSE null 不清锁', () => {
    expect(shouldClearToolStopPending(null)).toBe(false)
    expect(shouldClearToolStopPending(undefined)).toBe(false)
  })
})

describe('App.vue toolStopPending 兜底复位（2026-07-06 新增）', () => {
  it('test_clearToolStopPending_works 直接调用清锁函数', () => {
    const state = { toolStopPending: true }
    clearToolStopPending(state)
    expect(state.toolStopPending).toBe(false)
  })

  it('test_clearToolStopPending_idempotent 重复调用幂等', () => {
    const state = { toolStopPending: true }
    clearToolStopPending(state)
    clearToolStopPending(state)
    expect(state.toolStopPending).toBe(false)
  })

  it('test_clearToolStopPending_on_already_false 已是 false 时调用无副作用', () => {
    const state = { toolStopPending: false }
    clearToolStopPending(state)
    expect(state.toolStopPending).toBe(false)
  })
})

describe('App.vue toolStopPending 综合场景（2026-07-06 新增）', () => {
  it('test_full_workflow_pending_then_end 用户点 stop → 工具完成 → SSE end 复位', async () => {
    const cancelFn = vi.fn().mockResolvedValue(undefined)
    const state = {
      isStreaming: true,
      toolStopPending: false,
      currentStreamReader: { cancel: cancelFn },
      messages: [
        { id: 1, type: 'ai', text: 'partial', ended: false, isThinkingActive: true }
      ]
    }

    // Step 1: 用户点击停止按钮
    await handleStopMessage(state)
    expect(state.toolStopPending).toBe(true)
    expect(state.isStreaming).toBe(true)

    // Step 2: 模拟 SSE 流继续推完当前 tools 节点，最终推送 end 事件
    const endEvent = { type: 'end' }
    if (shouldClearToolStopPending(endEvent)) {
      clearToolStopPending(state)
    }
    // 模拟 SSE done → isStreaming 由外层代码重置为 false
    state.isStreaming = false

    expect(state.toolStopPending).toBe(false)
    expect(state.isStreaming).toBe(false)
  })

  it('test_full_workflow_pending_then_error 用户点 stop → 错误 → SSE error 复位', async () => {
    const cancelFn = vi.fn().mockResolvedValue(undefined)
    const state = {
      isStreaming: true,
      toolStopPending: false,
      currentStreamReader: { cancel: cancelFn },
      messages: [
        { id: 1, type: 'ai', text: 'partial', ended: false, isThinkingActive: true }
      ]
    }

    await handleStopMessage(state)
    expect(state.toolStopPending).toBe(true)

    // 模拟 SSE error 事件
    const errorEvent = { type: 'error', message: 'stream error' }
    if (shouldClearToolStopPending(errorEvent)) {
      clearToolStopPending(state)
    }
    state.isStreaming = false

    expect(state.toolStopPending).toBe(false)
    expect(state.isStreaming).toBe(false)
  })

  it('test_full_workflow_pending_then_interrupt HITL 中断场景', async () => {
    const cancelFn = vi.fn().mockResolvedValue(undefined)
    const state = {
      isStreaming: true,
      toolStopPending: false,
      currentStreamReader: { cancel: cancelFn },
      messages: [
        { id: 1, type: 'ai', text: 'partial', ended: false, isThinkingActive: true }
      ]
    }

    await handleStopMessage(state)
    expect(state.toolStopPending).toBe(true)

    // 模拟 HITL interrupt 事件
    const interruptEvent = { type: 'interrupt', data: { requests: [{ action: 'ask_user_question' }] } }
    if (shouldClearToolStopPending(interruptEvent)) {
      clearToolStopPending(state)
    }

    expect(state.toolStopPending).toBe(false)
  })

  it('test_full_workflow_pending_then_newsession 用户点 stop → 立即 newSession 兜底清锁', async () => {
    const cancelFn = vi.fn().mockResolvedValue(undefined)
    const state = {
      isStreaming: true,
      toolStopPending: true,  // 用户已点 stop
      currentStreamReader: { cancel: cancelFn },
      messages: [
        { id: 1, type: 'ai', text: 'partial', ended: false, isThinkingActive: true }
      ]
    }

    // 模拟 newSession 入口前置清锁（兜底层）
    clearToolStopPending(state)
    state.isStreaming = false

    expect(state.toolStopPending).toBe(false)
    expect(state.isStreaming).toBe(false)
  })
})