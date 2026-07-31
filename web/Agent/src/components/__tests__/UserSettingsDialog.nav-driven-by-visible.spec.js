/**
 * UserSettingsDialog navItems 数据驱动回归测试
 *
 * 验证：navItems 不再硬编码 isAdmin，改从 visibleMenus 派生
 * （2026-07-23 菜单权限管理改造）
 */
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

import UserSettingsDialog from '../UserSettingsDialog.vue'

// 拦截 utils/api 导入，避免组件挂载时拉真实数据
vi.mock('../../utils/api.js', () => ({
  fetchUserProfile: vi.fn().mockResolvedValue({}),
  updateUserProfile: vi.fn(),
  updatePassword: vi.fn(),
  updateUsername: vi.fn(),
  fetchUserList: vi.fn().mockResolvedValue([]),
  fetchAdminAgentList: vi.fn().mockResolvedValue([]),
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
  searchSessionsByUsername: vi.fn()
}))

// stub 掉子组件
vi.mock('../McpServerManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../AgentManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../ToolManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../SkillManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../TaskSchedulerManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../EmailSettingsManager.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../MenuPermissionManager.vue', () => ({ default: { template: '<div />' } }))

describe('UserSettingsDialog navItems 数据驱动', () => {
  it('test_nav_items_driven_by_visible_menus visibleMenus 决定 navItems', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'user',
        userId: 5,
        username: 'zhangsan',
        initialTab: 'profile',
        visibleMenus: ['profile', 'user-management', 'user-management.users']
      },
      global: {
        stubs: {
          teleport: true,
          transition: true
        }
      }
    })
    await flushPromises()
    const navItems = wrapper.vm.navItems
    const ids = navItems.map(i => i.id)
    // 应包含 profile 和 user-management（因为其二级被授权）
    expect(ids).toContain('profile')
    expect(ids).toContain('user-management')
    // 不应包含 admin-only 菜单
    expect(ids).not.toContain('agent-management')
    expect(ids).not.toContain('permission-management')
  })

  it('test_nav_items_admin_role_gets_all admin 角色 + 完整 visibleMenus 看到所有一级菜单', async () => {
    const allMenus = [
      'profile', 'user-management', 'user-management.users',
      'user-management.online-monitor', 'user-management.session-query',
      'agent-management', 'mcp-management', 'tool-management',
      'skill-management', 'task-scheduler', 'task-scheduler.scheduled',
      'task-scheduler.script-scan', 'task-scheduler.api-config',
      'task-scheduler.email-settings', 'permission-management',
      'permission-management.menu'
    ]
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'admin',
        userId: 1,
        username: 'admin',
        initialTab: 'profile',
        visibleMenus: allMenus
      },
      global: {
        stubs: {
          teleport: true,
          transition: true
        }
      }
    })
    await flushPromises()
    const ids = wrapper.vm.navItems.map(i => i.id)
    // admin 应看到所有一级菜单
    expect(ids).toContain('profile')
    expect(ids).toContain('user-management')
    expect(ids).toContain('agent-management')
    expect(ids).toContain('task-scheduler')
    expect(ids).toContain('permission-management')
  })

  it('test_nav_items_empty_visible_menus_fallback_only_profile 空 visibleMenus 退化到仅 profile', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'user',
        userId: 5,
        username: 'zhangsan',
        initialTab: 'profile',
        visibleMenus: []
      },
      global: {
        stubs: {
          teleport: true,
          transition: true
        }
      }
    })
    await flushPromises()
    const ids = wrapper.vm.navItems.map(i => i.id)
    expect(ids).toEqual(['profile'])
  })

  it('test_child_menu_visible_makes_parent_visible 二级子菜单可见触发父级可见', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'user',
        userId: 5,
        username: 'zhangsan',
        initialTab: 'profile',
        // 2026-07-23：task-scheduler.email-settings 已升级为一级菜单，不再挂在 task-scheduler 下。
        // 这里改用真实的二级场景（task-scheduler.scheduled）做"二级 → 父级可见"的回归。
        visibleMenus: ['profile', 'task-scheduler.scheduled']
      },
      global: {
        stubs: {
          teleport: true,
          transition: true
        }
      }
    })
    await flushPromises()
    const ids = wrapper.vm.navItems.map(i => i.id)
    // 二级 'task-scheduler.scheduled' 应让父级 'task-scheduler' 可见
    expect(ids).toContain('task-scheduler')
    // 旧 'email-settings' 顶级壳已不存在（与后端注册表对齐）
    expect(ids).not.toContain('email-settings')
  })

  // 2026-07-31：「消息设置」是 messaging 父级，子菜单授权通过 PARENT_TO_CHILDREN_ALIAS 推父级可见
  it('test_messaging_l1_self_visible 消息设置父级自身授权即自身可见', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'user',
        userId: 5,
        username: 'zhangsan',
        initialTab: 'profile',
        visibleMenus: ['profile', 'messaging']
      },
      global: {
        stubs: {
          teleport: true,
          transition: true
        }
      }
    })
    await flushPromises()
    const ids = wrapper.vm.navItems.map(i => i.id)
    expect(ids).toContain('messaging')
    // 旧顶级壳 'email-settings' / 'task-scheduler.email-settings' 不再作为一级菜单可见
    expect(ids).not.toContain('email-settings')
    expect(ids).not.toContain('task-scheduler.email-settings')
  })

  // 2026-07-31 二次调整：原中间层 task-scheduler.email-settings 已删除
  // 父菜单「消息设置」(messaging) 与孙 tab id 前缀不匹配
  // 需要通过 PARENT_TO_CHILDREN_ALIAS 让孙 tab 授权时父级也可见
  it('test_messaging_visible_when_email_settings_subtab_authorized 消息设置父级通过 alias 在子菜单授权时可见', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'user',
        userId: 6,
        username: 'lisi',
        initialTab: 'profile',
        // 普通用户只授权了一个孙 tab（task-scheduler.email-settings.server），
        // 没有显式授权 channel messaging.email 与父级 messaging —— 此时父级仍应可见（alias 推导）
        visibleMenus: ['profile', 'task-scheduler.email-settings.server']
      },
      global: {
        stubs: {
          teleport: true,
          transition: true
        }
      }
    })
    await flushPromises()
    const ids = wrapper.vm.navItems.map(i => i.id)
    expect(ids).toContain('messaging')
  })

  // 2026-07-31：父菜单「消息设置」下三个子 Tab 授权时父级仍可见
  it('test_messaging_visible_when_email_tab_authorized 消息设置父级在子 Tab 授权时也可见', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: true,
        role: 'user',
        userId: 7,
        username: 'wangwu',
        initialTab: 'profile',
        visibleMenus: ['profile', 'task-scheduler.email-settings.policies']
      },
      global: {
        stubs: {
          teleport: true,
          transition: true
        }
      }
    })
    await flushPromises()
    const ids = wrapper.vm.navItems.map(i => i.id)
    // 父级 messaging 可见（子 Tab 授权 → 父级 alias）
    expect(ids).toContain('messaging')
  })
})