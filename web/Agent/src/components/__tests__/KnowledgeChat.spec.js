# -*- coding:utf-8 -*-
/**
 * KnowledgeChat 组件测试（2026-06-15 新增）
 *
 * 覆盖：KnowledgeChat 把 subAgents / downloadInfo 透传给 MessageBubble，
 *      并把 MessageBubble 的 open-subagent-drawer 事件向上 emit。
 *
 * 测试策略：使用 @vue/test-utils 的 mount + stub MessageBubble 子组件，
 *          通过断言 stub 接收到的 props 与 wrapper.emitted() 来验证透传与冒泡。
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import KnowledgeChat from '../KnowledgeChat.vue'

const makeSubAgent = () => ({
  toolCallId: 'tc_test_1',
  threadId: 'tc_test_1',
  tool: 'explore',
  parentPrompt: '查询土地管理法相关内容',
  messages: [],
  events: [],
  status: 'running',
  startTime: Date.now(),
  endTime: null,
  error: null
})

describe('KnowledgeChat 子智能体能力透传（2026-06-15 新增）', () => {
  it('test_knowledge_chat_importable 组件可被 import', () => {
    expect(KnowledgeChat).toBeDefined()
  })

  it('test_knowledge_chat_passes_sub_agents_to_message_bubble 透传 subAgents prop', () => {
    const subAgents = [makeSubAgent()]
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
      props: { messages: [aiMessage], sessionId: 'sid_1', isStreaming: true }
    })
    // 子组件 MessageBubble 应接收到 subAgents prop
    const bubble = wrapper.findComponent({ name: 'MessageBubble' })
    expect(bubble.exists()).toBe(true)
    expect(bubble.props('subAgents')).toEqual(subAgents)
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
      props: { messages: [aiMessage], sessionId: 'sid_1', isStreaming: false }
    })
    const bubble = wrapper.findComponent({ name: 'MessageBubble' })
    expect(bubble.exists()).toBe(true)
    expect(bubble.props('downloadInfo')).toEqual(downloadInfo)
  })

  it('test_knowledge_chat_emits_open_subagent_drawer_on_subagent_click 转发 open-subagent-drawer 事件', async () => {
    const subAgents = [makeSubAgent()]
    const aiMessage = {
      id: 3,
      type: 'ai',
      content: '',
      attachments: [],
      timeline: [
        {
          type: 'tool',
          content: {
            type: 'custom',
            data: { type: 'tool_start', tool: 'explore', tool_call_id: 'tc_test_1', data: {} }
          }
        }
      ],
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
      props: { messages: [aiMessage], sessionId: 'sid_1', isStreaming: true }
    })
    const bubble = wrapper.findComponent({ name: 'MessageBubble' })
    expect(bubble.exists()).toBe(true)
    // 模拟点击 SubAgentCard → MessageBubble 触发 open-subagent-drawer 事件
    await bubble.vm.$emit('open-subagent-drawer', subAgents[0])
    // KnowledgeChat 应向上冒泡该事件
    expect(wrapper.emitted('open-subagent-drawer')).toBeTruthy()
    expect(wrapper.emitted('open-subagent-drawer')[0][0]).toEqual(subAgents[0])
  })
})