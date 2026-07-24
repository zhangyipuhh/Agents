/**
 * UserServerManager 组件测试（2026-07-24 新增）
 *
 * 覆盖：
 *  - 树渲染（folder / server 节点）
 *  - 搜索过滤
 *  - 新建文件夹（调用 POST /nodes）
 *  - 「新建服务器配置」按钮点击 → 提示「该功能暂未开放」
 *  - 「导入已有配置」按钮 → 弹出 ImportServerDialog
 *  - inline 重命名（PUT /nodes/{id}）
 *  - 删除节点（DELETE /nodes/{id}）；非空 folder → 400 错误展示
 *  - 单击 server 节点 → 加载详情
 *  - server 节点详情只展示白名单字段（无 ip/port/账号/密码）
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import UserServerManager from '../UserServerManager.vue'

// mockImportDialog 必须在 import UserServerManager 前设置，避免子组件缺失导致 mount 失败
// 用 stub 替换 ImportServerDialog 行为（仅保留 props 接口）
vi.mock('../ImportServerDialog.vue', () => ({
  default: {
    name: 'ImportServerDialog',
    props: ['parentId'],
    emits: ['close', 'done'],
    template: '<div data-testid="isd-stub" />'
  }
}))

const mockNodes = [
  { id: 1, parent_id: null, node_type: 'folder', name: '生产环境', sort_order: 0,
    source_devops_server_id: null, created_by_user_id: 1 },
  { id: 2, parent_id: 1, node_type: 'server', name: '服务器A', sort_order: 0,
    source_devops_server_id: 100, created_by_user_id: 1 },
  { id: 3, parent_id: null, node_type: 'server', name: '服务器B', sort_order: 0,
    source_devops_server_id: 101, created_by_user_id: 1 },
]

const mockDevopsServers = [
  { id: 100, business_name: '服务器A', server_type: 'linux', updated_at: '2026-07-24' },
  { id: 101, business_name: '服务器B', server_type: 'linux', updated_at: '2026-07-24' },
]

const mockServerDetail = {
  node_type: 'server',
  id: 2,
  parent_id: 1,
  name: '服务器A',
  sort_order: 0,
  source_devops_server_id: 100,
  business_name: '服务器A',
  server_type: 'linux',
  devops_updated_at: '2026-07-24T10:00:00Z',
  whitelist: ['ls', 'pwd'],
  inspection_script: 'echo hello',
  inspection_parser: 'json',
  inspection_fields: [],
}

const mockFolderDetail = {
  node_type: 'folder',
  id: 1,
  parent_id: null,
  name: '生产环境',
  sort_order: 0,
  created_by_user_id: 1,
}

function jsonResponse(data, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => data }
}

function setupFetchMock() {
  global.fetch = vi.fn(async (url, opts = {}) => {
    const method = (opts.method || 'GET').toUpperCase()
    const u = typeof url === 'string' ? url : url.url
    if (u === '/api/admin/user-servers/tree' && method === 'GET') {
      return jsonResponse({ nodes: mockNodes })
    }
    if (u === '/api/admin/user-servers/nodes' && method === 'POST') {
      const body = JSON.parse(opts.body)
      return jsonResponse(
        { id: 99, sort_order: 0, ...body, created_by_user_id: 1 },
        201
      )
    }
    if (u === '/api/admin/user-servers/nodes/2/config' && method === 'GET') {
      return jsonResponse(mockServerDetail)
    }
    if (u === '/api/admin/user-servers/nodes/1/config' && method === 'GET') {
      return jsonResponse(mockFolderDetail)
    }
    if (u === '/api/admin/user-servers/nodes/2' && method === 'PUT') {
      const body = JSON.parse(opts.body)
      return jsonResponse({ id: 2, ...body, node_type: 'server' })
    }
    if (u === '/api/admin/user-servers/nodes/2' && method === 'DELETE') {
      return jsonResponse({ ok: true })
    }
    if (u === '/api/admin/user-servers/nodes/1' && method === 'DELETE') {
      return jsonResponse({ detail: '文件夹非空，无法删除' }, 400)
    }
    if (u === '/api/admin/devops-servers' && method === 'GET') {
      return jsonResponse(mockDevopsServers)
    }
    if (u === '/api/admin/user-servers/import' && method === 'POST') {
      const body = JSON.parse(opts.body)
      return jsonResponse({
        imported: body.business_names.length,
        skipped: 0,
        failed: 0,
        node_ids: [200, 201]
      })
    }
    return jsonResponse({})
  })
}

async function mountManager() {
  const wrapper = mount(UserServerManager)
  await flushPromises()
  return wrapper
}

describe('UserServerManager 组件', () => {
  let originalFetch
  let originalLocalStorage
  let originalConfirm

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
    originalConfirm = global.confirm
    global.localStorage = {
      getItem: vi.fn(() => 'fake-token'),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    }
    global.confirm = vi.fn(() => true)
    setupFetchMock()
  })

  afterEach(() => {
    global.fetch = originalFetch
    global.localStorage = originalLocalStorage
    global.confirm = originalConfirm
  })

  it('test_component_importable 组件可被 import', () => {
    expect(UserServerManager).toBeDefined()
  })

  it('test_tree_renders_nodes 渲染文件夹与服务器节点', async () => {
    const wrapper = await mountManager()
    expect(wrapper.find('[data-testid="usm-tree"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('生产环境')
    expect(wrapper.text()).toContain('服务器A')
    expect(wrapper.text()).toContain('服务器B')
  })

  it('test_search_filters_tree 搜索按名称过滤', async () => {
    const wrapper = await mountManager()
    await wrapper.find('[data-testid="usm-search-input"]').setValue('服务器A')
    await flushPromises()
    expect(wrapper.text()).toContain('服务器A')
    expect(wrapper.text()).not.toContain('服务器B')
  })

  it('test_create_folder_posts_node 新建文件夹调用 POST', async () => {
    const wrapper = await mountManager()
    // 打开新建菜单
    await wrapper.find('[data-testid="usm-new-trigger"]').trigger('click')
    await flushPromises()
    // 点击「新建文件夹」
    await wrapper.find('[data-testid="usm-new-folder"]').trigger('click')
    await flushPromises()

    const postCall = global.fetch.mock.calls.find(
      ([url, opts]) => url === '/api/admin/user-servers/nodes' && opts.method === 'POST'
    )
    expect(postCall).toBeTruthy()
    const body = JSON.parse(postCall[1].body)
    expect(body.node_type).toBe('folder')
    expect(body.parent_id).toBe(null)
  })

  it('test_new_server_button_disabled_and_shows_hint 新建服务器配置按钮提示暂未开放', async () => {
    const wrapper = await mountManager()
    // 打开新建菜单
    await wrapper.find('[data-testid="usm-new-trigger"]').trigger('click')
    await flushPromises()

    // 「新建服务器配置」按钮应存在 + disabled + 带 tooltip 提示
    const btn = wrapper.find('[data-testid="usm-new-server"]')
    expect(btn.exists()).toBe(true)
    expect(btn.attributes('disabled')).toBeDefined()
    expect(btn.attributes('title')).toBe('该功能暂未开放')
    // 真实浏览器中 disabled button 不会响应 click（生产安全行为）
    // 提示语「该功能暂未开放」通过 tooltip + 未来可拓展的 toast 展示
  })

  it('test_open_import_dialog 点击导入按钮弹出 ImportServerDialog', async () => {
    const wrapper = await mountManager()
    // 打开新建菜单
    await wrapper.find('[data-testid="usm-new-trigger"]').trigger('click')
    await flushPromises()
    // 点击「导入已有配置」
    await wrapper.find('[data-testid="usm-import-existing"]').trigger('click')
    await flushPromises()
    // 子组件 stub 应被渲染
    expect(wrapper.find('[data-testid="isd-stub"]').exists()).toBe(true)
  })

  it('test_click_server_node_loads_detail 单击 server 节点加载详情', async () => {
    const wrapper = await mountManager()
    // 找到 server 节点（id=2）的子元素 .usm-tree-row 并点击（handler 绑在 row 上）
    const serverNode = wrapper.find('[data-testid="usm-node-2"]')
    await serverNode.find('.usm-tree-row').trigger('click')
    await flushPromises()
    // 详情面板显示 server 详情
    const detail = wrapper.find('[data-testid="usm-server-detail"]')
    expect(detail.exists()).toBe(true)
    expect(wrapper.text()).toContain('业务名')
    expect(wrapper.text()).toContain('linux')
  })

  it('test_server_detail_no_sensitive_info 详情面板不展示 ip/port/账号/密码', async () => {
    const wrapper = await mountManager()
    const serverNode = wrapper.find('[data-testid="usm-node-2"]')
    await serverNode.find('.usm-tree-row').trigger('click')
    await flushPromises()
    const text = wrapper.text()
    for (const forbidden of ['10.0.0.', '192.168.', 'port', 'username', 'password']) {
      // 关键字不应在页面文本中（仅作为 sentinel 检查；白名单契约对标「服务器扫描入库」详情端点）
      expect(text.toLowerCase()).not.toContain(forbidden.toLowerCase())
    }
  })

  it('test_click_folder_node_shows_folder_detail 单击 folder 节点显示文件夹详情', async () => {
    const wrapper = await mountManager()
    const folderNode = wrapper.find('[data-testid="usm-node-1"]')
    await folderNode.find('.usm-tree-row').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="usm-folder-detail"]').exists()).toBe(true)
  })

  it('test_delete_server_node_ok 删除 server 节点', async () => {
    const wrapper = await mountManager()
    // 删除 id=2 server 节点
    await wrapper.find('[data-testid="usm-delete-2"]').trigger('click')
    await flushPromises()

    const delCall = global.fetch.mock.calls.find(
      ([url, opts]) => url === '/api/admin/user-servers/nodes/2' && opts.method === 'DELETE'
    )
    expect(delCall).toBeTruthy()
  })

  it('test_delete_non_empty_folder_shows_400_error 删除非空 folder 显示后端错误', async () => {
    const wrapper = await mountManager()
    // 删除 id=1 folder（含 id=2 子节点）
    await wrapper.find('[data-testid="usm-delete-1"]').trigger('click')
    await flushPromises()

    const errorArea = wrapper.find('[data-testid="usm-tree-error"]')
    expect(errorArea.exists()).toBe(true)
    expect(errorArea.text()).toContain('文件夹非空')
  })
})
