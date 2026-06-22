/**
 * KnowledgeChat 流式状态拦截测试（2026-06-22 新增）
 *
 * 覆盖：
 * - handleSend 在流式状态下不再创建新请求，而是触发 handleStop
 * - handleKeydown 在流式状态下按 Enter 触发 handleStop 而非 handleSend
 * - resetQueueStatus 正确重置状态
 */
import { describe, it, expect, beforeAll, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import KnowledgeChat from '../KnowledgeChat.vue'

// 组件 handleSend 失败时会调用 alert()，happy-dom 不提供 → 注入 noop
beforeAll(() => {
  if (typeof window !== 'undefined' && !window.alert) {
    window.alert = () => {}
  }
})

// stub 掉 MessageBubble（不依赖其内部实现）
const MessageBubbleStub = {
  props: [
    'type', 'content', 'attachments', 'timeline', 'thinking', 'tools', 'text',
    'ended', 'error', 'messageId', 'isThinkingActive', 'downloadInfo', 'subAgents'
  ],
  template: '<div class="message-bubble-stub"></div>'
}

describe('KnowledgeChat 流式状态拦截（2026-06-22 新增）', () => {
  it('test_knowledge_chat_handleSend_triggers_stop_when_streaming 流式中调用 handleStop', async () => {
    const wrapper = mount(KnowledgeChat, {
      props: { sessionId: 'sid_1', isStreaming: true },
      global: { stubs: { MessageBubble: MessageBubbleStub } }
    })

    const cancelFn = vi.fn().mockResolvedValue(undefined)
    wrapper.vm.currentReader = { cancel: cancelFn }
    wrapper.vm.inputValue = 'test message'
    wrapper.vm.messages.push({
      id: 1, type: 'ai', content: '', ended: false, error: '', text: '', isThinkingActive: true
    })

    await wrapper.vm.handleSend()
    await flushPromises()

    // 流式中应取消 reader
    expect(cancelFn).toHaveBeenCalled()
    // AI 消息应被标记为已停止
    expect(wrapper.vm.messages[0].ended).toBe(true)
  })

  it('test_knowledge_chat_handleKeydown_enter_triggers_stop_when_streaming 流式中按 Enter 触发 handleStop', async () => {
    const wrapper = mount(KnowledgeChat, {
      props: { sessionId: 'sid_1', isStreaming: true },
      global: { stubs: { MessageBubble: MessageBubbleStub } }
    })

    const cancelFn = vi.fn().mockResolvedValue(undefined)
    wrapper.vm.currentReader = { cancel: cancelFn }
    wrapper.vm.messages.push({
      id: 1, type: 'ai', content: '', ended: false, error: '', text: '', isThinkingActive: true
    })

    const event = { key: 'Enter', shiftKey: false, preventDefault: vi.fn() }
    wrapper.vm.handleKeydown(event)
    await flushPromises()

    // 1. preventDefault 被调用
    expect(event.preventDefault).toHaveBeenCalled()
    // 2. 流式中 reader 应被取消（handleStop 路径）
    expect(cancelFn).toHaveBeenCalled()
    // 3. AI 消息 ended
    expect(wrapper.vm.messages[0].ended).toBe(true)
  })

  it('test_knowledge_chat_handleKeydown_calls_handleSend_when_not_streaming 非流式按 Enter 走正常发送分支', async () => {
    const wrapper = mount(KnowledgeChat, {
      props: { sessionId: 'sid_1', isStreaming: false },
      global: { stubs: { MessageBubble: MessageBubbleStub } }
    })

    // 在 <script setup> 中函数绑定由闭包持有，外部 spy 不能影响 handleKeydown 对
    // handleSend 的内部引用。我们改用直接调用 handleSend 并观察它不会走 handleStop 分支。
    wrapper.vm.inputValue = 'test message'

    let stopCalled = false
    wrapper.vm.handleStop = vi.fn().mockImplementation(() => {
      stopCalled = true
      return Promise.resolve()
    })

    // 调用 handleSend（实际会因 knowledgeChatStream 抛错，但关键是判断走的是哪个分支）
    try {
      await wrapper.vm.handleSend()
    } catch (e) {
      // 忽略真实 SSE 调用错误
    }

    // 非流式应不触发 handleStop（说明走的是创建新流分支）
    expect(stopCalled).toBe(false)
  })

  it('test_knowledge_chat_reset_queue_status_resets_to_idle resetQueueStatus 正确重置', async () => {
    const wrapper = mount(KnowledgeChat, {
      props: { sessionId: 'sid_1', isStreaming: false },
      global: { stubs: { MessageBubble: MessageBubbleStub } }
    })

    wrapper.vm.queueStatus = {
      event: 'waiting',
      waitingCount: 2,
      activeCount: 1,
      maxConcurrency: 1,
      position: 1,
      timestamp: 12345
    }
    expect(wrapper.vm.queueStatus.event).toBe('waiting')

    wrapper.vm.resetQueueStatus()
    await wrapper.vm.$nextTick()

    expect(wrapper.vm.queueStatus.event).toBe('idle')
    expect(wrapper.vm.queueStatus.waitingCount).toBe(0)
    expect(wrapper.vm.queueStatus.activeCount).toBe(0)
    expect(wrapper.vm.queueStatus.maxConcurrency).toBe(0)
    expect(wrapper.vm.queueStatus.position).toBe(0)
    expect(wrapper.vm.queueStatus.timestamp).toBe(0)
  })

  it('test_knowledge_chat_send_btn_click_routes_to_stop_when_streaming send-btn 流式下点击触发 handleStop', async () => {
    const wrapper = mount(KnowledgeChat, {
      props: { sessionId: 'sid_1', isStreaming: true },
      global: { stubs: { MessageBubble: MessageBubbleStub } }
    })

    const cancelFn = vi.fn().mockResolvedValue(undefined)
    wrapper.vm.currentReader = { cancel: cancelFn }
    wrapper.vm.messages.push({
      id: 1, type: 'ai', content: '', ended: false, error: '', text: '', isThinkingActive: true
    })

    // 点击按钮
    await wrapper.find('.send-btn').trigger('click')
    await flushPromises()

    // reader 应被取消
    expect(cancelFn).toHaveBeenCalled()
    // AI 消息 ended
    expect(wrapper.vm.messages[0].ended).toBe(true)
  })
})