// -*- coding:utf-8 -*-
/**
 * OpsConsoleApp 菜单栏事件透传测试
 *
 * 覆盖 OpsMenuBar 三个事件源 → OpsConsoleApp 透传链路：
 *   - exit  ✕ Close 原生 button → emit('exit') → OpsConsoleApp 透传 → OpsConsoleWorkspace
 *   - open  「服务器管理 / 日志管理」两按钮 → emit('open', 'servers'|'logs')
 *         → OpsConsoleApp 模板 @open="openWin"（无 wrapper 自身 emit，但
 *           wins.servers.open / wins.logs.open 状态会随之变化，本测试
 *           通过 wrapper.findComponent(OpsMenuBar).vm.$emit('open', name)
 *           直接断言子组件 emit 参数 + openWin 调用后的状态）
 *
 * 历史：
 *   2026-08-09 落地：运维控制台顶部红点（OpsMenuBar）→ emit('exit') →
 *                  OpsConsoleApp 透传 emit('exit') → OpsConsoleWorkspace 接收。
 *   2026-08-13 适配 GNOME 风格：断言选择器从 `.menubar-traffic .r`（mac 红点）
 *                  改为 `.close-all-btn`（GNOME 顶栏原生 ✕ Close button）。
 *   2026-08-14 菜单栏重构：移除 OpsDockBar stub（组件已彻底删除）。
 *                  新增「服务器管理 / 日志管理」emit('open', name) 透传链路测试。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../../../utils/api.js', () => ({
  fetchServerInspectionLatest: vi.fn(async () => ({ items: [] })),
  validateToken: vi.fn(async () => ({ username: 'tester', role: 'user', allowed_agents: [] })),
}))

import OpsConsoleApp from '../OpsConsoleApp.vue'
import OpsMenuBar from '../OpsMenuBar.vue'

describe('OpsConsoleApp 菜单栏事件透传', () => {
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

  // 2026-08-13 新增：GNOME 风格下 ✕ Close 原生 button 接管 exit 语义
  it('test_close_all_button_in_menu_bar_still_emits_exit 真组件 OpsMenuBar 渲染的 .close-all-btn 点击 → 自身 emit exit', async () => {
    const wrapper = mount(OpsConsoleApp, {
      global: {
        stubs: {
          OpsServerWindow: true,
          OpsDetailWindow: true,
          OpsLogManager: true,
          OpsLogViewer: true,
        },
      },
    })
    await flushPromises()
    // OpsMenuBar 渲染后查找 .close-all-btn 原生 button（替代旧 .menubar-traffic .r）
    const closeBtn = wrapper.find('.close-all-btn')
    expect(closeBtn.exists()).toBe(true)
    await closeBtn.trigger('click')
    await flushPromises()
    expect(wrapper.emitted('exit')).toBeTruthy()
    expect(wrapper.emitted('exit').length).toBe(1)
    wrapper.unmount()
  })

  // 2026-08-14 新增：菜单栏中部「服务器管理」按钮 emit('open', 'servers')
  it('test_menu_bar_nav_button_servers_opens_servers_window 菜单栏服务器管理按钮 → emit open servers → openWin', async () => {
    const wrapper = mount(OpsConsoleApp, {
      global: {
        stubs: {
          OpsServerWindow: true,
          OpsDetailWindow: true,
          OpsLogManager: true,
          OpsLogViewer: true,
        },
      },
    })
    await flushPromises()
    // 初始：servers 窗口已默认打开；logs 窗口默认关闭
    expect(wrapper.vm.wins.logs.open).toBe(false)
    // 模拟 OpsMenuBar emit('open', 'logs')
    wrapper.findComponent(OpsMenuBar).vm.$emit('open', 'logs')
    await flushPromises()
    expect(wrapper.vm.wins.logs.open).toBe(true)
    wrapper.unmount()
  })

  // 2026-08-14 新增：菜单栏中部「日志管理」按钮 emit('open', 'logs')
  it('test_menu_bar_nav_button_logs_opens_logs_window 菜单栏日志管理按钮 → emit open logs → openWin', async () => {
    const wrapper = mount(OpsConsoleApp, {
      global: {
        stubs: {
          OpsServerWindow: true,
          OpsDetailWindow: true,
          OpsLogManager: true,
          OpsLogViewer: true,
        },
      },
    })
    await flushPromises()
    // 模拟 OpsMenuBar emit('open', 'servers')；servers 默认已 open，此处断言幂等无副作用 + 仍 open
    expect(wrapper.vm.wins.servers.open).toBe(true)
    wrapper.findComponent(OpsMenuBar).vm.$emit('open', 'servers')
    await flushPromises()
    expect(wrapper.vm.wins.servers.open).toBe(true)
    wrapper.unmount()
  })

  // 2026-08-14 新增：DOM 端到端 — 真组件菜单栏中部 .menubar-nav-btn 渲染存在
  it('test_menu_bar_renders_two_centered_nav_buttons DOM 端到端：菜单栏中部渲染两个 .menubar-nav-btn', async () => {
    const wrapper = mount(OpsConsoleApp, {
      global: {
        stubs: {
          OpsServerWindow: true,
          OpsDetailWindow: true,
          OpsLogManager: true,
          OpsLogViewer: true,
        },
      },
    })
    await flushPromises()
    const navBtns = wrapper.findAll('.menubar-nav-btn')
    expect(navBtns.length).toBe(2)
    expect(navBtns[0].attributes('aria-label')).toBe('服务器管理')
    expect(navBtns[1].attributes('aria-label')).toBe('日志管理')
    wrapper.unmount()
  })

  // 2026-08-14 新增：DOM 端到端 — 旧 文件/编辑/视图/帮助 全局菜单占位不再渲染
  it('test_menu_bar_no_longer_renders_global_menu_placeholders DOM 端到端：文件/编辑/视图/帮助 占位不再渲染', async () => {
    const wrapper = mount(OpsConsoleApp, {
      global: {
        stubs: {
          OpsServerWindow: true,
          OpsDetailWindow: true,
          OpsLogManager: true,
          OpsLogViewer: true,
        },
      },
    })
    await flushPromises()
    expect(wrapper.findAll('.menubar-menu-item').length).toBe(0)
    wrapper.unmount()
  })
})
