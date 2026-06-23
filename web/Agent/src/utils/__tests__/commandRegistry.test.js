/**
 * commandRegistry 测试
 *
 * 覆盖：COMMAND_REGISTRY 含 agent 与 agents 命令、handleCommand 切换智能体、
 *      未知命令返回错误、缺少参数返回提示、/agents 列表与错误路径、
 *      /agent 后端失败错误向上抛出。
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
    expect(COMMAND_REGISTRY.length).toBe(2)
    expect(COMMAND_REGISTRY[0].name).toBe('agent')
    expect(COMMAND_REGISTRY[1].name).toBe('agents')
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

  it('test_list_agents_command_returns_agent_list 列表非空时返回格式化文本', async () => {
    const { listAgentsCommand } = await import('../commandRegistry.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [{ name: 'map_agent', display_name: '地图' }],
    })
    const text = await listAgentsCommand()
    expect(text).toContain('map_agent')
    expect(text).toContain('地图')
  })

  it('test_list_agents_command_empty_returns_placeholder 列表为空时返回占位提示', async () => {
    const { listAgentsCommand } = await import('../commandRegistry.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    })
    const text = await listAgentsCommand()
    expect(text).toBe('暂无可用智能体')
  })

  it('test_list_agents_command_network_error_propagates 网络失败时向上抛错', async () => {
    const { listAgentsCommand } = await import('../commandRegistry.js')
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ detail: '服务器错误' }),
    })
    await expect(listAgentsCommand()).rejects.toThrow('服务器错误')
  })

  it('test_handle_command_agent_fetch_failure_propagates 后端失败时向上抛错', async () => {
    const { handleCommand } = await import('../commandRegistry.js')
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ detail: '服务器错误' }),
    })
    await expect(handleCommand('agent', ['map_agent'])).rejects.toThrow('服务器错误')
  })
})
