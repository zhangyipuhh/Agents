/**
 * HelpLayout 三栏 layout 组件测试
 *
 * 覆盖：
 *   1. 渲染顶部品牌栏 / 左侧目录 / 右侧 anchor（标题存在 headings 时）
 *   2. 加载失败显示「重试」按钮
 *   3. 文档不存在显示 notfound 占位
 *   4. 关闭按钮在被脚本打开的 Tab 可见
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'

// mock help-loader 避免真实 fetch
const loadIndexMock = vi.fn()
const loadDocMock = vi.fn()
vi.mock('../../../utils/help-loader.js', () => ({
  loadIndex: () => loadIndexMock(),
  loadDoc: (path) => loadDocMock(path),
  extractHeadings: (md) => {
    if (!md) return []
    const out = []
    const lines = md.split('\n')
    for (const line of lines) {
      const m = line.match(/^(##|###)\s+(.+?)\s*$/)
      if (m) out.push({ level: m[1] === '##' ? 2 : 3, text: m[2], id: m[2] })
    }
    return out
  },
}))

// mock safeMarkdown（避免引入 marked/DOMPurify 在 happy-dom 下复杂度）
vi.mock('../../../utils/sanitize-marked.js', () => ({
  safeMarkdown: (md) => `<rendered>${md}</rendered>`,
}))

// mock vue-router useRouter（2026-09-03 新增：HelpLayout 引入 router 用于 back 模式跳转）
// 用 vi.hoisted 让 routerPushMock 在 mock 中可访问
const { routerPushMock } = vi.hoisted(() => ({
  routerPushMock: vi.fn(),
}))
vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: routerPushMock,
    replace: vi.fn(),
    currentRoute: { value: { name: 'help', path: '/help' } },
  }),
  useRoute: () => ({ name: 'help', path: '/help', fullPath: '/help' }),
}))

import HelpLayout from '../HelpLayout.vue'

const fakeTree = [
  { title: '概述', path: 'overview' },
  {
    title: '功能指南',
    children: [
      { title: '智能体对话', path: 'features/chat' },
    ],
  },
  { title: '常见问题', path: 'faq' },
]

describe('HelpLayout 组件', () => {
  beforeEach(() => {
    loadIndexMock.mockReset()
    loadDocMock.mockReset()
    // 默认 window.opener 不存在（直接访问场景）
    try {
      Object.defineProperty(window, 'opener', { value: null, configurable: true })
    } catch (_) { /* ignore */ }
  })

  it('onMounted: loadIndex 拉取目录树，默认加载第一个文档', async () => {
    loadIndexMock.mockResolvedValue({ title: '帮助中心', tree: fakeTree })
    loadDocMock.mockResolvedValue('# Overview\n## 第一章')

    const wrapper = mount(HelpLayout)
    await flushPromises()
    await nextTick()

    expect(loadIndexMock).toHaveBeenCalledTimes(1)
    expect(loadDocMock).toHaveBeenCalledWith('overview')
    expect(wrapper.find('.help-root').exists()).toBe(true)
    expect(wrapper.find('.help-sidebar').exists()).toBe(true)
    expect(wrapper.text()).toContain('概述')
    expect(wrapper.text()).toContain('帮助中心')
  })

  it('右侧 toc: 文档含 h2/h3 时渲染', async () => {
    loadIndexMock.mockResolvedValue({ title: '帮助中心', tree: fakeTree })
    loadDocMock.mockResolvedValue('# Title\n## 第一章\n### 小节')

    const wrapper = mount(HelpLayout)
    await flushPromises()
    await nextTick()

    const tocItems = wrapper.findAll('.help-toc-item')
    expect(tocItems.length).toBe(2) // 一个 h2 + 一个 h3
  })

  it('右侧 toc: 文档无 headings 时不渲染 toc', async () => {
    loadIndexMock.mockResolvedValue({ title: '帮助中心', tree: fakeTree })
    loadDocMock.mockResolvedValue('没有标题的纯文本')

    const wrapper = mount(HelpLayout)
    await flushPromises()
    await nextTick()

    expect(wrapper.find('.help-toc').exists()).toBe(false)
  })

  it('loadIndex 失败：显示错误占位 + 重试按钮', async () => {
    loadIndexMock.mockRejectedValue(new Error('网络异常'))

    const wrapper = mount(HelpLayout)
    await flushPromises()
    await nextTick()

    expect(wrapper.find('.help-state--error').exists()).toBe(true)
    expect(wrapper.text()).toContain('加载失败')
    expect(wrapper.find('.help-retry-btn').exists()).toBe(true)
  })

  it('loadDoc 404：显示 notfound 占位', async () => {
    loadIndexMock.mockResolvedValue({ title: '帮助中心', tree: fakeTree })
    loadDocMock.mockRejectedValue(new Error('加载文档失败: HTTP 404（xxx）'))

    const wrapper = mount(HelpLayout)
    await flushPromises()
    await nextTick()

    expect(wrapper.find('.help-state--notfound').exists()).toBe(true)
    expect(wrapper.text()).toContain('文档不存在')
  })

  it('loadDoc 加载中：显示 loading 占位', async () => {
    loadIndexMock.mockResolvedValue({ title: '帮助中心', tree: fakeTree })
    // 让 loadDoc 永不 resolve
    loadDocMock.mockReturnValue(new Promise(() => {}))

    const wrapper = mount(HelpLayout)
    await flushPromises()
    await nextTick()

    expect(wrapper.find('.help-state--loading').exists()).toBe(true)
  })

  it('重试按钮：点击后重新调用 loadDoc', async () => {
    loadIndexMock.mockResolvedValue({ title: '帮助中心', tree: fakeTree })
    // 第一次失败，第二次成功
    loadDocMock
      .mockRejectedValueOnce(new Error('加载文档失败: HTTP 500（overview）'))
      .mockResolvedValueOnce('# 重试成功')

    const wrapper = mount(HelpLayout)
    await flushPromises()
    await nextTick()

    expect(wrapper.find('.help-state--error').exists()).toBe(true)

    // 点击重试
    await wrapper.find('.help-retry-btn').trigger('click')
    await flushPromises()
    await nextTick()

    expect(loadDocMock).toHaveBeenCalledTimes(2)
    expect(wrapper.find('.help-article').exists()).toBe(true)
  })

  it('空目录树：左侧导航不渲染（但 layout 仍存在）', async () => {
    loadIndexMock.mockResolvedValue({ title: '帮助中心', tree: [] })

    const wrapper = mount(HelpLayout)
    await flushPromises()
    await nextTick()

    expect(wrapper.find('.help-sidebar').exists()).toBe(false)
    expect(wrapper.find('.help-root').exists()).toBe(true)
  })

  it('被脚本打开的 Tab（window.opener 存在）显示关闭按钮且 aria-label=关闭', async () => {
    // 模拟被脚本打开：window.opener 存在
    try {
      Object.defineProperty(window, 'opener', { value: {}, configurable: true })
    } catch (_) { /* ignore */ }

    loadIndexMock.mockResolvedValue({ title: '帮助中心', tree: fakeTree })
    loadDocMock.mockResolvedValue('# test')

    const wrapper = mount(HelpLayout)
    await flushPromises()
    await nextTick()

    const closeBtn = wrapper.find('.help-topbar-close')
    expect(closeBtn.exists()).toBe(true)
    expect(closeBtn.attributes('aria-label')).toBe('关闭')
  })

  it('直接访问 /help（无 window.opener）也始终显示按钮，文案变为「返回主页」', async () => {
    // 模拟直接访问：window.opener 不存在（默认）
    try {
      Object.defineProperty(window, 'opener', { value: null, configurable: true })
    } catch (_) { /* ignore */ }

    loadIndexMock.mockResolvedValue({ title: '帮助中心', tree: fakeTree })
    loadDocMock.mockResolvedValue('# test')

    const wrapper = mount(HelpLayout)
    await flushPromises()
    await nextTick()

    // 2026-09-03 修复：按钮始终显示，不再依赖 window.opener 判定可见性
    const closeBtn = wrapper.find('.help-topbar-close')
    expect(closeBtn.exists()).toBe(true)
    // back 模式：aria-label 变为「返回主页」
    expect(closeBtn.attributes('aria-label')).toBe('返回主页')
  })

  it('直接访问 /help 时点击关闭按钮触发 router.push("/") 跳回主会话', async () => {
    // 模拟直接访问
    try {
      Object.defineProperty(window, 'opener', { value: null, configurable: true })
    } catch (_) { /* ignore */ }

    loadIndexMock.mockResolvedValue({ title: '帮助中心', tree: fakeTree })
    loadDocMock.mockResolvedValue('# test')

    const wrapper = mount(HelpLayout)
    await flushPromises()
    await nextTick()

    // 点击关闭按钮：back 模式 → emit('close') → handleClose → router.push('/')
    await wrapper.find('.help-topbar-close').trigger('click')
    await nextTick()

    expect(routerPushMock).toHaveBeenCalledWith('/')
  })
})