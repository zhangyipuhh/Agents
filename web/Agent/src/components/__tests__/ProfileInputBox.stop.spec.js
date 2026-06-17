/**
 * ProfileInputBox 停止按钮测试（2026-06-15 新增）
 *
 * 覆盖：ProfileInputBox 的 send-btn 在 isStreaming=true 时切换为 stop-mode，
 *      与 InputBox 同款测试逻辑（结构完全对齐）。
 */
import { describe, it, expect, beforeAll } from 'vitest'
import { mount } from '@vue/test-utils'
import ProfileInputBox from '../ProfileInputBox.vue'

// 组件 handleSend 失败时会调用 alert()，happy-dom 不提供 → 注入 noop 避免 unhandled error
beforeAll(() => {
  if (typeof window !== 'undefined' && !window.alert) {
    window.alert = () => {}
  }
})

describe('ProfileInputBox 停止按钮二态切换（2026-06-15 新增）', () => {
  it('test_profile_inputbox_importable 组件可被 import', () => {
    expect(ProfileInputBox).toBeDefined()
  })

  it('test_profile_inputbox_shows_send_icon_when_not_streaming 默认显示发送按钮（纸飞机）', () => {
    const wrapper = mount(ProfileInputBox, {
      props: { sessionId: 'sid_1', isStreaming: false }
    })
    const btn = wrapper.find('.send-btn')
    expect(btn.exists()).toBe(true)
    expect(btn.classes()).toContain('send-mode')
    expect(btn.classes()).not.toContain('stop-mode')
    expect(wrapper.find('.send-icon').exists()).toBe(true)
    expect(wrapper.find('.stop-icon').exists()).toBe(false)
    expect(btn.attributes('title')).toBe('发送消息')
  })

  it('test_profile_inputbox_shows_stop_icon_when_streaming 流式时显示停止按钮（实心方块）', () => {
    const wrapper = mount(ProfileInputBox, {
      props: { sessionId: 'sid_1', isStreaming: true }
    })
    const btn = wrapper.find('.send-btn')
    expect(btn.exists()).toBe(true)
    expect(btn.classes()).toContain('stop-mode')
    expect(btn.classes()).not.toContain('send-mode')
    expect(wrapper.find('.stop-icon').exists()).toBe(true)
    expect(wrapper.find('.send-icon').exists()).toBe(false)
    expect(btn.attributes('title')).toBe('停止生成')
    expect(btn.attributes('disabled')).toBeUndefined()
  })

  it('test_profile_inputbox_emits_stop_event_when_streaming_clicked 流式时点击触发 stop 事件', async () => {
    const wrapper = mount(ProfileInputBox, {
      props: { sessionId: 'sid_1', isStreaming: true }
    })
    const btn = wrapper.find('.send-btn')
    await btn.trigger('click')
    expect(wrapper.emitted('stop')).toBeTruthy()
    expect(wrapper.emitted('stop').length).toBe(1)
    expect(wrapper.emitted('send')).toBeFalsy()
  })

  it('test_profile_inputbox_does_not_emit_stop_when_not_streaming 非流式时点击不触发 stop 事件', async () => {
    const wrapper = mount(ProfileInputBox, {
      props: { sessionId: 'sid_1', isStreaming: false }
    })
    await wrapper.setData({ inputValue: 'hello world' })
    const textarea = wrapper.find('textarea.text-input')
    await textarea.setValue('hello world')
    const btn = wrapper.find('.send-btn')
    await btn.trigger('click')
    // 不会 emit('stop')（点击会调 handleSend 走 send 路径）
    expect(wrapper.emitted('stop')).toBeFalsy()
  })

  it('test_profile_inputbox_stop_button_disabled_when_no_text_and_not_streaming 非流式且无输入时按钮 disabled', () => {
    const wrapper = mount(ProfileInputBox, {
      props: { sessionId: 'sid_1', isStreaming: false }
    })
    const btn = wrapper.find('.send-btn')
    expect(btn.attributes('disabled')).toBeDefined()
    expect(btn.classes()).toContain('disabled')
  })

  it('test_profile_inputbox_stop_button_enabled_when_streaming 流式时停止按钮始终可点', () => {
    const wrapper = mount(ProfileInputBox, {
      props: { sessionId: 'sid_1', isStreaming: true }
    })
    const btn = wrapper.find('.send-btn')
    expect(btn.attributes('disabled')).toBeUndefined()
    expect(btn.classes()).not.toContain('disabled')
  })
})
