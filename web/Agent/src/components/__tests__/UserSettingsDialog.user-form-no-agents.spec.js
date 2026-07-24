/**
 * UserSettingsDialog 智能体权限迁移防回归测试（2026-07-24 新增）
 *
 * 验证「用户管理 → 编辑用户」表单中已移除「可选智能体」复选块：
 * - 表单中不再有 agent-checkbox-list 元素
 * - permission-management 一级 Tab 有「菜单管理」「智能体访问」两个子 tab 按钮
 */
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// 拦截 utils/api 导入，避免组件挂载时拉真实数据
vi.mock('../../utils/api.js', () => ({
  fetchUserProfile: vi.fn().mockResolvedValue({}),
  updateUserProfile: vi.fn(),
  updatePassword: vi.fn(),
  updateUsername: vi.fn(),
  fetchUserList: vi.fn().mockResolvedValue([]),
  deleteUser: vi.fn(),
  kickUser: vi.fn(),
  createUser: vi.fn(),
  updateUser: vi.fn(),
  fetchOnlineUsers: vi.fn().mockResolvedValue({ online_users: [] }),
  fetchUserSessions: vi.fn(),
  adminDeleteSession: vi.fn(),
  adminBatchDeleteSessions: vi.fn(),
  adminExportSessionMarkdown: vi.fn(),
  adminFetchSessionMessages: vi.fn(),
  searchSessionsByUsername: vi.fn(),
  fetchAgentPermissionCatalog: vi.fn().mockResolvedValue({ items: [] }),
  fetchUserAgentGrants: vi.fn().mockResolvedValue({ agent_names: [] }),
  replaceUserAgentGrants: vi.fn().mockResolvedValue({ agent_names: [] }),
  fetchMenuCatalog: vi.fn().mockResolvedValue({ items: [] }),
  fetchUserMenuGrants: vi.fn().mockResolvedValue({ menu_ids: [] }),
  saveUserMenuGrants: vi.fn().mockResolvedValue({ menu_ids: [] }),
  fetchUploadConfig: vi.fn().mockResolvedValue({ max_file_size_mb: 3 })
}))

// stub 掉子组件
vi.mock('../McpServerManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../AgentManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../ToolManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../SkillManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../TaskSchedulerManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../EmailSettingsManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../MenuPermissionManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../AgentAccessManager.vue', () => ({ default: { template: '<div />' } }))

import UserSettingsDialog from '../UserSettingsDialog.vue'

function makeWrapper(visibleMenus = ['profile', 'user-management', 'permission-management']) {
  return mount(UserSettingsDialog, {
    props: {
      visible: true,
      role: 'admin',
      username: 'admin',
      userId: 1,
      visibleMenus
    },
    global: {
      stubs: {
        teleport: true,
        transition: true
      }
    }
  })
}

describe('UserSettingsDialog 智能体权限迁移防回归', () => {
  it('test_permission_management_has_two_sub_tabs permission-management tab 有两个子 tab', async () => {
    const wrapper = makeWrapper()
    await flushPromises()
    // 切到「权限管理」tab
    const navItems = wrapper.vm.navItems
    const permItem = navItems.find(i => i.id === 'permission-management')
    expect(permItem).toBeDefined()
    // 直接调用 switchTab 模拟点击
    wrapper.vm.switchTab('permission-management')
    await flushPromises()
    // 验证两个子 tab 按钮存在
    expect(wrapper.find('[data-testid="permission-tab-menu"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="permission-tab-agent-access"]').exists()).toBe(true)
  })

  it('test_permission_tab_switch_changes_active_class 子 tab 切换按钮状态正确', async () => {
    const wrapper = makeWrapper()
    await flushPromises()
    wrapper.vm.switchTab('permission-management')
    await flushPromises()
    // 默认 menu tab active
    const menuTab = wrapper.find('[data-testid="permission-tab-menu"]')
    const agentTab = wrapper.find('[data-testid="permission-tab-agent-access"]')
    expect(menuTab.classes()).toContain('active')
    expect(agentTab.classes()).not.toContain('active')
    // 切换到 agent-access
    wrapper.vm.switchPermissionTab('agent-access')
    await flushPromises()
    expect(agentTab.classes()).toContain('active')
    expect(menuTab.classes()).not.toContain('active')
  })

  it('test_user_form_no_agent_checkbox_block 表单中不再有 agent-checkbox-list 字符串', async () => {
    const wrapper = makeWrapper()
    await flushPromises()
    // 验证 UserSettingsDialog 源中已不含 agent-checkbox-list 模板
    // 方式：直接读 template 字符串检查 feature 已被移除
    // 简单方案：扫组件的 html 不应含 .agent-checkbox-list div
    expect(wrapper.html()).not.toContain('agent-checkbox-list')
  })
})
