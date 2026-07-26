/**
 * TriggerPanel 测试（2026-07-26 新增）
 *
 * 覆盖：
 *   - 基础渲染（搜索框、列表）
 *   - 搜索过滤（按 searchKeys OR 匹配，case-insensitive）
 *   - 加载 / 错误 / 空态
 *   - 键盘导航（ArrowDown / ArrowUp / Enter / Escape）
 *   - 鼠标点击 select
 *   - getItemKey / getItemLabel / getItemSubLabel 契约
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import TriggerPanel from '../TriggerPanel.vue'

const sampleItems = () => [
  { business_name: 'prod-api', server_type: 'linux' },
  { business_name: 'prod-db', server_type: 'linux' },
  { business_name: 'win-01', server_type: 'windows' },
]

const makePanel = (overrides = {}) => {
  const items = overrides.items ?? sampleItems()
  return mount(TriggerPanel, {
    props: {
      triggerId: 'server',
      items,
      searchKeys: ['business_name', 'server_type'],
      activeIndex: 0,
      loading: false,
      error: '',
      emptyHint: '暂无可引用项',
      searchPlaceholder: '搜索服务器...',
      getItemKey: (item) => item?.business_name,
      getItemLabel: (item) => item?.business_name,
      getItemSubLabel: (item) => (item?.server_type ? `[${item.server_type}]` : ''),
      ...overrides,
    },
  })
}

describe('TriggerPanel 通用触发面板', () => {
  beforeEach(() => {})

  it('test_panel_importable 组件可被 import', () => {
    expect(TriggerPanel).toBeDefined()
  })

  it('test_panel_renders_search_input_and_items 渲染搜索框与列表项', async () => {
    const wrapper = makePanel()
    await flushPromises()
    expect(wrapper.find('[data-testid="trigger-panel-search-server"]').exists()).toBe(true)
    const items = wrapper.findAll('[data-testid^="trigger-panel-item-server-"]')
    expect(items.length).toBe(3)
  })

  it('test_panel_shows_loading_state loading=true 显示加载态', () => {
    const wrapper = makePanel({ loading: true })
    expect(wrapper.text()).toContain('加载中')
  })

  it('test_panel_shows_error_state error 非空时显示错误', () => {
    const wrapper = makePanel({ error: '加载失败' })
    expect(wrapper.text()).toContain('加载失败')
  })

  it('test_panel_shows_empty_state items 为空时显示空态', () => {
    const wrapper = makePanel({ items: [] })
    expect(wrapper.text()).toContain('暂无可引用项')
  })

  it('test_search_filters_by_search_keys 搜索按 searchKeys OR 匹配', async () => {
    const wrapper = makePanel()
    await flushPromises()
    await wrapper.find('[data-testid="trigger-panel-search-server"]').setValue('linux')
    const items = wrapper.findAll('[data-testid^="trigger-panel-item-server-"]')
    expect(items.length).toBe(2)
    expect(wrapper.text()).toContain('prod-api')
    expect(wrapper.text()).toContain('prod-db')
  })

  it('test_search_is_case_insensitive 搜索不区分大小写', async () => {
    const wrapper = makePanel()
    await flushPromises()
    await wrapper.find('[data-testid="trigger-panel-search-server"]').setValue('WIN')
    const items = wrapper.findAll('[data-testid^="trigger-panel-item-server-"]')
    expect(items.length).toBe(1)
    expect(wrapper.text()).toContain('win-01')
  })

  it('test_arrow_down_increments_active_index ArrowDown 增加 activeIndex 并 emit', async () => {
    const wrapper = makePanel()
    await flushPromises()
    const input = wrapper.find('[data-testid="trigger-panel-search-server"]')
    await input.trigger('keydown', { key: 'ArrowDown' })
    const updates = wrapper.emitted('update:activeIndex')
    expect(updates).toBeTruthy()
    expect(updates[0]).toEqual([1])
  })

  it('test_arrow_up_wraps_to_last ArrowUp 在第一项时回到最后一项', async () => {
    const wrapper = makePanel({ activeIndex: 0 })
    await flushPromises()
    const input = wrapper.find('[data-testid="trigger-panel-search-server"]')
    await input.trigger('keydown', { key: 'ArrowUp' })
    const updates = wrapper.emitted('update:activeIndex')
    expect(updates[0]).toEqual([2])
  })

  it('test_enter_emits_select_with_active_item Enter 触发当前 activeIndex 项的 select', async () => {
    const wrapper = makePanel({ activeIndex: 1 })
    await flushPromises()
    const input = wrapper.find('[data-testid="trigger-panel-search-server"]')
    await input.trigger('keydown', { key: 'Enter' })
    const selects = wrapper.emitted('select')
    expect(selects).toBeTruthy()
    expect(selects[0][0].business_name).toBe('prod-db')
  })

  it('test_escape_emits_select_with_null Escape 触发 select(null)', async () => {
    const wrapper = makePanel()
    await flushPromises()
    const input = wrapper.find('[data-testid="trigger-panel-search-server"]')
    await input.trigger('keydown', { key: 'Escape' })
    const selects = wrapper.emitted('select')
    expect(selects).toBeTruthy()
    expect(selects[0][0]).toBeNull()
  })

  it('test_click_item_emits_select 点击列表项 emit select(item)', async () => {
    const wrapper = makePanel()
    await flushPromises()
    const item = wrapper.find('[data-testid="trigger-panel-item-server-0"]')
    await item.trigger('mousedown')
    const selects = wrapper.emitted('select')
    expect(selects[0][0].business_name).toBe('prod-api')
  })

  it('test_mouse_enter_updates_active_index 鼠标进入更新 activeIndex', async () => {
    const wrapper = makePanel({ activeIndex: 0 })
    await flushPromises()
    const item = wrapper.find('[data-testid="trigger-panel-item-server-2"]')
    await item.trigger('mouseenter')
    const updates = wrapper.emitted('update:activeIndex')
    expect(updates[updates.length - 1]).toEqual([2])
  })
})