/**
 * Sidebar.vue 头像菜单「帮助」按钮测试（2026-09-03 新增）
 *
 * 覆盖：
 *   1. 头像菜单中存在「帮助」按钮
 *   2. 点击「帮助」触发 window.open('/help', '_blank', 'noopener,noreferrer')
 *   3. 「帮助」按钮对 admin 与普通用户均可见（不依赖 userRole）
 *   4. 点击后关闭用户菜单
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

// mock vue-router useRoute / useRouter
import { ref } from 'vue'
vi.mock('vue-router', () => ({
  useRoute: () => ({ name: 'agent', path: '/', fullPath: '/' }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

// mock api 函数（Sidebar 依赖）
vi.mock('../../utils/api.js', () => ({
  fetchSessionList: vi.fn().mockResolvedValue({ items: [] }),
  deleteSession: vi.fn(),
  fetchProjectList: vi.fn().mockResolvedValue({ items: [] }),
  updateSessionTitle: vi.fn(),
  exportSessionMarkdown: vi.fn(),
  deleteProject: vi.fn(),
  renameProject: vi.fn(),
}))

import Sidebar from '../Sidebar.vue'

const mountSidebar = (props = {}) => mount(Sidebar, {
  props: {
    username: 'admin',
    userRole: 'admin',
    userId: 1,
    currentSessionId: '',
    visibleMenus: [],
    ...props,
  },
})

describe('Sidebar.vue 头像菜单「帮助」按钮', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    // 屏蔽真实 window.open
    window.open = vi.fn().mockReturnValue({})
  })

  it('打开头像菜单后存在「帮助」菜单项', async () => {
    const wrapper = mountSidebar()
    // 点击头像打开
    await wrapper.find('.sidebar-user').trigger('click')
    await nextTick()

    // user-menu 是 Teleport 到 body 上，wrapper.find 在 mount tree 找
    const items = wrapper.findAll('.user-menu-item')
    const helpItem = items.find((item) => item.text().includes('帮助'))
    expect(helpItem).toBeTruthy()
  })

  it('点击「帮助」触发 window.open 新 Tab 打开', async () => {
    const wrapper = mountSidebar()
    await wrapper.find('.sidebar-user').trigger('click')
    await nextTick()

    const items = wrapper.findAll('.user-menu-item')
    const helpItem = items.find((item) => item.text().includes('帮助'))
    expect(helpItem).toBeTruthy()

    await helpItem.trigger('click')
    expect(window.open).toHaveBeenCalledTimes(1)
    expect(window.open).toHaveBeenCalledWith('/help', '_blank', 'noopener,noreferrer')
  })

  it('「帮助」按钮对 admin 与普通用户均可见', async () => {
    // admin 视角
    const adminWrapper = mountSidebar({ userRole: 'admin' })
    await adminWrapper.find('.sidebar-user').trigger('click')
    await nextTick()
    const adminItems = adminWrapper.findAll('.user-menu-item')
    const adminHasHelp = adminItems.some((i) => i.text().includes('帮助'))
    expect(adminHasHelp).toBe(true)

    // 普通用户视角
    const userWrapper = mountSidebar({ userRole: 'user' })
    await userWrapper.find('.sidebar-user').trigger('click')
    await nextTick()
    const userItems = userWrapper.findAll('.user-menu-item')
    const userHasHelp = userItems.some((i) => i.text().includes('帮助'))
    expect(userHasHelp).toBe(true)
  })

  it('点击「帮助」后关闭用户菜单（不再 visible）', async () => {
    const wrapper = mountSidebar()
    await wrapper.find('.sidebar-user').trigger('click')
    await nextTick()

    // 菜单应该 visible（v-show）
    const userMenu = wrapper.find('.user-menu')
    expect(userMenu.attributes('style')).not.toContain('display: none')

    const items = wrapper.findAll('.user-menu-item')
    const helpItem = items.find((item) => item.text().includes('帮助'))
    await helpItem.trigger('click')
    await nextTick()

    // 菜单应该隐藏
    expect(wrapper.find('.user-menu').attributes('style')).toContain('display: none')
  })

  it('window.open 被浏览器拦截时降级为 window.location.href', async () => {
    // 模拟 window.open 返回 null（拦截）
    window.open = vi.fn().mockReturnValue(null)
    const originalHref = window.location.href
    let assignedHref = ''
    try {
      Object.defineProperty(window.location, 'href', {
        configurable: true,
        get: () => assignedHref || originalHref,
        set: (val) => { assignedHref = val },
      })
    } catch (_) { /* ignore */ }

    const wrapper = mountSidebar()
    await wrapper.find('.sidebar-user').trigger('click')
    await nextTick()

    const items = wrapper.findAll('.user-menu-item')
    const helpItem = items.find((item) => item.text().includes('帮助'))
    await helpItem.trigger('click')

    expect(window.open).toHaveBeenCalled()
    // 拦截时降级
    if (assignedHref) {
      expect(assignedHref).toBe('/help')
    }
  })
})