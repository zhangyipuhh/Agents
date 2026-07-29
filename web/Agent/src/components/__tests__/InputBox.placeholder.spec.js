﻿/**
 * InputBox placeholder 文案测试（2026-07-29 新增）
 *
 * 覆盖：空载 / 已选智能体 / 已绑定智能体三档 placeholder 文案。
 * 关键约束：仅在"空载场景"追加"输入 # 快捷添加引用"提示，
 *          已选智能体场景仍为"请输入消息，按「Enter」发送"。
 *          已绑定智能体场景展示当前智能体且不含 # 提示。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import InputBox from '../InputBox.vue'

describe('InputBox placeholder 文案', () => {
  let originalFetch
  let originalLocalStorage

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
    global.fetch = vi.fn((url) => {
      if (url === '/api/auth/refresh') {
        return Promise.resolve({
          ok: true,
          json: async () => ({ access_token: 'new-fake-token' }),
        })
      }
      if (url === '/api/agent/list') {
        return Promise.resolve({
          ok: true,
          json: async () => [{ name: 'map_agent', display_name: '地图' }],
        })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })
    global.localStorage = {
      getItem: vi.fn(() => 'fake-token'),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    }
    if (typeof window !== 'undefined' && !window.alert) {
      window.alert = () => {}
    }
  })

  afterEach(() => {
    global.fetch = originalFetch
    global.localStorage = originalLocalStorage
  })

  // 2026-07-29：空载场景 - props.boundAgentName 默认 ''（不进智能体分支）。
  it('test_placeholder_empty_includes_hash_hint 空载场景文案含 # 快捷添加引用 提示', async () => {
    const wrapper = mount(InputBox, {
      props: {
        sessionId: 'sid_1',
        isStreaming: false,
      },
    })
    await flushPromises()
    const placeholder = wrapper
      .find('[data-testid="input-editor"]')
      .attributes('data-placeholder')
    expect(placeholder).toBe('输入 / 快速使用智能体 · 输入 # 快捷添加引用')
  })

  // 2026-07-29：已选智能体场景 - 直接注入 selectedAgent.value（ref 非 prop）。
  it('test_placeholder_selected_agent_no_hash_hint 已选智能体场景不追加 # 提示', async () => {
    const wrapper = mount(InputBox, {
      props: {
        sessionId: 'sid_1',
        isStreaming: false,
      },
    })
    await flushPromises()
    wrapper.vm.selectedAgent = { name: 'map_agent', display_name: '地图' }
    await nextTick()
    const placeholder = wrapper
      .find('[data-testid="input-editor"]')
      .attributes('data-placeholder')
    expect(placeholder).toBe('请输入消息，按「Enter」发送')
    expect(placeholder).not.toContain('# 快捷添加引用')
  })

  // 2026-07-29：已绑定智能体场景 - 通过 props.boundAgentName 注入。
  it('test_placeholder_bound_agent_no_hash_hint 已绑定智能体场景展示当前智能体且不含 # 提示', async () => {
    const wrapper = mount(InputBox, {
      props: {
        sessionId: 'sid_1',
        isStreaming: false,
        boundAgentName: 'map_agent',
        boundAgentDisplayName: '地图',
      },
    })
    await flushPromises()
    const placeholder = wrapper
      .find('[data-testid="input-editor"]')
      .attributes('data-placeholder')
    expect(placeholder).toBe('当前智能体：地图')
    expect(placeholder).not.toContain('# 快捷添加引用')
  })
})
