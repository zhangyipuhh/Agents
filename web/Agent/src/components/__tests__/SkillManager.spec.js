/**
 * SkillManager 组件测试
 *
 * 覆盖：组件可导入、渲染 skill 列表、按 category 分组、点击 skill 选中、
 *      扫描未注册 skill 触发 API、切换启用状态调用 API、删除按钮调用 API。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import SkillManager from '../SkillManager.vue'

const mockSkills = [
  {
    name: 'code_review',
    display_name: '代码审查',
    category: 'workflow',
    description: '代码审查 skill',
    location: '/app/skills/code_review/SKILL.md',
    base_dir: '/app/skills/code_review',
    content: '# code review content',
    enabled: true,
    sort_order: 0,
  },
  {
    name: 'data_analyze',
    display_name: '数据分析',
    category: 'workflow',
    description: '数据分析 skill',
    location: '/app/skills/data_analyze/SKILL.md',
    base_dir: '/app/skills/data_analyze',
    content: '# data analyze content',
    enabled: false,
    sort_order: 0,
  },
  {
    name: 'custom_helper',
    display_name: '自定义助手',
    category: 'custom',
    description: '自定义助手',
    location: '/app/skills/custom_helper/SKILL.md',
    base_dir: '/app/skills/custom_helper',
    content: '# custom helper content',
    enabled: true,
    sort_order: 0,
  },
]

const mockUnregisteredSkills = [
  {
    name: 'pending_skill',
    description: '待注册 skill',
    location: '/app/skills/pending/SKILL.md',
    base_dir: '/app/skills/pending',
  },
]

describe('SkillManager 组件', () => {
  let originalFetch
  let originalLocalStorage
  let originalAlert
  let originalConfirm

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
    originalAlert = global.alert
    originalConfirm = global.confirm
    global.fetch = vi.fn()
    global.localStorage = {
      getItem: vi.fn(() => 'fake-token'),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    }
    global.alert = vi.fn()
    global.confirm = vi.fn(() => true)
  })

  afterEach(() => {
    global.fetch = originalFetch
    global.localStorage = originalLocalStorage
    global.alert = originalAlert
    global.confirm = originalConfirm
  })

  it('test_component_importable 组件可被 import', () => {
    expect(SkillManager).toBeDefined()
  })

  it('test_renders_skill_list 渲染 skill 列表', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockSkills,
    })
    const wrapper = mount(SkillManager)
    await flushPromises()
    expect(wrapper.text()).toContain('代码审查')
    expect(wrapper.text()).toContain('数据分析')
    expect(wrapper.text()).toContain('自定义助手')
  })

  it('test_groups_by_category 按 category 分组展示', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockSkills,
    })
    const wrapper = mount(SkillManager)
    await flushPromises()
    const categoryHeaders = wrapper.findAll('.category-name')
    const categoryNames = categoryHeaders.map(h => h.text())
    expect(categoryNames).toContain('workflow')
    expect(categoryNames).toContain('custom')
  })

  it('test_click_skill_selects_it 点击 skill 项选中', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockSkills,
    })
    const wrapper = mount(SkillManager)
    await flushPromises()
    const items = wrapper.findAll('.skill-item')
    expect(items.length).toBeGreaterThanOrEqual(1)
    await items[0].trigger('click')
    expect(wrapper.text()).toContain('代码审查')
  })

  it('test_empty_state_shows_hint 无 skill 时显示空状态', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    })
    const wrapper = mount(SkillManager)
    await flushPromises()
    expect(wrapper.text()).toContain('暂无')
  })

  it('test_scan_button_triggers_api 点击扫描按钮调用 API', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockSkills,
    })
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockUnregisteredSkills,
    })
    const wrapper = mount(SkillManager)
    await flushPromises()
    const scanBtn = wrapper.find('.btn-scan')
    expect(scanBtn.exists()).toBe(true)
    await scanBtn.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('未注册 skill 扫描结果')
    expect(wrapper.text()).toContain('pending_skill')
  })

  it('test_toggle_skill_calls_api 切换 skill 启用状态调用 API', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockSkills,
    })
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => { return { ...mockSkills[0], enabled: false } },
    })
    const wrapper = mount(SkillManager)
    await flushPromises()
    const toggles = wrapper.findAll('.skill-toggle')
    expect(toggles.length).toBeGreaterThanOrEqual(1)
    await toggles[0].setValue(false)
    await flushPromises()
    expect(global.fetch).toHaveBeenCalled()
  })

  it('test_delete_skill_calls_api 删除按钮调用 API', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockSkills,
    })
    global.fetch.mockResolvedValueOnce({
      ok: true,
      status: 204,
    })
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    })
    const wrapper = mount(SkillManager)
    await flushPromises()
    const items = wrapper.findAll('.skill-item')
    expect(items.length).toBeGreaterThanOrEqual(1)
    await items[0].trigger('click')
    await flushPromises()
    const deleteBtn = wrapper.find('.btn-delete')
    expect(deleteBtn.exists()).toBe(true)
    await deleteBtn.trigger('click')
    await flushPromises()
    expect(global.confirm).toHaveBeenCalled()
    expect(global.fetch).toHaveBeenCalled()
  })

  it('test_scan_button_label_correct 扫描按钮文字正确', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockSkills,
    })
    const wrapper = mount(SkillManager)
    await flushPromises()
    const scanBtn = wrapper.find('.btn-scan')
    expect(scanBtn.text()).toContain('扫描未注册 skill')
  })

  it('test_refresh_button_label_correct 刷新按钮文字正确', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockSkills,
    })
    const wrapper = mount(SkillManager)
    await flushPromises()
    const refreshBtn = wrapper.find('.btn-refresh')
    expect(refreshBtn.text()).toContain('刷新')
  })

  it('test_disabled_skill_shows_tag 禁用 skill 显示"已禁用"标签', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockSkills,
    })
    const wrapper = mount(SkillManager)
    await flushPromises()
    expect(wrapper.text()).toContain('已禁用')
  })

  it('test_scan_no_unregistered_shows_hint 扫描无未注册 skill 时显示提示', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockSkills,
    })
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    })
    const wrapper = mount(SkillManager)
    await flushPromises()
    const scanBtn = wrapper.find('.btn-scan')
    await scanBtn.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('未发现未注册 skill')
  })
})