/**
 * KnowledgeApp 组件测试（2026-06-15 新增）
 *
 * 覆盖：KnowledgeApp 作为独立 SPA，自持子智能体详情抽屉状态：
 *   - subAgentDrawerVisible / currentSubAgent 状态
 *   - openSubAgentDrawer / closeSubAgentDrawer 切换
 *   - <SubAgentDrawer> 渲染与事件绑定
 *
 * 测试策略：mount + 全量 stub 子组件（包括 SubAgentDrawer），通过断言 stub 的 DOM
 *          可见性（v-show 控制）+ 组件 wrapper 自身暴露的方法（openSubAgentDrawer /
 *          closeSubAgentDrawer）来验证自持逻辑。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'

// 隔离 onMounted 内异步副作用：mock 掉 api.js / auth.js
vi.mock('./utils/api.js', () => ({
  fetchKnowledgeFiles: vi.fn(async () => []),
  fetchFilePreview: vi.fn(async () => ({ content: '', preview_mode: 'text', file_url: '' })),
  createNewSession: vi.fn(async () => 'session_xxx'),
  knowledgeChatStream: vi.fn(async () => ({
    getReader: () => ({ read: async () => ({ done: true, value: undefined }) })
  })),
  validateToken: vi.fn(async () => ({ username: 'u', role: 'user', user_id: 1 })),
  refreshToken: vi.fn(async () => 'token_xxx')
}))
vi.mock('./utils/auth.js', () => ({
  redirectToLogin: vi.fn()
}))

// 给所有 stub 一个稳定的可识别 class，便于 DOM 查询
const stubWithClass = (cls, extraProps = []) => ({
  template: `<div class="${cls}" v-show="true">{{ ${cls} }}</div>`,
  props: extraProps
})

import KnowledgeApp from './KnowledgeApp.vue'

describe('KnowledgeApp 子智能体抽屉自持（2026-06-15 新增）', () => {
  it('test_knowledge_app_importable 组件可被 import', () => {
    expect(KnowledgeApp).toBeDefined()
  })

  it('test_knowledge_app_renders_subagent_drawer_component SubAgentDrawer stub 在 DOM 中', async () => {
    const wrapper = mount(KnowledgeApp, {
      global: {
        stubs: {
          FileList: stubWithClass('file-list-stub'),
          FilePreview: stubWithClass('file-preview-stub'),
          MessageBubble: stubWithClass('message-bubble-stub'),
          ProfileInputBox: stubWithClass('profile-input-stub'),
          HumanApprovalBox: stubWithClass('approval-stub'),
          SubAgentDrawer: stubWithClass('subagent-drawer-stub')
        }
      }
    })
    await flushPromises()
    const drawer = wrapper.find('.subagent-drawer-stub')
    expect(drawer.exists()).toBe(true)
  })

  it('test_knowledge_app_open_subagent_drawer_changes_dom_visible_openSubAgentDrawer 切换 DOM', async () => {
    const SubAgentDrawerStub = {
      // 暴露 props 给 e2e 验证
      props: ['visible', 'subAgent'],
      template: `<div class="subagent-drawer-stub"><span class="visible">{{ visible }}</span><span class="has-agent">{{ subAgent ? 'yes' : 'no' }}</span></div>`
    }
    const wrapper = mount(KnowledgeApp, {
      global: {
        stubs: {
          FileList: stubWithClass('file-list-stub'),
          FilePreview: stubWithClass('file-preview-stub'),
          MessageBubble: stubWithClass('message-bubble-stub'),
          ProfileInputBox: stubWithClass('profile-input-stub'),
          HumanApprovalBox: stubWithClass('approval-stub'),
          SubAgentDrawer: SubAgentDrawerStub
        }
      }
    })
    await flushPromises()
    // 初始：visible=false，subAgent=null
    expect(wrapper.find('.subagent-drawer-stub .visible').text()).toBe('false')
    expect(wrapper.find('.subagent-drawer-stub .has-agent').text()).toBe('no')
    // 调用 openSubAgentDrawer
    const fakeSubAgent = {
      toolCallId: 'tc_open_test',
      threadId: 'tc_open_test',
      tool: 'explore',
      parentPrompt: 'p',
      messages: [],
      events: [],
      status: 'running',
      startTime: Date.now(),
      endTime: null,
      error: null
    }
    wrapper.vm.openSubAgentDrawer(fakeSubAgent)
    await nextTick()
    expect(wrapper.find('.subagent-drawer-stub .visible').text()).toBe('true')
    expect(wrapper.find('.subagent-drawer-stub .has-agent').text()).toBe('yes')
  })

  it('test_knowledge_app_close_subagent_drawer_resets_visible 关闭抽屉后 visible=false', async () => {
    const SubAgentDrawerStub = {
      props: ['visible', 'subAgent'],
      template: `<div class="subagent-drawer-stub"><span class="visible">{{ visible }}</span></div>`
    }
    const wrapper = mount(KnowledgeApp, {
      global: {
        stubs: {
          FileList: stubWithClass('file-list-stub'),
          FilePreview: stubWithClass('file-preview-stub'),
          MessageBubble: stubWithClass('message-bubble-stub'),
          ProfileInputBox: stubWithClass('profile-input-stub'),
          HumanApprovalBox: stubWithClass('approval-stub'),
          SubAgentDrawer: SubAgentDrawerStub
        }
      }
    })
    await flushPromises()
    const fakeSubAgent = { toolCallId: 'tc_close', tool: 'explore', messages: [] }
    wrapper.vm.openSubAgentDrawer(fakeSubAgent)
    await nextTick()
    expect(wrapper.find('.subagent-drawer-stub .visible').text()).toBe('true')
    wrapper.vm.closeSubAgentDrawer()
    await nextTick()
    expect(wrapper.find('.subagent-drawer-stub .visible').text()).toBe('false')
  })

  it('test_knowledge_app_subagent_drawer_close_event_resets_visible 监听 drawer @close 事件', async () => {
    const SubAgentDrawerStub = {
      props: ['visible', 'subAgent'],
      emits: ['close'],
      template: `<div class="subagent-drawer-stub"><button class="close-btn" @click="$emit('close')">close</button><span class="visible">{{ visible }}</span></div>`
    }
    const wrapper = mount(KnowledgeApp, {
      global: {
        stubs: {
          FileList: stubWithClass('file-list-stub'),
          FilePreview: stubWithClass('file-preview-stub'),
          MessageBubble: stubWithClass('message-bubble-stub'),
          ProfileInputBox: stubWithClass('profile-input-stub'),
          HumanApprovalBox: stubWithClass('approval-stub'),
          SubAgentDrawer: SubAgentDrawerStub
        }
      }
    })
    await flushPromises()
    const fakeSubAgent = { toolCallId: 'tc_ev', tool: 'explore' }
    wrapper.vm.openSubAgentDrawer(fakeSubAgent)
    await nextTick()
    expect(wrapper.find('.subagent-drawer-stub .visible').text()).toBe('true')
    // 触发 stub 内的 close 按钮 → emit('close') → KnowledgeApp.closeSubAgentDrawer
    await wrapper.find('.subagent-drawer-stub .close-btn').trigger('click')
    await nextTick()
    expect(wrapper.find('.subagent-drawer-stub .visible').text()).toBe('false')
  })
})