/**
 * InputBox 中断待生效（isStopPending）测试（2026-07-06 新增）
 *
 * 覆盖：父组件 App.vue/KnowledgeApp.vue 透传 isStopPending=true 时，
 *      - send-btn 切换为 stop-pending-mode（背景灰、旋转圆环图标、右上角 badge、cursor not-allowed）
 *      - canSend 为 false（即使有输入文字也不能发送）
 *      - title 文案改为「中断中，等待工具完成...」
 *      - 点击按钮被 handleSendBtnClick 拦截：不 emit('stop') 也不 emit('send')
 *      - 不再走 send 流程（即使 prop isStreaming=false）
 *
 * 设计要点：与 InputBox.stop.spec.js 互补，
 *   - stop.spec.js 覆盖「流式 vs 非流式」二态
 *   - stop-pending.spec.js 覆盖「中断等待工具完成」第三态
 */
import { describe, it, expect, beforeAll, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import InputBox from '../InputBox.vue'

// 组件 handleSend 失败时会调用 alert()，happy-dom 不提供 → 注入 noop
beforeAll(() => {
  if (typeof window !== 'undefined' && !window.alert) {
    window.alert = () => {}
  }
})

describe('InputBox 中断待生效 stop-pending-mode（2026-07-06 新增）', () => {
  it('test_inputbox_importable 组件可被 import', () => {
    expect(InputBox).toBeDefined()
  })

  it('test_inputbox_stop_pending_shows_pending_mode isStopPending=true 时显示 stop-pending 样式', () => {
    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_1', isStreaming: false, isStopPending: true }
    })
    const btn = wrapper.find('.send-btn')
    expect(btn.exists()).toBe(true)
    expect(btn.classes()).toContain('stop-pending-mode')
    expect(btn.classes()).not.toContain('stop-mode')
    expect(btn.classes()).not.toContain('send-mode')
  })

  it('test_inputbox_stop_pending_renders_spinner_icon 内嵌旋转圆环图标存在', () => {
    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_1', isStreaming: false, isStopPending: true }
    })
    expect(wrapper.find('.stop-pending-inner-icon').exists()).toBe(true)
    // 纸飞机和停止方块都不应出现
    expect(wrapper.find('.send-icon').exists()).toBe(false)
    expect(wrapper.find('.stop-icon').exists()).toBe(false)
  })

  it('test_inputbox_stop_pending_renders_corner_badge 右上角旋转 badge 存在', () => {
    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_1', isStreaming: false, isStopPending: true }
    })
    const badge = wrapper.find('.stop-pending-badge')
    expect(badge.exists()).toBe(true)
    // aria-label 用于无障碍
    expect(badge.attributes('aria-label')).toBe('中断中')
  })

  it('test_inputbox_stop_pending_title_changes title 文案变为「中断中，等待工具完成...」', () => {
    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_1', isStreaming: false, isStopPending: true }
    })
    const btn = wrapper.find('.send-btn')
    expect(btn.attributes('title')).toBe('中断中，等待工具完成...')
  })

  it('test_inputbox_stop_pending_cannot_send_even_with_input 即使有输入也不能发送', async () => {
    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_1', isStreaming: false, isStopPending: true }
    })
    const textarea = wrapper.find('textarea.text-input')
    await textarea.setValue('hello')
    await wrapper.vm.$nextTick()

    // canSend 计算属性应为 false（被 isStopPending 短路）
    expect(wrapper.vm.canSend).toBe(false)

    // 按钮进入 stop-pending-mode（视觉禁用）
    const btn = wrapper.find('.send-btn')
    expect(btn.classes()).toContain('stop-pending-mode')
    expect(btn.classes()).toContain('send-btn')
  })

  it('test_inputbox_stop_pending_click_intercepted 点击被 handleSendBtnClick 拦截（不 emit stop/send）', async () => {
    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_1', isStreaming: false, isStopPending: true }
    })
    // 注入输入让 canSend 在非 stop-pending 时会通过 → 验证 stop-pending 确实拦截
    await wrapper.find('textarea.text-input').setValue('hello')
    const btn = wrapper.find('.send-btn')
    // 强制触发 click（即使按钮 disabled，handler 也应拦截）
    await btn.trigger('click')
    expect(wrapper.emitted('stop')).toBeFalsy()
    expect(wrapper.emitted('send')).toBeFalsy()
  })

  it('test_inputbox_stop_pending_even_when_streaming_true stop-pending 优先级高于 streaming', async () => {
    // 父组件可能在工具完成后才把 isStreaming 复位，但 stop-pending 仍 true
    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_1', isStreaming: true, isStopPending: true }
    })
    const btn = wrapper.find('.send-btn')
    expect(btn.classes()).toContain('stop-pending-mode')
    // 不能同时是 stop-mode（互斥）
    expect(btn.classes()).not.toContain('stop-mode')
  })

  it('test_inputbox_stop_pending_disabled_tooltip 默认 isStopPending=false 时按钮可发送', async () => {
    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_1', isStreaming: false, isStopPending: false }
    })
    await wrapper.find('textarea.text-input').setValue('hello')
    await wrapper.vm.$nextTick()
    expect(wrapper.vm.canSend).toBe(true)
    const btn = wrapper.find('.send-btn')
    expect(btn.attributes('disabled')).toBeUndefined()
    expect(btn.classes()).not.toContain('stop-pending-mode')
  })

  it('test_inputbox_handleSendBtnClick_routes_to_stop_when_streaming isStreaming=true 时点击触发 emit stop', async () => {
    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_1', isStreaming: true, isStopPending: false }
    })
    const btn = wrapper.find('.send-btn')
    await btn.trigger('click')
    expect(wrapper.emitted('stop')).toBeTruthy()
    expect(wrapper.emitted('stop').length).toBe(1)
  })

  it('test_inputbox_handleSendBtnClick_short_circuit handleSendBtnClick 在 isStopPending=true 时立即返回', async () => {
    const wrapper = mount(InputBox, {
      props: { sessionId: 'sid_1', isStreaming: true, isStopPending: true }
    })
    const handleStopSpy = vi.fn()
    const handleSendSpy = vi.fn()
    wrapper.vm.emit = vi.fn((event, ...args) => {
      if (event === 'stop') handleStopSpy(args)
    })
    wrapper.vm.handleSend = handleSendSpy

    await wrapper.vm.handleSendBtnClick()

    expect(handleStopSpy).not.toHaveBeenCalled()
    expect(handleSendSpy).not.toHaveBeenCalled()
  })
})