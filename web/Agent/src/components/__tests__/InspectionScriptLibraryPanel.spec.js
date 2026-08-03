/**
 * InspectionScriptLibraryPanel 单元测试（2026-08-04 新增）
 *
 * 覆盖：搜索框渲染、节点列表渲染、搜索过滤、点击节点派发 select 事件。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

describe('InspectionScriptLibraryPanel（巡检脚本库左侧节点列表）', () => {
  beforeEach(() => {
    global.fetch = vi.fn()
  })

  it('test_renders_search_box_and_list 渲染搜索框与节点列表', async () => {
    const { default: Panel } = await import('../InspectionScriptLibraryPanel.vue')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ([
        { id: 1, name: 'linux-bash', display_name: 'Linux Bash', platform: 'linux' },
        { id: 2, name: 'windows-ps-5.1', display_name: 'Windows PS 5.1', platform: 'windows' },
      ]),
    })
    const wrapper = mount(Panel)
    await flushPromises()
    expect(wrapper.find('[data-testid="library-search-input"]').exists()).toBe(true)
    const items = wrapper.findAll('[data-testid="library-node-item"]')
    expect(items.length).toBe(2)
  })

  it('test_search_filters_list 搜索词过滤节点', async () => {
    const { default: Panel } = await import('../InspectionScriptLibraryPanel.vue')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ([
        { id: 1, name: 'linux-bash', display_name: 'Linux Bash', platform: 'linux' },
        { id: 2, name: 'windows-ps-5.1', display_name: 'Windows PS 5.1', platform: 'windows' },
      ]),
    })
    const wrapper = mount(Panel)
    await flushPromises()
    await wrapper.find('[data-testid="library-search-input"]').setValue('windows')
    await flushPromises()
    const items = wrapper.findAll('[data-testid="library-node-item"]')
    expect(items.length).toBe(1)
    expect(items[0].text()).toContain('Windows')
  })

  it('test_click_emits_select 点击节点派发 select 事件', async () => {
    const { default: Panel } = await import('../InspectionScriptLibraryPanel.vue')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ([{ id: 7, name: 'linux-bash', display_name: 'Linux Bash' }]),
    })
    const wrapper = mount(Panel)
    await flushPromises()
    await wrapper.find('[data-testid="library-node-item"]').trigger('click')
    expect(wrapper.emitted('select')?.[0]?.[0]).toBe(7)
  })

  it('test_load_failure_shows_alert 加载失败显示错误提示', async () => {
    const { default: Panel } = await import('../InspectionScriptLibraryPanel.vue')
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'service down' }),
    })
    const wrapper = mount(Panel)
    await flushPromises()
    expect(wrapper.find('[data-testid="library-error"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('service down')
  })
})
