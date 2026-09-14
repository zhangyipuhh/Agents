/**
 * HelpSidebar 左侧目录导航组件测试
 *
 * 覆盖：
 *   1. 递归渲染嵌套树
 *   2. 当前激活项高亮
 *   3. 点击叶子节点 emit('select', path)
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import HelpSidebar from '../HelpSidebar.vue'
import HelpSidebarItem from '../HelpSidebarItem.vue'

describe('HelpSidebar 组件', () => {
  it('递归渲染嵌套树：分组标题 + 叶子链接', () => {
    const tree = [
      { title: '概述', path: 'overview' },
      {
        title: '功能指南',
        children: [
          { title: '智能体对话', path: 'features/chat' },
          { title: '知识库', path: 'features/knowledge' },
        ],
      },
      { title: '常见问题', path: 'faq' },
    ]
    const wrapper = mount(HelpSidebar, {
      props: { tree, activePath: 'overview' },
    })

    // 验证所有叶子节点被渲染
    expect(wrapper.text()).toContain('概述')
    expect(wrapper.text()).toContain('功能指南')
    expect(wrapper.text()).toContain('智能体对话')
    expect(wrapper.text()).toContain('知识库')
    expect(wrapper.text()).toContain('常见问题')
  })

  it('激活项高亮（active class）', () => {
    const tree = [
      { title: '概述', path: 'overview' },
      { title: '快速入门', path: 'getting-started' },
    ]
    const wrapper = mount(HelpSidebar, {
      props: { tree, activePath: 'getting-started' },
    })

    const links = wrapper.findAll('.help-nav-link')
    expect(links).toHaveLength(2)

    expect(links[0].classes()).not.toContain('help-nav-link--active')
    expect(links[1].classes()).toContain('help-nav-link--active')
  })

  it('点击叶子节点 emit("select", path)', async () => {
    const tree = [
      { title: '概述', path: 'overview' },
      { title: '常见问题', path: 'faq' },
    ]
    const wrapper = mount(HelpSidebar, {
      props: { tree, activePath: 'overview' },
    })

    await wrapper.findAll('.help-nav-link')[1].trigger('click')
    expect(wrapper.emitted('select')).toBeTruthy()
    expect(wrapper.emitted('select')[0]).toEqual(['faq'])
  })

  it('空树不渲染导航列表', () => {
    const wrapper = mount(HelpSidebar, {
      props: { tree: [], activePath: '' },
    })
    expect(wrapper.find('.help-nav-list').exists()).toBe(true)
    expect(wrapper.findAll('.help-nav-link')).toHaveLength(0)
    expect(wrapper.findAll('.help-nav-group')).toHaveLength(0)
  })

  it('HelpSidebarItem 独立单元：叶子节点点击触发 select', async () => {
    const node = { title: '概述', path: 'overview' }
    const wrapper = mount(HelpSidebarItem, {
      props: { node, activePath: '' },
    })
    await wrapper.find('.help-nav-link').trigger('click')
    expect(wrapper.emitted('select')[0]).toEqual(['overview'])
  })

  it('HelpSidebarItem 独立单元：无 children 时渲染为叶子链接，点击触发 select', async () => {
    // 无 children + 有 path → 叶子节点，渲染为可点击 button
    const node = { title: '独立叶子', path: 'standalone' }
    const wrapper = mount(HelpSidebarItem, {
      props: { node, activePath: '' },
    })
    expect(wrapper.find('.help-nav-link').exists()).toBe(true)
    expect(wrapper.find('.help-nav-group-label').exists()).toBe(false)

    await wrapper.find('.help-nav-link').trigger('click')
    expect(wrapper.emitted('select')[0]).toEqual(['standalone'])
  })

  it('HelpSidebarItem 独立单元：有 children 时渲染为分组', () => {
    const node = {
      title: '父分组',
      children: [{ title: '子1', path: 'child1' }],
    }
    const wrapper = mount(HelpSidebarItem, {
      props: { node, activePath: '' },
    })
    // 父分组渲染为 .help-nav-group-label，不渲染 .help-nav-link
    expect(wrapper.find('.help-nav-group').exists()).toBe(true)
    expect(wrapper.find('.help-nav-group-label').exists()).toBe(true)
  })

  it('生产 index.json 含 IP 白名单配置节点,且对应 .md 文件存在', () => {
    // 解析 __tests__ 当前目录 → 推出 public/help/index.json 绝对路径
    const here = dirname(fileURLToPath(import.meta.url))
    const indexPath = resolve(here, '../../../../public/help/index.json')
    const raw = readFileSync(indexPath, 'utf-8')
    const data = JSON.parse(raw)

    // 定位「功能指南」分组
    const featuresGroup = data.tree.find((n) => n.title === '功能指南')
    expect(featuresGroup, 'index.json 必须包含「功能指南」分组').toBeTruthy()
    expect(Array.isArray(featuresGroup.children)).toBe(true)

    // 在 children 中查找 ip-whitelist 节点
    const ipNode = featuresGroup.children.find((c) => c.path === 'features/ip-whitelist')
    expect(ipNode, 'index.json 必须包含 features/ip-whitelist 节点').toBeTruthy()
    expect(ipNode.title).toBe('IP 白名单配置')

    // 对应 .md 资源必须真实存在（防目录与文件脱节）
    const mdPath = resolve(here, '../../../../public/help/features/ip-whitelist.md')
    expect(existsSync(mdPath), `帮助文档 ${mdPath} 必须存在`).toBe(true)
  })

  it('递归渲染含 IP 白名单配置节点的真实目录树', () => {
    // 用与生产一致的目录树结构（对齐 public/help/index.json），覆盖递归组件
    const tree = [
      { title: '概述', path: 'overview' },
      {
        title: '功能指南',
        children: [
          { title: '智能体对话', path: 'features/chat' },
          { title: '知识库', path: 'features/knowledge' },
          { title: '智能运维中心', path: 'features/ops-console' },
          { title: 'IP 白名单配置', path: 'features/ip-whitelist' },
        ],
      },
      { title: '常见问题', path: 'faq' },
    ]
    const wrapper = mount(HelpSidebar, {
      props: { tree, activePath: 'features/ip-whitelist' },
    })

    // 新节点出现在文本中
    expect(wrapper.text()).toContain('IP 白名单配置')

    // 递归叶子链接数量 = 1（概述）+ 4（功能指南子项）+ 1（常见问题）= 6
    const links = wrapper.findAll('.help-nav-link')
    expect(links).toHaveLength(6)

    // 当前激活项是 ip-whitelist
    const activeLinks = links.filter((l) => l.classes().includes('help-nav-link--active'))
    expect(activeLinks).toHaveLength(1)
    expect(activeLinks[0].text()).toBe('IP 白名单配置')
  })
})