/**
 * InspectionScriptLibraryPanel unit tests (2026-08-04)
 *
 * Covers search box rendering, list rendering, search filtering,
 * click-to-select, load failure alert, delete button per row,
 * confirm-cancel-DELETE interaction and DELETE failure desensitized error.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

describe('InspectionScriptLibraryPanel', () => {
  let confirmSpy

  beforeEach(() => {
    global.fetch = vi.fn()
    // happy-dom does not implement window.confirm by default
    if (typeof window.confirm !== 'function') {
      window.confirm = () => true
    }
    confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  afterEach(() => {
    if (confirmSpy) confirmSpy.mockRestore()
  })

  it('test_renders_search_box_and_list', async () => {
    const m = await import('../InspectionScriptLibraryPanel.vue')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [
        { id: 1, name: 'linux-bash', display_name: 'Linux Bash', platform: 'linux' },
        { id: 2, name: 'windows-ps-5.1', display_name: 'Windows PS 5.1', platform: 'windows' },
      ],
    })
    const wrapper = mount(m.default)
    await flushPromises()
    expect(wrapper.find('[data-testid="library-search-input"]').exists()).toBe(true)
    const items = wrapper.findAll('[data-testid="library-node-item"]')
    expect(items.length).toBe(2)
  })

  it('test_search_filters_list', async () => {
    const m = await import('../InspectionScriptLibraryPanel.vue')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [
        { id: 1, name: 'linux-bash', display_name: 'Linux Bash', platform: 'linux' },
        { id: 2, name: 'windows-ps-5.1', display_name: 'Windows PS 5.1', platform: 'windows' },
      ],
    })
    const wrapper = mount(m.default)
    await flushPromises()
    await wrapper.find('[data-testid="library-search-input"]').setValue('windows')
    await flushPromises()
    const items = wrapper.findAll('[data-testid="library-node-item"]')
    expect(items.length).toBe(1)
    expect(items[0].text()).toContain('Windows')
  })

  it('test_click_emits_select', async () => {
    const m = await import('../InspectionScriptLibraryPanel.vue')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [{ id: 7, name: 'linux-bash', display_name: 'Linux Bash' }],
    })
    const wrapper = mount(m.default)
    await flushPromises()
    await wrapper.find('[data-testid="library-node-item"]').trigger('click')
    expect(wrapper.emitted('select') && wrapper.emitted('select')[0][0]).toBe(7)
  })

  it('test_load_failure_shows_alert', async () => {
    const m = await import('../InspectionScriptLibraryPanel.vue')
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'service down' }),
    })
    const wrapper = mount(m.default)
    await flushPromises()
    expect(wrapper.find('[data-testid="library-error"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('service down')
  })

  it('test_refresh_token_reload_list 刷新信号变化后重新加载列表', async () => {
    const m = await import('../InspectionScriptLibraryPanel.vue')
    global.fetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          { id: 1, name: 'linux-bash', display_name: 'Linux Bash', platform: 'linux' },
        ],
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          { id: 1, name: 'linux-bash', display_name: 'Linux Bash', platform: 'linux' },
          { id: 2, name: 'windows-ps', display_name: 'Windows PowerShell', platform: 'windows' },
        ],
      })
    const wrapper = mount(m.default, { props: { refreshToken: 0 } })
    await flushPromises()
    expect(wrapper.findAll('[data-testid="library-node-item"]')).toHaveLength(1)

    await wrapper.setProps({ refreshToken: 1 })
    await flushPromises()

    expect(global.fetch).toHaveBeenCalledTimes(2)
    expect(wrapper.findAll('[data-testid="library-node-item"]')).toHaveLength(2)
    expect(wrapper.text()).toContain('Windows PowerShell')
  })

  it('test_refresh_failure_shows_error 刷新失败后显示错误提示', async () => {
    const m = await import('../InspectionScriptLibraryPanel.vue')
    global.fetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          { id: 1, name: 'linux-bash', display_name: 'Linux Bash', platform: 'linux' },
        ],
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'refresh failed' }),
      })
    const wrapper = mount(m.default, { props: { refreshToken: 0 } })
    await flushPromises()

    await wrapper.setProps({ refreshToken: 1 })
    await flushPromises()

    expect(wrapper.find('[data-testid="library-error"]').text()).toContain('refresh failed')
    expect(wrapper.vm.scripts).toHaveLength(1)
  })

  it('test_delete_button_rendered_per_node', async () => {
    const m = await import('../InspectionScriptLibraryPanel.vue')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [
        { id: 1, name: 'linux-bash', display_name: 'Linux Bash', platform: 'linux' },
        { id: 2, name: 'windows-ps-5.1', display_name: 'Windows PS 5.1', platform: 'windows' },
      ],
    })
    const wrapper = mount(m.default)
    await flushPromises()
    const btns = wrapper.findAll('[data-testid="library-node-delete-btn"]')
    expect(btns.length).toBe(2)
    // 复用 UserServerManager 风格：纯文本图标 ×，无背景 / 无边框
    btns.forEach((btn) => {
      expect(btn.text()).toBe('×')
    })
    // 同时给每个节点提供编辑按钮（hover 才显示的 icon-btn）
    const editBtns = wrapper.findAll('[data-testid="library-node-edit-btn"]')
    expect(editBtns.length).toBe(2)
  })

  it('test_delete_confirm_calls_api_and_removes_node', async () => {
    const m = await import('../InspectionScriptLibraryPanel.vue')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [
        { id: 1, name: 'linux-bash', display_name: 'Linux Bash', platform: 'linux' },
        { id: 2, name: 'windows-ps-5.1', display_name: 'Windows PS 5.1', platform: 'windows' },
      ],
    })
    global.fetch.mockResolvedValueOnce({
      ok: true,
      status: 204,
      json: async () => {
        throw new Error('no body')
      },
    })
    const wrapper = mount(m.default)
    await flushPromises()
    const items = wrapper.findAll('[data-testid="library-node-item"]')
    expect(items.length).toBe(2)
    const btns = wrapper.findAll('[data-testid="library-node-delete-btn"]')
    await btns[0].trigger('click')
    await flushPromises()
    expect(confirmSpy).toHaveBeenCalledTimes(1)
    expect(global.fetch).toHaveBeenCalledTimes(2)
    const deleteCall = global.fetch.mock.calls[1]
    expect(deleteCall[0]).toContain('/api/admin/inspection-scripts/1')
    const opts = deleteCall[1] || {}
    expect(opts.method).toBe('DELETE')
    const after = wrapper.findAll('[data-testid="library-node-item"]')
    expect(after.length).toBe(1)
    expect(after[0].text()).toContain('Windows')
  })

  it('test_delete_cancel_does_not_call_api', async () => {
    const m = await import('../InspectionScriptLibraryPanel.vue')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [{ id: 1, name: 'linux-bash', display_name: 'Linux Bash' }],
    })
    confirmSpy.mockReturnValueOnce(false)
    const wrapper = mount(m.default)
    await flushPromises()
    const btn = wrapper.find('[data-testid="library-node-delete-btn"]')
    await btn.trigger('click')
    await flushPromises()
    expect(confirmSpy).toHaveBeenCalledTimes(1)
    expect(global.fetch).toHaveBeenCalledTimes(1)
    expect(wrapper.findAll('[data-testid="library-node-item"]').length).toBe(1)
  })

  it('test_delete_emits_select_null_when_deleting_selected_node', async () => {
    const m = await import('../InspectionScriptLibraryPanel.vue')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [{ id: 5, name: 'linux-bash', display_name: 'Linux Bash' }],
    })
    global.fetch.mockResolvedValueOnce({
      ok: true,
      status: 204,
      json: async () => {
        throw new Error('no body')
      },
    })
    const wrapper = mount(m.default)
    await flushPromises()
    await wrapper.find('[data-testid="library-node-item"]').trigger('click')
    expect(wrapper.emitted('select') && wrapper.emitted('select')[0][0]).toBe(5)
    await wrapper.find('[data-testid="library-node-delete-btn"]').trigger('click')
    await flushPromises()
    const selectEvents = wrapper.emitted('select')
    expect(selectEvents).toBeTruthy()
    expect(selectEvents[selectEvents.length - 1][0]).toBeNull()
  })

  it('test_delete_failure_shows_error_alert', async () => {
    const m = await import('../InspectionScriptLibraryPanel.vue')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [{ id: 1, name: 'linux-bash', display_name: 'Linux Bash' }],
    })
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'sensitive detail' }),
    })
    const wrapper = mount(m.default)
    await flushPromises()
    await wrapper.find('[data-testid="library-node-delete-btn"]').trigger('click')
    await flushPromises()
    const err = wrapper.find('[data-testid="library-error"]')
    expect(err.exists()).toBe(true)
    expect(err.text()).toBe('删除失败，请稍后重试')
    expect(err.text()).not.toContain('sensitive detail')
    // DELETE 失败时，列表项不应该从 scripts.value 中移除
    // 当前实现：errorMessage 非空时整个 ul 隐藏（仅显示错误提示）；
    // 实际数据源 scripts.value 仍含原项，刷新或 errorMessage 清空后即可恢复
    expect(wrapper.vm.scripts.length).toBe(1)
  })

  it('test_delete_button_click_does_not_trigger_row_select', async () => {
    const m = await import('../InspectionScriptLibraryPanel.vue')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [{ id: 1, name: 'linux-bash', display_name: 'Linux Bash' }],
    })
    const wrapper = mount(m.default)
    await flushPromises()
    const item = wrapper.find('[data-testid="library-node-item"]')
    await item.trigger('click')
    expect(wrapper.emitted('select') && wrapper.emitted('select')[0][0]).toBe(1)
    confirmSpy.mockReturnValueOnce(false)
    await wrapper.find('[data-testid="library-node-delete-btn"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('select').length).toBe(1)
  })
})
