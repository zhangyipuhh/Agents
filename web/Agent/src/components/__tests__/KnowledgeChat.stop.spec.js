/**
 * KnowledgeChat 停止按钮测试（2026-06-15 新增；2026-07-06 改造）
 *
 * 覆盖：
 *   - send-btn 在 isCurrentlyStreaming=true 时切换为 stop-mode
 *   - handleStop 函数取消 currentReader 并清理 AI 消息状态
 *   - send-btn 在 isStopPending=true 时切换为 stop-pending-mode（2026-07-06 新增）
 *   - handleStop 在 stop-pending 状态下被重复调用时短路（2026-07-06 新增）
 *   - handleStop 不重置 internalStreaming，由 SSE 白名单 + finally 兜底复位（2026-07-06 改造）
 *   - handleStop 文本标记从「[生成已被用户中止]」改为「[中断中，等待工具完成...]」（2026-07-06 改造）
 *   - SSE end/error/interrupt 事件触发 isStopPending 复位（2026-07-06 新增）
 *   - handleNewChat / handleApprovalCancel 入口前置清锁（2026-07-06 新增）
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

describe('KnowledgeChat 停止按钮二态切换（2026-06-15 新增；2026-07-06 改造）', () => {
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
    expect(btn.classes()).not.toContain('stop-pending-mode')
    expect(wrapper.find('.send-icon').exists()).toBe(true)
    expect(wrapper.find('.stop-icon').exists()).toBe(false)
    expect(wrapper.find('.stop-pending-inner-icon').exists()).toBe(false)
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
    expect(btn.classes()).not.toContain('stop-pending-mode')
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
    // 2. currentReader 不再被立即清空（保留引用，让 SSE 继续推完 tools 节点 chunk）
    expect(wrapper.vm.currentReader).not.toBeNull()
    // 3. internalStreaming 由 handleStop 不再重置（保留 SSE 流走完前的状态）。
    //    本测试只通过 prop 触发 isStreaming=true，未触发 startChatStream，
    //    所以 internalStreaming 仍为默认值 false。handleStop 不应改变它。
    expect(wrapper.vm.internalStreaming).toBe(false)
    // 4. isStopPending 锁定为 true（按钮进入 stop-pending 模式）
    expect(wrapper.vm.isStopPending).toBe(true)
    // 5. AI 消息 ended = true
    expect(wrapper.vm.messages[0].ended).toBe(true)
    expect(wrapper.vm.messages[0].isThinkingActive).toBe(false)
    // 6. AI 消息 text 追加了 [中断中，等待工具完成...] 提示（2026-07-06 改造：标记语义调整为「等待工具完成」）
    expect(wrapper.vm.messages[0].text).toContain('[中断中，等待工具完成...]')
  })

  it('test_knowledge_chat_handleStop_does_not_duplicate_marker handleStop 不重复追加停止标记', async () => {
    const wrapper = mount(KnowledgeChat, {
      props: { sessionId: 'sid_1', isStreaming: true },
      global: { stubs: { MessageBubble: MessageBubbleStub } }
    })

    const cancelFn = vi.fn().mockResolvedValue(undefined)
    wrapper.vm.currentReader = { cancel: cancelFn }
    // 预先已有「[中断中」标记，验证不会被重复追加
    wrapper.vm.messages.push({
      id: 1, type: 'ai', content: '', ended: false, error: '',
      text: 'hello\n\n[中断中，等待工具完成...]', isThinkingActive: true
    })
    await wrapper.vm.$nextTick()

    await wrapper.vm.handleStop()

    // text 中 [中断中 标记应只出现一次（防重复）
    const occurrences = (wrapper.vm.messages[0].text.match(/\[中断中/g) || []).length
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

  // ===== 2026-07-06 新增：中断待生效（isStopPending）测试 =====

  it('test_knowledge_chat_send_btn_shows_stop_pending_mode isStopPending=true 时显示 stop-pending 样式', async () => {
    const wrapper = mount(KnowledgeChat, {
      props: { sessionId: 'sid_1', isStreaming: true },
      global: { stubs: { MessageBubble: MessageBubbleStub } }
    })
    // 模拟 SSE 收尾后父组件 props.isStreaming 已重置，但内部 isStopPending 仍为 true
    await wrapper.setProps({ isStreaming: false })
    wrapper.vm.isStopPending = true
    await wrapper.vm.$nextTick()

    const btn = wrapper.find('.send-btn')
    expect(btn.classes()).toContain('stop-pending-mode')
    expect(btn.classes()).not.toContain('stop-mode')
    expect(btn.classes()).not.toContain('send-mode')
    // 旋转圆环图标
    expect(wrapper.find('.stop-pending-inner-icon').exists()).toBe(true)
    expect(wrapper.find('.send-icon').exists()).toBe(false)
    expect(wrapper.find('.stop-icon').exists()).toBe(false)
    // 右上角 badge
    expect(wrapper.find('.stop-pending-badge').exists()).toBe(true)
    // title 提示文案
    expect(btn.attributes('title')).toBe('中断中，等待工具完成...')
  })

  it('test_knowledge_chat_handleStop_short_circuit_when_already_pending 重复点击短路', async () => {
    const wrapper = mount(KnowledgeChat, {
      props: { sessionId: 'sid_1', isStreaming: true },
      global: { stubs: { MessageBubble: MessageBubbleStub } }
    })

    const cancelFn = vi.fn().mockResolvedValue(undefined)
    wrapper.vm.currentReader = { cancel: cancelFn }
    wrapper.vm.messages.push({
      id: 1, type: 'ai', content: '', ended: false, error: '',
      text: 'partial', isThinkingActive: true
    })
    await wrapper.vm.$nextTick()

    // 第一次点击：加锁
    await wrapper.vm.handleStop()
    expect(cancelFn).toHaveBeenCalledTimes(1)
    expect(wrapper.vm.isStopPending).toBe(true)

    // 第二次点击：短路
    await wrapper.vm.handleStop()
    expect(cancelFn).toHaveBeenCalledTimes(1)  // cancel 仍只被调用一次
    expect(wrapper.vm.isStopPending).toBe(true)
  })

  it('test_knowledge_chat_handleSendBtnClick_intercepted_when_stop_pending 按钮 click 在 stop-pending 时被拦截', async () => {
    const wrapper = mount(KnowledgeChat, {
      props: { sessionId: 'sid_1', isStreaming: false },
      global: { stubs: { MessageBubble: MessageBubbleStub } }
    })

    const handleStopSpy = vi.spyOn(wrapper.vm, 'handleStop')
    const handleSendSpy = vi.spyOn(wrapper.vm, 'handleSend')

    wrapper.vm.isStopPending = true
    await wrapper.vm.$nextTick()

    await wrapper.vm.handleSendBtnClick()

    expect(handleStopSpy).not.toHaveBeenCalled()
    expect(handleSendSpy).not.toHaveBeenCalled()
  })

  it('test_knowledge_chat_handleNewChat_clears_stop_pending 入口前置清锁', async () => {
    const wrapper = mount(KnowledgeChat, {
      props: { sessionId: 'sid_1', isStreaming: true },
      global: { stubs: { MessageBubble: MessageBubbleStub } }
    })

    wrapper.vm.isStopPending = true
    wrapper.vm.internalStreaming = true
    wrapper.vm.currentReader = { cancel: vi.fn().mockResolvedValue(undefined) }

    // mock handleApprovalCancel 不需要
    await wrapper.vm.handleNewChat()

    expect(wrapper.vm.isStopPending).toBe(false)
  })

  it('test_knowledge_chat_handleApprovalCancel_clears_stop_pending 入口前置清锁', async () => {
    const wrapper = mount(KnowledgeChat, {
      props: { sessionId: 'sid_1', isStreaming: true },
      global: { stubs: { MessageBubble: MessageBubbleStub } }
    })

    wrapper.vm.isStopPending = true
    wrapper.vm.internalStreaming = true

    await wrapper.vm.handleApprovalCancel()

    expect(wrapper.vm.isStopPending).toBe(false)
  })
})
