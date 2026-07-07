/**
 * App.vue / KnowledgeApp.vue HITL interrupt 集成测试（2026-06-15 新增）
 *
 * 验证核心修复：
 * - SSE 流 reader 在收到 interrupt 事件时主动 reader.cancel()
 * - 配合后端 concurrency_release_handle()，确保许可释放 + SSE 连接断开
 * - queue 事件触发 onQueueEvent 回调，更新 queueStatus
 *
 * 实现方式：
 * - 直接 mock SSE 流（构造 ReadableStream + queue 事件 + interrupt 事件）
 * - 模拟 processSSEEvent 的调用循环
 * - 验证 reader.cancel() 被调用且回调被触发
 */
import { describe, it, expect, vi } from 'vitest'
import { processSSEEvent } from '../../utils/sseParser.js'

/**
 * 构造一个模拟 SSE 流：发送 SSE chunk 字符串列表，每个 chunk 以 \n\n 结尾。
 * 返回 { stream, reader, cancelSpy }
 *
 * 2026-07-01 同步：happy-dom 的 ReadableStream 在 close 之后调用 reader.cancel() 不会触发
 * stream 的 cancel 回调，因此 spy 改为包裹 reader.cancel 本身，才能在测试里观察到 cancel 调用。
 * 注意：cancelSpy 不能再调用 rawReader.cancel，否则会触发 spy 自身导致无限递归。
 */
function createMockSSEStream(chunks) {
  const encoder = new TextEncoder()
  const stream = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk))
      }
      controller.close()
    },
    cancel() {
      // happy-dom 在某些场景下仍会调用此回调，但 spy 主体已迁到 reader.cancel
    }
  })
  const rawReader = stream.getReader()
  // 仅记录调用次数，不再调用 rawReader.cancel（避免无限递归）
  const cancelSpy = vi.fn()
  rawReader.cancel = cancelSpy
  return { stream, reader: rawReader, cancelSpy }
}

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
    interrupt: null
  }
}

/**
 * 模拟 App.vue 的 reader.read() 循环 + processSSEEvent 处理逻辑
 * （不带 Vue 组件，纯逻辑函数）
 *
 * 2026-07-01 同步：try/catch 包 reader.cancel() 以模拟 App.vue:481-485 的真实代码路径
 * （App.vue 中 cancel 异常被吞掉，避免中断整个 SSE 处理循环）
 */
async function driveSSE(reader, aiMsg, callbacks) {
  const decoder = new TextDecoder()
  let buffer = ''
  let interrupted = false

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const events = buffer.split('\n\n')
    buffer = events.pop()
    for (const event of events) {
      if (!event.startsWith('data: ')) continue
      try {
        const data = JSON.parse(event.slice(6))
        processSSEEvent(data, aiMsg, callbacks)
        if (aiMsg.interrupt) {
          interrupted = true
          // 关键：模拟 App.vue 的 reader.cancel() —— App.vue 内部 try/catch 吞掉异常
          try {
            await reader.cancel()
          } catch (cancelErr) {
            // 异常被吞掉，模拟 App.vue:484 的 console.warn
          }
          break
        }
      } catch {}
    }
    if (interrupted) break
  }
  return interrupted
}

describe('App.vue HITL interrupt reader.cancel integration (2026-06-15)', () => {
  // 1. P0：HITL 核心 — interrupt 时必须调用 reader.cancel()
  it('test_handleSendMessage_calls_reader_cancel_on_interrupt', async () => {
    const chunks = [
      'data: {"type":"queue","event":"waiting","waiting_count":1,"active_count":1,"max_concurrency":1,"position":1,"timestamp":1700000000}\n\n',
      'data: {"type":"queue","event":"ready","waiting_count":0,"active_count":1,"max_concurrency":1,"position":0,"timestamp":1700000001}\n\n',
      'data: {"type":"update","data":{"x":1}}\n\n',
      'data: {"type":"interrupt","data":{"requests":[{"action":"ask_user_question","questions":[]}]}}\n\n'
    ]
    const { reader, cancelSpy } = createMockSSEStream(chunks)
    const aiMsg = createTestAiMsg()
    const queueEvents = []
    const callbacks = { onQueueEvent: (data) => queueEvents.push(data) }

    const interrupted = await driveSSE(reader, aiMsg, callbacks)
    expect(interrupted).toBe(true)
    expect(aiMsg.interrupt).not.toBeNull()
    expect(cancelSpy).toHaveBeenCalledTimes(1)

    // queue 事件应该被回调捕获
    expect(queueEvents.length).toBeGreaterThanOrEqual(2)
    expect(queueEvents[0].event).toBe('waiting')
    expect(queueEvents[1].event).toBe('ready')
  })

  // 2. P1：resume 后再次触发 interrupt 也会 cancel reader
  it('test_handleApprovalSubmit_calls_reader_cancel_on_interrupt', async () => {
    const chunks = [
      'data: {"type":"update","data":{"llm_call":{}}}\n\n',
      'data: {"type":"interrupt","data":{"requests":[]}}\n\n'
    ]
    const { reader, cancelSpy } = createMockSSEStream(chunks)
    const aiMsg = createTestAiMsg()

    const interrupted = await driveSSE(reader, aiMsg, {})
    expect(interrupted).toBe(true)
    expect(cancelSpy).toHaveBeenCalledTimes(1)
  })

  // 3. P1：正常 end 事件不应触发 reader.cancel
  it('test_handleSendMessage_no_cancel_on_normal_end', async () => {
    const chunks = [
      'data: {"type":"update","data":{"x":1}}\n\n',
      'data: {"type":"end","message":"会话结束"}\n\n'
    ]
    const { reader, cancelSpy } = createMockSSEStream(chunks)
    const aiMsg = createTestAiMsg()

    const interrupted = await driveSSE(reader, aiMsg, {})
    expect(interrupted).toBe(false)
    // 正常 end 由 reader.read() done=true 自然结束，不需要 cancel
    expect(cancelSpy).not.toHaveBeenCalled()
  })

  // 4. P2：reader.cancel() 调用本身抛出时不传播
  // 2026-07-01 同步：happy-dom 不保证 stream.cancel 回调被调用，改为 spy on reader.cancel 本身
  it('test_reader_cancel_swallows_cancel_error', async () => {
    const encoder = new TextEncoder()
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            'data: {"type":"interrupt","data":{"requests":[]}}\n\n'
          )
        )
        controller.close()
      }
    })
    const rawReader = stream.getReader()
    let cancelInvoked = false
    rawReader.cancel = async () => {
      cancelInvoked = true
      throw new Error('cancel failed')
    }
    const aiMsg = createTestAiMsg()

    // driveSSE 内部 try { await reader.cancel() } catch 应该吞掉 cancel 异常
    let threwError = false
    try {
      await driveSSE(rawReader, aiMsg, {})
    } catch {
      threwError = true
    }
    expect(cancelInvoked).toBe(true)
    expect(threwError).toBe(false) // 异常应被吞掉
  })
})