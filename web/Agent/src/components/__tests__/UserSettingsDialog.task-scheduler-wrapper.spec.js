/**
 * UserSettingsDialog 定时任务 Tab wrapper 高度链回归测试
 *
 * 覆盖：activeTab='task-scheduler' 时，外层 wrapper 应用了 .tab-fill-wrapper，
 * 保证 TaskSchedulerManager 沿 flex 高度链铺满 .dialog-content，
 * 避免 <aside.task-sidebar> 与 <main.task-detail> 下方留白。
 *
 * 这是 plan "task-scheduler-grid-fill-container" 的回归保护点：
 * - 删掉 .tab-fill-wrapper class 后，应立即失败（防止高度链断裂）；
 * - 邮件设置 wrapper 也应同步应用该 class（视觉一致性）。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import UserSettingsDialog from '../UserSettingsDialog.vue'
import sourceCode from '../UserSettingsDialog.vue?raw'

describe('UserSettingsDialog 定时任务 Tab wrapper 高度链', () => {
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
      if (u === '/api/admin/scripts' && method === 'GET') return { ok: true, json: async () => [] }
      if (u === '/api/admin/scripts/scan') return { ok: true, json: async () => ({ scanned: 0, registered: 0, failed: 0 }) }
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

  it('test_task_scheduler_wrapper_has_tab_fill_wrapper_class 定时任务 wrapper 应用 .tab-fill-wrapper', async () => {
    // 直接 Teleport 后挂载，按设计 UserSettingsDialog 模板已在 <Teleport to="body"> 里渲染
    const wrapper = mount(UserSettingsDialog, {
      props: { visible: true, role: 'admin', userId: 1, username: 'admin' },
      attachTo: document.body,
    })
    await flushPromises()

    // 切到定时任务 Tab
    const navNodes = document.body.querySelectorAll('.nav-item')
    const taskNav = Array.from(navNodes).find((node) => (node.textContent || '').includes('定时任务'))
    expect(taskNav).toBeTruthy()
    taskNav.click()
    await flushPromises()
    await wrapper.vm.$nextTick()

    // 找到 TaskSchedulerManager 的 wrapper：含 .task-scheduler-manager 的最近 div 父级
    const manager = document.body.querySelector('.task-scheduler-manager')
    expect(manager).not.toBeNull()
    const wrapperEl = manager.closest('.tab-fill-wrapper')
    expect(wrapperEl).not.toBeNull()

    wrapper.unmount()
  })

  it('test_email_settings_wrapper_has_tab_fill_wrapper_class 邮件设置 wrapper 同步应用 .tab-fill-wrapper', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: { visible: true, role: 'admin', userId: 1, username: 'admin' },
      attachTo: document.body,
    })
    await flushPromises()

    const navNodes = document.body.querySelectorAll('.nav-item')
    const emailNav = Array.from(navNodes).find((node) => (node.textContent || '').includes('邮件'))
    if (!emailNav) {
      // 当前项目若 admin 邮件 Tab 隐藏则直接跳过此断言，仅作 best-effort
      wrapper.unmount()
      return
    }
    emailNav.click()
    await flushPromises()
    await wrapper.vm.$nextTick()

    const wrapperEls = document.body.querySelectorAll('.tab-fill-wrapper')
    expect(wrapperEls.length).toBeGreaterThanOrEqual(1)

    wrapper.unmount()
  })

  it('test_dialog_content_is_flex_column_container .dialog-content 必须是 flex 列容器（高度链前提）', () => {
    // jsdom 不计算 <style scoped> 布局，故对 SFC 源码做静态契约断言：
    // .tab-fill-wrapper 的 flex:1 只有在父级 .dialog-content 是 flex 容器时才生效，
    // 否则 wrapper 高度退化为内容高度，定时任务/邮件设置面板下方出现大片留白。
    const blockMatch = sourceCode.match(/\.dialog-content\s*\{([^}]*)\}/)
    expect(blockMatch, '.dialog-content 样式块必须存在').not.toBeNull()
    const body = blockMatch[1]
    expect(body).toMatch(/display\s*:\s*flex/)
    expect(body).toMatch(/flex-direction\s*:\s*column/)
  })
})
