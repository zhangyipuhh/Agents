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
 * 触发指定文本的菜单项点击
 */
function clickUserMenuItem(text) {
  const items = findUserMenuItems()
  const item = items.find((el) => el.textContent.includes(text))
  if (!item) throw new Error(`未找到含「${text}」的菜单项`)
  item.click()
}

describe('Sidebar.vue 头像菜单「帮助」按钮', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    // 屏蔽真实 window.open
    window.open = vi.fn().mockReturnValue({})
    // 清理 body 中可能的残留
    document.body.innerHTML = ''
  })

  it('打开头像菜单后存在「帮助」菜单项', async () => {
    const wrapper = mountSidebar()
    // 点击头像打开
    await wrapper.find('.sidebar-user').trigger('click')
    await nextTick()
    // 再等一帧让 Teleport 完成
    await nextTick()

    const items = findUserMenuItems()
    const helpItem = items.find((el) => el.textContent.includes('帮助'))
    expect(helpItem).toBeTruthy()
    // 「帮助」应在「管理后台」之前出现
    const adminItem = items.find((el) => el.textContent.includes('管理后台'))
    const helpIdx = items.indexOf(helpItem)
    const adminIdx = items.indexOf(adminItem)
    expect(helpIdx).toBeLessThan(adminIdx)
  })

  it('点击「帮助」触发 window.open 新 Tab 打开（不带 features 参数，避免 popup-blocking）', async () => {
    const wrapper = mountSidebar()
    await wrapper.find('.sidebar-user').trigger('click')
    await nextTick()
    await nextTick()

    clickUserMenuItem('帮助')

    expect(window.open).toHaveBeenCalledTimes(1)
    // 2026-09-03 修复：仅传 target，不传 features 字符串
    // 原因：`noopener,noreferrer` 会在某些浏览器（Firefox 严格模式 / Safari ITP）触发 popup-blocking
    // 返回 null，导致原兜底 window.location.href='/help' 污染主 Tab
    expect(window.open).toHaveBeenCalledWith('/help', '_blank')
  })

  it('「帮助」按钮对 admin 与普通用户均可见', async () => {
    // admin 视角
    const adminWrapper = mountSidebar({ userRole: 'admin' })
    await adminWrapper.find('.sidebar-user').trigger('click')
    await nextTick()
    await nextTick()
    const adminItems = findUserMenuItems()
    const adminHasHelp = adminItems.some((el) => el.textContent.includes('帮助'))
    expect(adminHasHelp).toBe(true)

    // 普通用户视角
    document.body.innerHTML = ''
    const userWrapper = mountSidebar({ userRole: 'user' })
    await userWrapper.find('.sidebar-user').trigger('click')
    await nextTick()
    await nextTick()
    const userItems = findUserMenuItems()
    const userHasHelp = userItems.some((el) => el.textContent.includes('帮助'))
    expect(userHasHelp).toBe(true)
  })

  it('window.open 被浏览器拦截时不污染主 Tab URL（仅 console.warn + 友好 alert，不再跳转）', async () => {
    // 模拟 window.open 返回 null（拦截）
    window.open = vi.fn().mockReturnValue(null)
    // mock alert 防止 happy-dom 抛错
    window.alert = vi.fn()
    // 记录原始 location.href 防止测试污染
    const originalHref = window.location.href
    // console.warn spy
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const wrapper = mountSidebar()
    await wrapper.find('.sidebar-user').trigger('click')
    await nextTick()
    await nextTick()

    clickUserMenuItem('帮助')

    expect(window.open).toHaveBeenCalled()
    // 2026-09-03 修复：拦截时**不再**调用 window.location.href 跳转（会污染主 Tab）
    // 改为 console.warn + 友好 alert，让用户手动复制 URL
    expect(window.alert).toHaveBeenCalled()
    expect(warnSpy).toHaveBeenCalled()
    expect(window.location.href).toBe(originalHref)
  })
})