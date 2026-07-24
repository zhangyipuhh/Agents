/**
 * ImportServerDialog 组件测试（2026-07-24 新增）
 *
 * 覆盖：
 *  - 弹窗打开时拉取 devops_servers 列表
 *  - label 卡片方式罗列服务器（server-option__label 样式）
 *  - 搜索框按 business_name 过滤
 *  - 多选 / 全选 / 取消全选
 *  - 确认按钮 disabled 条件（未勾选 / 提交中）
 *  - 确认按钮点击 → 调 import 接口 + emit 'done'
 *  - 取消按钮 / 点击遮罩 → emit 'close'
 *  - ESC 键关闭弹窗
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ImportServerDialog from '../ImportServerDialog.vue'

const mockDevopsServers = [
  { id: 100, business_name: 'web-server-01', server_type: 'linux', updated_at: '2026-07-24' },
  { id: 101, business_name: 'web-server-02', server_type: 'linux', updated_at: '2026-07-24' },
  { id: 102, business_name: 'db-server-01', server_type: 'windows', updated_at: '2026-07-24' },
]

function jsonResponse(data, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => data }
}

function setupFetchMock() {
  global.fetch = vi.fn(async (url, opts = {}) => {
    const method = (opts.method || 'GET').toUpperCase()
    const u = typeof url === 'string' ? url : url.url
    if (u === '/api/admin/devops-servers' && method === 'GET') {
      return jsonResponse(mockDevopsServers)
    }
    if (u === '/api/admin/user-servers/import' && method === 'POST') {
      const body = JSON.parse(opts.body)
      return jsonResponse({
        imported: body.business_names.length,
        skipped: 0,
        failed: 0,
        node_ids: [200, 201]
      })
    }
    return jsonResponse({})
  })
}

async function mountDialog(props = {}) {
  const wrapper = mount(ImportServerDialog, { props: { parentId: null, ...props } })
  await flushPromises()
  return wrapper
}

describe('ImportServerDialog 组件', () => {
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
  })

  afterEach(() => {
    global.fetch = originalFetch
    global.localStorage = originalLocalStorage
  })

  it('test_component_importable 组件可被 import', () => {
    expect(ImportServerDialog).toBeDefined()
  })

  it('test_loads_servers_on_mount mount 时拉取 devops_servers 列表', async () => {
    const wrapper = await mountDialog()
    expect(wrapper.find('[data-testid="isd-server-list"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('web-server-01')
    expect(wrapper.text()).toContain('web-server-02')
    expect(wrapper.text()).toContain('db-server-01')
  })

  it('test_uses_label_card_style 列表使用 server-option__label 样式', async () => {
    const wrapper = await mountDialog()
    // 至少有一张 label 卡片
    const labels = wrapper.findAll('label.server-option__label')
    expect(labels.length).toBe(3)
  })

  it('test_search_filters_servers 搜索框按 business_name 过滤', async () => {
    const wrapper = await mountDialog()
    await wrapper.find('[data-testid="isd-search-input"]').setValue('web')
    await flushPromises()
    expect(wrapper.text()).toContain('web-server-01')
    expect(wrapper.text()).toContain('web-server-02')
    expect(wrapper.text()).not.toContain('db-server-01')
  })

  it('test_toggle_selection 单选切换勾选状态', async () => {
    const wrapper = await mountDialog()
    // 勾选 web-server-01
    await wrapper.find('[data-testid="isd-option-100"]').setChecked()
    await flushPromises()
    expect(wrapper.find('[data-testid="isd-selected-count"]').text()).toContain('已选 1')

    // 取消勾选
    await wrapper.find('[data-testid="isd-option-100"]').setChecked(false)
    await flushPromises()
    expect(wrapper.find('[data-testid="isd-selected-count"]').text()).toContain('已选 0')
  })

  it('test_confirm_button_disabled_when_no_selection 未勾选时确认按钮 disabled', async () => {
    const wrapper = await mountDialog()
    const confirmBtn = wrapper.find('[data-testid="isd-confirm"]')
    expect(confirmBtn.attributes('disabled')).toBeDefined()
  })

  it('test_select_all 全选当前可见项', async () => {
    const wrapper = await mountDialog()
    // 搜索过滤到 2 个 web server
    await wrapper.find('[data-testid="isd-search-input"]').setValue('web')
    await flushPromises()
    // 全选
    await wrapper.find('[data-testid="isd-select-all"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="isd-selected-count"]').text()).toContain('已选 2')
  })

  it('test_confirm_calls_import_and_emits_done 确认导入调 import 接口并 emit done', async () => {
    const wrapper = await mountDialog({ parentId: 5 })
    await wrapper.find('[data-testid="isd-option-100"]').setChecked()
    await wrapper.find('[data-testid="isd-option-101"]').setChecked()
    await flushPromises()
    await wrapper.find('[data-testid="isd-confirm"]').trigger('click')
    await flushPromises()

    const importCall = global.fetch.mock.calls.find(
      ([url, opts]) => url === '/api/admin/user-servers/import' && opts.method === 'POST'
    )
    expect(importCall).toBeTruthy()
    const body = JSON.parse(importCall[1].body)
    expect(body.parent_id).toBe(5)
    expect(body.business_names).toEqual(['web-server-01', 'web-server-02'])

    // 触发 done 事件
    expect(wrapper.emitted('done')).toBeTruthy()
    expect(wrapper.emitted('done')[0][0]).toMatchObject({
      imported: 2,
      skipped: 0,
      failed: 0
    })
  })

  it('test_cancel_button_emits_close 取消按钮 emit close', async () => {
    const wrapper = await mountDialog()
    await wrapper.find('[data-testid="isd-cancel"]').trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('test_overlay_click_emits_close 点击遮罩 emit close', async () => {
    const wrapper = await mountDialog()
    await wrapper.find('[data-testid="isd-overlay"]').trigger('click.self')
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('test_esc_key_emits_close ESC 键 emit close', async () => {
    const wrapper = await mountDialog()
    // 触发 keydown 事件
    const escapeEvent = new KeyboardEvent('keydown', { key: 'Escape' })
    document.dispatchEvent(escapeEvent)
    await flushPromises()
    expect(wrapper.emitted('close')).toBeTruthy()
  })
})
