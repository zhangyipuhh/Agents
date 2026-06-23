/**
 * McpServerManager 组件测试
 *
 * 覆盖：组件可导入、渲染服务器列表、点击新增按钮触发表单、
 *      点击服务器项触发选中事件、toggle 开关调用 API。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import McpServerManager from '../McpServerManager.vue'

const mockServers = [
  { name: 'amap', display_name: '高德地图', type: 'sse', url: 'http://x', enabled: true, tags: ['map'] },
  { name: 'counter', display_name: '计数工具', type: 'stdio', enabled: false, tags: [] },
]

describe('McpServerManager 组件', () => {
  let originalFetch
  let originalLocalStorage

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
    global.fetch = vi.fn()
    global.localStorage = {
      getItem: vi.fn(() => 'fake-token'),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    }
  })

  afterEach(() => {
    global.fetch = originalFetch
    global.localStorage = originalLocalStorage
  })

  it('test_component_importable 组件可被 import', () => {
    expect(McpServerManager).toBeDefined()
  })

  it('test_renders_server_list 渲染服务器列表', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockServers,
    })
    const wrapper = mount(McpServerManager)
    await flushPromises()
    expect(wrapper.text()).toContain('高德地图')
    expect(wrapper.text()).toContain('计数工具')
  })

  it('test_click_server_selects_it 点击服务器项选中', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockServers,
    })
    const wrapper = mount(McpServerManager)
    await flushPromises()
    const items = wrapper.findAll('.server-item')
    expect(items.length).toBeGreaterThanOrEqual(1)
    await items[0].trigger('click')
    expect(wrapper.text()).toContain('高德地图')
  })

  it('test_click_new_server_button_shows_form 点击新增按钮显示表单', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    })
    const wrapper = mount(McpServerManager)
    await flushPromises()
    const newBtn = wrapper.find('.new-server-btn')
    expect(newBtn.exists()).toBe(true)
    await newBtn.trigger('click')
    expect(wrapper.find('.server-form').exists()).toBe(true)
  })

  it('test_refresh_methods_button_visible 选中 server 后显示刷新方法按钮', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockServers,
    })
    // I4 修复：为 selectServer 触发的 listMcpMethods 补充 mock
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    })
    const wrapper = mount(McpServerManager)
    await flushPromises()
    const items = wrapper.findAll('.server-item')
    expect(items.length).toBeGreaterThanOrEqual(1)
    await items[0].trigger('click')
    expect(wrapper.find('.refresh-methods-btn').exists()).toBe(true)
  })

  it('test_empty_state_shows_hint 无服务器时显示空状态', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    })
    const wrapper = mount(McpServerManager)
    await flushPromises()
    expect(wrapper.text()).toContain('暂无')
  })

  it('test_toggle_server_calls_toggle_api 切换服务器启用状态调用 API', async () => {
    // listMcpServers onMounted
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockServers,
    })
    // toggleMcpServer（注意：toggle 在列表项内，无需先 selectServer）
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    })
    const wrapper = mount(McpServerManager)
    await flushPromises()
    const items = wrapper.findAll('.server-item')
    expect(items.length).toBeGreaterThanOrEqual(1)
    const toggle = items[0].find('.server-toggle')
    expect(toggle.exists()).toBe(true)
    await toggle.setValue(false)
    await flushPromises()
    // 验证第二次 fetch 调用是 toggle（0=list, 1=toggle）
    const toggleCall = global.fetch.mock.calls[1]
    expect(toggleCall[0]).toContain('/toggle')
    expect(toggleCall[0]).toContain('enabled=false')
  })

  it('test_save_new_server_calls_create_api 保存新服务器调用 create API', async () => {
    // listMcpServers onMounted
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    })
    // createMcpServer
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ name: 'new' }),
    })
    // loadServers after save
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [{ name: 'new', display_name: '新', type: 'sse', enabled: true, tags: [] }],
    })
    const wrapper = mount(McpServerManager)
    await flushPromises()
    await wrapper.find('.new-server-btn').trigger('click')
    await wrapper.find('.save-btn').trigger('click')
    await flushPromises()
    const createCall = global.fetch.mock.calls[1]
    expect(createCall[0]).toBe('/api/admin/mcp/servers')
    expect(createCall[1].method).toBe('POST')
  })

  it('test_delete_server_calls_delete_api 删除服务器调用 delete API', async () => {
    global.window.confirm = vi.fn(() => true)
    // listMcpServers onMounted
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockServers,
    })
    // selectServer -> listMcpMethods
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    })
    // deleteMcpServer
    global.fetch.mockResolvedValueOnce({
      ok: true,
    })
    // loadServers after delete
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    })
    const wrapper = mount(McpServerManager)
    await flushPromises()
    const items = wrapper.findAll('.server-item')
    await items[0].trigger('click')
    await flushPromises()
    await wrapper.find('.delete-btn').trigger('click')
    await flushPromises()
    const deleteCall = global.fetch.mock.calls[2]
    expect(deleteCall[0]).toContain('/api/admin/mcp/servers/amap')
    expect(deleteCall[1].method).toBe('DELETE')
  })

  it('test_edit_server_populates_form 编辑服务器回填表单', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockServers,
    })
    // selectServer -> listMcpMethods
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    })
    const wrapper = mount(McpServerManager)
    await flushPromises()
    const items = wrapper.findAll('.server-item')
    await items[0].trigger('click')
    await flushPromises()
    await wrapper.find('.edit-btn').trigger('click')
    expect(wrapper.find('.server-form').exists()).toBe(true)
    // 验证表单已回填
    const nameInput = wrapper.find('input[placeholder="amap"]')
    expect(nameInput.element.value).toBe('amap')
  })

  it('test_toggle_method_calls_toggle_api 切换方法启用状态调用 API', async () => {
    const mockMethods = [
      { method_name: 'search', enabled: true, description: '搜索' },
    ]
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockServers,
    })
    // selectServer -> listMcpMethods
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockMethods,
    })
    // toggleMcpMethod
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    })
    const wrapper = mount(McpServerManager)
    await flushPromises()
    const items = wrapper.findAll('.server-item')
    await items[0].trigger('click')
    await flushPromises()
    const methodToggle = wrapper.find('.method-toggle-wrapper input[type="checkbox"]')
    expect(methodToggle.exists()).toBe(true)
    await methodToggle.setValue(false)
    await flushPromises()
    const toggleCall = global.fetch.mock.calls[2]
    expect(toggleCall[0]).toContain('/methods/search/toggle')
    expect(toggleCall[0]).toContain('enabled=false')
  })

  it('test_refresh_methods_calls_refresh_api 刷新方法列表调用 API', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockServers,
    })
    // selectServer -> listMcpMethods (first time)
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    })
    // refreshMcpMethods
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ methods_count: 2 }),
    })
    // listMcpMethods (second time, after refresh)
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [{ method_name: 'search', enabled: true }],
    })
    const wrapper = mount(McpServerManager)
    await flushPromises()
    const items = wrapper.findAll('.server-item')
    await items[0].trigger('click')
    await flushPromises()
    await wrapper.find('.refresh-methods-btn').trigger('click')
    await flushPromises()
    const refreshCall = global.fetch.mock.calls[2]
    expect(refreshCall[0]).toContain('/refresh-methods')
    expect(refreshCall[1].method).toBe('POST')
  })
})
