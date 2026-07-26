/**
 * InputBox 「#」触发器集成测试（2026-07-26 新增）
 *
 * 覆盖：
 *   - 输入 `#` 触发 TriggerPanel
 *   - 词边界规则（C# 不触发）
 *   - 工具栏 `#` 按钮点击 = 键入（在光标处插入 # + 聚焦）
 *   - chips 渲染与移除
 *   - 发送携带 extras（referenced_servers）
 *   - 切换 session 清空 trigger 选择
 *   - 流式期间禁用 trigger 按钮
 */
import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import InputBox from '../InputBox.vue'

const mockUploadResult = {
  files: [{ filename: 'test.txt', stored_path: '/tmp/test.md', file_type: 'md' }]
}

vi.mock('../../utils/api.js', () => ({
  uploadFileInChunks: vi.fn(() => Promise.resolve(mockUploadResult)),
  formatFileSize: vi.fn((size) => `${size} bytes`),
  getFileExtension: vi.fn((name) => {
    const parts = name.split('.')
    return parts.length > 1 ? parts.pop() : ''
  }),
  refreshToken: vi.fn(() => Promise.resolve('fake-token')),
  fetchAgentList: vi.fn(() => Promise.resolve([])),
  deleteAttachments: vi.fn(() => Promise.resolve()),
  fetchUploadConfig: vi.fn(() => Promise.resolve({ max_file_size_mb: 3 })),
  // 2026-07-26 新增：triggerRegistry 数据源 mock（后端返回 { nodes: [...] }）
  fetchUserServerTree: vi.fn(() => Promise.resolve({
    nodes: [
      { id: 1, node_type: 'folder', name: '生产' },
      { id: 2, node_type: 'server', business_name: 'prod-api', server_type: 'linux' },
      { id: 3, node_type: 'server', business_name: 'win-01', server_type: 'windows' },
    ],
  })),
}))

beforeAll(() => {
  if (typeof window !== 'undefined' && !window.alert) {
    window.alert = () => {}
  }
})

const mountInputBox = (props = {}) =>
  mount(InputBox, {
    props: {
      sessionId: 'sid-001',
      isStreaming: false,
      currentProject: null,
      ensureSession: vi.fn(() => Promise.resolve('sid-001')),
      ...props,
    },
  })

const setTextareaValue = async (wrapper, value) => {
  const textarea = wrapper.find('textarea')
  await textarea.setValue(value)
  await textarea.trigger('input')
}

