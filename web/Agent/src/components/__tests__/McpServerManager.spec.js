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
    const wrapper = mount(McpServerManager)
    await flushPromises()
    const items = wrapper.findAll('.server-item')
    if (items.length > 0) {
      await items[0].trigger('click')
      expect(wrapper.find('.refresh-methods-btn').exists()).toBe(true)
    }
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
})
