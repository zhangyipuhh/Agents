/**
 * InspectionScriptEditorPanel 单元测试（2026-08-04 新增；2026-09-16 重构）
 *
 * 覆盖：
 *   - 空态显示 / 拉取详情 / 保存触发 PUT / 保存失败脱敏
 *   - 字段规则 CRUD（保留单表格，组级共享）
 *   - 保存 payload 保留 ssd_warn/ssd_crit（保留为单条契约）
 *   - 2026-09-16 新增:分段 UI 渲染 / /启用翻转 / /脏检测 / /失败聚合 / /legacy 只读折叠
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const SEGMENT_DETAIL_BASE = (overrides = {}) => ({
  id: 1, name: 'linux-bash', display_name: 'Linux Bash',
  platform: 'linux', version: 'bash', inspection_parser: 'json',
  inspection_script: null, inspection_fields: [],
  created_at: null, updated_at: '2026-08-04',
  ...overrides,
})

const SEGMENT_SEGMENTS_BASE = [
  { id: 10, script_id: 1, segment_key: 'cpu', display_name: 'CPU',
    sort_order: 40, script: 'echo c', enabled: true,
    created_at: null, updated_at: null },
  { id: 11, script_id: 1, segment_key: 'memory', display_name: '内存',
    sort_order: 30, script: 'echo m', enabled: true,
    created_at: null, updated_at: null },
]

describe('InspectionScriptEditorPanel（巡检脚本库右侧编辑）', () => {
  beforeEach(() => {
    global.fetch = vi.fn()
    // 默认:detail + segments 都返成功;detail=SEGMENT_DETAIL_BASE, segments=SEGMENT_SEGMENTS_BASE
    global.fetch.mockImplementation((url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      if (url.endsWith('/segments')) {
        return Promise.resolve({
          ok: true,
          json: async () => JSON.parse(JSON.stringify(SEGMENT_SEGMENTS_BASE)),
        })
      }
      if (method === 'PUT' || method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: async () => JSON.parse(JSON.stringify(SEGMENT_DETAIL_BASE())),
        })
      }
      return Promise.resolve({
        ok: true,
        json: async () => JSON.parse(JSON.stringify(SEGMENT_DETAIL_BASE())),
      })
    })
  })

  it('test_empty_state_when_no_id scriptId 为空显示空态', async () => {
    const { default: Editor } = await import('../InspectionScriptEditorPanel.vue')
    const wrapper = mount(Editor, { props: { scriptId: null } })
    await flushPromises()
    expect(wrapper.find('[data-testid="editor-empty"]').exists()).toBe(true)
  })

  it('test_loads_detail_on_id 注入 scriptId 时拉取详情 + 分段', async () => {
    const { default: Editor } = await import('../InspectionScriptEditorPanel.vue')
    const wrapper = mount(Editor, { props: { scriptId: 1 } })
    await flushPromises()
    expect(wrapper.find('[data-testid="editor-form"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="editor-display-name"]').element.value).toBe('Linux Bash')
    // 2026-09-16 新增:分段卡片按 segments 数组渲染
    expect(wrapper.findAll('[data-testid^="editor-segment-card-"]').length).toBe(SEGMENT_SEGMENTS_BASE.length)
  })

  it('test_save_button_triggers_put 点击保存触发 PUT（不发送 inspection_script）', async () => {
    const { default: Editor } = await import('../InspectionScriptEditorPanel.vue')
    // 全局 mock:GET 返 detail + segments;PUT 返带「(改)」后缀的 detail
    global.fetch.mockImplementation((url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      if (url.endsWith('/segments') && method === 'GET') {
        return Promise.resolve({
          ok: true,
          json: async () => JSON.parse(JSON.stringify(SEGMENT_SEGMENTS_BASE)),
        })
      }
      if (method === 'PUT' && url === '/api/admin/inspection-scripts/1') {
        return Promise.resolve({
          ok: true,
          json: async () => JSON.parse(JSON.stringify(
            SEGMENT_DETAIL_BASE({ display_name: 'Linux Bash (改)' })
          )),
        })
      }
      return Promise.resolve({
        ok: true,
        json: async () => JSON.parse(JSON.stringify(SEGMENT_DETAIL_BASE())),
      })
    })
    const wrapper = mount(Editor, { props: { scriptId: 1 } })
    await flushPromises()
    const input = wrapper.find('[data-testid="editor-display-name"]')
    await input.setValue('Linux Bash (改)')
    await flushPromises()
    expect(input.element.value).toBe('Linux Bash (改)')
    const saveBtn = wrapper.find('[data-testid="editor-save-btn"]')
    expect(saveBtn.attributes('disabled')).toBeUndefined()
    await saveBtn.trigger('click')
    const form = wrapper.find('[data-testid="editor-form"]')
    await form.trigger('submit.prevent')
    await flushPromises()
    const calls = global.fetch.mock.calls.filter(([, opts]) => opts?.method === 'PUT')
    expect(calls.length).toBe(1)
    expect(calls[0][0]).toBe('/api/admin/inspection-scripts/1')
    // 2026-09-16 D4:payload 不再含 inspection_script / segments
    const body = JSON.parse(calls[0][1].body)
    expect(body).not.toHaveProperty('inspection_script')
    expect(body).not.toHaveProperty('segments')
    expect(wrapper.emitted('saved')?.[0]?.[0]?.display_name).toBe('Linux Bash (改)')
    expect(wrapper.find('[data-testid="editor-success"]').exists()).toBe(true)
  })

  it('test_save_failure_shows_alert 保存失败显示脱敏提示', async () => {
    const { default: Editor } = await import('../InspectionScriptEditorPanel.vue')
    global.fetch.mockImplementation((url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      if (url.endsWith('/segments')) {
        return Promise.resolve({
          ok: true,
          json: async () => JSON.parse(JSON.stringify(SEGMENT_SEGMENTS_BASE)),
        })
      }
      if (method === 'PUT') {
        return Promise.resolve({
          ok: false,
          status: 500,
          json: async () => ({ detail: 'database down with sensitive info' }),
        })
      }
      return Promise.resolve({
        ok: true,
        json: async () => JSON.parse(JSON.stringify(SEGMENT_DETAIL_BASE({ display_name: 'X' }))),
      })
    })
    const wrapper = mount(Editor, { props: { scriptId: 1 } })
    await flushPromises()
    await wrapper.find('[data-testid="editor-save-btn"]').trigger('click')
    const form = wrapper.find('[data-testid="editor-form"]')
    await form.trigger('submit.prevent')
    await flushPromises()
    expect(wrapper.find('[data-testid="editor-error"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('保存失败')
    // 脱敏:不回显后端 detail
    expect(wrapper.text()).not.toContain('sensitive')
  })

  it('test_field_rule_add_remove 字段规则可新增 / 删除', async () => {
    const { default: Editor } = await import('../InspectionScriptEditorPanel.vue')
    global.fetch.mockImplementation((url, opts = {}) => {
      if (url.endsWith('/segments')) {
        return Promise.resolve({ ok: true, json: async () => [] })
      }
      return Promise.resolve({
        ok: true,
        json: async () => JSON.parse(JSON.stringify(
          SEGMENT_DETAIL_BASE({
            inspection_fields: [
              { key: 'cpu', name_zh: 'CPU', unit: '%', direction: 'high', warn: 80, crit: 90 },
            ],
          })
        )),
      })
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
    const detail = SEGMENT_DETAIL_BASE({
      inspection_fields: [
        { key: 'io_await_ms', name_zh: 'IO等待', unit: 'ms', direction: 'high',
          warn: 100, crit: 200, ssd_warn: 20, ssd_crit: 50 },
      ],
    })
    global.fetch.mockImplementation((url, opts = {}) => {
      if (url.endsWith('/segments')) {
        return Promise.resolve({ ok: true, json: async () => [] })
      }
      return Promise.resolve({ ok: true, json: async () => JSON.parse(JSON.stringify(detail)) })
    })
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

  // ============================== 2026-09-16 新增分段用例 ==============================

  it('test_segments_loaded_after_detail 详情含 segments 字段则渲染段卡片', async () => {
    const { default: Editor } = await import('../InspectionScriptEditorPanel.vue')
    const wrapper = mount(Editor, { props: { scriptId: 1 } })
    await flushPromises()
    const cards = wrapper.findAll('[data-testid^="editor-segment-card-"]')
    expect(cards.length).toBe(SEGMENT_SEGMENTS_BASE.length)
    // 段头含 segment_key(只读展示)
    expect(wrapper.text()).toContain('cpu')
    expect(wrapper.text()).toContain('memory')
  })

  it('test_segment_toggle_enabled 点击 enabled 复选框翻转状态', async () => {
    const { default: Editor } = await import('../InspectionScriptEditorPanel.vue')
    const wrapper = mount(Editor, { props: { scriptId: 1 } })
    await flushPromises()
    const cb0 = wrapper.find('[data-testid="editor-segment-enabled-0"]')
    expect(cb0.element.checked).toBe(true)
    await cb0.setChecked(false)
    await flushPromises()
    expect(cb0.element.checked).toBe(false)
  })

  it('test_segment_save_sends_dirty_only 修改 1 段 → 仅触发 1 个 PUT', async () => {
    const { default: Editor } = await import('../InspectionScriptEditorPanel.vue')
    global.fetch.mockImplementation((url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      if (url.endsWith('/segments')) {
        // 第 1 次:GET 返回原始 segments
        // 第 2 次:GET 模拟「保存后再拉」场景,这里 mock 直接返最新内存
        return Promise.resolve({
          ok: true,
          json: async () => JSON.parse(JSON.stringify(SEGMENT_SEGMENTS_BASE)),
        })
      }
      if (method === 'PUT') {
        return Promise.resolve({
          ok: true,
          json: async () => JSON.parse(JSON.stringify(SEGMENT_SEGMENTS_BASE[0])),
        })
      }
      return Promise.resolve({
        ok: true,
        json: async () => JSON.parse(JSON.stringify(SEGMENT_DETAIL_BASE())),
      })
    })
    const wrapper = mount(Editor, { props: { scriptId: 1 } })
    await flushPromises()
    // 改第 0 段(cpu)的 display_name → dirty=true
    await wrapper.find('[data-testid="editor-segment-display-name-0"]').setValue('CPU 改')
    await flushPromises()
    await wrapper.find('[data-testid="editor-save-segments-btn"]').trigger('click')
    await flushPromises()
    const segPutCalls = global.fetch.mock.calls.filter(
      ([url, opts]) => /\/segments\/\d+$/.test(url) && (opts?.method || 'GET').toUpperCase() === 'PUT'
    )
    expect(segPutCalls.length).toBe(1)
    expect(segPutCalls[0][0]).toBe('/api/admin/inspection-scripts/1/segments/10')
    const segBody = JSON.parse(segPutCalls[0][1].body)
    expect(segBody.display_name).toBe('CPU 改')
    expect(wrapper.find('[data-testid="editor-save-segments-status"]').exists()).toBe(true)
  })

  it('test_segment_save_partial_failure_shows_segment_error mock 1 段失败 → 该段卡片显示 segment-error', async () => {
    const { default: Editor } = await import('../InspectionScriptEditorPanel.vue')
    let putCount = 0
    global.fetch.mockImplementation((url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      if (url.endsWith('/segments')) {
        return Promise.resolve({
          ok: true,
          json: async () => JSON.parse(JSON.stringify(SEGMENT_SEGMENTS_BASE)),
        })
      }
      if (method === 'PUT' && /\/segments\/\d+$/.test(url)) {
        putCount++
        // 第 1 次 PUT(段 10 cpu)失败;其他成功
        if (url.endsWith('/segments/10')) {
          return Promise.resolve({
            ok: false,
            status: 400,
            json: async () => ({ detail: 'mock segment validation failed' }),
          })
        }
        return Promise.resolve({
          ok: true,
          json: async () => JSON.parse(JSON.stringify(SEGMENT_SEGMENTS_BASE[1])),
        })
      }
      return Promise.resolve({
        ok: true,
        json: async () => JSON.parse(JSON.stringify(SEGMENT_DETAIL_BASE())),
      })
    })
    const wrapper = mount(Editor, { props: { scriptId: 1 } })
    await flushPromises()
    // 改两段都触发 PUT
    await wrapper.find('[data-testid="editor-segment-display-name-0"]').setValue('CPU 改')
    await wrapper.find('[data-testid="editor-segment-display-name-1"]').setValue('MEM 改')
    await flushPromises()
    await wrapper.find('[data-testid="editor-save-segments-btn"]').trigger('click')
    await flushPromises()
    expect(putCount).toBe(2)
    // 第 0 段(失败)显示 segment-error
    const err0 = wrapper.find('[data-testid="editor-segment-error-0"]')
    expect(err0.exists()).toBe(true)
    expect(wrapper.text()).toContain('mock segment validation failed')
    // 第 1 段(成功)无错误
    expect(wrapper.find('[data-testid="editor-segment-error-1"]').exists()).toBe(false)
    // 顶部 status 提示「部分成功」
    const status = wrapper.find('[data-testid="editor-save-segments-status"]')
    expect(status.text()).toContain('部分')
  })

  it('test_segment_legacy_combined_view_only_readonly 折叠区拼接各段脚本但无 textarea', async () => {
    const { default: Editor } = await import('../InspectionScriptEditorPanel.vue')
    const wrapper = mount(Editor, { props: { scriptId: 1 } })
    await flushPromises()
    // 折叠 details 元素存在(默认关闭)
    const legacy = wrapper.find('[data-testid="editor-legacy-pre"]')
    expect(legacy.exists()).toBe(true)
    // 该 <pre> 内容含拼接的段标记,无 <textarea>
    const text = legacy.text()
    expect(text).toContain('segment cpu')
    expect(text).toContain('echo c')
    expect(legacy.element.tagName.toLowerCase()).toBe('pre')
    // 折叠区内只能通过 data-testid 找到 <pre>;不应有 <textarea> 渲染该文本
    const legacyTextarea = legacy.findAll('textarea')
    expect(legacyTextarea.length).toBe(0)
  })
})