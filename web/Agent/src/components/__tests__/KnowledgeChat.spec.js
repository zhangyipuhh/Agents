/**
 * KnowledgeChat 组件测试（2026-06-15 新增）
 *
 * 覆盖：KnowledgeChat 把 subAgents / downloadInfo 透传给 MessageBubble，
 *      并把 MessageBubble 的 open-subagent-drawer 事件向上 emit。
 *
 * 测试策略：mount + stub MessageBubble 子组件（template 内暴露所有 props 为可见 DOM），
 *          通过 DOM 查询验证 prop 透传 + emit 冒泡。
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import KnowledgeChat from '../KnowledgeChat.vue'

// 把 MessageBubble stub 化，把所有接收到的 props 渲染到 DOM 上，便于断言
const MessageBubbleStub = {
  props: [
    'type', 'content', 'attachments', 'timeline', 'thinking', 'tools', 'text',
    'ended', 'error', 'messageId', 'isThinkingActive', 'downloadInfo', 'subAgents'
  ],
  emits: ['open-subagent-drawer'],
  template: `
    <div class="message-bubble-stub">
      <span class="prop-sub-agents">{{ JSON.stringify(subAgents) }}</span>
      <span class="prop-download-info">{{ JSON.stringify(downloadInfo) }}</span>
      <button class="emit-open" @click="$emit('open-subagent-drawer', subAgents[0])">emit</button>
    </div>
  `
}

describe('KnowledgeChat 子智能体能力透传（2026-06-15 新增）', () => {
  it('test_knowledge_chat_importable 组件可被 import', () => {
    expect(KnowledgeChat).toBeDefined()
  })

  it('test_knowledge_chat_passes_sub_agents_to_message_bubble 透传 subAgents prop', () => {
    const subAgents = [{
      toolCallId: 'tc_test_1',
      threadId: 'tc_test_1',
      tool: 'explore',
      parentPrompt: '查询土地管理法相关内容',
      messages: [],
      events: [],
      status: 'running',
      startTime: 1,
      endTime: null,
      error: null
    }]
    const aiMessage = {
      id: 1,
      type: 'ai',
      content: '',
      attachments: [],
      timeline: [],
      thinking: [],
      tools: [],
      text: '',
      ended: false,
      error: '',
      messageId: 1,
      isThinkingActive: true,
      subAgents,
      downloadInfo: null
    }
    const wrapper = mount(KnowledgeChat, {
      props: { messages: [aiMessage], sessionId: 'sid_1', isStreaming: true },
      global: {
        stubs: { MessageBubble: MessageBubbleStub }
      }
    })
    // MessageBubble stub 应在 DOM 中
    const stub = wrapper.find('.message-bubble-stub')
    expect(stub.exists()).toBe(true)
    // 断言 subAgents 已透传到 MessageBubble
    const subText = stub.find('.prop-sub-agents').text()
    expect(JSON.parse(subText)).toEqual(subAgents)
  })

  it('test_knowledge_chat_passes_download_info_to_message_bubble 透传 downloadInfo prop', () => {
    const downloadInfo = {
      downloadUrl: '/api/core/download/file?file_uuid=abc',
      fileName: '报告.pdf'
    }
    const aiMessage = {
      id: 2,
      type: 'ai',
      content: '',
      attachments: [],
      timeline: [],
      thinking: [],
      tools: [],
      text: '',
      ended: true,
      error: '',
      messageId: 2,
      isThinkingActive: false,
      subAgents: [],
      downloadInfo
    }
    const wrapper = mount(KnowledgeChat, {
      props: { messages: [aiMessage], sessionId: 'sid_1', isStreaming: false },
      global: {
        stubs: { MessageBubble: MessageBubbleStub }
      }
    })
    const stub = wrapper.find('.message-bubble-stub')
    expect(stub.exists()).toBe(true)
    const dlText = stub.find('.prop-download-info').text()
    expect(JSON.parse(dlText)).toEqual(downloadInfo)
  })

  it('test_knowledge_chat_emits_open_subagent_drawer_on_subagent_click 转发 open-subagent-drawer 事件', async () => {
    const subAgents = [{
      toolCallId: 'tc_test_1',
      threadId: 'tc_test_1',
      tool: 'explore',
      parentPrompt: 'p',
      messages: [],
      events: [],
      status: 'running',
      startTime: 1,
      endTime: null,
      error: null
    }]
    const aiMessage = {
      id: 3,
      type: 'ai',
      content: '',
      attachments: [],
      timeline: [],
      thinking: [],
      tools: [],
      text: '',
      ended: false,
      error: '',
      messageId: 3,
      isThinkingActive: true,
      subAgents,
      downloadInfo: null
    }
    const wrapper = mount(KnowledgeChat, {
      props: { messages: [aiMessage], sessionId: 'sid_1', isStreaming: true },
      global: {
        stubs: { MessageBubble: MessageBubbleStub }
      }
    })
    expect(wrapper.find('.message-bubble-stub').exists()).toBe(true)
    // 点击 stub 内的 emit 按钮 → MessageBubble 触发 open-subagent-drawer
    await wrapper.find('.message-bubble-stub .emit-open').trigger('click')
    // KnowledgeChat 应向上冒泡该事件
    expect(wrapper.emitted('open-subagent-drawer')).toBeTruthy()
    expect(wrapper.emitted('open-subagent-drawer')[0][0]).toEqual(subAgents[0])
  })
})