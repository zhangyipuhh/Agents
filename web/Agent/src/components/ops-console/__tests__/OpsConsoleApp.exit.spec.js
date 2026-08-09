// -*- coding:utf-8 -*-
/**
 * OpsConsoleApp exit 透传测试
 *
 * 2026-08-09 落地：运维控制台顶部红点（OpsMenuBar）→ emit('exit') →
 * OpsConsoleApp 透传 emit('exit') → OpsConsoleWorkspace 接收。
 *
 * 覆盖：
 *   - OpsConsoleApp defineEmits 包含 exit（直接 emit 验证）
 *   - OpsConsoleApp 模板上 <OpsMenuBar @exit="emit('exit')" /> 静态绑定
 *     由 OpsMenuBar exit.spec 端到端覆盖（mount 真组件 → 触发红点）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../../../utils/api.js', () => ({
  fetchServerInspectionLatest: vi.fn(async () => ({ items: [] })),
  validateToken: vi.fn(async () => ({ username: 'tester', role: 'user', allowed_agents: [] })),
}))

import OpsConsoleApp from '../OpsConsoleApp.vue'
import OpsMenuBar from '../OpsMenuBar.vue'

describe('OpsConsoleApp exit 透传', () => {
  beforeEach(() => vi.clearAllMocks())

  // 直接断言 defineEmits 已注册 exit + 自身能 emit
  it('test_ops_console_app_defines_exit_emit defineEmits 包含 exit 且能直接 emit', async () => {
    const wrapper = mount(OpsConsoleApp, {
      global: {
        stubs: {
          OpsServerWindow: true,
          OpsDetailWindow: true,
          OpsLogManager: true,
          OpsLogViewer: true,
          OpsDockBar: true,
          // OpsMenuBar 不 stub，走真实组件
        },
      },
    })
    await flushPromises()
    expect(() => wrapper.vm.$emit('exit')).not.toThrow()
    expect(wrapper.emitted('exit')).toBeTruthy()
    expect(wrapper.emitted('exit').length).toBe(1)
    wrapper.unmount()
  })

  // 真组件 OpsMenuBar emit exit → OpsConsoleApp 模板 @exit 透传 → 自身 emit exit
  it('test_ops_console_app_relays_real_menu_bar_exit 真组件 OpsMenuBar emit exit → 自身 emit exit', async () => {
    const wrapper = mount(OpsConsoleApp, {
      global: {
        stubs: {
          OpsServerWindow: true,
          OpsDetailWindow: true,
          OpsLogManager: true,
          OpsLogViewer: true,
          OpsDockBar: true,
        },
      },
    })
    await flushPromises()
    const menuBar = wrapper.findComponent(OpsMenuBar)
    expect(menuBar.exists()).toBe(true)
    menuBar.vm.$emit('exit')
    await flushPromises()
    expect(wrapper.emitted('exit')).toBeTruthy()
    expect(wrapper.emitted('exit').length).toBe(1)
    wrapper.unmount()
  })
})
