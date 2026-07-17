/* EmailSettingsManager 收件人搜索与新建策略回归测试。 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import EmailSettingsManager from '../EmailSettingsManager.vue'

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
    const wrapper = mount(EmailSettingsManager)
    await flushPromises()

    await openPolicyEditor(wrapper)

    const errors = consoleError.mock.calls.flat().join(' ')
    expect(errors).not.toContain('recipientKeyword is not defined')
    expect(wrapper.find('.policy-editor').exists()).toBe(true)
  })

  it('test_create_policy_resets_recipient_keyword 新建策略时清空收件人搜索关键字', async () => {
    const wrapper = mount(EmailSettingsManager)
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

  it('test_policy_name_and_description_use_full_rows 策略名称和描述各占满一行', async () => {
    const wrapper = mount(EmailSettingsManager)
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
    const wrapper = mount(EmailSettingsManager)
    await flushPromises()
    await openPolicyEditor(wrapper)

    await wrapper.find('input[aria-label="搜索收件人"]').setValue('alice')

    const recipientItems = wrapper.findAll('.recipient-item')
    expect(recipientItems).toHaveLength(1)
    expect(recipientItems[0].text()).toContain('alice@example.com')
  })

  it('test_select_and_cancel_policy_reset_recipient_keyword 编辑和取消策略时清空收件人搜索关键字', async () => {
    const wrapper = mount(EmailSettingsManager)
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
