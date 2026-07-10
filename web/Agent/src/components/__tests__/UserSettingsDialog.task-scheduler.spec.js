/**
 * UserSettingsDialog 定时任务 Tab 测试
 *
 * 覆盖：admin 角色能看到定时任务 Tab，普通用户不可见，点击后渲染 TaskSchedulerManager。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import UserSettingsDialog from '../UserSettingsDialog.vue'

function getNavItemTexts() {
  const nodes = document.body.querySelectorAll('.nav-item')
  return Array.from(nodes).map((n) => n.textContent || '')
}

describe('UserSettingsDialog 定时任务 Tab', () => {
  let originalFetch
  let originalLocalStorage

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules') return { ok: true, json: async () => [] }
      if (u === '/api/admin/agents' && method === 'GET') return { ok: true, json: async () => [] }
      return { ok: true, json: async () => [] }
    })
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
    document.body.innerHTML = ''
  })

  it('test_admin_sees_task_scheduler_tab admin 显示定时任务 Tab', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: { visible: true, role: 'admin', userId: 1, username: 'admin' },
    })
    await flushPromises()

    const navTexts = getNavItemTexts()
    expect(navTexts.some((text) => text.includes('定时任务'))).toBe(true)
    wrapper.unmount()
  })

  it('test_user_does_not_see_task_scheduler_tab 普通用户不显示定时任务 Tab', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: { visible: true, role: 'user', userId: 2, username: 'user1' },
    })
    await flushPromises()

    const navTexts = getNavItemTexts()
    expect(navTexts.some((text) => text.includes('定时任务'))).toBe(false)
    wrapper.unmount()
  })

  it('test_click_task_scheduler_tab_shows_manager 点击定时任务 Tab 显示管理组件', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: { visible: true, role: 'admin', userId: 1, username: 'admin' },
    })
    await flushPromises()

    const navNodes = document.body.querySelectorAll('.nav-item')
    const taskNav = Array.from(navNodes).find((node) => (node.textContent || '').includes('定时任务'))
    expect(taskNav).toBeTruthy()
    taskNav.click()
    await flushPromises()

    expect(document.body.querySelector('.task-scheduler-manager')).not.toBeNull()
    wrapper.unmount()
  })
})
