/**
 * Sidebar.vue 头像菜单「帮助」按钮测试（2026-09-03 新增）
 *
 * 覆盖：
 *   1. 头像菜单中存在「帮助」按钮
 *   2. 点击「帮助」触发 window.open('/help', '_blank', 'noopener,noreferrer')
 *   3. 「帮助」按钮对 admin 与普通用户均可见（不依赖 userRole）
 *
 * 注意：用户菜单用 <Teleport to="body"> 渲染，测试需从 document.body 查询
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

// mock vue-router useRoute / useRouter
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
  attachTo: document.body,
})

/**
 * 从 document.body 找当前 Teleport 出的 .user-menu
 */
function findUserMenuItems() {
  // user-menu 是 Teleport 到 body 上，wrapper 内部 findAll 拿不到
  const menu = document.body.querySelector('.user-menu')
  if (!menu) return []
  // 注意：v-show 隐藏的元素仍在 DOM 中，只是 style="display:none"
  const items = Array.from(menu.querySelectorAll('.user-menu-item'))
  return items
}

/**
 * 触发指定文本或 selector 的菜单项
 * - 传 text 时按 textContent 匹配（管理后台/设置/退出登录 等文字菜单）
 * - 传 selector 时按 querySelector 匹配（图标菜单如"帮助"：'.user-menu-item--icon-only'）
 * @param {string} target - 菜单项文本 或 CSS selector
 */
function clickUserMenuItem(target) {
  const items = findUserMenuItems()
  let item = null
  if (target.startsWith('.') || target.includes('[')) {
    item = items.find((el) => el.matches(target))
  } else {
    item = items.find((el) => el.textContent.includes(target))
  }
  if (!item) throw new Error(`未找到匹配「${target}」的菜单项`)
  item.click()
}

