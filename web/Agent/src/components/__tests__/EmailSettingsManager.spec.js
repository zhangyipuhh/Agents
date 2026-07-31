/* EmailSettingsManager 收件人搜索与新建策略回归测试。 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import EmailSettingsManager from '../EmailSettingsManager.vue'
import EmailSettingsManagerSource from '../EmailSettingsManager.vue?raw'

const emailableUsers = [
  { id: 1, username: 'alice', real_name: 'Alice', email: 'alice@example.com' },
  { id: 2, username: 'bob', real_name: 'Bob', email: 'bob@example.com' },
]

const policies = [
  {
    id: 10,
    name: '运维通知',
    description: '运维人员收件人策略',
    recipient_user_ids: [1],
  },
]

function jsonResponse(data, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  }
}

function setupFetchMock() {
  global.fetch = vi.fn(async (url) => {
    if (url === '/api/admin/email/emailable-users') return jsonResponse(emailableUsers)
    if (url === '/api/admin/email/policies') return jsonResponse(policies)
    if (url === '/api/admin/email/server-config') return jsonResponse(null)
    return jsonResponse({})
  })
}

async function openPolicyEditor(wrapper) {
  const policiesTab = wrapper.find('[data-testid="email-tab-policies"]')
  await policiesTab.trigger('click')
  await flushPromises()
  await wrapper.find('button.primary-btn').trigger('click')
  await flushPromises()
}

describe('EmailSettingsManager 收件人策略', () => {
  let originalFetch
  let originalLocalStorage
  let originalConsoleError

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
    originalConsoleError = console.error
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
    console.error = originalConsoleError
  })

  it('test_component_importable 组件可以导入', () => {
    expect(EmailSettingsManager).toBeDefined()
  })

  it('test_create_policy_does_not_log_recipient_keyword_error 点击新建策略不产生 recipientKeyword 异常', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    const wrapper = mount(EmailSettingsManager, { props: { isAdmin: true } })
    await flushPromises()

    await openPolicyEditor(wrapper)

    const errors = consoleError.mock.calls.flat().join(' ')
    expect(errors).not.toContain('recipientKeyword is not defined')
    expect(wrapper.find('.policy-editor').exists()).toBe(true)
  })

  it('test_create_policy_resets_recipient_keyword 新建策略时清空收件人搜索关键字', async () => {
    const wrapper = mount(EmailSettingsManager, { props: { isAdmin: true } })
    await flushPromises()
    await openPolicyEditor(wrapper)

    const searchInput = wrapper.find('input[aria-label="搜索收件人"]')
    await searchInput.setValue('alice')
    expect(searchInput.element.value).toBe('alice')

    await wrapper.find('.secondary-btn').trigger('click')
    await wrapper.find('button.primary-btn').trigger('click')
    await flushPromises()

    expect(wrapper.find('input[aria-label="搜索收件人"]').element.value).toBe('')
  })

  it('test_email_settings_section_fills_available_height 邮件设置根 section 铺满可用高度', () => {
    const styleBlock = EmailSettingsManagerSource.match(/\.email-settings-manager\s*\{([^}]*)\}/s)

    expect(styleBlock).not.toBeNull()
    expect(styleBlock[1]).toMatch(/display\s*:\s*flex/)
    expect(styleBlock[1]).toMatch(/flex-direction\s*:\s*column/)
    expect(styleBlock[1]).toMatch(/flex\s*:\s*1/)
    expect(styleBlock[1]).toMatch(/min-height\s*:\s*0/)
  })

  it('test_policy_name_and_description_use_full_rows 策略名称和描述各占满一行', async () => {
    const wrapper = mount(EmailSettingsManager, { props: { isAdmin: true } })
    await flushPromises()
    await openPolicyEditor(wrapper)

    const nameRow = wrapper.find('#policy-name').element.closest('.field-row')
    const descRow = wrapper.find('#policy-desc').element.closest('.field-row')

    expect(nameRow).not.toBeNull()
    expect(descRow).not.toBeNull()
    expect(nameRow.classList.contains('full')).toBe(true)
    expect(descRow.classList.contains('full')).toBe(true)
  })

  it('test_recipient_keyword_filters_users 收件人搜索只展示匹配用户', async () => {
    const wrapper = mount(EmailSettingsManager, { props: { isAdmin: true } })
    await flushPromises()
    await openPolicyEditor(wrapper)

    await wrapper.find('input[aria-label="搜索收件人"]').setValue('alice')

    const recipientItems = wrapper.findAll('.recipient-item')
    expect(recipientItems).toHaveLength(1)
    expect(recipientItems[0].text()).toContain('alice@example.com')
  })

  it('test_select_and_cancel_policy_reset_recipient_keyword 编辑和取消策略时清空收件人搜索关键字', async () => {
    const wrapper = mount(EmailSettingsManager, { props: { isAdmin: true } })
    await flushPromises()
    await wrapper.find('[data-testid="email-tab-policies"]').trigger('click')
    await flushPromises()

    await wrapper.find('.policy-item').trigger('click')
    await flushPromises()
    const searchInput = wrapper.find('input[aria-label="搜索收件人"]')
    await searchInput.setValue('alice')

    await wrapper.find('.secondary-btn').trigger('click')
    expect(wrapper.find('.policy-editor').exists()).toBe(false)

    await wrapper.find('button.primary-btn').trigger('click')
    await flushPromises()
    expect(wrapper.find('input[aria-label="搜索收件人"]').element.value).toBe('')
  })
})

/* 2026-07-31 新增：内部 panel 高度链 + 自滚动契约（防内容溢出卡片）。
   复刻 TaskSchedulerManager.spec.js 末尾「内部滚动契约」同款源码静态断言模式。 */
