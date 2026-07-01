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

  it('test_chat_stream_default_no_agent_name 默认不传 agent_name', async () => {
    const { chatStream } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      body: { getReader: () => ({ read: async () => ({ done: true }) }) },
    })
    await chatStream('sess-001', 'hello')
    const body = JSON.parse(global.fetch.mock.calls[0][1].body)
    expect(body.agent_name).toBeUndefined()
  })

  it('test_chat_stream_with_agent_name_includes_it 传入 agentName 时请求体包含 agent_name', async () => {
    const { chatStream } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      body: { getReader: () => ({ read: async () => ({ done: true }) }) },
    })
    await chatStream('sess-001', 'hello', [], null, 'map_agent')
    const body = JSON.parse(global.fetch.mock.calls[0][1].body)
    expect(body.agent_name).toBe('map_agent')
  })

  // 2026-07-01 新增：context_overrides 通道 + project_id 显式传递
  it('test_chat_stream_default_includes_context_overrides_with_empty_geometry 默认请求体含 context_overrides.geometry_data 为 {}', async () => {
    const { chatStream } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      body: { getReader: () => ({ read: async () => ({ done: true }) }) },
    })
    await chatStream('sess-001', 'hello')
    const body = JSON.parse(global.fetch.mock.calls[0][1].body)
    expect(body.context_overrides).toBeDefined()
    expect(body.context_overrides.geometry_data).toEqual({})
  })

  it('test_chat_stream_with_project_id_includes_it_in_context_overrides 传入 projectId 时写入 context_overrides.project_id', async () => {
    const { chatStream } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      body: { getReader: () => ({ read: async () => ({ done: true }) }) },
    })
    await chatStream('sess-001', 'hello', [], null, 'map_agent', 42)
    const body = JSON.parse(global.fetch.mock.calls[0][1].body)
    expect(body.context_overrides).toBeDefined()
    expect(body.context_overrides.project_id).toBe(42)
    // geometry_data 仍保留
    expect(body.context_overrides.geometry_data).toEqual({})
  })

  it('test_chat_stream_omits_project_id_when_null 不传 projectId 时 context_overrides 不含 project_id 键', async () => {
    const { chatStream } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      body: { getReader: () => ({ read: async () => ({ done: true }) }) },
    })
    await chatStream('sess-001', 'hello')
    const body = JSON.parse(global.fetch.mock.calls[0][1].body)
    expect(body.context_overrides).toBeDefined()
    expect('project_id' in body.context_overrides).toBe(false)
  })

  it('test_chat_stream_top_level_geometry_data_removed 顶层不再含 geometry_data 字段', async () => {
    const { chatStream } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      body: { getReader: () => ({ read: async () => ({ done: true }) }) },
    })
    await chatStream('sess-001', 'hello')
    const body = JSON.parse(global.fetch.mock.calls[0][1].body)
    expect(body.geometry_data).toBeUndefined()
  })

  it('test_knowledge_chat_stream_with_project_id_includes_it_in_context_overrides knowledgeChatStream 传入 projectId 时写入 context_overrides.project_id', async () => {
    const { knowledgeChatStream } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      body: { getReader: () => ({ read: async () => ({ done: true }) }) },
    })
    await knowledgeChatStream('sess-002', 'hi', [], null, 7)
    const url = global.fetch.mock.calls[0][0]
    const body = JSON.parse(global.fetch.mock.calls[0][1].body)
    expect(url).toBe('/api/map/knowledge-chat')
    expect(body.context_overrides).toBeDefined()
    expect(body.context_overrides.project_id).toBe(7)
  })

  it('test_knowledge_chat_stream_omits_project_id_when_null knowledgeChatStream 不传 projectId 时 context_overrides 不含 project_id 键', async () => {
    const { knowledgeChatStream } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      body: { getReader: () => ({ read: async () => ({ done: true }) }) },
    })
    await knowledgeChatStream('sess-002', 'hi')
    const body = JSON.parse(global.fetch.mock.calls[0][1].body)
    expect(body.context_overrides).toBeDefined()
    expect('project_id' in body.context_overrides).toBe(false)
  })
})
