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
 * 复刻 App.vue 的 handleStopMessage 行为（纯函数版，2026-07-06 重构）
 *
 * 与旧版（App.stop.spec.js）差异：
 *   - 加锁 toolStopPending = true（重复点击短路）
 *   - 调 triggerAbort 而非 reader.cancel（2026-07-06 重构）
 *   - 启动 60s 兜底 timer（2026-07-06 新增）
 *   - 不重置 isStreaming —— 由 SSE 事件流自然走完时复位
 *   - 文本标记从「[生成已被用户中止]」改为「[中断中，等待工具完成...]」
 *   - currentStreamReader 不再被清空（保留引用让 SSE 继续推完 tools 节点 chunk）
 *
 * Args:
 *   state: { isStreaming, toolStopPending, currentStreamReader, messages, triggerAbortFn, stopTimeoutMs }
 *
 * Returns: 修改后的 state
 */
async function handleStopMessage(state) {
  if (!state.isStreaming) return state
  // 重复点击短路（核心新逻辑）
  if (state.toolStopPending) return state

  // 加锁
  state.toolStopPending = true

  // 2026-07-06 改造：调 triggerAbort 而非 reader.cancel
  if (state.triggerAbortFn) {
    try {
      await state.triggerAbortFn()
    } catch (err) {
      // best-effort，失败时 60s 兜底 timer 兜底
    }
  }
  // 2026-07-06 新增：模拟启动 60s 兜底 timer（测试中不真正跑 60s，仅记录）
  state.stopTimeoutStarted = true

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
 * 白名单事件（2026-07-06 扩展）：
 *   - end: 工具完成 + 流走完
 *   - error: 错误收尾
 *   - interrupt: HITL 进入审批
 *   - tools 节点 update（含 ToolMessage）：abort 真正生效的信号
 *     data 格式：{ type: 'update', data: { tools: { messages: [ToolMessage, ...] } } }
 *
 * @param {object} data - SSE 事件数据
 * @returns {boolean}
 */
function shouldClearToolStopPending(data) {
  if (!data) return false
  if (data.type === 'end' || data.type === 'error' || data.type === 'interrupt') return true
  if (
    data.type === 'update' &&
    data.data &&
    typeof data.data === 'object' &&
    data.data.tools &&
    Array.isArray(data.data.tools.messages) &&
    data.data.tools.messages.length > 0
  ) {
    return true
  }
  return false
}

describe('App.vue toolStopPending 状态机（2026-07-06 新增）', () => {
  it('test_handleStopMessage_locks_toolStopPending 流式时点击 stop 加锁 toolStopPending', async () => {
    const cancelFn = vi.fn().mockResolvedValue(undefined)
    const triggerAbortFn = vi.fn().mockResolvedValue(undefined)
    const state = {
      isStreaming: true,
      toolStopPending: false,
      currentStreamReader: { cancel: cancelFn },
      triggerAbortFn,
      messages: [
        { id: 1, type: 'ai', text: 'partial', ended: false, isThinkingActive: true }
      ]
    }

    await handleStopMessage(state)

    // 加锁
    expect(state.toolStopPending).toBe(true)
    // 2026-07-06 改造：调 triggerAbort 而非 reader.cancel
    expect(triggerAbortFn).toHaveBeenCalledTimes(1)
    // reader.cancel 不应被调（避免立即断开 SSE）
    expect(cancelFn).not.toHaveBeenCalled()
    // currentStreamReader 不被立即清空（保留引用让 SSE 继续推完 tools 节点 chunk）
    expect(state.currentStreamReader).not.toBeNull()
    // isStreaming 不被立即重置（保留 stop-pending 期间 true）
    expect(state.isStreaming).toBe(true)
    // 60s 兜底 timer 启动
    expect(state.stopTimeoutStarted).toBe(true)
    // AI 消息 ended = true
    expect(state.messages[0].ended).toBe(true)
    expect(state.messages[0].isThinkingActive).toBe(false)
    // 文本标记改为「[中断中，等待工具完成...]」
    expect(state.messages[0].text).toContain('[中断中，等待工具完成...]')
    expect(state.messages[0].text).not.toContain('[生成已被用户中止]')
  })

  it('test_handleStopMessage_short_circuit_when_already_pending 重复点击短路', async () => {
    const cancelFn = vi.fn().mockResolvedValue(undefined)
    const triggerAbortFn = vi.fn().mockResolvedValue(undefined)
    const state = {
      isStreaming: true,
      toolStopPending: false,
      currentStreamReader: { cancel: cancelFn },
      triggerAbortFn,
      messages: [
        { id: 1, type: 'ai', text: 'partial', ended: false, isThinkingActive: true }
      ]
    }

    // 第一次点击：加锁 + 调 triggerAbort
    await handleStopMessage(state)
    expect(triggerAbortFn).toHaveBeenCalledTimes(1)
    expect(state.toolStopPending).toBe(true)

    // 第二次点击：短路（triggerAbort 不再被调）
    await handleStopMessage(state)
    expect(triggerAbortFn).toHaveBeenCalledTimes(1)  // 仍只调用一次
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
    const triggerAbortFn = vi.fn().mockResolvedValue(undefined)
    const state = {
      isStreaming: true,
      toolStopPending: false,
      currentStreamReader: { cancel: cancelFn },
      triggerAbortFn,
      messages: []
    }

    await expect(handleStopMessage(state)).resolves.toBeTruthy()
    // 2026-07-06 改造：调 triggerAbort 而非 reader.cancel
    expect(triggerAbortFn).toHaveBeenCalledTimes(1)
    expect(cancelFn).not.toHaveBeenCalled()
    expect(state.toolStopPending).toBe(true)
    expect(state.stopTimeoutStarted).toBe(true)
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

  // ===== 2026-07-06 新增：tools 节点 update 识别（abort 真正生效的信号） =====

  it('test_shouldClearToolStopPending_tools_update_event SSE tools 节点 update 含 ToolMessage 时清锁', () => {
    // 模拟 abort 真正生效：sandbox 工具主动 return ToolMessage 后，
    // LangGraph yield tools 节点 update，data.data.tools.messages 含 ToolMessage
    expect(shouldClearToolStopPending({
      type: 'update',
      data: { tools: { messages: [{ __class__: 'ToolMessage', tool_call_id: 'call_001' }] } }
    })).toBe(true)
  })

  it('test_shouldClearToolStopPending_tools_update_empty_messages tools 节点 update 但 messages 为空时不清锁', () => {
    // 防御：只有 messages 数组非空时才视为"工具完成"信号
    expect(shouldClearToolStopPending({
      type: 'update',
      data: { tools: { messages: [] } }
    })).toBe(false)
  })

  it('test_shouldClearToolStopPending_tools_update_missing_messages tools 节点 update 缺 messages 字段时不清锁', () => {
    expect(shouldClearToolStopPending({
      type: 'update',
      data: { tools: {} }
    })).toBe(false)
  })

  it('test_shouldClearToolStopPending_other_node_update llm_call 节点 update 不清锁', () => {
    // llm_call 节点 update 仍走流，不应立即清锁（等真正 end 事件）
    expect(shouldClearToolStopPending({
      type: 'update',
      data: { llm_call: { messages: [] } }
    })).toBe(false)
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
    const triggerAbortFn = vi.fn().mockResolvedValue(undefined)
    const state = {
      isStreaming: true,
      toolStopPending: false,
      currentStreamReader: { cancel: cancelFn },
      triggerAbortFn,
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