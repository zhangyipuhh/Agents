/**
 * triggerRegistry 测试（2026-07-26 新增）
 *
 * 覆盖：
 *   - TRIGGER_REGISTRY 注册项契约（id/char/title 必填）
 *   - searchTriggerByChar / searchTriggerById
 *   - buildOverridesFor 输出 context_overrides 片段结构
 *   - fetchServerItems 拍平 user-server tree + 仅保留 node_type='server' + 去重
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const mockFetchUserServerTree = vi.fn()

vi.mock('../api.js', () => ({
  fetchUserServerTree: (...args) => mockFetchUserServerTree(...args),
}))

describe('triggerRegistry 触发器注册表', () => {
  beforeEach(() => {
    mockFetchUserServerTree.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // ============== 注册表契约 ==============

  it('test_registry_has_server_entry TRIGGER_REGISTRY 应包含 server 条目', async () => {
    const { TRIGGER_REGISTRY } = await import('../triggerRegistry.js')
    const server = TRIGGER_REGISTRY.find((t) => t.id === 'server')
    expect(server).toBeDefined()
    expect(server.char).toBe('#')
    expect(typeof server.title).toBe('string')
    expect(typeof server.fetchItems).toBe('function')
    expect(typeof server.itemKey).toBe('function')
    expect(typeof server.buildOverrides).toBe('function')
  })

  it('test_registry_entries_have_required_fields 所有注册条目必须有 id/char/title/fetchItems/buildOverrides', async () => {
    const { TRIGGER_REGISTRY } = await import('../triggerRegistry.js')
    for (const t of TRIGGER_REGISTRY) {
      expect(typeof t.id).toBe('string')
      expect(t.id.length).toBeGreaterThan(0)
      expect(typeof t.char).toBe('string')
      expect(t.char.length).toBe(1)
      expect(typeof t.title).toBe('string')
      expect(typeof t.fetchItems).toBe('function')
      expect(typeof t.buildOverrides).toBe('function')
    }
  })

  // ============== searchTriggerByChar / searchTriggerById ==============

  it('test_search_trigger_by_char_finds_hash 通过 char=# 找到 server 条目', async () => {
    const { searchTriggerByChar } = await import('../triggerRegistry.js')
    const t = searchTriggerByChar('#')
    expect(t?.id).toBe('server')
  })

  it('test_search_trigger_by_char_unknown_returns_undefined 未注册字符返回 undefined', async () => {
    const { searchTriggerByChar } = await import('../triggerRegistry.js')
    expect(searchTriggerByChar('@')).toBeUndefined()
    expect(searchTriggerByChar('$')).toBeUndefined()
    expect(searchTriggerByChar('/')).toBeUndefined() // "/" 由 commandRegistry 管理
  })

  it('test_search_trigger_by_id_finds_entry 通过 id 查找注册条目', async () => {
    const { searchTriggerById } = await import('../triggerRegistry.js')
    expect(searchTriggerById('server')?.char).toBe('#')
    expect(searchTriggerById('nonexistent')).toBeUndefined()
  })

  // ============== fetchServerItems ==============

  it('test_fetch_server_items_filters_non_server_nodes 仅保留 node_type=server 的节点', async () => {
    mockFetchUserServerTree.mockResolvedValueOnce({
      nodes: [
        { id: 1, node_type: 'folder', name: '生产' },
        { id: 2, node_type: 'server', business_name: 'prod-api', server_type: 'linux' },
        { id: 3, node_type: 'folder', name: '测试' },
      ],
    })
    const { TRIGGER_REGISTRY } = await import('../triggerRegistry.js')
    const server = TRIGGER_REGISTRY.find((t) => t.id === 'server')
    const items = await server.fetchItems()
    expect(items).toHaveLength(1)
    expect(items[0].business_name).toBe('prod-api')
  })

  it('test_fetch_server_items_dedupes_by_business_name 重复 business_name 去重（保留首次出现）', async () => {
    mockFetchUserServerTree.mockResolvedValueOnce({
      nodes: [
        { id: 1, node_type: 'server', business_name: 'prod-api', server_type: 'linux' },
        { id: 2, node_type: 'server', business_name: 'prod-api', server_type: 'linux' },
        { id: 3, node_type: 'server', business_name: 'win-01', server_type: 'windows' },
      ],
    })
    const { TRIGGER_REGISTRY } = await import('../triggerRegistry.js')
    const server = TRIGGER_REGISTRY.find((t) => t.id === 'server')
    const items = await server.fetchItems()
    expect(items).toHaveLength(2)
    expect(items.map((i) => i.business_name)).toEqual(['prod-api', 'win-01'])
  })

  it('test_fetch_server_items_handles_empty_tree tree 为空时返回空数组', async () => {
    mockFetchUserServerTree.mockResolvedValueOnce({ nodes: [] })
    const { TRIGGER_REGISTRY } = await import('../triggerRegistry.js')
    const server = TRIGGER_REGISTRY.find((t) => t.id === 'server')
    const items = await server.fetchItems()
    expect(items).toEqual([])
  })

  it('test_fetch_server_items_handles_non_array_response nodes 非数组时安全降级', async () => {
    mockFetchUserServerTree.mockResolvedValueOnce({ nodes: null })
    const { TRIGGER_REGISTRY } = await import('../triggerRegistry.js')
    const server = TRIGGER_REGISTRY.find((t) => t.id === 'server')
    const items = await server.fetchItems()
    expect(items).toEqual([])
  })

  it('test_fetch_server_items_handles_plain_array_response 直接返回数组时兼容兜底', async () => {
    mockFetchUserServerTree.mockResolvedValueOnce([
      { id: 1, node_type: 'folder', name: '生产' },
      { id: 2, node_type: 'server', business_name: 'prod-api', server_type: 'linux' },
    ])
    const { TRIGGER_REGISTRY } = await import('../triggerRegistry.js')
    const server = TRIGGER_REGISTRY.find((t) => t.id === 'server')
    const items = await server.fetchItems()
    expect(items).toHaveLength(1)
    expect(items[0].business_name).toBe('prod-api')
  })

  it('test_fetch_server_items_skips_entries_without_business_name 缺 business_name 的 server 节点被跳过', async () => {
    mockFetchUserServerTree.mockResolvedValueOnce({
      nodes: [
        { id: 1, node_type: 'server', business_name: '', server_type: 'linux' },
        { id: 2, node_type: 'server', server_type: 'linux' }, // 缺 business_name
        { id: 3, node_type: 'server', business_name: 'prod-api', server_type: 'linux' },
      ],
    })
    const { TRIGGER_REGISTRY } = await import('../triggerRegistry.js')
    const server = TRIGGER_REGISTRY.find((t) => t.id === 'server')
    const items = await server.fetchItems()
    expect(items.map((i) => i.business_name)).toEqual(['prod-api'])
  })

  // ============== buildOverridesFor ==============

  it('test_build_overrides_for_server_outputs_referenced_servers server 触发器 buildOverrides 输出 referenced_servers', async () => {
    const { buildOverridesFor } = await import('../triggerRegistry.js')
    const items = [
      { business_name: 'prod-api', server_type: 'linux' },
      { business_name: 'win-01', server_type: 'windows' },
    ]
    const overrides = buildOverridesFor('server', items)
    expect(overrides).toEqual({
      referenced_servers: [
        { name: 'prod-api', server_type: 'linux' },
        { name: 'win-01', server_type: 'windows' },
      ],
    })
  })

  it('test_build_overrides_for_empty_items_returns_empty_object 选中项为空时返回空对象', async () => {
    const { buildOverridesFor } = await import('../triggerRegistry.js')
    expect(buildOverridesFor('server', [])).toEqual({})
    expect(buildOverridesFor('server', null)).toEqual({})
  })

  it('test_build_overrides_for_unknown_trigger_returns_empty_object 未注册的 trigger id 返回空对象', async () => {
    const { buildOverridesFor } = await import('../triggerRegistry.js')
    expect(buildOverridesFor('nonexistent', [{ x: 1 }])).toEqual({})
  })
})