/**
 * InputBox 项目锁定 prop 透传测试（2026-07-01 新增）
 *
 * 覆盖：InputBox 接收 projectLocked prop，并将其透传给内部 ProjectDropdown。
 *       即 App.vue 只需 :project-locked 传给 InputBox，InputBox 负责下发到 ProjectDropdown。
 */
import { describe, it, expect, beforeAll } from 'vitest'
import { mount } from '@vue/test-utils'
import InputBox from '../InputBox.vue'

beforeAll(() => {
  if (typeof window !== 'undefined' && !window.alert) {
    window.alert = () => {}
  }
})

describe('InputBox projectLocked 透传（2026-07-01 新增）', () => {
  it('test_inputbox_locked_importable 组件可被 import', () => {
    expect(InputBox).toBeDefined()
  })

  it('test_inputbox_passes_project_locked_true_to_dropdown projectLocked=true → ProjectDropdown.locked=true', () => {
    const wrapper = mount(InputBox, {
      props: {
        sessionId: 'sid_lock_1',
        isStreaming: false,
        currentProject: null,
        projectLocked: true
      }
    })
    const dropdown = wrapper.findComponent({ name: 'ProjectDropdown' })
    expect(dropdown.exists()).toBe(true)
    expect(dropdown.props('locked')).toBe(true)
  })

  it('test_inputbox_passes_project_locked_false_to_dropdown projectLocked=false → ProjectDropdown.locked=false', () => {
    const wrapper = mount(InputBox, {
      props: {
        sessionId: 'sid_lock_2',
        isStreaming: false,
        currentProject: null,
        projectLocked: false
      }
    })
    const dropdown = wrapper.findComponent({ name: 'ProjectDropdown' })
    expect(dropdown.props('locked')).toBe(false)
  })

  it('test_inputbox_default_project_locked_is_false 未传 projectLocked 时默认 false', () => {
    const wrapper = mount(InputBox, {
      props: {
        sessionId: 'sid_lock_3',
        isStreaming: false,
        currentProject: null
      }
    })
    const dropdown = wrapper.findComponent({ name: 'ProjectDropdown' })
    expect(dropdown.props('locked')).toBe(false)
  })

  it('test_inputbox_streaming_disabled_still_passed_to_dropdown isStreaming=true 仍透传 disabled', () => {
    const wrapper = mount(InputBox, {
      props: {
        sessionId: 'sid_lock_4',
        isStreaming: true,
        currentProject: null,
        projectLocked: false
      }
    })
    const dropdown = wrapper.findComponent({ name: 'ProjectDropdown' })
    expect(dropdown.props('disabled')).toBe(true)
    // locked 仍是 false（用户没显式锁）
    expect(dropdown.props('locked')).toBe(false)
  })

  it('test_inputbox_locked_and_streaming_combine 当 projectLocked=true + isStreaming=true 都传下去', () => {
    const wrapper = mount(InputBox, {
      props: {
        sessionId: 'sid_lock_5',
        isStreaming: true,
        currentProject: null,
        projectLocked: true
      }
    })
    const dropdown = wrapper.findComponent({ name: 'ProjectDropdown' })
    expect(dropdown.props('disabled')).toBe(true)
    expect(dropdown.props('locked')).toBe(true)
  })
})