describe('InputBox 「#」触发器集成（2026-07-26 新增）', () => {
  beforeEach(() => {})

  it('test_hash_button_rendered 工具栏渲染 # 按钮（由 registry 驱动）', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    const btn = wrapper.find('[data-testid="trigger-btn-server"]')
    expect(btn.exists()).toBe(true)
  })

  it('test_typing_hash_opens_panel 输入 # 后 trigger 面板打开', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    await setTextareaValue(wrapper, '#', 1)
    await flushPromises()
    expect(wrapper.find('[data-testid="trigger-panel-server"]').exists()).toBe(true)
  })

  it('test_mid_word_hash_does_not_trigger C# 不触发面板（词边界）', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    await setTextareaValue(wrapper, 'C#', 2)
    await flushPromises()
    expect(wrapper.find('[data-testid="trigger-panel-server"]').exists()).toBe(false)
  })

  it('test_hash_after_whitespace_triggers 空白后 # 触发面板', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    await setTextareaValue(wrapper, 'hello #', 7)
    await flushPromises()
    expect(wrapper.find('[data-testid="trigger-panel-server"]').exists()).toBe(true)
  })

  it('test_click_hash_button_inserts_char 工具栏 # 按钮点击插入字符并触发面板', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    const textarea = wrapper.find('textarea')
    await textarea.setValue('hello')
    const btn = wrapper.find('[data-testid="trigger-btn-server"]')
    await btn.trigger('click')
    await flushPromises()
    // textarea 值应包含 #（无论插入位置如何，因 happy-dom 不保证光标持久化）
    expect(textarea.element.value).toContain('#')
    // 触发面板应打开
    expect(wrapper.find('[data-testid="trigger-panel-server"]').exists()).toBe(true)
  })

  it('test_selecting_server_emits_chip 选择服务器后渲染可移除 chip', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    // 打开面板
    await setTextareaValue(wrapper, '#', 1)
    await flushPromises()
    // 模拟面板选中第一项（prod-api）
    const triggerPanel = wrapper.findComponent({ name: 'TriggerPanel' })
    const items = wrapper.findAll('[data-testid^="trigger-panel-item-server-"]')
    expect(items.length).toBeGreaterThan(0)
    await items[0].trigger('mousedown')
    await flushPromises()
    // chip 应出现
    const chip = wrapper.find('[data-testid="selected-trigger-chip-server-prod-api"]')
    expect(chip.exists()).toBe(true)
    expect(chip.text()).toContain('prod-api')
    // 面板已关闭
    expect(wrapper.find('[data-testid="trigger-panel-server"]').exists()).toBe(false)
  })

  it('test_chip_remove_button_removes_chip chip 移除按钮可移除项', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    await setTextareaValue(wrapper, '#', 1)
    await flushPromises()
    const items = wrapper.findAll('[data-testid^="trigger-panel-item-server-"]')
    await items[0].trigger('mousedown')
    await flushPromises()
    const chip = wrapper.find('[data-testid="selected-trigger-chip-server-prod-api"]')
    expect(chip.exists()).toBe(true)
    await chip.find('.trigger-chip-remove-btn').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="selected-trigger-chip-server-prod-api"]').exists()).toBe(false)
  })

  it('test_send_carries_referenced_servers_in_extras 发送时 emit send 携带 extras.referenced_servers 且文本含前缀', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    // 选两项：先 # → 选 prod-api
    await setTextareaValue(wrapper, '#', 1)
    await flushPromises()
    let items = wrapper.findAll('[data-testid^="trigger-panel-item-server-"]')
    await items[0].trigger('mousedown')
    await flushPromises()
    // 再 # → 选 win-01
    await setTextareaValue(wrapper, '#', 1)
    await flushPromises()
    items = wrapper.findAll('[data-testid^="trigger-panel-item-server-"]')
    await items[1].trigger('mousedown')
    await flushPromises()
    // 输入文本后发送
    await wrapper.find('textarea').setValue('请巡检')
    await wrapper.find('.send-btn').trigger('click')
    await flushPromises()
    const sends = wrapper.emitted('send')
    expect(sends).toBeTruthy()
    const last = sends[sends.length - 1]
    // signature: send(text, files, extras)
    expect(last[0]).toBe('引用服务器：prod-api、win-01\n请巡检')
    expect(last[2].referenced_servers).toEqual([
      { name: 'prod-api', server_type: 'linux' },
      { name: 'win-01', server_type: 'windows' },
    ])
  })

  it('test_send_keeps_trigger_chips 发送成功后保留 trigger chips', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    await setTextareaValue(wrapper, '#', 1)
    await flushPromises()
    const items = wrapper.findAll('[data-testid^="trigger-panel-item-server-"]')
    await items[0].trigger('mousedown')
    await flushPromises()
    expect(wrapper.find('[data-testid="selected-trigger-chip-server-prod-api"]').exists()).toBe(true)
    await wrapper.find('textarea').setValue('hi')
    await wrapper.find('.send-btn').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="selected-trigger-chip-server-prod-api"]').exists()).toBe(true)
  })

  it('test_send_appends_server_prefix_to_text 发送文本前附加服务器引用前缀', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    await setTextareaValue(wrapper, '#', 1)
    await flushPromises()
    const items = wrapper.findAll('[data-testid^="trigger-panel-item-server-"]')
    await items[0].trigger('mousedown')
    await flushPromises()
    await wrapper.find('textarea').setValue('请检查磁盘')
    await wrapper.find('.send-btn').trigger('click')
    await flushPromises()
    const sends = wrapper.emitted('send')
    expect(sends).toBeTruthy()
    const last = sends[sends.length - 1]
    expect(last[0]).toBe('引用服务器：prod-api\n请检查磁盘')
  })

  it('test_session_change_clears_for_new_session 切换到新 session 时 trigger chips 为空', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    await setTextareaValue(wrapper, '#', 1)
    await flushPromises()
    const items = wrapper.findAll('[data-testid^="trigger-panel-item-server-"]')
    await items[0].trigger('mousedown')
    await flushPromises()
    expect(wrapper.find('[data-testid="selected-trigger-chip-server-prod-api"]').exists()).toBe(true)
    // 模拟切换到新 session
    await wrapper.setProps({ sessionId: 'sid-002' })
    await flushPromises()
    expect(wrapper.find('[data-testid="selected-trigger-chip-server-prod-api"]').exists()).toBe(false)
  })

  it('test_session_change_keeps_trigger_chips_for_previous_session 切回原 session 时恢复 trigger chips', async () => {
    const wrapper = mountInputBox({ sessionId: 'sid-001' })
    await flushPromises()
    await setTextareaValue(wrapper, '#', 1)
    await flushPromises()
    const items = wrapper.findAll('[data-testid^="trigger-panel-item-server-"]')
    await items[0].trigger('mousedown')
    await flushPromises()
    expect(wrapper.find('[data-testid="selected-trigger-chip-server-prod-api"]').exists()).toBe(true)
    // 切换到新 session 后 chips 消失
    await wrapper.setProps({ sessionId: 'sid-002' })
    await flushPromises()
    expect(wrapper.find('[data-testid="selected-trigger-chip-server-prod-api"]').exists()).toBe(false)
    // 切回原 session 后 chips 恢复
    await wrapper.setProps({ sessionId: 'sid-001' })
    await flushPromises()
    expect(wrapper.find('[data-testid="selected-trigger-chip-server-prod-api"]').exists()).toBe(true)
  })

  it('test_hash_button_disabled_during_streaming 流式期间 # 按钮 disabled', async () => {
    const wrapper = mountInputBox({ isStreaming: true })
    await flushPromises()
    const btn = wrapper.find('[data-testid="trigger-btn-server"]')
    expect(btn.attributes('disabled')).toBeDefined()
  })
})