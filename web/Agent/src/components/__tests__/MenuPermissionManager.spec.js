/**
 * MenuPermissionManager 组件测试
 *
 * 覆盖：
 * - 左侧人员列表 + 搜索过滤
 * - 切换人员自动加载 grants
 * - 右侧树形 checkbox（一级 + 二级）
 * - 父级半选态（indeterminate）
 * - 「个人设置」永远 checked + disabled
 * - enabled=False 菜单隐藏
 * - 保存触发 PUT
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import MenuPermissionManager from '../MenuPermissionManager.vue'

const mockCatalog = {
  items: [
    { id: 'profile', level: 1, parent_id: null, label: '个人设置', icon_key: 'user', sort_order: 1, required_role: null, enabled: true },
    { id: 'user-management', level: 1, parent_id: null, label: '用户管理', icon_key: 'users', sort_order: 2, required_role: 'admin', enabled: true },
    { id: 'user-management.users', level: 2, parent_id: 'user-management', label: '用户列表', icon_key: 'list', sort_order: 1, required_role: 'admin', enabled: true },
    { id: 'user-management.online-monitor', level: 2, parent_id: 'user-management', label: '在线监控', icon_key: 'eye', sort_order: 2, required_role: 'admin', enabled: true },
    { id: 'task-scheduler', level: 1, parent_id: null, label: '运维任务', icon_key: 'clock', sort_order: 8, required_role: 'admin', enabled: true },
    // 2026-07-23：「邮件设置」升级为一级菜单，id 保持 task-scheduler.email-settings，sort_order=9
    { id: 'task-scheduler.email-settings', level: 1, parent_id: null, label: '邮件设置', icon_key: 'mail', sort_order: 9, required_role: 'admin', enabled: true },
    { id: 'disabled-menu', level: 1, parent_id: null, label: '已禁用菜单', icon_key: 'x', sort_order: 99, required_role: 'admin', enabled: false }
  ]
}

const mockUserList = [
  { id: 1, username: 'admin', role: 'admin', real_name: '管理员', allowed_agents: [], created_at: '2026-01-01', updated_at: '2026-01-01' },
  { id: 2, username: 'zhangsan', role: 'user', real_name: '张三', allowed_agents: [], created_at: '2026-01-01', updated_at: '2026-01-01' },
  { id: 3, username: 'lisi', role: 'user', real_name: '李四', allowed_agents: [], created_at: '2026-01-01', updated_at: '2026-01-01' }
]

function jsonResponse(data, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => data }
}

function setupFetchMock({ grantsByUser = {} } = {}) {
  global.fetch = vi.fn(async (url, opts = {}) => {
    const urlStr = String(url)
    const method = (opts.method || 'GET').toUpperCase()

    if (urlStr.includes('/menu-catalog') && method === 'GET') {
      return jsonResponse(mockCatalog)
    }
    // /api/users (人员列表)
    if (urlStr.includes('/api/users') && !urlStr.includes('/grants') && method === 'GET') {
      return jsonResponse(mockUserList)
    }
    // /api/admin/permissions/users/{id}/grants
    const grantsMatch = urlStr.match(/\/users\/(\d+)\/grants/)
    if (grantsMatch) {
      const uid = grantsMatch[1]
      if (method === 'GET') {
        return jsonResponse({ menu_ids: grantsByUser[uid] || ['profile'] })
      }
      if (method === 'PUT') {
        const body = JSON.parse(opts.body || '{}')
        grantsByUser[uid] = body.menu_ids
        return jsonResponse({ menu_ids: body.menu_ids })
      }
    }
    return jsonResponse({ detail: 'not mocked' }, 404)
  })
}

describe('MenuPermissionManager', () => {
  beforeEach(() => {
    setupFetchMock()
  })

  it('test_renders_user_list_and_menu_tree 渲染左侧人员列表 + 右侧菜单树', async () => {
    const wrapper = mount(MenuPermissionManager)
    await flushPromises()
    expect(wrapper.find('[data-testid="user-list"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="menu-tree"]').exists()).toBe(true)
  })

  it('test_disabled_menu_not_rendered enabled=False 的菜单不渲染', async () => {
    const wrapper = mount(MenuPermissionManager)
    await flushPromises()
    expect(wrapper.find('[data-testid="menu-checkbox-disabled-menu"]').exists()).toBe(false)
  })

  it('test_profile_checkbox_always_checked_and_disabled profile 永远 checked+disabled', async () => {
    const wrapper = mount(MenuPermissionManager)
    await flushPromises()
    const profileCb = wrapper.find('[data-testid="menu-checkbox-profile"]')
    expect(profileCb.element.checked).toBe(true)
    expect(profileCb.element.disabled).toBe(true)
  })

  it('test_loads_user_grants_on_user_select 切换人员自动加载 grants', async () => {
    setupFetchMock({ grantsByUser: { 2: ['profile', 'user-management.users'] } })
    const wrapper = mount(MenuPermissionManager)
    await flushPromises()
    // 选中 zhangsan (id=2)
    const items = wrapper.findAll('[data-testid="user-list-item"]')
    expect(items.length).toBeGreaterThan(1)
    await items[1].trigger('click')
    await flushPromises()
    const calls = global.fetch.mock.calls
    const grantsCall = calls.find(c => String(c[0]).includes('/users/2/grants') && (c[1]?.method || 'GET') === 'GET')
    expect(grantsCall).toBeTruthy()
  })

  it('test_parent_checkbox_indeterminate_when_partial 父级半选态', async () => {
    setupFetchMock({ grantsByUser: { 2: ['profile', 'user-management.users'] } })
    const wrapper = mount(MenuPermissionManager)
    await flushPromises()
    const items = wrapper.findAll('[data-testid="user-list-item"]')
    await items[1].trigger('click')
    await flushPromises()
    const parentCb = wrapper.find('[data-testid="menu-checkbox-user-management"]')
    expect(parentCb.exists()).toBe(true)
    expect(parentCb.element.indeterminate).toBe(true)
    expect(parentCb.element.checked).toBe(false)
  })

  it('test_save_calls_put 保存触发 PUT', async () => {
    const wrapper = mount(MenuPermissionManager)
    await flushPromises()
    const items = wrapper.findAll('[data-testid="user-list-item"]')
    await items[1].trigger('click') // 选 zhangsan
    await flushPromises()
    await wrapper.find('[data-testid="save-button"]').trigger('click')
    await flushPromises()
    const calls = global.fetch.mock.calls
    const putCall = calls.find(c => String(c[0]).includes('/users/2/grants') && c[1]?.method === 'PUT')
    expect(putCall).toBeTruthy()
  })

  it('test_search_filters_user_list 搜索过滤人员', async () => {
    const wrapper = mount(MenuPermissionManager)
    await flushPromises()
    const searchInput = wrapper.find('[data-testid="user-search"]')
    await searchInput.setValue('zhang')
    await flushPromises()
    const visibleItems = wrapper.findAll('[data-testid="user-list-item"]')
    // 只剩 zhangsan 匹配
    expect(visibleItems.length).toBe(1)
  })

  // 2026-07-23：「邮件设置」升级为一级菜单，回归保护：
  // - task-scheduler.email-settings 应作为一级 checkbox 渲染
  // - 不应再作为 task-scheduler 的 children checkbox 出现
  it('test_email_settings_is_level1_not_under_task_scheduler 邮件设置是一级菜单而非运维任务子级', async () => {
    const wrapper = mount(MenuPermissionManager)
    await flushPromises()
    // 一级：存在 menu-checkbox-task-scheduler.email-settings
    const l1 = wrapper.find('[data-testid="menu-checkbox-task-scheduler.email-settings"]')
    expect(l1.exists()).toBe(true)
    // 选 zhangsan
    const items = wrapper.findAll('[data-testid="user-list-item"]')
    await items[1].trigger('click')
    await flushPromises()
    // 切到任务调度父级，不应半选（子集为空）
    const parent = wrapper.find('[data-testid="menu-checkbox-task-scheduler"]')
    expect(parent.exists()).toBe(true)
    expect(parent.element.indeterminate).toBe(false)
  })
})