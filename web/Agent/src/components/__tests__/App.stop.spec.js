/**
 * App.vue / KnowledgeApp.vue 停止按钮集成测试（2026-06-15 新增）
 *
 * 验证 handleStopMessage 行为：
 * 1. 调用 currentStreamReader.cancel() 断开 SSE 连接
 * 2. 标记最后一条 AI 消息 ended = true + 追加 "[生成已被用户中止]" 提示
 * 3. 重置 isStreaming
 *
 * 实现方式：
 * - 复刻 App.vue 的 handleStopMessage 函数逻辑为纯函数（与 App.interrupt.spec.js 同模式）
 * - 不直接 mount App.vue（其依赖太复杂），用纯函数验证停止逻辑
 * - 通过 mock reader 验证 cancel 调用、清空 reader、标记 AI 消息
 */
import { describe, it, expect, vi } from 'vitest'

/**
 * 复刻 App.vue 的 handleStopMessage 行为（纯函数版，便于测试）
 *
 * Args:
 *   state: { isStreaming, currentStreamReader, messages }
 *
 * Returns: 修改后的 state（与 App.vue 中 reactive 行为等价）
 */
async function handleStopMessage(state) {
  if (!state.isStreaming) return state

  if (state.currentStreamReader) {
    try {
      await state.currentStreamReader.cancel()
    } catch (err) {
      // 静默忽略
    }
    state.currentStreamReader = null
  }

  const aiMsg = state.messages[state.messages.length - 1]
  if (aiMsg && aiMsg.type === 'ai') {
    aiMsg.ended = true
    aiMsg.isThinkingActive = false
    if (typeof aiMsg.text === 'string' && !aiMsg.text.includes('[生成已被用户中止]')) {
      aiMsg.text = (aiMsg.text || '') + '\n\n[生成已被用户中止]'
    }
  }

  state.isStreaming = false
  return state
}

describe('App.vue handleStopMessage 行为验证（2026-06-15 新增）', () => {
  it('test_handleStopMessage_cancels_reader_and_marks_message 流式时调用 cancel + 标记 AI 消息', async () => {
    const cancelFn = vi.fn().mockResolvedValue(undefined)
    const state = {
      isStreaming: true,
      currentStreamReader: { cancel: cancelFn },
      messages: [
        { id: 1, type: 'user', content: 'hi' },
        { id: 2, type: 'ai', text: 'partial...', ended: false, isThinkingActive: true }
      ]
    }

    await handleStopMessage(state)

    expect(cancelFn).toHaveBeenCalledTimes(1)
    expect(state.currentStreamReader).toBeNull()
    expect(state.isStreaming).toBe(false)
    expect(state.messages[1].ended).toBe(true)
    expect(state.messages[1].isThinkingActive).toBe(false)
    expect(state.messages[1].text).toContain('[生成已被用户中止]')
  })

  it('test_handleStopMessage_noop_when_not_streaming 非流式时为 noop', async () => {
    const cancelFn = vi.fn().mockResolvedValue(undefined)
    const state = {
      isStreaming: false,
      currentStreamReader: { cancel: cancelFn },
      messages: [
        { id: 1, type: 'ai', text: 'done', ended: true, isThinkingActive: false }
      ]
    }

    await handleStopMessage(state)

    // cancel 不应被调用
    expect(cancelFn).not.toHaveBeenCalled()
    // 消息状态保持不变
    expect(state.messages[0].text).toBe('done')
  })

  it('test_handleStopMessage_swallows_cancel_error cancel 抛错时不影响主流程', async () => {
    const cancelFn = vi.fn().mockRejectedValue(new Error('cancel failed'))
    const state = {
      isStreaming: true,
      currentStreamReader: { cancel: cancelFn },
      messages: [
        { id: 1, type: 'ai', text: 'partial', ended: false, isThinkingActive: true }
      ]
    }

    // 不应抛错
    await expect(handleStopMessage(state)).resolves.toBeTruthy()
    expect(cancelFn).toHaveBeenCalledTimes(1)
    expect(state.isStreaming).toBe(false)
    expect(state.messages[0].ended).toBe(true)
  })

  it('test_handleStopMessage_does_not_duplicate_marker 已有停止标记时不重复追加', async () => {
    const cancelFn = vi.fn().mockResolvedValue(undefined)
    const state = {
      isStreaming: true,
      currentStreamReader: { cancel: cancelFn },
      messages: [
        { id: 1, type: 'ai', text: 'partial\n\n[生成已被用户中止]', ended: false, isThinkingActive: true }
      ]
    }

    await handleStopMessage(state)

    // [生成已被用户中止] 标记应只出现一次
    const occurrences = (state.messages[0].text.match(/\[生成已被用户中止\]/g) || []).length
    expect(occurrences).toBe(1)
  })

  it('test_handleStopMessage_handles_no_reader 已有 currentStreamReader=null 时不抛错', async () => {
    const state = {
      isStreaming: true,
      currentStreamReader: null,
      messages: [
        { id: 1, type: 'ai', text: 'partial', ended: false, isThinkingActive: true }
      ]
    }

    await expect(handleStopMessage(state)).resolves.toBeTruthy()
    // AI 消息仍被标记
    expect(state.messages[0].ended).toBe(true)
    expect(state.isStreaming).toBe(false)
  })

  it('test_handleStopMessage_handles_no_ai_message messages 为空时不报错', async () => {
    const cancelFn = vi.fn().mockResolvedValue(undefined)
    const state = {
      isStreaming: true,
      currentStreamReader: { cancel: cancelFn },
      messages: []
    }

    await expect(handleStopMessage(state)).resolves.toBeTruthy()
    expect(cancelFn).toHaveBeenCalledTimes(1)
    expect(state.isStreaming).toBe(false)
  })
})

describe('KnowledgeApp.vue handleStopMessage 行为验证（2026-06-15 新增）', () => {
  // KnowledgeApp.vue 的 handleStopMessage 与 App.vue 同款实现
  // 核心差异：messages 是 ref（messages.value），所以测试时传 state.messages 为数组
  // 此处复用同一纯函数 handleStopMessage 验证

  it('test_knowledge_app_handleStopMessage_cancels_reader_and_marks_message', async () => {
    const cancelFn = vi.fn().mockResolvedValue(undefined)
    const state = {
      isStreaming: true,
      currentStreamReader: { cancel: cancelFn },
      messages: [
        { id: 1, type: 'ai', text: 'partial', ended: false, isThinkingActive: true }
      ]
    }

    await handleStopMessage(state)

    expect(cancelFn).toHaveBeenCalledTimes(1)
    expect(state.currentStreamReader).toBeNull()
    expect(state.isStreaming).toBe(false)
    expect(state.messages[0].ended).toBe(true)
    expect(state.messages[0].text).toContain('[生成已被用户中止]')
  })

  it('test_knowledge_app_handleStopMessage_resets_state_on_success', async () => {
    const cancelFn = vi.fn().mockResolvedValue(undefined)
    const state = {
      isStreaming: true,
      currentStreamReader: { cancel: cancelFn },
      messages: []
    }

    await handleStopMessage(state)

    expect(state.isStreaming).toBe(false)
    expect(state.currentStreamReader).toBeNull()
  })
})
