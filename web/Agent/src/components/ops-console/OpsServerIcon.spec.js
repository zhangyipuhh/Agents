// -*- coding:utf-8 -*-
/**
 * OpsServerIcon 组件测试（2026-08-05 新增）。
 *
 * 覆盖：
 *   - 组件可被 import；
 *   - status='ok' / 'err' / 'unknown' 三态 LED 颜色映射（绿灯 / 红灯 / 灰灯）。
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import OpsServerIcon from './OpsServerIcon.vue'

describe('OpsServerIcon 服务器图标组件', () => {
  beforeEach(() => {
    // 每个用例独立（避免测试间状态泄漏）
  })

  it('test_ops_server_icon_importable 组件可被 import', () => {
    expect(OpsServerIcon).toBeTruthy()
    expect(typeof OpsServerIcon).toBe('object')
  })

  it('test_status_ok_renders_green_led status=ok → LED class=green', () => {
    const wrapper = mount(OpsServerIcon, { props: { status: 'ok' } })
    const led = wrapper.find('.led')
    expect(led.exists()).toBe(true)
    expect(led.classes()).toContain('green')
    expect(led.classes()).not.toContain('red')
    expect(led.classes()).not.toContain('gray')
  })

  it('test_status_err_renders_red_led status=err → LED class=red', () => {
    const wrapper = mount(OpsServerIcon, { props: { status: 'err' } })
    const led = wrapper.find('.led')
    expect(led.classes()).toContain('red')
    expect(led.classes()).not.toContain('green')
    expect(led.classes()).not.toContain('gray')
  })

  it('test_status_unknown_renders_gray_led status=unknown → LED class=gray', () => {
    const wrapper = mount(OpsServerIcon, { props: { status: 'unknown' } })
    const led = wrapper.find('.led')
    expect(led.classes()).toContain('gray')
    expect(led.classes()).not.toContain('green')
    expect(led.classes()).not.toContain('red')
  })

  it('test_default_status_is_ok 默认 status=ok → 绿灯', () => {
    const wrapper = mount(OpsServerIcon)
    const led = wrapper.find('.led')
    expect(led.classes()).toContain('green')
  })

  it('test_led_can_be_hidden led=false → 不渲染右上角灯', () => {
    const wrapper = mount(OpsServerIcon, {
      props: { status: 'ok', led: false },
    })
    expect(wrapper.find('.led').exists()).toBe(false)
  })
})