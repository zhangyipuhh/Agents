/**
 * UserSettingsDialog 普通用户左侧导航栏回归测试
 *
 * 覆盖：所有用户角色都能看到左侧 .dialog-nav 导航栏；
 * 普通用户（role='user'）仅显示「个人设置」一项；
 * 标题统一为「用户设置与管理」。
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
  return Array.from(nodes).map((n) => (n.textContent || '').trim())
}

/**
 * 从 document.body 收集所有 .dialog-nav 元素
 * @returns {Array<Element>} .dialog-nav 元素列表
 */
function getDialogNavElements() {
  return Array.from(document.body.querySelectorAll('.dialog-nav'))
}

describe('UserSettingsDialog 普通用户左侧导航栏', () => {
  let originalFetch
  let originalLocalStorage

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
    global.fetch = vi.fn(async (url, opts = {}) => {
      const u = typeof url === 'string' ? url : url.url
      if (u.includes('/api/users/')) {
        return {
          ok: true,
          json: async () => ({
            id: 1,
            username: 'user1',
            role: 'user',
            real_name: '',
            phone: '',
            email: '',
            department: '',
            position: '',
            allowed_agents: [],
            created_at: '2026-07-23',
            updated_at: '2026-07-23',
          })
        }
      }
      return { ok: true, json: async () => [] }
    })
    global.localStorage = {
      getItem: vi.fn((key) => {
        if (key === 'user_id') return '1'
        if (key === 'auth_token') return 'fake-token'
        if (key === 'session_id') return 'fake-session'
        return null
      }),
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

  it('test_user_sees_dialog_nav 普通用户也能看到 .dialog-nav 左侧导航栏', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'user',
        userId: 1,
        username: 'user1',
      },
    })
    await flushPromises()
    const navs = getDialogNavElements()
    expect(navs.length).toBe(1)
    wrapper.unmount()
  })

  it('test_user_nav_contains_only_profile 普通用户 .dialog-nav 只包含「个人设置」一项', async () => {
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
    expect(navTexts.length).toBe(1)
    expect(navTexts[0]).toBe('个人设置')
    wrapper.unmount()
  })

  it('test_user_dialog_body_uses_horizontal_layout 普通用户 dialog-body 使用水平布局（dialog-body-horizontal）', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'user',
        userId: 1,
        username: 'user1',
      },
    })
    await flushPromises()
    const dialogBody = document.body.querySelector('.dialog-body')
    expect(dialogBody).not.toBeNull()
    expect(dialogBody.classList.contains('dialog-body-horizontal')).toBe(true)
    wrapper.unmount()
  })

  it('test_user_title_unified_to_admin_text 普通用户标题统一为「用户设置与管理」', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'user',
        userId: 1,
        username: 'user1',
      },
    })
    await flushPromises()
    const title = document.body.querySelector('.dialog-title')
    expect(title).not.toBeNull()
    expect((title.textContent || '').trim()).toBe('用户设置与管理')
    wrapper.unmount()
  })

  it('test_user_profile_nav_item_is_active 普通用户进入 dialog 时「个人设置」处于激活态', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'user',
        userId: 1,
        username: 'user1',
      },
    })
    await flushPromises()
    const activeItems = document.body.querySelectorAll('.nav-item.active')
    expect(activeItems.length).toBe(1)
    expect((activeItems[0].textContent || '').trim()).toBe('个人设置')
    wrapper.unmount()
  })

  it('test_admin_regression_admin 仍显示完整 9 项导航 + 标题为「用户设置与管理」', async () => {
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
    // 2026-07-23：新增「权限管理」一级菜单（admin-only）后，admin 共可见 9 项
    // (个人设置 + 8 个管理类: 用户/智能体/MCP/工具/Skill/运维任务/消息设置/权限管理)
    expect(navTexts.length).toBe(9)
    expect(navTexts).toContain('个人设置')
    expect(navTexts).toContain('用户管理')
    expect(navTexts).toContain('智能体管理')
    expect(navTexts).toContain('权限管理')
    expect(navTexts).toContain('MCP 管理')
    expect(navTexts).toContain('工具管理')
    expect(navTexts).toContain('Skill 管理')
    expect(navTexts).toContain('运维任务')
    // 2026-07-23：email-settings 改名为「消息设置」（与后端注册表 label 对齐）
    expect(navTexts).toContain('消息设置')

    const title = document.body.querySelector('.dialog-title')
    expect((title.textContent || '').trim()).toBe('用户设置与管理')

    const navs = getDialogNavElements()
    expect(navs.length).toBe(1)
    wrapper.unmount()
  })
})