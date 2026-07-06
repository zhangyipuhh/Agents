/**
 * Sidebar 项目分组默认展开测试（2026-07-02 新增）
 *
 * 覆盖：
 *   1. 挂载后「项目」分组默认展开（项目列表可见）
 *   2. 各项目下的会话列表仍默认折叠（projectCollapsedMap 未受影响）
 *   3. 点击「项目」分组头部可切换折叠/展开状态
 *
 * 测试策略：mock api.js 中的 fetchProjectList / fetchSessionList，mount Sidebar 后断言 DOM 可见性。
 *           由于项目列表通过 Teleport 以外的普通 DOM 渲染，无需 attachTo body。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import Sidebar from '../Sidebar.vue'
import { fetchProjectList, renameProject, deleteProject } from '../../utils/api.js'

const mockProjects = [
  { id: 1, name: '我的文件夹' },
  { id: 2, name: '测试项目' }
]

const mockSessions = [
  {
    session_id: 'sess_001',
    title: '会话一',
    last_active_at: '2026-07-02T08:00:00Z',
    project_id: 1
  },
  {
    session_id: 'sess_002',
    title: '会话二',
    last_active_at: '2026-07-02T09:00:00Z',
    project_id: 2
  }
]

vi.mock('../../utils/api.js', () => {
  const mockRenameProject = vi.fn(async () => ({ success: true, project: { id: 1, name: '重命名后' } }))
  const mockDeleteProject = vi.fn(async () => ({ success: true }))
  return {
    fetchSessionList: vi.fn(async () => ({ sessions: mockSessions })),
    deleteSession: vi.fn(async () => ({})),
    fetchProjectList: vi.fn(async () => ({ projects: mockProjects })),
    updateSessionTitle: vi.fn(async () => ({})),
    exportSessionMarkdown: vi.fn(async () => ({ text: '# 测试', filename: 'test.md' })),
    renameProject: mockRenameProject,
    deleteProject: mockDeleteProject
  }
})

describe('Sidebar 项目分组默认展开（2026-07-02 新增）', () => {
  let wrapper
  let freshProjects

  beforeEach(() => {
    // 深拷贝，避免测试间修改 project.name 互相污染
    freshProjects = JSON.parse(JSON.stringify(mockProjects))
    fetchProjectList.mockResolvedValue({ projects: freshProjects })

    wrapper = mount(Sidebar, {
      props: {
        currentPage: 'agent',
        username: 'tester',
        userRole: 'user',
        userId: 1,
        currentSessionId: ''
      }
    })
  })

  afterEach(() => {
    wrapper?.unmount()
  })

  it('test_sidebar_importable 组件可被 import', () => {
    expect(Sidebar).toBeDefined()
  })

  it('test_project_group_expanded_by_default 项目分组默认展开且项目列表可见', async () => {
    await flushPromises()
    // group-items 容器可见，内部渲染项目
    const groupItems = wrapper.find('.group-items')
    expect(groupItems.exists()).toBe(true)
    expect(groupItems.isVisible()).toBe(true)
    expect(groupItems.findAll('.project-item').length).toBe(mockProjects.length)
  })

  it('test_project_sessions_collapsed_by_default 项目下会话列表默认折叠', async () => {
    await flushPromises()
    const projectSessions = wrapper.findAll('.project-sessions')
    expect(projectSessions.length).toBe(mockProjects.length)
    // project-sessions 通过 v-show 控制，折叠时其 CSS display 应为 none
    projectSessions.forEach((node) => {
      expect(node.element.style.display).toBe('none')
    })
  })

  it('test_click_group_header_can_collapse_project_group 点击分组头部可折叠项目分组', async () => {
    await flushPromises()
    const header = wrapper.find('.group-header')
    expect(header.exists()).toBe(true)

    // 初始展开：group-items 不应是 display:none
    expect(wrapper.find('.group-items').element.style.display).not.toBe('none')

    // 点击后折叠
    await header.trigger('click')
    await flushPromises()
    expect(wrapper.find('.group-items').element.style.display).toBe('none')

    // 再次点击展开
    await header.trigger('click')
    await flushPromises()
    expect(wrapper.find('.group-items').element.style.display).not.toBe('none')
  })

  it('test_project_delete_button_exists 项目行存在删除按钮', async () => {
    await flushPromises()
    const projectHeader = wrapper.find('.project-header')
    expect(projectHeader.exists()).toBe(true)

    const deleteBtn = projectHeader.find('.project-delete-btn')
    expect(deleteBtn.exists()).toBe(true)
  })

  it('test_project_context_menu_opens_on_right_click 右键项目行弹出重命名菜单', async () => {
    await flushPromises()
    const projectHeader = wrapper.find('.project-header')
    expect(projectHeader.exists()).toBe(true)

    await projectHeader.trigger('contextmenu')
    await flushPromises()

    const menu = document.querySelector('.session-context-menu')
    expect(menu).not.toBeNull()
    expect(menu.textContent).toContain('重命名')
    expect(menu.textContent).not.toContain('导出为 Markdown')
  })

  it('test_project_rename_inline_enter_calls_api 项目行内重命名回车时调用 renameProject', async () => {
    await flushPromises()
    const projectHeader = wrapper.find('.project-header')

    // 打开右键菜单并点击重命名
    await projectHeader.trigger('contextmenu')
    await flushPromises()
    const menuItem = document.querySelector('.session-context-menu-item')
    await menuItem.click()
    await flushPromises()

    // 应出现输入框
    const input = projectHeader.find('.project-name-input')
    expect(input.exists()).toBe(true)

    // 修改值并回车
    await input.setValue('新的项目名')
    await input.trigger('keydown.enter')
    await flushPromises()

    expect(renameProject).toHaveBeenCalledWith(1, '新的项目名')
  })

  it('test_project_delete_button_opens_confirm_dialog 项目删除按钮打开确认弹窗', async () => {
    await flushPromises()
    const deleteBtn = wrapper.find('.project-delete-btn')
    expect(deleteBtn.exists()).toBe(true)

    await deleteBtn.trigger('click')
    await flushPromises()

    const dialog = document.querySelector('.delete-confirm-container')
    expect(dialog).not.toBeNull()
    expect(dialog.textContent).toContain('确认删除项目')
    expect(dialog.textContent).toContain('我的文件夹')

    // 点击确认删除
    const confirmBtn = dialog.querySelector('.btn-confirm')
    await confirmBtn.click()
    await flushPromises()

    expect(deleteProject).toHaveBeenCalledWith(1)
  })
})
