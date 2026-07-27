/**
 * InputBox 「#」触发器集成测试。
 * 覆盖编辑器触发检测、服务器 Chip 原位插入、删除、发送序列化、会话隔离和流式禁用。
 */
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import InputBox from '../InputBox.vue'

vi.mock('../../utils/api.js', () => ({
  uploadFileInChunks: vi.fn(() => Promise.resolve({ files: [] })),
  formatFileSize: vi.fn((size) => `${size} bytes`),
  getFileExtension: vi.fn((name) => name.split('.').pop()),
  refreshToken: vi.fn(() => Promise.resolve('fake-token')),
  fetchAgentList: vi.fn(() => Promise.resolve([])),
  deleteAttachments: vi.fn(() => Promise.resolve()),
  fetchUploadConfig: vi.fn(() => Promise.resolve({ max_file_size_mb: 3 })),
  fetchUserServerTree: vi.fn(() => Promise.resolve({
    nodes: [
      { id: 1, node_type: 'folder', name: '生产' },
      { id: 2, node_type: 'server', business_name: 'prod-api', server_type: 'linux' },
      { id: 3, node_type: 'server', business_name: 'win-01', server_type: 'windows' },
    ],
  })),
}))

beforeAll(() => {
  if (typeof window !== 'undefined' && !window.alert) window.alert = () => {}
})

const mountInputBox = (props = {}) => mount(InputBox, {
  props: {
    sessionId: 'sid-001',
    isStreaming: false,
    currentProject: null,
    ensureSession: vi.fn(() => Promise.resolve('sid-001')),
    ...props,
  },
})

function setCaret(editor, node, offset) {
  const range = document.createRange()
  range.setStart(node, Math.min(offset, node.textContent.length))
  range.collapse(true)
  const selection = window.getSelection()
  selection.removeAllRanges()
  selection.addRange(range)
  editor.element.focus()
}

const setEditorText = async (wrapper, value, caret = value.length) => {
  const editor = wrapper.find('[data-testid="input-editor"]')
  editor.element.replaceChildren(document.createTextNode(value))
  setCaret(editor, editor.element.firstChild, caret)
  await editor.trigger('input')
  return editor
}

const setCaretInText = async (wrapper, textPart, offset) => {
  const editor = wrapper.find('[data-testid="input-editor"]')
  // 跨文本节点 / Chip 累积找到含 textPart 的位置，再把光标映射回真实 DOM 节点 + 偏移。
  const children = Array.from(editor.element.childNodes)
  let concat = ''
  const map = [] // [{ childIndex, node, offsetWithin }]
  for (const node of children) {
    if (node.nodeType === Node.TEXT_NODE) {
      const text = node.textContent || ''
      for (let i = 0; i < text.length; i++) {
        map.push({ node, offset: i })
        concat += text[i]
      }
    } else {
      map.push({ node, offset: 0 })
      concat += ' '
    }
  }
  const idx = concat.indexOf(textPart)
  if (idx < 0) throw new Error(`未找到文本节点：${textPart}`)
  const target = map[idx + offset] || map[map.length - 1]
  setCaret(editor, target.node, target.offset)
  await editor.trigger('input')
  return editor
}

const readEditorDisplay = (wrapper) => {
  const editor = wrapper.find('[data-testid="input-editor"]')
  return Array.from(editor.element.childNodes).map((node) => {
    if (node.nodeType === Node.TEXT_NODE) return node.textContent
    if (node.nodeType === Node.ELEMENT_NODE && node.dataset?.triggerId === 'server') {
      return `#${node.dataset.businessName}`
    }
    return node.textContent || ''
  }).join('')
}

const selectServer = async (wrapper, index = 0) => {
  const items = wrapper.findAll('[data-testid^="trigger-panel-item-server-"]')
  expect(items.length).toBeGreaterThan(index)
  await items[index].trigger('mousedown')
  await flushPromises()
}