describe('Sidebar.vue 头像菜单「帮助」按钮', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    // 屏蔽真实 window.open（默认成功打开，避免触发 notice 路径污染其他用例）
    window.open = vi.fn().mockReturnValue({})
    // 用 unmount() 替代 innerHTML = '' 清理，避免破坏 attachTo 引用导致后续 mount 失败
  })

  afterEach(() => {
    // 清理每次测试挂载的 Sidebar（确保 Teleport 内容被卸载）
    // 此处无 wrapper 句柄，由各用例负责 unmount；统一清掉残留 help-blocked-notice
    document.querySelectorAll('.help-blocked-notice').forEach((el) => el.remove())
  })

  it('打开头像菜单后存在「帮助」菜单项', async () => {
    const wrapper = mountSidebar()
    try {
      // 点击头像打开
      await wrapper.find('.sidebar-user').trigger('click')
      await nextTick()
      // 再等一帧让 Teleport 完成
      await nextTick()

      const items = findUserMenuItems()
      // 2026-09-03 简化：「帮助」按钮只剩图标（class="user-menu-item--icon-only"），
      // 不再含文字 "帮助"。改用 class 选择器定位。
      const helpItem = items.find((el) => el.classList.contains('user-menu-item--icon-only'))
      expect(helpItem).toBeTruthy()
      // 「帮助」应在「管理后台」之前出现
      const adminItem = items.find((el) => el.textContent.includes('管理后台'))
      const helpIdx = items.indexOf(helpItem)
      const adminIdx = items.indexOf(adminItem)
      expect(helpIdx).toBeLessThan(adminIdx)
    } finally {
      wrapper.unmount()
    }
  })

  it('点击「帮助」触发 window.open 新 Tab 打开（不带 features 参数，避免 popup-blocking）', async () => {
    const wrapper = mountSidebar()
    try {
      await wrapper.find('.sidebar-user').trigger('click')
      await nextTick()
      await nextTick()

      clickUserMenuItem('.user-menu-item--icon-only')

      expect(window.open).toHaveBeenCalledTimes(1)
      // 2026-09-03 修复：仅传 target，不传 features 字符串
      // 原因：`noopener,noreferrer` 会在某些浏览器（Firefox 严格模式 / Safari ITP）触发 popup-blocking
      // 返回 null，导致原兜底 window.location.href='/help' 污染主 Tab
      expect(window.open).toHaveBeenCalledWith('/help', '_blank')
    } finally {
      wrapper.unmount()
    }
  })

  it('「帮助」按钮对 admin 与普通用户均可见', async () => {
    const adminWrapper = mountSidebar({ userRole: 'admin' })
    try {
      await adminWrapper.find('.sidebar-user').trigger('click')
      await nextTick()
      await nextTick()
      const adminItems = findUserMenuItems()
      const adminHasHelp = adminItems.some((el) => el.classList.contains('user-menu-item--icon-only'))
      expect(adminHasHelp).toBe(true)
    } finally {
      adminWrapper.unmount()
    }

    const userWrapper = mountSidebar({ userRole: 'user' })
    try {
      await userWrapper.find('.sidebar-user').trigger('click')
      await nextTick()
      await nextTick()
      const userItems = findUserMenuItems()
      const userHasHelp = userItems.some((el) => el.classList.contains('user-menu-item--icon-only'))
      expect(userHasHelp).toBe(true)
    } finally {
      userWrapper.unmount()
    }
  })

  it('window.open 被浏览器拦截时显示非阻塞 notice（不再 alert，避免卡死假象）', async () => {
    // 模拟 window.open 返回 null（拦截）
    window.open = vi.fn().mockReturnValue(null)
    // mock alert 防止 happy-dom 抛错；确保**不调用** alert（替代方案是页面内 notice）
    const alertSpy = vi.fn()
    window.alert = alertSpy
    // 记录原始 location.href 防止测试污染
    const originalHref = window.location.href
    // console.warn spy
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const wrapper = mountSidebar()
    try {
      await wrapper.find('.sidebar-user').trigger('click')
      await nextTick()
      await nextTick()

      clickUserMenuItem('.user-menu-item--icon-only')
      // 多等一帧让 Teleport 渲染 + Vue 异步更新完成
      await nextTick()
      await nextTick()

      expect(window.open).toHaveBeenCalled()
      // 2026-09-03 修复：拦截时**不再**调 alert（alert 会阻塞主 Tab = 卡死）
      // 改为页面右下角非阻塞 notice + console.warn
      expect(alertSpy).not.toHaveBeenCalled()
      expect(warnSpy).toHaveBeenCalled()
      expect(window.location.href).toBe(originalHref)
      // notice 通过 Teleport 渲染到 body，从 document.body 查询
      const notice = document.body.querySelector('.help-blocked-notice')
      expect(notice).toBeTruthy()
      expect(notice.textContent).toContain('帮助页面被浏览器拦截')
      // 提供三个操作按钮
      const buttons = notice.querySelectorAll('.help-blocked-notice__btn')
      expect(buttons.length).toBeGreaterThanOrEqual(3)
    } finally {
      wrapper.unmount()
    }
  })

  it('点击「在当前页打开」关闭 notice（router.push 由 vue-router 接管，handleHelp 链路验证）', async () => {
    window.open = vi.fn().mockReturnValue(null)
    const wrapper = mountSidebar()
    try {
      await wrapper.find('.sidebar-user').trigger('click')
      await nextTick()
      await nextTick()
      clickUserMenuItem('.user-menu-item--icon-only')
      await nextTick()

      const notice = document.body.querySelector('.help-blocked-notice')
      expect(notice).toBeTruthy()
      // 点「在当前页打开」按钮
      const primaryBtn = notice.querySelector('.help-blocked-notice__btn--primary')
      expect(primaryBtn).toBeTruthy()
      primaryBtn.click()
      await nextTick()
      // notice 应消失（router.push 失败时已 catch，不会让 notice 残留）
      expect(document.body.querySelector('.help-blocked-notice')).toBeFalsy()
    } finally {
      wrapper.unmount()
    }
  })

  it('点击 notice ✕ 关闭按钮立即关闭 notice', async () => {
    window.open = vi.fn().mockReturnValue(null)
    const wrapper = mountSidebar()
    try {
      await wrapper.find('.sidebar-user').trigger('click')
      await nextTick()
      await nextTick()
      clickUserMenuItem('.user-menu-item--icon-only')
      await nextTick()

      const notice = document.body.querySelector('.help-blocked-notice')
      expect(notice).toBeTruthy()
      const closeBtn = notice.querySelector('.help-blocked-notice__btn--close')
      expect(closeBtn).toBeTruthy()
      closeBtn.click()
      await nextTick()
      expect(document.body.querySelector('.help-blocked-notice')).toBeFalsy()
    } finally {
      wrapper.unmount()
    }
  })
})
