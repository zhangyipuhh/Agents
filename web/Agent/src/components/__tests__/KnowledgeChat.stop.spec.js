/**
 * KnowledgeChat 停止按钮测试（2026-06-15 新增）
 *
 * 覆盖：KnowledgeChat 的 send-btn 在 isCurrentlyStreaming=true 时切换为 stop-mode，
 *      handleStop 函数取消 currentReader 并清理 AI 消息状态。
 */
import { describe, it, expect, beforeAll, vi } from 'vitest'
import { mount } from '@vue/test-utils'
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

describe('KnowledgeChat 停止按钮二态切换（2026-06-15 新增）', () => {
  it('test_knowledge_chat_importable 组件可被 import', () => {
    expect(KnowledgeChat).toBeDefined()
  })

  it('test_knowledge_chat_send_btn_shows_send_mode_when_not_streaming 默认显示发送按钮', () => {
    const wrapper = mount(KnowledgeChat, {
      props: { sessionId: 'sid_1', isStreaming: false },
      global: { stubs: { MessageBubble: MessageBubbleStub } }
    })
    const btn = wrapper.find('.send-btn')
    expect(btn.exists()).toBe(true)
    expect(btn.classes()).toContain('send-mode')
    expect(btn.classes()).not.toContain('stop-mode')
    expect(wrapper.find('.send-icon').exists()).toBe(true)
    expect(wrapper.find('.stop-icon').exists()).toBe(false)
    expect(btn.attributes('title')).toBe('发送消息')
  })

  it('test_knowledge_chat_send_btn_shows_stop_mode_when_internal_streaming 内部流式时显示停止按钮', async () => {
    const wrapper = mount(KnowledgeChat, {
      props: { sessionId: 'sid_1', isStreaming: false },
      global: { stubs: { MessageBubble: MessageBubbleStub } }
    })
    // 通过 prop 触发 isCurrentlyStreaming 计算
    await wrapper.setProps({ isStreaming: true })
    const btn = wrapper.find('.send-btn')
    expect(btn.exists()).toBe(true)
    expect(btn.classes()).toContain('stop-mode')
    expect(btn.classes()).not.toContain('send-mode')
    expect(wrapper.find('.stop-icon').exists()).toBe(true)
    expect(wrapper.find('.send-icon').exists()).toBe(false)
    expect(btn.attributes('title')).toBe('停止生成')
  })

  it('test_knowledge_chat_handleStop_cancels_reader_and_marks_message handleStop 取消 reader 并标记 AI 消息', async () => {
    const wrapper = mount(KnowledgeChat, {
      props: { sessionId: 'sid_1', isStreaming: true },
      global: { stubs: { MessageBubble: MessageBubbleStub } }
    })

    // stub currentReader 为 mock 对象（带 cancel 方法）
    const cancelFn = vi.fn().mockResolvedValue(undefined)
    wrapper.vm.currentReader = { cancel: cancelFn }

    // 注入 AI 消息（模拟流式中）
    wrapper.vm.messages.push({
      id: 1, type: 'ai', content: 'partial response...',
      ended: false, error: '', text: 'partial response...', isThinkingActive: true
    })
    await wrapper.vm.$nextTick()

    // 调用 handleStop
    await wrapper.vm.handleStop()

    // 1. currentReader.cancel 被调用
    expect(cancelFn).toHaveBeenCalledTimes(1)
    // 2. currentReader 被清空
    expect(wrapper.vm.currentReader).toBeNull()
    // 3. internalStreaming 被重置
    expect(wrapper.vm.internalStreaming).toBe(false)
    // 4. AI 消息 ended = true
    expect(wrapper.vm.messages[0].ended).toBe(true)
    expect(wrapper.vm.messages[0].isThinkingActive).toBe(false)
    // 5. AI 消息 text 追加了 [生成已被用户中止] 提示
    expect(wrapper.vm.messages[0].text).toContain('[生成已被用户中止]')
  })

  it('test_knowledge_chat_handleStop_does_not_duplicate_marker handleStop 不重复追加停止标记', async () => {
    const wrapper = mount(KnowledgeChat, {
      props: { sessionId: 'sid_1', isStreaming: true },
      global: { stubs: { MessageBubble: MessageBubbleStub } }
    })

    const cancelFn = vi.fn().mockResolvedValue(undefined)
    wrapper.vm.currentReader = { cancel: cancelFn }
    wrapper.vm.messages.push({
      id: 1, type: 'ai', content: '', ended: false, error: '',
      text: 'hello\n\n[生成已被用户中止]', isThinkingActive: true
    })
    await wrapper.vm.$nextTick()

    await wrapper.vm.handleStop()

    // text 中 [生成已被用户中止] 标记应只出现一次（防重复）
    const occurrences = (wrapper.vm.messages[0].text.match(/\[生成已被用户中止\]/g) || []).length
    expect(occurrences).toBe(1)
  })

  it('test_knowledge_chat_handleStop_noop_when_not_streaming handleStop 在非流式时为 noop', async () => {
    const wrapper = mount(KnowledgeChat, {
      props: { sessionId: 'sid_1', isStreaming: false },
      global: { stubs: { MessageBubble: MessageBubbleStub } }
    })
    const cancelFn = vi.fn().mockResolvedValue(undefined)
    wrapper.vm.currentReader = { cancel: cancelFn }
    // 调用 handleStop 但 isCurrentlyStreaming 为 false
    await wrapper.vm.handleStop()
    // cancel 不应被调用
    expect(cancelFn).not.toHaveBeenCalled()
  })
})
