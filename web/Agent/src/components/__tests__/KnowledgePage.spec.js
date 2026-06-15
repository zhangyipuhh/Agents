# -*- coding:utf-8 -*-
/**
 * KnowledgePage 组件测试（2026-06-15 新增）
 *
 * 覆盖：KnowledgePage 把 KnowledgeChat 的 open-subagent-drawer 事件向上冒泡，
 *      最终触发 App.vue 顶层 <SubAgentDrawer> 打开。
 *
 * 测试策略：mount + stub KnowledgeChat 子组件，直接模拟其 emit。
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import KnowledgePage from '../KnowledgePage.vue'

describe('KnowledgePage 子智能体事件透传（2026-06-15 新增）', () => {
  it('test_knowledge_page_importable 组件可被 import', () => {
    expect(KnowledgePage).toBeDefined()
  })

  it('test_knowledge_page_emits_open_subagent_drawer_from_chat KnowledgeChat emit 向上冒泡', async () => {
    const fakeSubAgent = {
      toolCallId: 'tc_test_2',
      threadId: 'tc_test_2',
      tool: 'explore',
      parentPrompt: 'p',
      messages: [],
      events: [],
      status: 'running',
      startTime: Date.now(),
      endTime: null,
      error: null
    }
    const wrapper = mount(KnowledgePage, {
      global: {
        stubs: {
          FileList: { template: '<div class="file-list-stub" />' },
          FilePreview: { template: '<div class="file-preview-stub" />' }
        }
      }
    })
    const chat = wrapper.findComponent({ name: 'KnowledgeChat' })
    expect(chat.exists()).toBe(true)
    // 模拟 KnowledgeChat 触发 open-subagent-drawer
    await chat.vm.$emit('open-subagent-drawer', fakeSubAgent)
    // KnowledgePage 应向上冒泡该事件
    expect(wrapper.emitted('open-subagent-drawer')).toBeTruthy()
    expect(wrapper.emitted('open-subagent-drawer')[0][0]).toEqual(fakeSubAgent)
  })
})