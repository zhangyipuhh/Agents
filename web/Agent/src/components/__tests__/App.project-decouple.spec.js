/**
 * App.vue 项目选择与 session 解耦测试（2026-07-06 新增）
 *
 * 覆盖：
 *   1. 无 session 时选择现有项目 → 不调用 /api/session/create 与 /api/project/session/bind，仅更新 currentProject。
 *   2. 有 session 时选择现有项目 → 调用 /api/project/session/bind，并更新 currentProject。
 *   3. 无 session 时创建项目 → 调用 /api/project/create 且 body 不含 uuid，不创建 session，更新 currentProject。
 *   4. 无 session 时选择「不使用文件夹」→ 不调用后端 API，仅 currentProject = null。
 *   5. 发送第一条消息（ensureSessionForFirstOp）时，使用 currentProject.id 创建 session 并绑定项目。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

function createMockFetch() {
  return vi.fn((url, options) => {
    if (url === '/api/auth/refresh') {
      return Promise.resolve({ ok: true, json: async () => ({ access_token: 'fake-token' }) })
    }
    if (url === '/api/auth/validate') {
      return Promise.resolve({ ok: true, json: async () => ({ username: 'tester', role: 'user', user_id: 1 }) })
    }
    if (url === '/api/project/list') {
      return Promise.resolve({
        ok: true,
        json: async () => ({ projects: [{ id: 2, name: 'Existing Project', uuid: 'existing-uuid' }] })
      })
    }
    if (url === '/api/project/create') {
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, project: { id: 1, name: 'New Project', uuid: 'auto-generated-uuid' } })
      })
    }
    if (url === '/api/project/session/bind') {
      return Promise.resolve({ ok: true, json: async () => ({ success: true }) })
    }
    if (url === '/api/project/session/unbind') {
      return Promise.resolve({ ok: true, json: async () => ({ success: true }) })
    }
    if (url === '/api/session/create') {
      return Promise.resolve({ ok: true, json: async () => ({ session_id: 'sess_auto_001' }) })
    }
    return Promise.resolve({ ok: true, json: async () => ({}) })
  })
}

describe('App.vue 项目选择与 session 解耦（2026-07-06）', () => {
  let originalFetch
  let originalLocalStorage

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
    global.localStorage = {
      getItem: vi.fn((key) => {
        if (key === 'auth_token') return 'fake-token'
        if (key === 'session_id') return ''
        return null
      }),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    }
  })

  afterEach(() => {
    global.fetch = originalFetch
    global.localStorage = originalLocalStorage
  })

  it('test_pick_project_without_session_does_not_create_session 无 session 选择现有项目只更新前端状态', { timeout: 15000 }, async () => {
    global.fetch = createMockFetch()
    const App = (await import('../../App.vue')).default
    const wrapper = mount(App, {
      global: { stubs: ['router-link', 'router-view'] }
    })
    await flushPromises()

    expect(wrapper.vm.sessionId.value).toBe('')

    const project = { id: 2, name: 'Existing Project', uuid: 'existing-uuid' }
    wrapper.vm.handleProjectPick(project)
    await flushPromises()

    expect(wrapper.vm.currentProject).toEqual(project)
    const createSessionCalls = global.fetch.mock.calls.filter(([url]) => url === '/api/session/create')
    const bindCalls = global.fetch.mock.calls.filter(([url]) => url === '/api/project/session/bind')
    expect(createSessionCalls).toHaveLength(0)
    expect(bindCalls).toHaveLength(0)
  })

  it('test_pick_project_with_session_calls_bind 有 session 选择现有项目同步绑定当前会话', { timeout: 15000 }, async () => {
    global.fetch = createMockFetch()
    const App = (await import('../../App.vue')).default
    const wrapper = mount(App, {
      global: { stubs: ['router-link', 'router-view'] }
    })
    await flushPromises()

    wrapper.vm.sessionId.value = 'sess_existing'
    const project = { id: 2, name: 'Existing Project', uuid: 'existing-uuid' }
    wrapper.vm.handleProjectPick(project)
    await flushPromises()

    expect(wrapper.vm.currentProject).toEqual(project)
    const bindCalls = global.fetch.mock.calls.filter(([url]) => url === '/api/project/session/bind')
    expect(bindCalls).toHaveLength(1)
    const [, options] = bindCalls[0]
    const body = JSON.parse(options.body)
    expect(body).toMatchObject({ session_id: 'sess_existing', project_id: 2 })
  })

  it('test_create_project_without_session_uses_auto_uuid 无 session 创建项目由后端生成 uuid', { timeout: 15000 }, async () => {
    global.fetch = createMockFetch()
    const App = (await import('../../App.vue')).default
    const wrapper = mount(App, {
      global: { stubs: ['router-link', 'router-view'] }
    })
    await flushPromises()

    expect(wrapper.vm.sessionId.value).toBe('')

    wrapper.vm.handleProjectCreate({ name: 'New Project' })
    await flushPromises()

    expect(wrapper.vm.currentProject).toMatchObject({ id: 1, name: 'New Project' })
    const createProjectCalls = global.fetch.mock.calls.filter(([url]) => url === '/api/project/create')
    expect(createProjectCalls).toHaveLength(1)
    const [, options] = createProjectCalls[0]
    const body = JSON.parse(options.body)
    expect(body.name).toBe('New Project')
    expect(body).not.toHaveProperty('uuid')
    const createSessionCalls = global.fetch.mock.calls.filter(([url]) => url === '/api/session/create')
    expect(createSessionCalls).toHaveLength(0)
  })

  it('test_select_none_without_session_only_clears_state 无 session 不使用文件夹仅清空前端状态', { timeout: 15000 }, async () => {
    global.fetch = createMockFetch()
    const App = (await import('../../App.vue')).default
    const wrapper = mount(App, {
      global: { stubs: ['router-link', 'router-view'] }
    })
    await flushPromises()

    const project = { id: 2, name: 'Existing Project', uuid: 'existing-uuid' }
    await wrapper.vm.handleProjectPick(project)
    await flushPromises()
    expect(wrapper.vm.currentProject).toEqual(project)

    wrapper.vm.sessionId.value = ''
    wrapper.vm.handleProjectSelectNone()
    await flushPromises()

    expect(wrapper.vm.currentProject).toBeNull()
    const unbindCalls = global.fetch.mock.calls.filter(([url]) => url === '/api/project/session/unbind')
    const createSessionCalls = global.fetch.mock.calls.filter(([url]) => url === '/api/session/create')
    expect(unbindCalls).toHaveLength(0)
    expect(createSessionCalls).toHaveLength(0)
  })

  it('test_ensure_session_uses_current_project_id 首次需要后端时使用 currentProject.id 创建 session', { timeout: 15000 }, async () => {
    global.fetch = createMockFetch()
    const App = (await import('../../App.vue')).default
    const wrapper = mount(App, {
      global: { stubs: ['router-link', 'router-view'] }
    })
    await flushPromises()

    const project = { id: 2, name: 'Existing Project', uuid: 'existing-uuid' }
    await wrapper.vm.handleProjectPick(project)
    await flushPromises()

    wrapper.vm.sessionId.value = ''
    const projectIdForChat = wrapper.vm.currentProject ? wrapper.vm.currentProject.id : null
    await wrapper.vm.ensureSessionForFirstOp(projectIdForChat)
    await flushPromises()

    expect(wrapper.vm.sessionId.value).toBe('sess_auto_001')
    const createSessionCalls = global.fetch.mock.calls.filter(([url]) => url === '/api/session/create')
    expect(createSessionCalls).toHaveLength(1)
    const [, options] = createSessionCalls[0]
    const body = JSON.parse(options.body)
    expect(body).toMatchObject({ project_id: 2 })
  })
})