describe('内部滚动契约（防内容溢出）', () => {
  it('test_tabpanel_flex_fills_root_section tabpanel 必须 flex:1 + min-height:0', () => {
    // 高度链从 .email-settings-manager (flex:1) 传到三个 <section role="tabpanel">，
    // 让 panel 沿父级 flex 列铺满剩余高度，外框始终贴满可视区。
    const m = EmailSettingsManagerSource.match(
      /\.email-settings-manager\s*>\s*section\[role="tabpanel"\]\s*\{([^}]*)\}/s,
    )
    expect(m, '.email-settings-manager > section[role="tabpanel"] 样式块必须存在').not.toBeNull()
    expect(m[1]).toMatch(/flex\s*:\s*1/)
    expect(m[1]).toMatch(/min-height\s*:\s*0/)
  })

  it('test_policies_layout_unlocks_flex_chain policies-layout 必须解封 flex 链断点', () => {
    // .policies-layout 是 grid 容器，必须有 min-height:0 才能让子级 .policies-list /
    // .policy-editor 真正滚动；否则 min-height: auto 默认值会让 grid 高度 = 内容高度。
    const m = EmailSettingsManagerSource.match(/\.policies-layout\s*\{([^}]*)\}/s)
    expect(m, '.policies-layout 样式块必须存在').not.toBeNull()
    expect(m[1]).toMatch(/min-height\s*:\s*0/)
  })

  it('test_policies_list_and_policy_editor_scroll_internally 内部自滚动契约', () => {
    // 策略列表与策略编辑器必须有独立 overflow-y:auto，长内容在 panel 内滚动，
    // 而非被外层 .tab-fill-wrapper 的 overflow-y:auto 吃掉。
    const hasListScroll = /\.policies-list\s*\{[^}]*overflow-y\s*:\s*auto/s.test(
      EmailSettingsManagerSource,
    )
    const hasEditorScroll = /\.policy-editor\s*\{[^}]*overflow-y\s*:\s*auto/s.test(
      EmailSettingsManagerSource,
    )
    expect(hasListScroll && hasEditorScroll, '.policies-list 和 .policy-editor 都必须 overflow-y:auto').toBe(true)
  })

  it('test_email_form_scrolls_in_server_and_test_tabs 服务器配置/测试发送 Tab 表单必须自滚动', () => {
    // 服务器配置 Tab（高级选项展开）与测试发送 Tab（多附件/长正文）共用 .email-form，
    // 必须有 flex:1 + min-height:0 + overflow-y:auto，否则内容超高时被外层 .tab-fill-wrapper 滚动条吞掉。
    const m = EmailSettingsManagerSource.match(/\.email-form\s*\{([^}]*)\}/s)
    expect(m, '.email-form 样式块必须存在').not.toBeNull()
    expect(m[1]).toMatch(/flex\s*:\s*1/)
    expect(m[1]).toMatch(/min-height\s*:\s*0/)
    expect(m[1]).toMatch(/overflow-y\s*:\s*auto/)
  })

  it('test_detail_header_does_not_shrink 详情头必须 flex-shrink:0 防被压缩成 0', () => {
    // tabpanel 是 flex 列容器，.detail-header 不声明 flex-shrink:0 会被默认的 1 压缩到 0。
    const m = EmailSettingsManagerSource.match(/\.detail-header\s*\{([^}]*)\}/s)
    expect(m, '.detail-header 样式块必须存在').not.toBeNull()
    expect(m[1]).toMatch(/flex-shrink\s*:\s*0/)
  })
})
