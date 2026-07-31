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
    // 2026-07-31：邮件设置降级为「消息设置」(messaging) 下的二级菜单
    // 2026-07-31 二次调整：删除 task-scheduler.email-settings 中间层，新增 channel 级 messaging.email
    // - messaging 一级菜单（sort_order=10）
    // - messaging.email channel（level=2, parent_id=messaging, sort_order=1）
    // - 三个 Tab（server/policies/test）parent_id 改为 messaging.email
    { id: 'messaging', level: 1, parent_id: null, label: '消息设置', icon_key: 'message', sort_order: 10, required_role: 'admin', enabled: true },
    { id: 'messaging.email', level: 2, parent_id: 'messaging', label: '邮件设置', icon_key: 'mail', sort_order: 1, required_role: 'admin', enabled: true },
    { id: 'task-scheduler.email-settings.server', level: 2, parent_id: 'messaging.email', label: '服务器配置', icon_key: 'server', sort_order: 1, required_role: 'admin', enabled: true },
    { id: 'task-scheduler.email-settings.policies', level: 2, parent_id: 'messaging.email', label: '发送策略', icon_key: 'list', sort_order: 2, required_role: 'admin', enabled: true },
    { id: 'task-scheduler.email-settings.test', level: 2, parent_id: 'messaging.email', label: '测试发送', icon_key: 'send', sort_order: 3, required_role: 'admin', enabled: true },
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
    const wrapper = mount(MenuPermissionManager, { props: { isAdmin: true } })
    await flushPromises()
    expect(wrapper.find('[data-testid="user-list"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="menu-tree"]').exists()).toBe(true)
  })

  it('test_disabled_menu_not_rendered enabled=False 的菜单不渲染', async () => {
    const wrapper = mount(MenuPermissionManager, { props: { isAdmin: true } })
    await flushPromises()
    expect(wrapper.find('[data-testid="menu-checkbox-disabled-menu"]').exists()).toBe(false)
  })

  it('test_profile_checkbox_always_checked_and_disabled profile 永远 checked+disabled', async () => {
    const wrapper = mount(MenuPermissionManager, { props: { isAdmin: true } })
    await flushPromises()
    const profileCb = wrapper.find('[data-testid="menu-checkbox-profile"]')
    expect(profileCb.element.checked).toBe(true)
    expect(profileCb.element.disabled).toBe(true)
  })

  it('test_loads_user_grants_on_user_select 切换人员自动加载 grants', async () => {
    setupFetchMock({ grantsByUser: { 2: ['profile', 'user-management.users'] } })
    const wrapper = mount(MenuPermissionManager, { props: { isAdmin: true } })
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
    const wrapper = mount(MenuPermissionManager, { props: { isAdmin: true } })
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
    const wrapper = mount(MenuPermissionManager, { props: { isAdmin: true } })
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
    const wrapper = mount(MenuPermissionManager, { props: { isAdmin: true } })
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
  // 2026-07-31：邮件设置降级为 messaging 下的二级菜单
  // - 一级：存在 menu-checkbox-messaging
  // - 二级（messaging 下）：menu-checkbox-task-scheduler.email-settings / server / policies / test
  it('test_messaging_is_level1_with_email_settings_as_child 消息设置是一级菜单，邮件设置是其下二级', async () => {
    // 2026-07-31 二次调整：原中间层 `task-scheduler.email-settings` 已删除
    // 新结构：messaging 一级 → messaging.email channel → 三个孙 tab
    const wrapper = mount(MenuPermissionManager, { props: { isAdmin: true } })
    await flushPromises()
    // 一级：存在 messaging
    const l1 = wrapper.find('[data-testid="menu-checkbox-messaging"]')
    expect(l1.exists()).toBe(true)
    // 二级（channel）：messaging.email 在 messaging 下
    const channel = wrapper.find('[data-testid="menu-checkbox-messaging.email"]')
    expect(channel.exists()).toBe(true)
    // 旧中间层 task-scheduler.email-settings 已删除
    const oldMid = wrapper.find('[data-testid="menu-checkbox-task-scheduler.email-settings"]')
    expect(oldMid.exists()).toBe(false)
    // 选 zhangsan
    const items = wrapper.findAll('[data-testid="user-list-item"]')
    await items[1].trigger('click')
    await flushPromises()
    // 切到任务调度父级，不应半选（邮件设置不在其下）
    const parent = wrapper.find('[data-testid="menu-checkbox-task-scheduler"]')
    expect(parent.exists()).toBe(true)
    expect(parent.element.indeterminate).toBe(false)
  })
})

