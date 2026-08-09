// -*- coding:utf-8 -*-
/**
 * OpsConsoleWorkspace exit 出口测试
 *
 * 2026-08-09 落地：运维控制台顶部红点 → OpsMenuBar emit('exit')
 * → OpsConsoleApp 透传 → OpsConsoleWorkspace.handleExit。
 * 关闭策略：
 *   - 优先 window.close()（被 window.open 打开的 Tab 才有效）
 *   - 失败/无 opener → router.push('/') 回到主会话
 *
 * 覆盖：
 *   - exit 触发 window.close 优先路径
 *   - exit 在 window.close 被浏览器拒绝时降级为 router.push('/')
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

vi.mock('../../components/ops-console/OpsConsoleApp.vue', () => ({
  default: {
    name: 'OpsConsoleApp',
    emits: ['exit'],
    template: '<div class="ops-stub" @click="$emit(\'exit\')" />',
  },
}))

vi.mock('../../utils/ops-console-styles.js', () => ({
  ensureOpsConsoleStyles: vi.fn(),
}))

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'agent', component: { template: '<div />' } },
      { path: '/ops-console', name: 'ops-console', component: { template: '<div />' } },
    ],
  })
}

describe('OpsConsoleWorkspace exit 出口', () => {
  let mockWindowClose
  let router

  beforeEach(async () => {
    mockWindowClose = vi.fn()
    window.close = mockWindowClose
    router = makeRouter()
    await router.push('/ops-console')
    await router.isReady()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    // 还原 window.close 以免污染其他 spec
    delete window.close
  })

  it('test_workspace_exits_via_window_close_when_opened_in_new_tab OpsConsoleApp emit exit → window.close() 优先', async () => {
    // 模拟「被 window.open 打开」场景：window.opener 非空
    const opener = {}
    Object.defineProperty(window, 'opener', { value: opener, configurable: true })
    const pushSpy = vi.spyOn(router, 'push')

    const OpsConsoleWorkspace = (await import('../OpsConsoleWorkspace.vue')).default
    const wrapper = mount(OpsConsoleWorkspace, { global: { plugins: [router] } })
    await flushPromises()
    await wrapper.find('.ops-stub').trigger('click')
    await flushPromises()

    expect(mockWindowClose).toHaveBeenCalledTimes(1)
    expect(pushSpy).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('test_workspace_falls_back_to_router_push_when_close_blocked window.close() 不可用 → 降级 router.push("/")', async () => {
    // 直接访问 /ops-console：window.close() 抛错（浏览器同源策略）
    mockWindowClose.mockImplementation(() => {
      throw new Error('Scripts may close only the windows that were opened by them.')
    })
    Object.defineProperty(window, 'opener', { value: null, configurable: true })
    const pushSpy = vi.spyOn(router, 'push')

    const OpsConsoleWorkspace = (await import('../OpsConsoleWorkspace.vue')).default
    const wrapper = mount(OpsConsoleWorkspace, { global: { plugins: [router] } })
    await flushPromises()
    await wrapper.find('.ops-stub').trigger('click')
    await flushPromises()

    expect(pushSpy).toHaveBeenCalledWith('/')
    wrapper.unmount()
  })
})
