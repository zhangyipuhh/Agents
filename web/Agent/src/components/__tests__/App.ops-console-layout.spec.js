// -*- coding:utf-8 -*-
/**
 * App.vue 路由级 layout 切换测试
 *
 * 2026-08-09 落地：访问 /ops-console 时必须呈现完整独立界面，
 * 不挂主会话的 <Sidebar> / <ProjectDialog> / <SubAgentDrawer>。
 *
 * 覆盖：
 *   - 路由 ops-console 时 Sidebar 不渲染
 *   - 路由 agent 时 Sidebar 仍渲染（默认 layout）
 *   - 路由 knowledge 时 Sidebar 仍渲染（默认 layout）
 *
 * 策略：使用真实 vue-router 创建 router 实例并 push 路由，
 * mount App 时通过 plugins 注入 router，trigger 'route.name' 变化。
 * mock api.js 所有 App.vue 启动期调用的端点，避免真实网络请求。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import Sidebar from '../Sidebar.vue'

vi.mock('../../utils/api.js', () => ({
  validateToken: vi.fn(async () => ({ username: 'tester', role: 'user', allowed_agents: [] })),
  chatStream: vi.fn(async () => ({ getReader: () => ({ read: async () => ({ done: true }) }) })),
  fetchSessionList: vi.fn(async () => ({ sessions: [] })),
  fetchProjectList: vi.fn(async () => ({ projects: [] })),
  createNewSession: vi.fn(async () => ({ session_id: 'sess_x' })),
  fetchSessionDetail: vi.fn(async () => ({})),
  fetchSessionAttachments: vi.fn(async () => []),
  fetchSessionMessages: vi.fn(async () => ({ messages: [] })),
  refreshToken: vi.fn(async () => ({ access_token: 'tok' })),
  clearAuth: vi.fn(),
  tryParsePythonLiteral: vi.fn(s => s),
  isThinkingBlock: () => false,
  extractTextFromBlock: b => b,
  processContentBlocks: b => b,
  parseMessageContent: () => ({}),
  processSSEEvent: () => ({}),
  createAiMessage: () => ({}),
  isSubAgentHistoryItem: () => false,
  convertSubAgentHistoryToAiSubAgent: () => ({}),
  isSubAgentTool: () => false,
  logout: vi.fn(),
  redirectToLogin: vi.fn(),
  tryRefreshOrRedirect: vi.fn(),
  createProject: vi.fn(),
  fetchProjectInfo: vi.fn(),
  bindSessionToProject: vi.fn(),
  unbindSessionFromProject: vi.fn(),
  fetchSessionFileTree: vi.fn(),
  previewSessionFile: vi.fn(),
  submitMessageFeedback: vi.fn(),
  triggerAbort: vi.fn(),
}))

function makeRouter(initialPath) {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'agent', component: { template: '<div />' } },
      { path: '/knowledge', name: 'knowledge', component: { template: '<div />' } },
      { path: '/ops-console', name: 'ops-console', component: { template: '<div />' } },
    ],
  })
}

describe('App.vue 路由级 layout 切换', () => {
  let originalFetch
  let originalLocalStorage
  let router

  beforeEach(async () => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
    global.fetch = vi.fn(url => {
      if (url === '/api/auth/refresh') {
        return Promise.resolve({ ok: true, json: async () => ({ access_token: 'tok' }) })
      }
      if (url === '/api/auth/validate') {
        return Promise.resolve({ ok: true, json: async () => ({ username: 'tester', role: 'user', user_id: 1 }) })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })
    global.localStorage = {
      getItem: k => (k === 'username' ? 'tester' : null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    }
    router = makeRouter()
    await router.push('/')
    await router.isReady()
  })

  afterEach(() => {
    global.fetch = originalFetch
    global.localStorage = originalLocalStorage
    vi.clearAllMocks()
  })

  it('test_route_ops_console_hides_sidebar 路由 ops-console 时 Sidebar 不渲染', { timeout: 20000 }, async () => {
    const App = (await import('../../App.vue')).default
    const wrapper = mount(App, {
      global: {
        plugins: [router],
        stubs: {
          'router-link': true,
          'router-view': true,
          AgentWorkspace: true,
          KnowledgeWorkspace: true,
          OpsConsoleWorkspace: true,
          ProjectDialog: true,
          SubAgentDrawer: true,
        },
      },
    })
    await router.push('/ops-console')
    await flushPromises()
    expect(wrapper.findComponent(Sidebar).exists()).toBe(false)
    wrapper.unmount()
  })

  it('test_route_agent_renders_sidebar 路由 agent 时 Sidebar 渲染', { timeout: 20000 }, async () => {
    const App = (await import('../../App.vue')).default
    const wrapper = mount(App, {
      global: {
        plugins: [router],
        stubs: {
          'router-link': true,
          'router-view': true,
          AgentWorkspace: true,
          KnowledgeWorkspace: true,
          OpsConsoleWorkspace: true,
          ProjectDialog: true,
          SubAgentDrawer: true,
        },
      },
    })
    await router.push('/')
    await flushPromises()
    expect(wrapper.findComponent(Sidebar).exists()).toBe(true)
    wrapper.unmount()
  })

  it('test_route_knowledge_renders_sidebar 路由 knowledge 时 Sidebar 渲染', { timeout: 20000 }, async () => {
    const App = (await import('../../App.vue')).default
    const wrapper = mount(App, {
      global: {
        plugins: [router],
        stubs: {
          'router-link': true,
          'router-view': true,
          AgentWorkspace: true,
          KnowledgeWorkspace: true,
          OpsConsoleWorkspace: true,
          ProjectDialog: true,
          SubAgentDrawer: true,
        },
      },
    })
    await router.push('/knowledge')
    await flushPromises()
    expect(wrapper.findComponent(Sidebar).exists()).toBe(true)
    wrapper.unmount()
  })
})
