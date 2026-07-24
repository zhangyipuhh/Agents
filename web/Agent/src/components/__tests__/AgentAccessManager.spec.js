/**
 * AgentAccessManager 组件测试（2026-07-24 新增）
 *
 * 覆盖：
 * - 左侧人员列表 + 搜索过滤
 * - 切换人员自动加载该用户的 agent_names
 * - 右侧智能体 checkbox 列表 + 全选 / 清空
 * - 勾选 / 取消触发 debounce 自动保存
 * - isAdmin=false 时不触发 admin-only 请求
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import AgentAccessManager from '../AgentAccessManager.vue'

const mockCatalog = {
  items: [
    { name: 'map_agent', display_name: '地图智能体' },
    { name: 'project', display_name: '运维项目智能体' },
    { name: 'knowledge_ydt', display_name: '一点通规则库' }
  ]
}

const mockUserList = [
  { id: 1, username: 'admin', role: 'admin', allowed_agents: [], created_at: '2026-01-01', updated_at: '2026-01-01' },
  { id: 2, username: 'zhangsan', role: 'user', allowed_agents: ['map_agent'], created_at: '2026-01-01', updated_at: '2026-01-01' },
  { id: 3, username: 'lisi', role: 'user', allowed_agents: [], created_at: '2026-01-01', updated_at: '2026-01-01' }
]

function jsonResponse(data, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => data }
}

function setupFetchMock({ grantsByUser = {} } = {}) {
  global.fetch = vi.fn(async (url, opts = {}) => {
    const urlStr = String(url)
    const method = (opts.method || 'GET').toUpperCase()

    // 智能体目录
    if (urlStr.includes('/api/admin/permissions/agents/catalog') && method === 'GET') {
      return jsonResponse(mockCatalog)
    }
    // 人员列表
    if (urlStr.includes('/api/users') && !urlStr.includes('/grants') && method === 'GET') {
      return jsonResponse(mockUserList)
    }
    // 用户智能体授权
    const grantsMatch = urlStr.match(/\/agents\/users\/(\d+)\/grants/)
    if (grantsMatch) {
      const uid = grantsMatch[1]
      if (method === 'GET') {
        return jsonResponse({ agent_names: grantsByUser[uid] || [] })
      }
      if (method === 'PUT') {
        const body = JSON.parse(opts.body || '{}')
        grantsByUser[uid] = body.agent_names
        return jsonResponse({ agent_names: body.agent_names })
      }
    }
    return jsonResponse({ detail: 'not mocked' }, 404)
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
}

describe('AgentAccessManager', () => {
  beforeEach(() => {
    setupFetchMock()
  })

  it('test_renders_user_list_and_agent_panel 渲染左侧人员列表 + 选中后渲染右侧智能体面板', async () => {
    const wrapper = mount(AgentAccessManager, { props: { isAdmin: true } })
    await flushPromises()
    expect(wrapper.find('[data-testid="agent-access-user-list"]').exists()).toBe(true)
    // 选中第一个用户，张开右侧面板
    const items = wrapper.findAll('[data-testid="agent-access-user-list-item"]')
    expect(items.length).toBe(3)
    await items[0].trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="agent-access-select-all"]').exists()).toBe(true)
  })

  it('test_loads_catalog_after_admin_mount admin 挂载后加载 catalog + 选中后渲染智能体', async () => {
    const wrapper = mount(AgentAccessManager, { props: { isAdmin: true } })
    await flushPromises()
    // 选中第一个用户
    const items = wrapper.findAll('[data-testid="agent-access-user-list-item"]')
    await items[0].trigger('click')
    await flushPromises()
    // 三个智能体 checkbox 都已渲染
    expect(wrapper.find('[data-testid="agent-access-checkbox-map_agent"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="agent-access-checkbox-project"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="agent-access-checkbox-knowledge_ydt"]').exists()).toBe(true)
  })

  it('test_non_admin_skips_data_loading isAdmin=false 时不触发请求', async () => {
    const fetchSpy = vi.fn()
    global.fetch = fetchSpy
    const wrapper = mount(AgentAccessManager, { props: { isAdmin: false } })
    await flushPromises()
    expect(fetchSpy).not.toHaveBeenCalled()
    // 智能体 checkbox 列表为空
    expect(wrapper.find('[data-testid="agent-access-checkbox-map_agent"]').exists()).toBe(false)
  })

  it('test_select_user_loads_their_agent_grants 切换人员加载其授权', async () => {
    setupFetchMock({ grantsByUser: { 2: ['map_agent'] } })
    const wrapper = mount(AgentAccessManager, { props: { isAdmin: true } })
    await flushPromises()
    // 选中 zhangsan (id=2)
    const items = wrapper.findAll('[data-testid="agent-access-user-list-item"]')
    await items[1].trigger('click')
    await flushPromises()
    // map_agent 应已勾选
    const mapCb = wrapper.find('[data-testid="agent-access-checkbox-map_agent"] input[type="checkbox"]')
    expect(mapCb.element.checked).toBe(true)
    // project 应未勾选
    const projectCb = wrapper.find('[data-testid="agent-access-checkbox-project"] input[type="checkbox"]')
    expect(projectCb.element.checked).toBe(false)
  })

  it('test_toggle_triggers_debounce_save 勾选触发 debounce 保存', async () => {
    vi.useFakeTimers()
    const fetchSpy = vi.fn(async (url, opts = {}) => {
      const urlStr = String(url)
      if (urlStr.includes('/api/admin/permissions/agents/catalog')) {
        return jsonResponse(mockCatalog)
      }
      if (urlStr.includes('/api/users') && !urlStr.includes('/grants')) {
        return jsonResponse(mockUserList)
      }
      const grantsMatch = urlStr.match(/\/agents\/users\/(\d+)\/grants/)
      if (grantsMatch) {
        const uid = grantsMatch[1]
        if (opts.method === 'GET' || !opts.method) {
          return jsonResponse({ agent_names: [] })
        }
        if (opts.method === 'PUT') {
          const body = JSON.parse(opts.body || '{}')
          return jsonResponse({ agent_names: body.agent_names })
        }
      }
      return jsonResponse({ detail: 'not mocked' }, 404)
    })
    global.fetch = fetchSpy

    const wrapper = mount(AgentAccessManager, { props: { isAdmin: true } })
    await flushPromises()
    // 选中 zhangsan
    const items = wrapper.findAll('[data-testid="agent-access-user-list-item"]')
    await items[1].trigger('click')
    await flushPromises()

    // 勾选 project
    const projectCb = wrapper.find('[data-testid="agent-access-checkbox-project"] input[type="checkbox"]')
    await projectCb.setValue(true)
    // 推进 debounce 定时器
    await vi.advanceTimersByTimeAsync(500)
    await flushPromises()

    // 验证 PUT 调用
    const putCalls = fetchSpy.mock.calls.filter(([url, opts]) => {
      return String(url).includes('/agents/users/2/grants') && (opts?.method === 'PUT')
    })
    expect(putCalls.length).toBeGreaterThanOrEqual(1)
    const body = JSON.parse(putCalls[0][1].body)
    expect(body.agent_names).toContain('project')

    vi.useRealTimers()
  })

  it('test_select_all_button 全选按钮触发全部勾选', async () => {
    const wrapper = mount(AgentAccessManager, { props: { isAdmin: true } })
    await flushPromises()
    // 选中 zhangsan
    const items = wrapper.findAll('[data-testid="agent-access-user-list-item"]')
    await items[1].trigger('click')
    await flushPromises()
    // 点击全选
    await wrapper.find('[data-testid="agent-access-select-all"]').trigger('click')
    await flushPromises()
    const mapCb = wrapper.find('[data-testid="agent-access-checkbox-map_agent"] input[type="checkbox"]')
    const projectCb = wrapper.find('[data-testid="agent-access-checkbox-project"] input[type="checkbox"]')
    const ydtCb = wrapper.find('[data-testid="agent-access-checkbox-knowledge_ydt"] input[type="checkbox"]')
    expect(mapCb.element.checked).toBe(true)
    expect(projectCb.element.checked).toBe(true)
    expect(ydtCb.element.checked).toBe(true)
  })

  it('test_select_none_button 清空按钮触发全部取消', async () => {
    setupFetchMock({ grantsByUser: { 2: ['map_agent', 'project'] } })
    const wrapper = mount(AgentAccessManager, { props: { isAdmin: true } })
    await flushPromises()
    const items = wrapper.findAll('[data-testid="agent-access-user-list-item"]')
    await items[1].trigger('click')
    await flushPromises()
    // 点击清空
    await wrapper.find('[data-testid="agent-access-select-none"]').trigger('click')
    await flushPromises()
    const mapCb = wrapper.find('[data-testid="agent-access-checkbox-map_agent"] input[type="checkbox"]')
    expect(mapCb.element.checked).toBe(false)
  })

  it('test_search_filters_user_list 搜索过滤用户列表', async () => {
    const wrapper = mount(AgentAccessManager, { props: { isAdmin: true } })
    await flushPromises()
    const searchInput = wrapper.find('[data-testid="agent-access-user-search"]')
    await searchInput.setValue('zhang')
    await flushPromises()
    const items = wrapper.findAll('[data-testid="agent-access-user-list-item"]')
    expect(items.length).toBe(1)
    expect(items[0].text()).toContain('zhangsan')
  })
})
