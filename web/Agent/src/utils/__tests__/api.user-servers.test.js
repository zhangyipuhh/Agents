/**
 * 用户服务器管理 API 测试（2026-07-24 新增）
 *
 * 覆盖：树查询、节点 CRUD、详情查询、批量导入。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

describe('用户服务器管理 API', () => {
  let originalFetch
  let originalLocalStorage

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
    global.fetch = vi.fn()
    global.localStorage = {
      getItem: vi.fn((key) => {
        if (key === 'auth_token') return 'fake-token'
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

  it('test_fetch_user_server_tree_calls_correct_url 树查询调用正确地址', async () => {
    const { fetchUserServerTree } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ nodes: [{ id: 1, name: '生产环境', node_type: 'folder' }] })
    })

    const result = await fetchUserServerTree()

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/admin/user-servers/tree',
      expect.objectContaining({ method: 'GET' })
    )
    expect(result.nodes[0].name).toBe('生产环境')
  })

  it('test_create_user_server_folder_node 新建 folder 节点', async () => {
    const { createUserServerNode } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true, status: 201,
      json: async () => ({ id: 99, name: '新建文件夹', node_type: 'folder' })
    })

    const result = await createUserServerNode(null, 'folder', '新建文件夹', null)

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/admin/user-servers/nodes',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          parent_id: null,
          node_type: 'folder',
          name: '新建文件夹',
          source_devops_server_id: null
        })
      })
    )
    expect(result.id).toBe(99)
  })

  it('test_create_user_server_server_node 新建 server 节点带 source_devops_server_id', async () => {
    const { createUserServerNode } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true, status: 201,
      json: async () => ({ id: 100, name: '服务器A', node_type: 'server' })
    })

    await createUserServerNode(1, 'server', '服务器A', 999)

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/admin/user-servers/nodes',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          parent_id: 1,
          node_type: 'server',
          name: '服务器A',
          source_devops_server_id: 999
        })
      })
    )
  })

  it('test_update_user_server_node 更新节点', async () => {
    const { updateUserServerNode } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: 1, name: '新名' })
    })

    await updateUserServerNode(1, { name: '新名' })

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/admin/user-servers/nodes/1',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ name: '新名' })
      })
    )
  })

  it('test_delete_user_server_node 删除节点', async () => {
    const { deleteUserServerNode } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ ok: true })
    })

    const result = await deleteUserServerNode(2)

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/admin/user-servers/nodes/2',
      expect.objectContaining({ method: 'DELETE' })
    )
    expect(result.ok).toBe(true)
  })

  it('test_fetch_user_server_config 获取节点详情', async () => {
    const { fetchUserServerConfig } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ node_type: 'server', business_name: 'X' })
    })

    const result = await fetchUserServerConfig(5)

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/admin/user-servers/nodes/5/config',
      expect.objectContaining({ method: 'GET' })
    )
    expect(result.node_type).toBe('server')
  })

  it('test_import_devops_servers 批量导入', async () => {
    const { importDevopsServers } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ imported: 2, skipped: 0, failed: 0, node_ids: [10, 11] })
    })

    const result = await importDevopsServers(1, ['服务器A', '服务器B'])

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/admin/user-servers/import',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          parent_id: 1,
          business_names: ['服务器A', '服务器B']
        })
      })
    )
    expect(result.imported).toBe(2)
    expect(result.node_ids).toEqual([10, 11])
  })

  it('test_fetch_user_server_tree_error_raises 失败时抛错', async () => {
    const { fetchUserServerTree } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ detail: '服务挂了' })
    })

    await expect(fetchUserServerTree()).rejects.toThrow('服务挂了')
  })
})
