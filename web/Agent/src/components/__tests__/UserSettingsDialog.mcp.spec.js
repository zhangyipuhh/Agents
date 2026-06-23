/**
 * UserSettingsDialog MCP Tab 测试
 *
 * 覆盖：admin 角色能看到 MCP 管理 Tab，点击后渲染 McpServerManager 组件。
 *
 * 注意：UserSettingsDialog 使用 <Teleport to="body">，nav-item 与 tab 内容
 * 均渲染到 document.body，因此需通过 document.body 查询元素，
 * 而非 wrapper.findAll / wrapper.find。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import UserSettingsDialog from '../UserSettingsDialog.vue'

/**
 * 从 document.body 收集所有 .nav-item 的文本内容
 * @returns {Array<string>} nav-item 文本数组
 */
function getNavItemTexts() {
  const nodes = document.body.querySelectorAll('.nav-item')
  return Array.from(nodes).map((n) => n.textContent || '')
}

describe('UserSettingsDialog MCP 管理 Tab', () => {
  let originalFetch
  let originalLocalStorage

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
    global.fetch = vi.fn()
    global.localStorage = {
      getItem: vi.fn(() => 'fake-token'),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    }
  })

  afterEach(() => {
    global.fetch = originalFetch
    global.localStorage = originalLocalStorage
    // 清理 Teleport 挂载到 body 的残留节点
    document.body.innerHTML = ''
  })

  it('test_admin_sees_mcp_tab admin 角色显示 MCP 管理 Tab', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'admin',
        userId: 1,
        username: 'admin',
      },
    })
    await flushPromises()
    const navTexts = getNavItemTexts()
    expect(navTexts.some((t) => t.includes('MCP'))).toBe(true)
    wrapper.unmount()
  })

  it('test_user_does_not_see_mcp_tab 普通用户不显示 MCP 管理 Tab', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'user',
        userId: 1,
        username: 'user1',
      },
    })
    await flushPromises()
    const navTexts = getNavItemTexts()
    expect(navTexts.some((t) => t.includes('MCP'))).toBe(false)
    wrapper.unmount()
  })

  it('test_click_mcp_tab_shows_manager 点击 MCP Tab 显示管理组件', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => [],
    })
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'admin',
        userId: 1,
        username: 'admin',
      },
    })
    await flushPromises()
    const navNodes = document.body.querySelectorAll('.nav-item')
    const mcpNav = Array.from(navNodes).find((n) => (n.textContent || '').includes('MCP'))
    expect(mcpNav).toBeTruthy()
    mcpNav.click()
    await flushPromises()
    expect(document.body.querySelector('.mcp-server-manager')).not.toBeNull()
    wrapper.unmount()
  })
})
