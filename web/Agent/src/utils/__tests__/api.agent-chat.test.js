/**
 * chatStream 改用 /api/agent/chat 测试
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

describe('chatStream 统一接口', () => {
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

  it('test_chat_stream_calls_agent_endpoint 调用 /api/agent/chat', async () => {
    const { chatStream } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      body: { getReader: () => ({ read: async () => ({ done: true }) }) },
    })
    await chatStream('sess-001', 'hello')
    const url = global.fetch.mock.calls[0][0]
    expect(url).toBe('/api/agent/chat')
  })

  it('test_chat_stream_includes_agent_name 请求体包含 agent_name', async () => {
    const { chatStream } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      body: { getReader: () => ({ read: async () => ({ done: true }) }) },
    })
    await chatStream('sess-001', 'hello', [], null, 'map_agent')
    const body = JSON.parse(global.fetch.mock.calls[0][1].body)
    expect(body.agent_name).toBe('map_agent')
  })

  it('test_chat_stream_default_agent_name 默认 agent_name 为 map_agent', async () => {
    const { chatStream } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      body: { getReader: () => ({ read: async () => ({ done: true }) }) },
    })
    await chatStream('sess-001', 'hello')
    const body = JSON.parse(global.fetch.mock.calls[0][1].body)
    expect(body.agent_name).toBe('map_agent')
  })
})