// 2026-07-31 二次调整：messaging → messaging.email(channel) → 三个孙 tab 三级结构测试
describe('MenuPermissionManager 三级菜单结构（2026-07-31）', () => {
  beforeEach(() => {
    setupFetchMock()
  })

  it('test_messaging_email_channel_renders_as_child messaging 下渲染 messaging.email channel', async () => {
    const wrapper = mount(MenuPermissionManager, { props: { isAdmin: true } })
    await flushPromises()
    // messaging 一级 + messaging.email channel 都在
    expect(wrapper.find('[data-testid="menu-checkbox-messaging"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="menu-checkbox-messaging.email"]').exists()).toBe(true)
    // 中间层 task-scheduler.email-settings 已删除
    expect(wrapper.find('[data-testid="menu-checkbox-task-scheduler.email-settings"]').exists()).toBe(false)
    // 三个孙 tab 都在
    expect(wrapper.find('[data-testid="menu-checkbox-task-scheduler.email-settings.server"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="menu-checkbox-task-scheduler.email-settings.policies"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="menu-checkbox-task-scheduler.email-settings.test"]').exists()).toBe(true)
  })

  it('test_toggle_parent_messaging_auto_checks_all_descendants 勾 messaging 父级 → 自动勾 channel + 三个孙 tab', async () => {
    const wrapper = mount(MenuPermissionManager, { props: { isAdmin: true } })
    await flushPromises()
    const items = wrapper.findAll('[data-testid="user-list-item"]')
    await items[1].trigger('click') // 选 zhangsan
    await flushPromises()

    // 勾 messaging
    const messagingCb = wrapper.find('[data-testid="menu-checkbox-messaging"]')
    await messagingCb.setValue(true)
    await flushPromises()

    // channel + 三个孙 tab 都被勾
    expect(wrapper.find('[data-testid="menu-checkbox-messaging.email"]').element.checked).toBe(true)
    expect(wrapper.find('[data-testid="menu-checkbox-task-scheduler.email-settings.server"]').element.checked).toBe(true)
    expect(wrapper.find('[data-testid="menu-checkbox-task-scheduler.email-settings.policies"]').element.checked).toBe(true)
    expect(wrapper.find('[data-testid="menu-checkbox-task-scheduler.email-settings.test"]').element.checked).toBe(true)
  })

  it('test_toggle_channel_messaging_email_auto_checks_grandchildren 勾 channel → 自动勾所有孙 tab', async () => {
    const wrapper = mount(MenuPermissionManager, { props: { isAdmin: true } })
    await flushPromises()
    const items = wrapper.findAll('[data-testid="user-list-item"]')
    await items[1].trigger('click')
    await flushPromises()

    const channelCb = wrapper.find('[data-testid="menu-checkbox-messaging.email"]')
    await channelCb.setValue(true)
    await flushPromises()

    // 三个孙 tab 都被勾
    expect(wrapper.find('[data-testid="menu-checkbox-task-scheduler.email-settings.server"]').element.checked).toBe(true)
    expect(wrapper.find('[data-testid="menu-checkbox-task-scheduler.email-settings.policies"]').element.checked).toBe(true)
    expect(wrapper.find('[data-testid="menu-checkbox-task-scheduler.email-settings.test"]').element.checked).toBe(true)
    // messaging 父级也变为 checked（所有子级都勾）
    expect(wrapper.find('[data-testid="menu-checkbox-messaging"]').element.checked).toBe(true)
  })

  it('test_toggle_one_grandchild_channel_becomes_indeterminate 勾一个孙 tab → channel 半选', async () => {
    const wrapper = mount(MenuPermissionManager, { props: { isAdmin: true } })
    await flushPromises()
    const items = wrapper.findAll('[data-testid="user-list-item"]')
    await items[1].trigger('click')
    await flushPromises()

    // 只勾 server
    const serverCb = wrapper.find('[data-testid="menu-checkbox-task-scheduler.email-settings.server"]')
    await serverCb.setValue(true)
    await flushPromises()

    // channel 半选
    const channelCb = wrapper.find('[data-testid="menu-checkbox-messaging.email"]')
    expect(channelCb.element.checked).toBe(false)
    expect(channelCb.element.indeterminate).toBe(true)
    // messaging 父级也半选
    const messagingCb = wrapper.find('[data-testid="menu-checkbox-messaging"]')
    expect(messagingCb.element.indeterminate).toBe(true)
  })

  it('test_toggle_all_grandchildren_channel_and_parent_become_checked 勾全部孙 tab → channel + parent 全勾', async () => {
    const wrapper = mount(MenuPermissionManager, { props: { isAdmin: true } })
    await flushPromises()
    const items = wrapper.findAll('[data-testid="user-list-item"]')
    await items[1].trigger('click')
    await flushPromises()

    // 勾全部孙 tab
    await wrapper.find('[data-testid="menu-checkbox-task-scheduler.email-settings.server"]').setValue(true)
    await flushPromises()
    await wrapper.find('[data-testid="menu-checkbox-task-scheduler.email-settings.policies"]').setValue(true)
    await flushPromises()
    await wrapper.find('[data-testid="menu-checkbox-task-scheduler.email-settings.test"]').setValue(true)
    await flushPromises()

    // channel 勾上
    expect(wrapper.find('[data-testid="menu-checkbox-messaging.email"]').element.checked).toBe(true)
    // messaging 父级也勾上
    expect(wrapper.find('[data-testid="menu-checkbox-messaging"]').element.checked).toBe(true)
  })

  it('test_untoggle_parent_unchecks_all_descendants 取消 messaging → channel + 全部孙 tab 都取消', async () => {
    const wrapper = mount(MenuPermissionManager, { props: { isAdmin: true } })
    await flushPromises()
    const items = wrapper.findAll('[data-testid="user-list-item"]')
    await items[1].trigger('click')
    await flushPromises()

    // 先全部勾上
    await wrapper.find('[data-testid="menu-checkbox-messaging"]').setValue(true)
    await flushPromises()
    // 再取消
    await wrapper.find('[data-testid="menu-checkbox-messaging"]').setValue(false)
    await flushPromises()

    expect(wrapper.find('[data-testid="menu-checkbox-messaging.email"]').element.checked).toBe(false)
    expect(wrapper.find('[data-testid="menu-checkbox-task-scheduler.email-settings.server"]').element.checked).toBe(false)
    expect(wrapper.find('[data-testid="menu-checkbox-task-scheduler.email-settings.policies"]').element.checked).toBe(false)
    expect(wrapper.find('[data-testid="menu-checkbox-task-scheduler.email-settings.test"]').element.checked).toBe(false)
  })
})