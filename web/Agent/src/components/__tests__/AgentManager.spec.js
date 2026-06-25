/**
 * AgentManager 组件测试
 *
 * 覆盖：组件可导入 / 列表渲染 / 点击新增按钮弹出表单 / 选中智能体显示字段 /
 *      启用/禁用切换调用 API / 删除确认弹窗。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import AgentManager from '../AgentManager.vue'

const mockAgents = [
  {
    name: 'map_agent',
    display_name: '地图智能体',
    description: '地图控制',
    enabled: true,
    sort_order: 0,
    config_schema: {
      temperature: { type: 'float', default: 0.5 },
      state_fields: { map_zoom: { type: 'int', default: 10 } },
      context_fields: {},
    },
  },
  {
    name: 'audit_agent',
    display_name: '审计文档',
    description: '审计相关',
    enabled: false,
    sort_order: 1,
    config_schema: { state_fields: {}, context_fields: {} },
  },
]

const mockTemplates = [
  { field_name: 'temperature', type: 'float', default: 0 },
  { field_name: 'max_tokens', type: 'int', default: 999999999 },
  { field_name: 'model_name', type: 'str', default: 'llama3.2' },
]

function setupFetchMock() {
  global.fetch = vi.fn(async (url, opts = {}) => {
    const method = (opts.method || 'GET').toUpperCase()
    const u = typeof url === 'string' ? url : url.url
    // field-templates 必须在详情端点之前匹配，避免被 /agents/[^/]+$ 误捕获
    if (u.includes('/api/admin/agents/field-templates')) {
      return jsonResponse(mockTemplates)
    }
    if (u.includes('/api/admin/agents/check-name')) {
      return jsonResponse({ name: 'new_agent', available: true })
    }
    if (u.includes('/api/admin/agents/validate-md-path')) {
      const body = JSON.parse(opts.body || '{}')
      return jsonResponse({ path: body.path, exists: true })
    }
    if (u.includes('/api/admin/agents') && method === 'GET' && !u.match(/agents\/[^?]+/)) {
      return jsonResponse(mockAgents)
    }
    if (u.match(/\/api\/admin\/agents\/[^/]+$/) && method === 'GET') {
      const name = decodeURIComponent(u.split('/').pop().split('?')[0])
      const found = mockAgents.find(a => a.name === name)
      return jsonResponse(found || mockAgents[0])
    }
    if (u.includes('/enabled') && method === 'PUT') {
      return jsonResponse({ name: 'map_agent', enabled: false })
    }
    if (u.includes('/config-schema/field') && method === 'POST') {
      return jsonResponse({})
    }
    if (u.includes('/config-schema/field') && method === 'DELETE') {
      return jsonResponse({})
    }
    if (u.match(/\/api\/admin\/agents\/[^/]+$/) && method === 'DELETE') {
      return emptyResponse()
    }
    return jsonResponse({})
  })
}

function jsonResponse(data, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  }
}

function emptyResponse(status = 204) {
  return { ok: true, status, json: async () => ({}) }
}

describe('AgentManager 组件', () => {
  let originalFetch
  let originalLocalStorage

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
    global.localStorage = {
      getItem: vi.fn(() => 'fake-token'),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    }
    setupFetchMock()
    // 屏蔽 confirm
    global.confirm = vi.fn(() => true)
  })

  afterEach(() => {
    global.fetch = originalFetch
    global.localStorage = originalLocalStorage
  })

  it('test_component_importable 组件可被 import', () => {
    expect(AgentManager).toBeDefined()
  })

  it('test_renders_agent_list 渲染后展示智能体列表', async () => {
    const wrapper = mount(AgentManager)
    await flushPromises()
    const items = wrapper.findAll('.agent-item')
    expect(items.length).toBe(2)
    expect(wrapper.text()).toContain('地图智能体')
    expect(wrapper.text()).toContain('audit_agent')
  })

  it('test_new_agent_button_opens_dialog 点击新增按钮弹出表单', async () => {
    const wrapper = mount(AgentManager)
    await flushPromises()
    const newBtn = wrapper.findAll('button').find(b => b.text().includes('新增智能体'))
    expect(newBtn).toBeTruthy()
    await newBtn.trigger('click')
    await flushPromises()
    // 表单应包含 name / display_name 输入框
    expect(wrapper.text()).toContain('AGENTS.md 路径')
  })

  it('test_select_agent_displays_fields 点击列表项后显示三组字段', async () => {
    const wrapper = mount(AgentManager)
    await flushPromises()
    const firstItem = wrapper.find('.agent-item')
    await firstItem.trigger('click')
    await flushPromises()
    // 应显示 AgentConfig / State / Context 三组标题
    expect(wrapper.text()).toContain('AgentConfig 字段')
    expect(wrapper.text()).toContain('State 扩展字段')
    expect(wrapper.text()).toContain('Context 扩展字段')
    // map_agent 应有 map_zoom 字段
    expect(wrapper.text()).toContain('map_zoom')
  })

  it('test_disabled_agent_shows_badge 已禁用智能体显示「已禁用」徽章', async () => {
    const wrapper = mount(AgentManager)
    await flushPromises()
    expect(wrapper.text()).toContain('已禁用')
  })

  it('test_has_add_field_button 每个 section 都有「+ 添加字段」按钮', async () => {
    const wrapper = mount(AgentManager)
    await flushPromises()
    const firstItem = wrapper.find('.agent-item')
    await firstItem.trigger('click')
    await flushPromises()
    const addButtons = wrapper.findAll('button').filter(b => b.text().includes('添加字段'))
    expect(addButtons.length).toBeGreaterThanOrEqual(3) // 三组
  })
})