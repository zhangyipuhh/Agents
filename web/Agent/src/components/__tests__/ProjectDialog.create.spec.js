/**
 * ProjectDialog.vue create 模式测试（2026-07-06 新增）
 *
 * 覆盖：
 *   1. create 模式输入名称点击保存后 emit 'created'；
 *   2. 保存后弹窗不自行关闭（由父组件 App.vue 控制关闭）；
 *   3. 空名称 / 超长名称校验；
 *   4. 父组件通过 v-model:visible 关闭弹窗。
 */
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { mount } from '@vue/test-utils'
import ProjectDialog from '../ProjectDialog.vue'

beforeAll(() => {
  // happy-dom 不提供 alert()，避免无关告警
  if (typeof window !== 'undefined' && !window.alert) {
    window.alert = () => {}
  }
})

describe('ProjectDialog create 模式（2026-07-06）', () => {
  it('test_project_dialog_create_importable 组件可被 import', () => {
    expect(ProjectDialog).toBeDefined()
  })

  it('test_create_mode_emits_created_on_submit 输入名称点击保存后 emit created', async () => {
    const wrapper = mount(ProjectDialog, {
      props: {
        visible: true,
        mode: 'create'
      },
      attachTo: document.body
    })
    await wrapper.vm.$nextTick()

    // ProjectDialog 使用 Teleport 到 body，需用 document.querySelector 查找
    const input = document.querySelector('#project-name-input')
    expect(input).not.toBeNull()
    input.value = 'My Project'
    await input.dispatchEvent(new Event('input'))
    await wrapper.vm.$nextTick()

    const confirmBtn = document.querySelector('.btn-confirm')
    expect(confirmBtn).not.toBeNull()
    await confirmBtn.click()
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('created')).toHaveLength(1)
    expect(wrapper.emitted('created')[0]).toEqual([{ name: 'My Project' }])
    wrapper.unmount()
  })

  it('test_create_mode_does_not_close_dialog_on_submit 保存后弹窗保持打开等待父组件关闭', async () => {
    const wrapper = mount(ProjectDialog, {
      props: {
        visible: true,
        mode: 'create'
      },
      attachTo: document.body
    })
    await wrapper.vm.$nextTick()

    const input = document.querySelector('#project-name-input')
    expect(input).not.toBeNull()
    input.value = 'My Project'
    await input.dispatchEvent(new Event('input'))
    await wrapper.vm.$nextTick()

    const confirmBtn = document.querySelector('.btn-confirm')
    expect(confirmBtn).not.toBeNull()
    await confirmBtn.click()
    await wrapper.vm.$nextTick()

    // 组件自身不 emit update:visible，弹窗仍应处于打开状态
    expect(wrapper.emitted('update:visible')).toBeFalsy()
    expect(document.querySelector('.project-dialog-overlay')).not.toBeNull()
    wrapper.unmount()
  })

  it('test_create_mode_validates_empty_name 空名称时显示错误且不 emit', async () => {
    const wrapper = mount(ProjectDialog, {
      props: {
        visible: true,
        mode: 'create'
      },
      attachTo: document.body
    })
    await wrapper.vm.$nextTick()

    const confirmBtn = document.querySelector('.btn-confirm')
    expect(confirmBtn).not.toBeNull()
    await confirmBtn.click()
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('created')).toBeFalsy()
    expect(document.querySelector('.project-dialog-error').textContent).toBe('请输入项目名称')
    wrapper.unmount()
  })

  it('test_create_mode_validates_long_name 超长名称时显示错误且不 emit', async () => {
    const wrapper = mount(ProjectDialog, {
      props: {
        visible: true,
        mode: 'create'
      },
      attachTo: document.body
    })
    await wrapper.vm.$nextTick()

    const input = document.querySelector('#project-name-input')
    expect(input).not.toBeNull()
    input.value = 'a'.repeat(51)
    await input.dispatchEvent(new Event('input'))
    await wrapper.vm.$nextTick()

    const confirmBtn = document.querySelector('.btn-confirm')
    expect(confirmBtn).not.toBeNull()
    await confirmBtn.click()
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('created')).toBeFalsy()
    expect(document.querySelector('.project-dialog-error').textContent).toBe('项目名称不能超过 50 字符')
    wrapper.unmount()
  })

  it('test_parent_can_close_dialog_via_visible 父组件通过 v-model 关闭弹窗', async () => {
    const wrapper = mount(ProjectDialog, {
      props: {
        visible: true,
        mode: 'create'
      },
      attachTo: document.body
    })
    await wrapper.vm.$nextTick()

    expect(document.querySelector('.project-dialog-overlay')).not.toBeNull()

    await wrapper.setProps({ visible: false })
    await wrapper.vm.$nextTick()

    expect(document.querySelector('.project-dialog-overlay')).toBeNull()
    wrapper.unmount()
  })
})
