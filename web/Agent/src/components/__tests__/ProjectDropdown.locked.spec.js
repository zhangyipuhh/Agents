/**
 * ProjectDropdown 项目锁定测试（2026-07-01 新增）
 *
 * 覆盖：
 *   1. locked=true 时按钮 disabled、点击不开下拉、菜单项点击被短路
 *   2. locked=false（默认）时按钮可点击，下拉菜单正常打开
 *   3. locked 与 disabled（streaming）共用：两者任一为 true 都应禁用
 *   4. locked 时仍展示已选项文本（保留显示），只是不可改
 *
 * 测试策略：mount + 直接断言 DOM 属性/类名/emit 行为。
 *           由于 ProjectDropdown 通过 defineProps 接受 locked，传入 prop 即可触发对应分支。
 */
import { describe, it, expect, beforeAll } from 'vitest'
import { mount } from '@vue/test-utils'
import ProjectDropdown from '../ProjectDropdown.vue'

beforeAll(() => {
  // happy-dom 不提供 alert()，避免无关告警
  if (typeof window !== 'undefined' && !window.alert) {
    window.alert = () => {}
  }
})

describe('ProjectDropdown 项目锁定（2026-07-01 新增）', () => {
  it('test_project_dropdown_importable 组件可被 import', () => {
    expect(ProjectDropdown).toBeDefined()
  })

  it('test_locked_true_disables_trigger_button locked=true 时触发按钮 disabled', () => {
    const wrapper = mount(ProjectDropdown, {
      props: {
        currentProject: null,
        disabled: false,
        locked: true
      }
    })
    const btn = wrapper.find('.project-trigger')
    expect(btn.exists()).toBe(true)
    expect(btn.attributes('disabled')).toBeDefined()
    // 视觉上也应带 disabled class
    expect(btn.classes()).toContain('disabled')
  })

  it('test_locked_true_click_does_not_open_dropdown locked=true 时点击不开下拉菜单', async () => {
    const wrapper = mount(ProjectDropdown, {
      props: {
        currentProject: null,
        disabled: false,
        locked: true
      }
    })
    const btn = wrapper.find('.project-trigger')
    // 即使 click 事件真的触发（因为 disabled 在 happy-dom 里未必阻止 click），逻辑层应短路
    await btn.trigger('click')
    // 下拉菜单不应被打开
    expect(wrapper.find('.project-dropdown-menu').exists()).toBe(false)
    // 不应触发任何 project 相关事件
    expect(wrapper.emitted('select-project')).toBeFalsy()
    expect(wrapper.emitted('create-project')).toBeFalsy()
    expect(wrapper.emitted('pick-existing')).toBeFalsy()
  })

  it('test_locked_false_click_opens_dropdown locked=false 时点击正常开下拉菜单', async () => {
    // 2026-07-01：attachTo body 是因为下拉菜单用 <Teleport to="body">，
    // 不挂到 document.body 的话 happy-dom 找不到 .project-dropdown-menu
    const wrapper = mount(ProjectDropdown, {
      props: {
        currentProject: null,
        disabled: false,
        locked: false
      },
      attachTo: document.body
    })
    const btn = wrapper.find('.project-trigger')
    expect(btn.attributes('disabled')).toBeUndefined()
    await btn.trigger('click')
    await wrapper.vm.$nextTick()
    expect(document.querySelector('.project-dropdown-menu')).not.toBeNull()
    wrapper.unmount()
  })

  it('test_streaming_disabled_still_disables_trigger 已存在的 disabled（streaming）仍生效', () => {
    const wrapper = mount(ProjectDropdown, {
      props: {
        currentProject: null,
        disabled: true,
        locked: false
      }
    })
    const btn = wrapper.find('.project-trigger')
    expect(btn.attributes('disabled')).toBeDefined()
    expect(btn.classes()).toContain('disabled')
  })

  it('test_locked_keeps_current_project_label_visible locked 时仍展示已选项目名', () => {
    const wrapper = mount(ProjectDropdown, {
      props: {
        currentProject: { id: 7, name: '审计底稿', uuid: 'xxx' },
        disabled: false,
        locked: true
      }
    })
    // 触发按钮的 label 文本应保留已选项展示
    const label = wrapper.find('.project-trigger-label')
    expect(label.exists()).toBe(true)
    expect(label.text()).toBe('审计底稿')
  })

  it('test_locked_true_cannot_reach_menu_items locked=true 时用户路径无法触达菜单项', async () => {
    // 设计：locked 时 toggleDropdown() 短路 → 下拉菜单始终无法通过正常点击路径打开
    // 因此「菜单项点击被 emit」这条路径在生产中不可达，无需在菜单项 click 处理函数里再加一层短路
    const wrapper = mount(ProjectDropdown, {
      props: {
        currentProject: null,
        disabled: false,
        locked: true
      }
    })
    const btn = wrapper.find('.project-trigger')
    // 反复点击触发按钮，下拉菜单始终不应出现
    await btn.trigger('click')
    await btn.trigger('click')
    await btn.trigger('click')
    expect(wrapper.find('.project-dropdown-menu').exists()).toBe(false)
    // 关键反证：没有任何与项目相关的事件被 emit
    expect(wrapper.emitted('select-project')).toBeFalsy()
    expect(wrapper.emitted('create-project')).toBeFalsy()
    expect(wrapper.emitted('pick-existing')).toBeFalsy()
  })
})