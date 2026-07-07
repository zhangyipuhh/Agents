/**
 * App.vue 项目锁定派生测试（2026-07-01 新增）
 *
 * 覆盖：
 *   1. messages 为空时（新建会话、messages.splice 后）→ canEditProject=true
 *   2. messages 非空时（发送过消息或恢复历史会话）→ canEditProject=false
 *   3. canEditProject 透传到 InputBox.projectLocked
 *   4. fetchSessionMessages 失败时 → historyLoadFailed=true → canEditProject=false
 *      （用户决策：历史会话拉取失败默认锁定）
 *
 * 设计：App.vue 已有 isEmptyState = computed(() => messages.length === 0)。
 *       新增 canEditProject = computed(() => isEmptyState.value && !historyLoadFailed.value)。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

describe('App.vue 项目锁定 canEditProject（2026-07-01 新增）', () => {
  let originalFetch
  let originalLocalStorage

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
    // mock fetch：让 checkAuth 跑通（refresh / validate 都返回成功）
    // 2026-07-01 同步：恢复页面加载后自动创建会话，mock /api/session/create
    global.fetch = vi.fn((url) => {
      if (url === '/api/auth/refresh') {
        return Promise.resolve({
          ok: true,
          json: async () => ({ access_token: 'fake-token' }),
        })
      }
      if (url === '/api/auth/validate') {
        return Promise.resolve({
          ok: true,
          json: async () => ({ username: 'tester', role: 'user', user_id: 1 }),
        })
      }
      if (url === '/api/session/create') {
        return Promise.resolve({
          ok: true,
          json: async () => ({ session_id: 'sess_auto_001' }),
        })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })
    global.localStorage = {
      getItem: vi.fn((key) => {
        if (key === 'auth_token') return 'fake-token'
        if (key === 'session_id') return 'fake-session'
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

  it('test_can_edit_project_initially_true 刚进入应用时 messages 为空 → canEditProject=true', { timeout: 15000 }, async () => {
    const App = (await import('../../App.vue')).default
    const wrapper = mount(App, {
      global: { stubs: ['router-link', 'router-view'] }
    })
    await flushPromises()
    // 派生计算：messages.length === 0 时 canEditProject=true
    expect(wrapper.vm.canEditProject).toBe(true)
  })

  it('test_history_messages_make_can_edit_false 恢复历史会话（含 messages）→ canEditProject=false', async () => {
    // mock fetch：让 fetchSessionDetail / fetchSessionMessages 返回历史消息
    global.fetch = vi.fn((url) => {
      if (url === '/api/auth/refresh') {
        return Promise.resolve({ ok: true, json: async () => ({ access_token: 'fake-token' }) })
      }
      if (url === '/api/auth/validate') {
        return Promise.resolve({ ok: true, json: async () => ({ username: 'tester', role: 'user', user_id: 1 }) })
      }
      if (url.includes('/api/session/') && url.endsWith('/detail')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            session_id: 'sess_hist',
            title: '历史会话',
            agent_type: 'default',
            project_id: null,
            attachments: []
          })
        })
      }
      if (url.includes('/api/session/') && url.endsWith('/messages')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            messages: [
              { id: '1', type: 'user', content: '你好', attachments: [] },
              { id: '2', type: 'ai', content: '你好！', timeline: [], thinking: [], text: '你好！', tools: [] }
            ]
          })
        })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })

    const App = (await import('../../App.vue')).default
    const wrapper = mount(App, {
      global: { stubs: ['router-link', 'router-view'] }
    })
    await flushPromises()

    // 初始为 true
    expect(wrapper.vm.canEditProject).toBe(true)

    // 模拟切换到历史会话
    wrapper.vm.handleSessionSwitch('sess_hist')
    await flushPromises()

    // messages 已非空 → canEditProject=false
    expect(wrapper.vm.canEditProject).toBe(false)
  })

  it('test_history_load_failure_defaults_to_locked fetchSessionMessages 抛错 → canEditProject=false', async () => {
    global.fetch = vi.fn((url) => {
      if (url === '/api/auth/refresh') {
        return Promise.resolve({ ok: true, json: async () => ({ access_token: 'fake-token' }) })
      }
      if (url === '/api/auth/validate') {
        return Promise.resolve({ ok: true, json: async () => ({ username: 'tester', role: 'user', user_id: 1 }) })
      }
      if (url.includes('/api/session/') && url.endsWith('/detail')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            session_id: 'sess_broken',
            title: '坏掉的会话',
            agent_type: 'default',
            project_id: 99,
            attachments: []
          })
        })
      }
      if (url.includes('/api/session/') && url.endsWith('/messages')) {
        // 模拟历史消息拉取失败
        return Promise.resolve({
          ok: false,
          status: 500,
          statusText: 'Internal Server Error',
          json: async () => ({ detail: 'redis down' })
        })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })

    const App = (await import('../../App.vue')).default
    const wrapper = mount(App, {
      global: { stubs: ['router-link', 'router-view'] }
    })
    await flushPromises()

    wrapper.vm.handleSessionSwitch('sess_broken')
    await flushPromises()

    // 用户决策：fetchSessionMessages 失败时默认锁定
    expect(wrapper.vm.canEditProject).toBe(false)
  })

  it('test_passes_project_locked_to_input_box projectLocked 正确透传到 InputBox', async () => {
    global.fetch = vi.fn((url) => {
      if (url === '/api/auth/refresh') {
        return Promise.resolve({ ok: true, json: async () => ({ access_token: 'fake-token' }) })
      }
      if (url === '/api/auth/validate') {
        return Promise.resolve({ ok: true, json: async () => ({ username: 'tester', role: 'user', user_id: 1 }) })
      }
      if (url.includes('/api/session/') && url.endsWith('/detail')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            session_id: 'sess_x',
            title: 'X',
            agent_type: 'default',
            project_id: null,
            attachments: []
          })
        })
      }
      if (url.includes('/api/session/') && url.endsWith('/messages')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            messages: [{ id: '1', type: 'user', content: 'a', attachments: [] }]
          })
        })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })

    const App = (await import('../../App.vue')).default
    const wrapper = mount(App, {
      global: { stubs: ['router-link', 'router-view'] }
    })
    await flushPromises()

    wrapper.vm.handleSessionSwitch('sess_x')
    await flushPromises()

    const inputBox = wrapper.findComponent({ name: 'InputBox' })
    expect(inputBox.exists()).toBe(true)
    expect(inputBox.props('projectLocked')).toBe(true)
  })

  it('test_new_session_resets_can_edit_project 新建会话（messages 清空）→ canEditProject=true', async () => {
    const App = (await import('../../App.vue')).default
    const wrapper = mount(App, {
      global: { stubs: ['router-link', 'router-view'] }
    })
    await flushPromises()

    // 先手动塞入消息让 canEditProject 变 false
    wrapper.vm.messages.push({ id: 1, type: 'user', content: 'test' })
    await flushPromises()
    expect(wrapper.vm.canEditProject).toBe(false)

    // 模拟新建会话
    wrapper.vm.newSession()
    await flushPromises()

    // messages 已被 splice 清空 → canEditProject=true
    expect(wrapper.vm.canEditProject).toBe(true)
  })

  it('test_upload_lock_makes_can_edit_false 存在成功上传文件时 → canEditProject=false', async () => {
    const App = (await import('../../App.vue')).default
    const wrapper = mount(App, {
      global: { stubs: ['router-link', 'router-view'] }
    })
    await flushPromises()

    // 初始可编辑
    expect(wrapper.vm.canEditProject).toBe(true)

    // 模拟 InputBox 上报存在成功上传文件
    wrapper.vm.projectLockedByUpload = true
    await flushPromises()

    expect(wrapper.vm.canEditProject).toBe(false)
  })

  it('test_new_session_resets_project_locked_by_upload 新建会话时 projectLockedByUpload 复位', async () => {
    const App = (await import('../../App.vue')).default
    const wrapper = mount(App, {
      global: { stubs: ['router-link', 'router-view'] }
    })
    await flushPromises()

    wrapper.vm.projectLockedByUpload = true
    await flushPromises()
    expect(wrapper.vm.canEditProject).toBe(false)

    wrapper.vm.newSession()
    await flushPromises()

    expect(wrapper.vm.projectLockedByUpload).toBe(false)
    expect(wrapper.vm.canEditProject).toBe(true)
  })

  it('test_new_session_resets_current_project_to_null 新建会话时 currentProject 重置为 null', async () => {
    const App = (await import('../../App.vue')).default
    const wrapper = mount(App, {
      global: { stubs: ['router-link', 'router-view'] }
    })
    await flushPromises()

    // 模拟用户已选择项目
    wrapper.vm.currentProject = { id: 42, name: '测试项目', uuid: 'proj-42' }
    await flushPromises()
    expect(wrapper.vm.currentProject).toEqual({ id: 42, name: '测试项目', uuid: 'proj-42' })

    // 触发新建任务
    wrapper.vm.newSession()
    await flushPromises()

    // 断言项目已被重置为 null
    expect(wrapper.vm.currentProject).toBeNull()
  })
})