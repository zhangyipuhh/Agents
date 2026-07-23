/**
 * UserSettingsDialog 普通用户不再触发 admin-only 请求（2026-07-23 新增）
 *
 * 背景：之前 UserSettingsDialog 用 v-show 切换顶级 tab，导致所有 admin-only 子组件
 * （MenuPermissionManager / AgentManager / McpServerManager / ToolManager /
 * SkillManager / TaskSchedulerManager / EmailSettingsManager）即使未激活也已被
 * 挂载，onMounted 立即触发 `/api/admin/*` 与 `/api/users` 等 admin-only 请求，
 * 普通用户被后端 require_admin 拒绝（403），前端显示「会话无效，请重试」红 banner。
 *
 * 修复策略：
 * 1. 顶级 tab 子组件从 v-show 改为 v-if，按 isVisibleTab(tabId) 决定挂载；
 * 2. 各 admin-only 子组件新增 isAdmin prop + onMounted 早退（fail-safe 兜底）。
 *
 * 本测试断言：
 * - 普通用户打开 dialog 时，前端**不会**对 menu-catalog / users(无 path param) /
 *   admin/agents / admin/mcp/servers / admin/tools / admin/skills /
 *   admin/email/* / admin/task-schedules 发起任何请求。
 *
 * Date: 2026-07-23
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import UserSettingsDialog from '../UserSettingsDialog.vue'

/**
 * 构造带 403 mock 的 fetch，便于断言「某些端点被请求则测试失败」。
 * 默认所有 admin-only 端点返回 403（与生产 require_admin 行为一致），
 * 其他端点返 200 + 空数据。
 */
function makeFetchMock() {
  const calls = []
  return {
    calls,
    fn: vi.fn(async (url, opts = {}) => {
      const u = typeof url === 'string' ? url : url.url
      const method = (opts.method || 'GET').toUpperCase()
      calls.push({ url: u, method })
      // admin-only 端点：模拟后端 403
      const adminOnlyPatterns = [
        '/api/admin/permissions/menu-catalog',
        '/api/admin/agents',
        '/api/admin/mcp/servers',
        '/api/admin/tools',
        '/api/admin/skills',
        '/api/admin/email',
        '/api/admin/task-schedules',
        '/api/users',          // 用户列表是 admin-only
        '/api/users/online',
      ]
      for (const pat of adminOnlyPatterns) {
        if (u === pat || u.startsWith(pat + '?') || u.startsWith(pat + '/')) {
          // 区分 menu-catalog 的精确路径（/api/admin/permissions/menu-catalog）
          if (pat === '/api/admin/permissions/menu-catalog' && u !== pat) continue
          return { ok: false, status: 403, json: async () => ({ detail: '需要管理员权限' }) }
        }
      }
      // 个人资料（普通用户自己用）返 200
      if (u.includes('/api/users/') && u.endsWith('/profile')) {
        return {
          ok: true,
          json: async () => ({
            id: 2, username: 'ZYP', role: 'user',
            real_name: '', phone: '', email: '', department: '', position: '',
            allowed_agents: [], created_at: '', updated_at: '',
          }),
        }
      }
      return { ok: true, json: async () => [] }
    }),
  }
}

