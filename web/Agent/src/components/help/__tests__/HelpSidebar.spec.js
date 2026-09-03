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
})