async function openServerPanel(wrapper, value = '#', caret = value.length) {
  await setEditorText(wrapper, value, caret)
  await flushPromises()
  expect(wrapper.find('[data-testid="trigger-panel-server"]').exists()).toBe(true)
}

describe('InputBox 「#」触发器集成', () => {
  it('test_hash_button_rendered 工具栏渲染 # 按钮', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    expect(wrapper.find('[data-testid="trigger-btn-server"]').exists()).toBe(true)
  })

  it('test_typing_hash_opens_panel 输入 # 后 trigger 面板打开', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    await openServerPanel(wrapper)
    expect(wrapper.find('[data-testid="trigger-panel-server"]').exists()).toBe(true)
  })

  it('test_mid_word_hash_does_not_trigger C# 不触发面板', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    await setEditorText(wrapper, 'C#')
    await flushPromises()
    expect(wrapper.find('[data-testid="trigger-panel-server"]').exists()).toBe(false)
  })

  it('test_hash_after_whitespace_triggers 空白后 # 触发面板', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    await openServerPanel(wrapper, 'hello #')
    expect(wrapper.find('[data-testid="trigger-panel-server"]').exists()).toBe(true)
  })

  it('test_click_hash_button_inserts_char 工具栏 # 按钮在光标处插入并触发面板', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    const editor = await setEditorText(wrapper, 'hello')
    setCaret(editor, editor.element.firstChild, 5)
    await wrapper.find('[data-testid="trigger-btn-server"]').trigger('click')
    await flushPromises()
    expect(readEditorDisplay(wrapper)).toContain('#')
    expect(wrapper.find('[data-testid="trigger-panel-server"]').exists()).toBe(true)
  })

  it('test_selecting_server_renders_inline_chip_at_hash_position 选择服务器后在原位置渲染灰色 Chip', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    await openServerPanel(wrapper, '请检查 # 后的磁盘', 5)
    await selectServer(wrapper)
    expect(readEditorDisplay(wrapper)).toBe('请检查 #prod-api 后的磁盘')
    const chip = wrapper.find('[data-testid="inline-trigger-chip-server-prod-api"]')
    expect(chip.exists()).toBe(true)
    expect(chip.classes()).toContain('selected-trigger-chip')
    expect(chip.attributes('contenteditable')).toBe('false')
    expect(wrapper.find('[data-testid="input-editor"]').text()).not.toContain('⟦引用服务器')
  })

  it('test_selecting_server_replaces_trigger_query 精确替换 # 查询串并保留周围文本', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    await openServerPanel(wrapper, '巡检 #pro 立即执行', 8)
    await selectServer(wrapper)
    expect(readEditorDisplay(wrapper)).toBe('巡检 #prod-api 立即执行')
  })

  it('test_multiple_inline_chips_keep_dom_order 多处选择服务器保持正文顺序', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    await openServerPanel(wrapper, '比较 # 与 # 的状态', 4)
    await selectServer(wrapper, 0)
    await setCaretInText(wrapper, '与 #', 4)
    await flushPromises()
    await selectServer(wrapper, 1)
    expect(readEditorDisplay(wrapper)).toBe('比较 #prod-api 与 #win-01 的状态')
    expect(wrapper.findAll('.inline-trigger-chip')).toHaveLength(2)
  })

  it('test_send_serializes_inline_chips_in_place_and_keeps_extras 发送按原位置序列化并携带 extras', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    await openServerPanel(wrapper, '比较 # 与 # 的状态', 4)
    await selectServer(wrapper, 0)
    await setCaretInText(wrapper, '与 #', 4)
    await flushPromises()
    await selectServer(wrapper, 1)

    // 取出两个 Chip DOM 节点保留，避免 setEditorText 把它们替换掉。
    const editor = wrapper.find('[data-testid="input-editor"]')
    const prodApiChip = wrapper.find('[data-testid="inline-trigger-chip-server-prod-api"]').element
    const win01Chip = wrapper.find('[data-testid="inline-trigger-chip-server-win-01"]').element
    editor.element.replaceChildren(
      document.createTextNode('比较 '),
      prodApiChip,
      document.createTextNode(' 与 '),
      win01Chip,
      document.createTextNode(' 的状态'),
    )
    setCaret(editor, editor.element.lastChild, editor.element.lastChild.textContent.length)
    await editor.trigger('input')

    await wrapper.find('.send-btn').trigger('click')
    await flushPromises()
    const last = wrapper.emitted('send').at(-1)
    expect(last[0]).toBe('比较 ⟦引用服务器：prod-api⟧ 与 ⟦引用服务器：win-01⟧ 的状态')
    expect(last[2].referenced_servers).toEqual([
      { name: 'prod-api', server_type: 'linux' },
      { name: 'win-01', server_type: 'windows' },
    ])
  })

  it('test_chip_remove_button_removes_inline_chip 点击移除按钮保留周围文本', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    await openServerPanel(wrapper, '请检查 # 后续', 5)
    await selectServer(wrapper)
    await wrapper.find('[data-testid="inline-trigger-chip-server-prod-api"] .trigger-chip-remove-btn').trigger('click')
    await flushPromises()
    expect(readEditorDisplay(wrapper)).toBe('请检查  后续')
    expect(wrapper.find('.inline-trigger-chip').exists()).toBe(false)
  })

  it('test_send_excludes_deleted_inline_chip 删除 Chip 后发送不携带服务器', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    await openServerPanel(wrapper)
    await selectServer(wrapper)
    await wrapper.find('.inline-trigger-chip .trigger-chip-remove-btn').trigger('click')
    await setEditorText(wrapper, '请巡检')
    await wrapper.find('.send-btn').trigger('click')
    await flushPromises()
    const last = wrapper.emitted('send').at(-1)
    expect(last[0]).toBe('请巡检')
    expect(last[2]).toEqual({})
  })

  it('test_send_clears_inline_chips 发送成功后清空编辑器', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    await openServerPanel(wrapper)
    await selectServer(wrapper)
    await wrapper.find('.send-btn').trigger('click')
    await flushPromises()
    expect(wrapper.find('.inline-trigger-chip').exists()).toBe(false)
    expect(readEditorDisplay(wrapper)).toBe('')
  })

  it('test_session_change_clears_editor_for_new_session 新 session 清空编辑器', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    await openServerPanel(wrapper)
    await selectServer(wrapper)
    await wrapper.setProps({ sessionId: 'sid-002' })
    await flushPromises()
    expect(readEditorDisplay(wrapper)).toBe('')
  })

  it('test_hash_still_triggers_when_agent_bound 已绑定智能体时 # 仍能触发', async () => {
    const wrapper = mountInputBox({ boundAgentName: 'ops_agent', boundAgentDisplayName: '运维项目智能体' })
    await flushPromises()
    await openServerPanel(wrapper)
    expect(wrapper.find('[data-testid="trigger-panel-server"]').exists()).toBe(true)
  })

  it('test_hash_button_disabled_during_streaming 流式期间 # 按钮 disabled', async () => {
    const wrapper = mountInputBox({ isStreaming: true })
    await flushPromises()
    expect(wrapper.find('[data-testid="trigger-btn-server"]').attributes('disabled')).toBeDefined()
  })

  // 2026-07-27 新增：行内 Chip 紧邻删除回归测试（覆盖用户截图场景）
  // 复现步骤：选中服务器 → 在 chip 后输入「对方」→ Backspace 想删「方」字
  // 期望：函数判定不拦截，原生退格正常删「方」字，chip 保留
  it('test_backspace_inside_text_after_chip_does_not_remove_chip chip 后文本内退格不删 chip', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    // 选中服务器：DOM = [Chip(prod-api), TextNode("对方")]
    await openServerPanel(wrapper)
    await selectServer(wrapper)
    const editor = wrapper.find('[data-testid="input-editor"]')
    const chip = wrapper.find('[data-testid="inline-trigger-chip-server-prod-api"]').element
    const textNode = document.createTextNode('对方')
    editor.element.replaceChildren(chip, textNode)
    // 光标放在「方」字后 → textNode offset=1（非贴边）
    setCaret(editor, textNode, 1)
    await editor.trigger('keydown', { key: 'Backspace' })
    await flushPromises()
    // 核心断言：函数未拦截，chip 不被破坏
    expect(wrapper.find('[data-testid="inline-trigger-chip-server-prod-api"]').exists()).toBe(true)
    // 我们的代码未触碰文本节点（happy-dom 不模拟原生删除，所以文本节点保持原值）
    expect(textNode.textContent).toBe('对方')
    // 编辑器 DOM 仍包含 chip
    expect(readEditorDisplay(wrapper)).toBe('#prod-api对方')
  })

  // 验证贴边场景仍能整块删除 chip（不被新逻辑误伤）
  it('test_backspace_at_text_start_after_chip_removes_whole_chip chip 后文本起点退格整块删 chip', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    await openServerPanel(wrapper)
    await selectServer(wrapper)
    const editor = wrapper.find('[data-testid="input-editor"]')
    const chip = wrapper.find('[data-testid="inline-trigger-chip-server-prod-api"]').element
    const textNode = document.createTextNode('对方')
    editor.element.replaceChildren(chip, textNode)
    // 光标放在「对方」文本起点 → textNode offset=0，贴边 chip
    setCaret(editor, textNode, 0)
    await editor.trigger('keydown', { key: 'Backspace' })
    await flushPromises()
    // chip 已被整块删除
    expect(wrapper.find('[data-testid="inline-trigger-chip-server-prod-api"]').exists()).toBe(false)
    // 文本节点保留「对方」
    expect(readEditorDisplay(wrapper)).toBe('对方')
  })

  // Delete 紧贴 chip 左侧（光标在 chip 前文本末尾）：整块删除 chip
  it('test_delete_at_text_end_before_chip_removes_whole_chip chip 前文本末尾 Delete 整块删 chip', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    await openServerPanel(wrapper)
    await selectServer(wrapper)
    const editor = wrapper.find('[data-testid="input-editor"]')
    const chip = wrapper.find('[data-testid="inline-trigger-chip-server-prod-api"]').element
    const textNode = document.createTextNode('巡检')
    editor.element.replaceChildren(textNode, chip)
    // 光标放在「巡检」文本末尾 → textNode offset=2，贴边 chip
    setCaret(editor, textNode, textNode.textContent.length)
    await editor.trigger('keydown', { key: 'Delete' })
    await flushPromises()
    // chip 已被整块删除
    expect(wrapper.find('[data-testid="inline-trigger-chip-server-prod-api"]').exists()).toBe(false)
    // 文本节点保留「巡检」
    expect(readEditorDisplay(wrapper)).toBe('巡检')
  })

  // Delete 在 chip 前文本节点内（非贴边）：只删字不删 chip
  it('test_delete_inside_text_before_chip_does_not_remove_chip chip 前文本内 Delete 不删 chip', async () => {
    const wrapper = mountInputBox()
    await flushPromises()
    await openServerPanel(wrapper)
    await selectServer(wrapper)
    const editor = wrapper.find('[data-testid="input-editor"]')
    const chip = wrapper.find('[data-testid="inline-trigger-chip-server-prod-api"]').element
    const textNode = document.createTextNode('巡检')
    editor.element.replaceChildren(textNode, chip)
    // 光标放在「巡」与「检」之间 → textNode offset=1（非贴边）
    setCaret(editor, textNode, 1)
    await editor.trigger('keydown', { key: 'Delete' })
    await flushPromises()
    // 核心断言：函数未拦截，chip 保留
    expect(wrapper.find('[data-testid="inline-trigger-chip-server-prod-api"]').exists()).toBe(true)
    // 我们的代码未触碰文本节点（happy-dom 不模拟原生删除，文本节点保持原值）
    expect(textNode.textContent).toBe('巡检')
    // 编辑器 DOM 仍包含 chip
    expect(readEditorDisplay(wrapper)).toBe('巡检#prod-api')
  })
})
