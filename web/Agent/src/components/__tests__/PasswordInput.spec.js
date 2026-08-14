// -*- coding:utf-8 -*-
/**
 * PasswordInput 组件测试（2026-08-14 新增）
 *
 * 覆盖契约：
 * - 默认渲染 type=password + 闭眼图标 + aria-pressed=false；
 * - 点击眼睛图标 → type=text + aria-pressed=true；
 * - 再次点击 → 还原 type=password + aria-pressed=false；
 * - v-model 双向绑定（input 输入触发 update:modelValue）；
 * - caps-lock 事件透传（keydown / keyup 触发 caps-lock emit）；
 * - usePasswordMask=true 时不切 type（始终 text），切 .password-mask class；
 * - disabled 时按钮禁用且不响应点击；
 * - inputId / autocomplete / inputTestId 透传到内部 <input>。
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PasswordInput from '../PasswordInput.vue'

function mountPassword(props = {}, options = {}) {
  return mount(PasswordInput, {
    props: { modelValue: '', ...props },
    ...options
  })
}

describe('PasswordInput 组件', () => {
  it('可导入', () => {
    expect(PasswordInput).toBeDefined()
  })

  it('默认渲染 type=password + aria-pressed=false + 显示密码 aria-label', () => {
    const w = mountPassword()
    const input = w.find('input')
    expect(input.attributes('type')).toBe('password')
    expect(input.attributes('autocomplete')).toBe('current-password')
    const btn = w.find('[data-testid="password-toggle"]')
    expect(btn.exists()).toBe(true)
    expect(btn.attributes('aria-pressed')).toBe('false')
    expect(btn.attributes('aria-label')).toBe('显示密码')
  })

  it('点击眼睛 → type=text + aria-pressed=true + aria-label=隐藏密码', async () => {
    const w = mountPassword()
    const btn = w.find('[data-testid="password-toggle"]')
    await btn.trigger('click')
    const input = w.find('input')
    expect(input.attributes('type')).toBe('text')
    expect(btn.attributes('aria-pressed')).toBe('true')
    expect(btn.attributes('aria-label')).toBe('隐藏密码')
  })

  it('再次点击 → 还原 type=password + aria-pressed=false', async () => {
    const w = mountPassword()
    const btn = w.find('[data-testid="password-toggle"]')
    await btn.trigger('click')
    await btn.trigger('click')
    expect(w.find('input').attributes('type')).toBe('password')
    expect(btn.attributes('aria-pressed')).toBe('false')
  })

  it('v-model 双向绑定：input 输入触发 update:modelValue', async () => {
    const w = mountPassword({ modelValue: '' })
    const input = w.find('input')
    await input.setValue('Aa1!aaaa')
    const emitted = w.emitted('update:modelValue')
    expect(emitted).toBeTruthy()
    expect(emitted.at(-1)).toEqual(['Aa1!aaaa'])
  })

  it('caps-lock 事件透传：keydown / keyup 触发 caps-lock emit', async () => {
    const w = mountPassword()
    const input = w.find('input')
    // happy-dom 下 vue-test-utils 的 trigger 不会透传自定义方法，
    // 改用真实 KeyboardEvent（getModifierState 默认返回 false），但通过 stub
    // HTMLElement.prototype.getModifierState 后再触发
    const origGetModifierState = window.KeyboardEvent.prototype.getModifierState
    let calls = []
    window.KeyboardEvent.prototype.getModifierState = function (key) {
      calls.push(key)
      // 偶数次调用返回 true，奇数次返回 false（keydown→true，keyup→false）
      return calls.length % 2 === 1
    }
    try {
      await input.trigger('keydown')
      await input.trigger('keyup')
    } finally {
      window.KeyboardEvent.prototype.getModifierState = origGetModifierState
    }
    const events = w.emitted('caps-lock')
    expect(events).toBeTruthy()
    expect(events).toEqual([[true], [false]])
  })

  it('usePasswordMask=true：始终 type=text，点击眼睛切换 password-mask class', async () => {
    const w = mountPassword({
      inputClass: 'form-input password-mask',
      usePasswordMask: true
    })
    const input = w.find('input')
    // 初始：type=text + 含 password-mask
    expect(input.attributes('type')).toBe('text')
    expect(input.classes()).toContain('password-mask')
    // 切到可见
    await w.find('[data-testid="password-toggle"]').trigger('click')
    expect(input.attributes('type')).toBe('text') // 不变
    expect(input.classes()).not.toContain('password-mask') // class 被移除
    // 再切回隐藏
    await w.find('[data-testid="password-toggle"]').trigger('click')
    expect(input.attributes('type')).toBe('text')
    expect(input.classes()).toContain('password-mask')
  })

  it('disabled 时按钮禁用且不响应点击', async () => {
    const w = mountPassword({ disabled: true })
    const btn = w.find('[data-testid="password-toggle"]')
    expect(btn.attributes('disabled')).toBeDefined()
    await btn.trigger('click')
    // type 仍为 password（没切换）
    expect(w.find('input').attributes('type')).toBe('password')
  })

  it('inputId / autocomplete / inputTestId 透传到内部 <input>', () => {
    const w = mountPassword({
      inputId: 'my-pwd',
      autocomplete: 'new-password',
      inputTestId: 'my-pwd-test'
    })
    const input = w.find('input')
    expect(input.attributes('id')).toBe('my-pwd')
    expect(input.attributes('autocomplete')).toBe('new-password')
    expect(input.attributes('data-testid')).toBe('my-pwd-test')
  })
})
