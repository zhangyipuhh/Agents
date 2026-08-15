/**
 * InspectionScriptEditorPanel 单元测试（2026-08-04 新增）
 *
 * 覆盖：空态显示 / 拉取详情 / 保存触发 PUT / 保存失败脱敏 / 字段规则 CRUD。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

describe('InspectionScriptEditorPanel（巡检脚本库右侧编辑）', () => {
  beforeEach(() => {
    global.fetch = vi.fn()
  })

  it('test_empty_state_when_no_id scriptId 为空显示空态', async () => {
    const { default: Editor } = await import('../InspectionScriptEditorPanel.vue')
    const wrapper = mount(Editor, { props: { scriptId: null } })
    await flushPromises()
    expect(wrapper.find('[data-testid="editor-empty"]').exists()).toBe(true)
  })

  it('test_loads_detail_on_id 注入 scriptId 时拉取详情', async () => {
    const { default: Editor } = await import('../InspectionScriptEditorPanel.vue')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        id: 1, name: 'linux-bash', display_name: 'Linux Bash',
        platform: 'linux', version: 'bash', inspection_parser: 'json',
        inspection_script: 'echo a', inspection_fields: [],
        created_at: null, updated_at: '2026-08-04',
      }),
    })
    const wrapper = mount(Editor, { props: { scriptId: 1 } })
    await flushPromises()
    expect(wrapper.find('[data-testid="editor-form"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="editor-display-name"]').element.value).toBe('Linux Bash')
  })

  it('test_save_button_triggers_put 点击保存触发 PUT', async () => {
    const { default: Editor } = await import('../InspectionScriptEditorPanel.vue')
    global.fetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 1, name: 'linux-bash', display_name: 'Linux Bash',
          platform: 'linux', version: 'bash', inspection_parser: 'json',
          inspection_script: 'echo a', inspection_fields: [],
          created_at: null, updated_at: '2026-08-04',
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 1, name: 'linux-bash', display_name: 'Linux Bash (改)',
          platform: 'linux', version: 'bash', inspection_parser: 'json',
          inspection_script: 'echo a', inspection_fields: [],
          created_at: null, updated_at: '2026-08-04',
        }),
      })
    const wrapper = mount(Editor, { props: { scriptId: 1 } })
    await flushPromises()
    const input = wrapper.find('[data-testid="editor-display-name"]')
    await input.setValue('Linux Bash (改)')
    await flushPromises()
    // 验证 v-model 已同步
    expect(input.element.value).toBe('Linux Bash (改)')
    // 验证 isFormValid 重新计算后按钮启用
    const saveBtn = wrapper.find('[data-testid="editor-save-btn"]')
    expect(saveBtn.attributes('disabled')).toBeUndefined()
    // 直接调 onSave（button type=submit 在 happy-dom 下 trigger('click') 不触发 form submit）
    await saveBtn.trigger('click')
    // 兼容：若 click 未触发，触发 form submit 兜底
    const form = wrapper.find('[data-testid="editor-form"]')
    await form.trigger('submit.prevent')
    await flushPromises()
    const calls = global.fetch.mock.calls.filter(([, opts]) => opts?.method === 'PUT')
    expect(calls.length).toBe(1)
    expect(calls[0][0]).toBe('/api/admin/inspection-scripts/1')
    expect(wrapper.emitted('saved')?.[0]?.[0]?.display_name).toBe('Linux Bash (改)')
    expect(wrapper.find('[data-testid="editor-success"]').exists()).toBe(true)
  })

  it('test_save_failure_shows_alert 保存失败显示脱敏提示', async () => {
    const { default: Editor } = await import('../InspectionScriptEditorPanel.vue')
    global.fetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 1, name: 'linux-bash', display_name: 'X',
          platform: 'linux', version: '', inspection_parser: 'json',
          inspection_script: null, inspection_fields: [],
        }),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'database down with sensitive info' }),
      })
    const wrapper = mount(Editor, { props: { scriptId: 1 } })
    await flushPromises()
    await wrapper.find('[data-testid="editor-save-btn"]').trigger('click')
    const form = wrapper.find('[data-testid="editor-form"]')
    await form.trigger('submit.prevent')
    await flushPromises()
    expect(wrapper.find('[data-testid="editor-error"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('保存失败')
    // 脱敏：不回显后端 detail
    expect(wrapper.text()).not.toContain('sensitive')
  })

  it('test_field_rule_add_remove 字段规则可新增 / 删除', async () => {
    const { default: Editor } = await import('../InspectionScriptEditorPanel.vue')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        id: 1, name: 'linux-bash', display_name: 'X',
        platform: 'linux', version: '', inspection_parser: 'json',
        inspection_script: null,
        inspection_fields: [
          { key: 'cpu', name_zh: 'CPU', unit: '%', direction: 'high', warn: 80, crit: 90 },
        ],
      }),
    })
    const wrapper = mount(Editor, { props: { scriptId: 1 } })
    await flushPromises()
    expect(wrapper.findAll('[data-testid="editor-field-row"]').length).toBe(1)
    await wrapper.find('[data-testid="editor-add-field-btn"]').trigger('click')
    expect(wrapper.findAll('[data-testid="editor-field-row"]').length).toBe(2)
    await wrapper.findAll('[data-testid="editor-remove-field-btn"]')[0].trigger('click')
    expect(wrapper.findAll('[data-testid="editor-field-row"]').length).toBe(1)
  })

  it('test_save_payload_preserves_ssd_thresholds 保存 payload 保留 ssd_warn/ssd_crit', async () => {
    const { default: Editor } = await import('../InspectionScriptEditorPanel.vue')
    const detail = {
      id: 1, name: 'linux-bash', display_name: 'X',
      platform: 'linux', version: '', inspection_parser: 'json',
      inspection_script: null,
      inspection_fields: [
        { key: 'io_await_ms', name_zh: 'IO等待', unit: 'ms', direction: 'high',
          warn: 100, crit: 200, ssd_warn: 20, ssd_crit: 50 },
      ],
    }
    global.fetch
      .mockResolvedValueOnce({ ok: true, json: async () => detail })
      .mockResolvedValueOnce({ ok: true, json: async () => detail })
    const wrapper = mount(Editor, { props: { scriptId: 1 } })
    await flushPromises()
    await wrapper.find('[data-testid="editor-save-btn"]').trigger('click')
    await wrapper.find('[data-testid="editor-form"]').trigger('submit.prevent')
    await flushPromises()
    const calls = global.fetch.mock.calls.filter(([, opts]) => opts?.method === 'PUT')
    expect(calls.length).toBe(1)
    const body = JSON.parse(calls[0][1].body)
    expect(body.inspection_fields[0].ssd_warn).toBe(20)
    expect(body.inspection_fields[0].ssd_crit).toBe(50)
  })
})
