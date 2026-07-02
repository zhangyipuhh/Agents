/**
 * UserSettingsDialog 会话查询 Tab 测试
 *
 * 覆盖：
 * - Admin 切换到「会话查询」后渲染人员列表
 * - 点击人员行进入会话列表，表格包含复选框、标题、导出、删除
 * - 勾选会话后显示「批量删除」按钮
 * - 点击会话标题打开历史消息弹窗，弹窗内渲染 MessageBubble
 * - 点击导出触发 Markdown 下载
 * - 点击批量删除触发批量删除 API 并刷新列表
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import UserSettingsDialog from '../UserSettingsDialog.vue'

/**
 * 构造 mock fetch，根据 URL 返回不同响应
 * @returns {Function} mock fetch 函数
 */
function createMockFetch() {
  return vi.fn(async (url) => {
    if (url.includes('/api/users/') && url.includes('/sessions')) {
      return {
        ok: true,
        json: async () => ({
          sessions: [
            {
              session_id: 'sess-001',
              title: '测试会话',
              last_active_at: new Date().toISOString()
            }
          ]
        })
      }
    }
    if (url.includes('/api/session/admin/batch')) {
      return {
        ok: true,
        json: async () => ({
          success: true,
          deleted_count: 1,
          total: 1,
          failed: []
        })
      }
    }
    if (url.includes('/api/session/admin/') && url.includes('/messages')) {
      return {
        ok: true,
        json: async () => ({
          session_id: 'sess-001',
          messages: [
            { id: 'm1', type: 'user', content: '你好' },
            { id: 'm2', type: 'ai', content: '您好，有什么可以帮您？' }
          ],
          total: 2
        })
      }
    }
    if (url.includes('/api/session/admin/') && url.includes('/export/markdown')) {
      return {
        ok: true,
        text: async () => '# 测试会话\n\n## 用户\n\n你好\n',
        headers: {
          get: () => 'attachment; filename*=UTF-8\'\'%E6%B5%8B%E8%AF%95%E4%BC%9A%E8%AF%9D.md'
        }
      }
    }
    if (url.includes('/api/users')) {
      return {
        ok: true,
        json: async () => [
          { id: 1, username: 'user1', role: 'user', created_at: new Date().toISOString() }
        ]
      }
    }
    return { ok: false, status: 404, json: async () => ({ detail: 'not found' }) }
  })
}

/**
 * 从 document.body 查询文本包含指定内容的元素
 * @param {string} text - 要查找的文本
 * @returns {Element | null} 匹配的元素
 */
function findByBodyText(text) {
  const nodes = document.body.querySelectorAll('*')
  for (const node of nodes) {
    if (node.textContent && node.textContent.trim() === text) {
      return node
    }
  }
  return null
}

