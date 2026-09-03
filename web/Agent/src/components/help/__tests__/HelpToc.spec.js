/**
 * HelpToc 右侧 anchor 索引组件测试
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import HelpToc from '../HelpToc.vue'

describe('HelpToc 组件', () => {
  it('渲染标题列表', () => {
    const headings = [
      { level: 2, text: '第一节', id: '第一节' },
      { level: 3, text: '小节', id: '小节' },
      { level: 2, text: '第二节', id: '第二节' },
    ]
    const wrapper = mount(HelpToc, {
      props: { headings, activeId: '' },
    })

    const items = wrapper.findAll('.help-toc-item')
    expect(items).toHaveLength(3)
    expect(items[0].classes()).toContain('help-toc-item--level-2')
    expect(items[1].classes()).toContain('help-toc-item--level-3')
    expect(items[2].classes()).toContain('help-toc-item--level-2')

    expect(wrapper.text()).toContain('第一节')
    expect(wrapper.text()).toContain('小节')
    expect(wrapper.text()).toContain('第二节')
  })

  it('空 headings：显示「无章节」占位', () => {
    const wrapper = mount(HelpToc, {
      props: { headings: [], activeId: '' },
    })
    expect(wrapper.find('.help-toc-empty').exists()).toBe(true)
    expect(wrapper.text()).toContain('无章节')
  })

  it('activeId 匹配时高亮', () => {
    const headings = [
      { level: 2, text: '第一节', id: '第一节' },
      { level: 2, text: '第二节', id: '第二节' },
    ]
    const wrapper = mount(HelpToc, {
      props: { headings, activeId: '第二节' },
    })

    const items = wrapper.findAll('.help-toc-item')
    expect(items[0].classes()).not.toContain('help-toc-item--active')
    expect(items[1].classes()).toContain('help-toc-item--active')
  })

  it('点击 anchor 触发 emit("jump", id)', async () => {
    const headings = [{ level: 2, text: '第一节', id: '第一节' }]
    const wrapper = mount(HelpToc, {
      props: { headings, activeId: '' },
    })

    await wrapper.find('.help-toc-link').trigger('click')
    expect(wrapper.emitted('jump')).toBeTruthy()
    expect(wrapper.emitted('jump')[0]).toEqual(['第一节'])
  })

  it('href 属性正确（#id）', () => {
    const headings = [{ level: 2, text: '登录问题', id: '登录问题' }]
    const wrapper = mount(HelpToc, {
      props: { headings, activeId: '' },
    })

    const link = wrapper.find('.help-toc-link')
    expect(link.attributes('href')).toBe('#登录问题')
  })
})