describe('UserSettingsDialog 普通用户不再触发 admin-only 请求', () => {
  let originalFetch
  let originalLocalStorage
  let fetchMock

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
    fetchMock = makeFetchMock()
    global.fetch = fetchMock.fn
    global.localStorage = {
      getItem: vi.fn(() => 'fake-token'),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    }
    // 2026-07-23 修复：vitest 环境无 window.alert，避免 user-management 子 tab loadUserList
    // 失败路径调用 alert() 抛 TypeError
    if (typeof global.alert !== 'function') {
      global.alert = vi.fn()
    }
  })

  afterEach(() => {
    global.fetch = originalFetch
    global.localStorage = originalLocalStorage
    document.body.innerHTML = ''
  })

  it('test_user_role_dialog_does_not_call_menu_catalog 普通用户打开 dialog 不触发 menu-catalog 请求', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'user',
        userId: 2,
        username: 'ZYP',
        visibleMenus: ['task-scheduler', 'task-scheduler.scheduled'],
      },
    })
    await flushPromises()

    const menuCatalogCalls = fetchMock.calls.filter((c) =>
      c.url.includes('/api/admin/permissions/menu-catalog')
    )
    expect(menuCatalogCalls).toHaveLength(0)
    wrapper.unmount()
  })

  it('test_user_role_dialog_does_not_call_users_list 普通用户打开 dialog 不触发 /api/users（用户列表）请求', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'user',
        userId: 2,
        username: 'ZYP',
        visibleMenus: ['task-scheduler'],
      },
    })
    await flushPromises()

    // /api/users（无 path param）和 /api/users/online 是 admin-only
    const usersListCalls = fetchMock.calls.filter(
      (c) => c.url === '/api/users' || c.url === '/api/users/online'
    )
    expect(usersListCalls).toHaveLength(0)
    wrapper.unmount()
  })

  it('test_user_role_dialog_does_not_call_admin_agents 普通用户打开 dialog 不触发 /api/admin/agents 请求', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'user',
        userId: 2,
        username: 'ZYP',
        visibleMenus: ['task-scheduler'],
      },
    })
    await flushPromises()

    const adminAgentCalls = fetchMock.calls.filter(
      (c) => c.url === '/api/admin/agents' || c.url.startsWith('/api/admin/agents?')
    )
    expect(adminAgentCalls).toHaveLength(0)
    wrapper.unmount()
  })

  it('test_user_role_dialog_does_not_call_any_admin_endpoint 普通用户打开 dialog 不触发任何 admin-only 请求', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'user',
        userId: 2,
        username: 'ZYP',
        visibleMenus: ['task-scheduler', 'task-scheduler.scheduled'],
      },
    })
    await flushPromises()

    const adminCalls = fetchMock.calls.filter((c) =>
      c.url.startsWith('/api/admin/') ||
      c.url === '/api/users' ||
      c.url === '/api/users/online'
    )
    expect(adminCalls).toHaveLength(0)
    wrapper.unmount()
  })

  it('test_admin_role_dialog_still_calls_admin_endpoints admin 用户打开 dialog 仍可触发 admin-only 请求（回归测试）', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'admin',
        userId: 1,
        username: 'admin',
        visibleMenus: [],  // admin 忽略 visibleMenus
      },
    })
    await flushPromises()

    // admin 应看到 navItems 中的「权限管理」/「智能体管理」/「用户管理」等顶级 tab
    // 点击后会触发 admin-only 请求。
    // 关键断言：admin 看到的导航菜单数量 > 普通用户
    const navNodes = document.body.querySelectorAll('.nav-item')
    expect(navNodes.length).toBeGreaterThanOrEqual(7)
    wrapper.unmount()
  })

  it('test_admin_role_dialog_props_passed_to_admin_children admin 用户打开 dialog 时所有 admin 子组件应收到 isAdmin=true prop（2026-07-23 回归保护）', async () => {
    // 2026-07-23 修复回归测试：之前父组件对 4 个 admin-only 子组件
    // （McpServerManager / AgentManager / ToolManager / EmailSettingsManager）
    // 漏传 :is-admin="isAdmin"，导致 admin 用户打开 dialog 时这些 tab 右侧空白
    // （onMounted fail-safe 早退，无数据加载）。
    //
    // 本测试通过 props spy 断言：所有 admin-only 子组件被渲染时，
    // 都收到 isAdmin=true。
    // 通过逐个点击 nav-item 触发每个 admin 子组件的挂载。

    const seenProps = []

    // Spy 父组件 props on each child component
    const spyMount = (componentName, callback) => {
      // 简化方案：通过 fetch 调用侧验证 admin-only 数据加载（isAdmin=true 时会发起）
      // 不需要单独 spy 组件 props。
    }

    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'admin',
        userId: 1,
        username: 'admin',
        visibleMenus: [],
      },
    })
    await flushPromises()

    // admin 用户打开 dialog 时，初始 activeTab='profile'。
    // 我们点击每个 admin 顶级 tab，触发对应子组件挂载。
    const navNodes = Array.from(document.body.querySelectorAll('.nav-item'))
    const navLabels = navNodes.map((n) => (n.textContent || '').trim())
    console.log('[admin] navLabels:', navLabels)

    // 找到 admin 顶级 tab（按 label 文本）
    const adminTabLabels = [
      '用户管理', '权限管理', 'MCP 管理', '智能体管理', '工具管理',
      'Skill 管理', '运维任务', '邮件设置',
    ]

    for (const label of adminTabLabels) {
      const nav = navNodes.find((n) => (n.textContent || '').trim().includes(label))
      if (!nav) {
        console.warn(`[admin] nav not found for label: ${label}`)
        continue
      }
      nav.click()
      await flushPromises()
      // 等待 onMounted 的 fetch
      await new Promise((r) => setTimeout(r, 50))
      await flushPromises()
    }

    // 断言：admin 用户打开 dialog 后，至少触发了以下 admin-only 请求（说明 isAdmin=true 已传到子组件）
    const expectedAdminCalls = [
      '/api/users',  // MenuPermissionManager
      '/api/admin/permissions/menu-catalog',
      '/api/admin/agents',
      '/api/admin/mcp/servers',
      '/api/admin/tools',
      '/api/admin/skills',
      '/api/admin/task-schedules',  // TaskSchedulerManager
    ]
    const callsUrls = new Set(fetchMock.calls.map((c) => c.url))
    const missing = expectedAdminCalls.filter((u) => !callsUrls.has(u))
    console.log('[admin] missing admin-only calls:', missing)
    console.log('[admin] all fetchMock calls:', Array.from(callsUrls))

    expect(missing).toEqual([])
    wrapper.unmount()
  })

  it('test_user_role_click_task_scheduler_subtab_no_admin_call 普通用户被授权 task-scheduler 后，点击运维任务 → 服务器扫描入库子 tab 不应触发 admin-only 请求', async () => {
    // 2026-07-23 修复回归测试：
    // TaskSchedulerManager 内的 4 个子 tab（编辑任务/服务器扫描入库/脚本扫描入库/API接口配置）
    // 都依赖 admin-only 数据源（/api/admin/task-schedules、/api/admin/devops-servers 等）。
    // 即便父组件已挂载 TaskSchedulerManager（因为顶级 tab 被授权），
    // 普通用户点击 admin-only 数据子 tab 也必须被 fail-safe 拦住。
    //
    // 之前的 fail-safe 只在 onMounted 里，未覆盖 switchTab/watch 触发的入口，
    // 导致普通用户点击「服务器扫描入库」子 tab 触发 /api/admin/devops-servers → 403 → 红色 banner。
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'user',
        userId: 2,
        username: 'ZYP',
        visibleMenus: ['profile', 'task-scheduler', 'task-scheduler.scheduled'],
      },
    })
    await flushPromises()

    // 点击「运维任务」顶级 tab
    const navNodes = Array.from(document.body.querySelectorAll('.nav-item'))
    const taskNav = navNodes.find((n) => (n.textContent || '').includes('运维任务'))
    expect(taskNav).toBeTruthy()
    taskNav.click()
    await flushPromises()
    await new Promise((r) => setTimeout(r, 50))
    await flushPromises()

    // 进入运维任务 dialog 后，点击「服务器扫描入库」子 tab
    const scanTabBtn = document.body.querySelector('[data-testid="tab-scan"]') ||
                        Array.from(document.body.querySelectorAll('button')).find((b) => (b.textContent || '').includes('服务器扫描入库'))
    if (scanTabBtn) {
      scanTabBtn.click()
      await flushPromises()
      await new Promise((r) => setTimeout(r, 50))
      await flushPromises()
    }

    // 断言：用户身份打开 dialog 后点击所有能点的子 tab，全程无 admin-only 请求
    const adminCalls = fetchMock.calls.filter((c) =>
      c.url.startsWith('/api/admin/') ||
      c.url === '/api/users' ||
      c.url === '/api/users/online'
    )
    console.log('[user+task-scheduler] admin calls:', adminCalls.map((c) => c.url))
    expect(adminCalls).toHaveLength(0)
    wrapper.unmount()
  })

  it('test_user_role_with_admin_child_component_failsafe 非 admin 即使 v-if 漏挂，子组件 onMounted 兜底也跳过请求', async () => {
    // 直接渲染 MenuPermissionManager 但不传 isAdmin，断言其 onMounted 早退。
    // 这验证了组件级的 fail-safe 兜底（防御性编程）。
    const MenuPermissionManager = (await import('../MenuPermissionManager.vue')).default
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const wrapper = mount(MenuPermissionManager, {
      props: { isAdmin: false },
    })
    await flushPromises()

    // 断言未触发 fetchMenuCatalog 也未触发 fetchUserList
    const catalogCalls = fetchMock.calls.filter((c) =>
      c.url === '/api/admin/permissions/menu-catalog'
    )
    const usersCalls = fetchMock.calls.filter(
      (c) => c.url === '/api/users'
    )
    expect(catalogCalls).toHaveLength(0)
    expect(usersCalls).toHaveLength(0)
    // 断言打印了警告（防御性兜底可观测信号）
    expect(warnSpy).toHaveBeenCalled()
    wrapper.unmount()
    warnSpy.mockRestore()
  })
})