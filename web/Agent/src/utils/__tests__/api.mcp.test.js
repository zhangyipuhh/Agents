/**
 * MCP 管理 API 测试
 *
 * 覆盖：listMcpServers / createMcpServer / updateMcpServer / deleteMcpServer /
 *      toggleMcpServer / listMcpMethods / refreshMcpMethods / toggleMcpMethod
 *      和 fetchAgentList。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

describe('MCP 管理 API', () => {
  let originalFetch
  let originalLocalStorage

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
    global.fetch = vi.fn()
    global.localStorage = {
      getItem: vi.fn((key) => {
        if (key === 'auth_token') return 'fake-token'
        if (key === 'session_id') return 'fake-session'
        return null
      }),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    }
  })

  afterEach(() => {
    global.fetch = originalFetch
    global.localStorage = originalLocalStorage
  })

  it('test_list_mcp_servers_calls_correct_url', async () => {
    const { listMcpServers } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [{ name: 'amap', enabled: true }],
    })
    const result = await listMcpServers()
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/admin/mcp/servers',
      expect.objectContaining({ method: 'GET' })
    )
    expect(result).toEqual([{ name: 'amap', enabled: true }])
  })

  it('test_create_mcp_server_posts_correct_body', async () => {
    const { createMcpServer } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      status: 201,
      json: async () => ({ name: 'amap' }),
    })
    const config = { name: 'amap', type: 'sse', url: 'http://x' }
    await createMcpServer(config)
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/admin/mcp/servers',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(config),
      })
    )
  })

  it('test_delete_mcp_server_uses_delete_method', async () => {
    const { deleteMcpServer } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({ ok: true, status: 204 })
    await deleteMcpServer('amap')
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/admin/mcp/servers/amap',
      expect.objectContaining({ method: 'DELETE' })
    )
  })

  it('test_toggle_mcp_server_passes_enabled_param', async () => {
    const { toggleMcpServer } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({ ok: true, json: async () => ({}) })
    await toggleMcpServer('amap', false)
    const callArgs = global.fetch.mock.calls[0]
    expect(callArgs[0]).toContain('/api/admin/mcp/servers/amap/toggle')
    expect(callArgs[0]).toContain('enabled=false')
    expect(callArgs[1].method).toBe('POST')
  })

  it('test_list_mcp_methods_calls_correct_url', async () => {
    const { listMcpMethods } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [{ method_name: 'search', enabled: true }],
    })
    await listMcpMethods('amap')
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/admin/mcp/servers/amap/methods',
      expect.objectContaining({ method: 'GET' })
    )
  })

  it('test_refresh_mcp_methods_posts_correct_url', async () => {
    const { refreshMcpMethods } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ methods_count: 3 }),
    })
    await refreshMcpMethods('amap')
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/admin/mcp/servers/amap/refresh-methods',
      expect.objectContaining({ method: 'POST' })
    )
  })

  it('test_toggle_mcp_method_passes_enabled_param', async () => {
    const { toggleMcpMethod } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({ ok: true, json: async () => ({}) })
    await toggleMcpMethod('amap', 'search', false)
    const callArgs = global.fetch.mock.calls[0]
    expect(callArgs[0]).toContain('/api/admin/mcp/servers/amap/methods/search/toggle')
    expect(callArgs[0]).toContain('enabled=false')
  })

  it('test_fetch_agent_list_calls_correct_url', async () => {
    const { fetchAgentList } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [{ name: 'map_agent', display_name: '地图' }],
    })
    const result = await fetchAgentList()
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/agent/list',
      expect.objectContaining({ method: 'GET' })
    )
    expect(result).toEqual([{ name: 'map_agent', display_name: '地图' }])
  })
})