describe('UserSettingsDialog 会话查询 Tab', () => {
  let originalFetch
  let originalLocalStorage
  let originalConfirm
  let originalAlert
  let originalCreateObjectURL
  let originalRevokeObjectURL

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
    originalConfirm = global.confirm
    originalAlert = global.alert
    originalCreateObjectURL = global.URL.createObjectURL
    originalRevokeObjectURL = global.URL.revokeObjectURL

    global.fetch = createMockFetch()
    global.localStorage = {
      getItem: vi.fn((key) => {
        if (key === 'auth_token') return 'fake-token'
        if (key === 'user_id') return '1'
        return null
      }),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn()
    }
    global.confirm = vi.fn(() => true)
    global.alert = vi.fn()
    global.URL.createObjectURL = vi.fn(() => 'blob://fake')
    global.URL.revokeObjectURL = vi.fn()
  })

  afterEach(() => {
    global.fetch = originalFetch
    global.localStorage = originalLocalStorage
    global.confirm = originalConfirm
    global.alert = originalAlert
    global.URL.createObjectURL = originalCreateObjectURL
    global.URL.revokeObjectURL = originalRevokeObjectURL
    document.body.innerHTML = ''
  })

  it('test_session_query_renders_personnel_list 会话查询 Tab 渲染人员列表', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: false,
        role: 'admin',
        userId: 1,
        username: 'admin',
        initialTab: 'session-query'
      }
    })
    await wrapper.setProps({ visible: true })
    await flushPromises()

    const userCell = findByBodyText('user1')
    expect(userCell).not.toBeNull()
    wrapper.unmount()
  })

  it('test_click_personnel_shows_session_list 点击人员行进入会话列表', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: false,
        role: 'admin',
        userId: 1,
        username: 'admin',
        initialTab: 'session-query'
      }
    })
    await wrapper.setProps({ visible: true })
    await flushPromises()

    const row = document.body.querySelector('.clickable-row')
    expect(row).not.toBeNull()
    expect(row.textContent).toContain('user1')
    row.click()
    await flushPromises()

    const sessionTitle = findByBodyText('测试会话')
    expect(sessionTitle).not.toBeNull()

    // 表格应包含复选框、导出按钮、删除按钮
    const exportBtn = findByBodyText('导出')
    expect(exportBtn).not.toBeNull()
    const deleteBtn = findByBodyText('删除')
    expect(deleteBtn).not.toBeNull()
    expect(document.body.querySelector('input[type="checkbox"]')).not.toBeNull()
    wrapper.unmount()
  })

  it('test_select_session_shows_batch_delete 勾选会话后显示批量删除按钮', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: false,
        role: 'admin',
        userId: 1,
        username: 'admin',
        initialTab: 'session-query'
      }
    })
    await wrapper.setProps({ visible: true })
    await flushPromises()

    const row = document.body.querySelector('.clickable-row')
    expect(row).not.toBeNull()
    row.click()
    await flushPromises()

    // 初始不应显示批量删除按钮
    expect(findByBodyText('批量删除')).toBeNull()

    const checkbox = document.body.querySelector('input[type="checkbox"]')
    expect(checkbox).not.toBeNull()
    checkbox.checked = true
    checkbox.dispatchEvent(new Event('change', { bubbles: true }))
    await flushPromises()

    expect(findByBodyText('批量删除')).not.toBeNull()
    wrapper.unmount()
  })

  it('test_click_session_title_opens_history_dialog 点击标题打开历史消息弹窗', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: false,
        role: 'admin',
        userId: 1,
        username: 'admin',
        initialTab: 'session-query'
      }
    })
    await wrapper.setProps({ visible: true })
    await flushPromises()

    const row = document.body.querySelector('.clickable-row')
    expect(row).not.toBeNull()
    row.click()
    await flushPromises()

    const sessionTitle = findByBodyText('测试会话')
    sessionTitle.click()
    await flushPromises()

    // 弹窗标题应显示会话标题
    expect(findByBodyText('测试会话')).not.toBeNull()

    // 历史消息应被渲染
    expect(findByBodyText('你好')).not.toBeNull()
    wrapper.unmount()
  })

  it('test_click_export_triggers_download 点击导出触发 Markdown 下载', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: false,
        role: 'admin',
        userId: 1,
        username: 'admin',
        initialTab: 'session-query'
      }
    })
    await wrapper.setProps({ visible: true })
    await flushPromises()

    const row = document.body.querySelector('.clickable-row')
    expect(row).not.toBeNull()
    row.click()
    await flushPromises()

    const exportBtn = findByBodyText('导出')
    exportBtn.click()
    await flushPromises()

    expect(global.URL.createObjectURL).toHaveBeenCalled()
    wrapper.unmount()
  })

  it('test_click_batch_delete_triggers_api_and_refreshes 点击批量删除触发 API 并刷新列表', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: false,
        role: 'admin',
        userId: 1,
        username: 'admin',
        initialTab: 'session-query'
      }
    })
    await wrapper.setProps({ visible: true })
    await flushPromises()

    const row = document.body.querySelector('.clickable-row')
    expect(row).not.toBeNull()
    row.click()
    await flushPromises()

    const checkbox = document.body.querySelector('input[type="checkbox"]')
    checkbox.checked = true
    checkbox.dispatchEvent(new Event('change', { bubbles: true }))
    await flushPromises()

    const batchDeleteBtn = findByBodyText('批量删除')
    batchDeleteBtn.click()
    await flushPromises()

    const batchCalls = global.fetch.mock.calls.filter(([url]) => url.includes('/api/session/admin/batch'))
    expect(batchCalls.length).toBeGreaterThan(0)
    const body = JSON.parse(batchCalls[0][1].body)
    expect(body.session_ids).toContain('sess-001')
    wrapper.unmount()
  })
})
