/**
 * commandRegistry 测试
 *
 * 覆盖：COMMAND_REGISTRY 只含 agent 命令、handleCommand 切换智能体、
 *      未知命令返回错误、缺少参数返回提示。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

describe('commandRegistry', () => {
  let originalFetch
  let originalLocalStorage

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
    global.fetch = vi.fn()
    global.localStorage = {
      getItem: vi.fn(() => 'fake-token'),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    }
  })

  afterEach(() => {
    global.fetch = originalFetch
    global.localStorage = originalLocalStorage
  })

  it('test_registry_only_has_agent_command 只包含 agent 命令', async () => {
    const { COMMAND_REGISTRY } = await import('../commandRegistry.js')
    expect(COMMAND_REGISTRY.length).toBe(1)
    expect(COMMAND_REGISTRY[0].name).toBe('agent')
  })

  it('test_handle_command_agent_switches_agent 切换智能体', async () => {
    const { handleCommand } = await import('../commandRegistry.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [{ name: 'map_agent', display_name: '地图' }],
    })
    const result = await handleCommand('agent', ['map_agent'])
    expect(result.switchAgent).toBe('map_agent')
    expect(result.text).toContain('地图')
  })

  it('test_handle_command_unknown_returns_error 未知命令返回错误', async () => {
    const { handleCommand } = await import('../commandRegistry.js')
    const result = await handleCommand('unknown', [])
    expect(result.text).toContain('未知命令')
  })

  it('test_handle_command_agent_missing_arg 缺少参数返回提示', async () => {
    const { handleCommand } = await import('../commandRegistry.js')
    const result = await handleCommand('agent', [])
    expect(result.text).toContain('用法')
  })

  it('test_handle_command_agent_not_found 智能体不存在', async () => {
    const { handleCommand } = await import('../commandRegistry.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [{ name: 'map_agent', display_name: '地图' }],
    })
    const result = await handleCommand('agent', ['non_existent'])
    expect(result.text).toContain('不存在')
  })
})
