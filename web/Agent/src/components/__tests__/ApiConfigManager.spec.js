/**
 * ApiConfigManager 组件测试
 *
 * 覆盖：
 *  - 树渲染（文件夹 / 接口节点、method 徽标）、搜索过滤
 *  - 新建文件夹 / 新建接口（选中文件夹下创建）、inline 重命名
 *  - 删除接口节点；删除非空文件夹时展示后端 400 提示
 *  - 点击接口节点加载配置（method / URL 回填）
 *  - 子 Tab 切换（Params / Body / Headers / Mock）
 *  - Body 类型切换（none 空态 / JSON textarea / form-data 表格）
 *  - Params 与 Mock 规则增删
 *  - 保存配置调用 PUT 且 expectations 规范化
 *  - 发送结果展示（状态码 / 耗时 / 校验徽标 / 断言明细 / 响应体预览 / 网络错误）
 *  - 工具栏：搜索框放大镜图标；新建 `+` 触发器与弹出菜单（开关、菜单项触发 createNode）
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ApiConfigManager from '../ApiConfigManager.vue'

const mockNodes = [
  { id: 1, parent_id: null, node_type: 'folder', name: '用户模块', sort_order: 0 },
  { id: 2, parent_id: 1, node_type: 'api', name: '创建用户', sort_order: 0 },
  { id: 3, parent_id: null, node_type: 'api', name: '更新配置', sort_order: 1 },
]

const mockConfigNode2 = {
  id: 10,
  node_id: 2,
  method: 'POST',
  url: 'https://api.example.com/users',
  params: [{ name: 'debug', value: '1', description: '调试开关' }],
  headers: [{ name: 'Content-Type', value: 'application/json', description: '' }],
  body_type: 'json',
  body_content: '{"name":"x"}',
  form_fields: [],
  expectations: [{ type: 'status_code', operator: 'eq', value: 200 }],
}

const mockConfigNode3 = {
  id: 11,
  node_id: 3,
  method: 'PUT',
  url: 'https://api.example.com/config',
  params: [],
  headers: [],
  body_type: 'none',
  body_content: '',
  form_fields: [],
  expectations: [],
}

const mockSendResult = {
  run_id: 5,
  http_status: 200,
  duration_ms: 123,
  response_body: '{"ok":true}',
  check_passed: true,
  assertion_results: [{ rule: 'status_code eq 200', passed: true, detail: '实际 200' }],
  error_message: null,
}

const mockRuns = [
  {
    id: 5,
    http_status: 200,
    duration_ms: 123,
    check_passed: true,
    response_excerpt: '{"ok":true}',
    error_message: null,
    created_at: '2026-07-20T10:00:00',
  },
]

function jsonResponse(data, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => data }
}

function setupFetchMock() {
  global.fetch = vi.fn(async (url, opts = {}) => {
    const method = (opts.method || 'GET').toUpperCase()
    const u = typeof url === 'string' ? url : url.url
    if (u === '/api/admin/api-configs/tree' && method === 'GET') return jsonResponse({ nodes: mockNodes })
    if (u === '/api/admin/api-configs/nodes' && method === 'POST') {
      const body = JSON.parse(opts.body)
      return jsonResponse({ id: 99, sort_order: 0, ...body }, 201)
    }
    if (u === '/api/admin/api-configs/nodes/2/config' && method === 'GET') return jsonResponse(mockConfigNode2)
    if (u === '/api/admin/api-configs/nodes/2/config' && method === 'PUT') {
      return jsonResponse({ ...mockConfigNode2, ...JSON.parse(opts.body) })
    }
    if (u === '/api/admin/api-configs/nodes/3/config' && method === 'GET') return jsonResponse(mockConfigNode3)
    if (u === '/api/admin/api-configs/nodes/2/send' && method === 'POST') return jsonResponse(mockSendResult)
    if (u.startsWith('/api/admin/api-configs/nodes/2/runs')) return jsonResponse({ runs: mockRuns })
    if (u.startsWith('/api/admin/api-configs/nodes/3/runs')) return jsonResponse({ runs: [] })
    if (u === '/api/admin/api-configs/nodes/3' && method === 'DELETE') return jsonResponse({ ok: true })
    if (u === '/api/admin/api-configs/nodes/1' && method === 'DELETE') {
      return jsonResponse({ detail: '文件夹非空，无法删除' }, 400)
    }
    if (u === '/api/admin/api-configs/nodes/99' && method === 'PUT') {
      return jsonResponse({ id: 99, parent_id: null, node_type: 'api', sort_order: 0, ...JSON.parse(opts.body) })
    }
    return jsonResponse({})
  })
}

/**
 * 挂载组件并等待树加载完成。
 * @returns {Promise<import('@vue/test-utils').VueWrapper>} 组件包装器
 */
async function mountManager() {
  const wrapper = mount(ApiConfigManager)
  await flushPromises()
  return wrapper
}

describe('ApiConfigManager 组件', () => {
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
    expect(ApiConfigManager).toBeDefined()
  })

  it('test_tree_renders_nodes 渲染文件夹与接口节点', async () => {
    const wrapper = await mountManager()

    expect(wrapper.find('[data-testid="api-tree"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('用户模块')
    expect(wrapper.text()).toContain('创建用户')
    expect(wrapper.text()).toContain('更新配置')
    // method 徽标（后台拉取配置后填充）
    expect(wrapper.text()).toContain('POST')
    expect(wrapper.text()).toContain('PUT')
  })

  it('test_search_filters_tree 搜索按名称过滤', async () => {
    const wrapper = await mountManager()

    await wrapper.find('[data-testid="api-tree-search"]').setValue('更新')
    await flushPromises()

    expect(wrapper.text()).toContain('更新配置')
    expect(wrapper.text()).not.toContain('创建用户')
    expect(wrapper.text()).not.toContain('用户模块')
  })

  it('test_create_folder_posts_node 新建文件夹调用 POST 并进入重命名', async () => {
    const wrapper = await mountManager()

    // 先点开「+」弹出菜单
    await wrapper.find('[data-testid="api-new-trigger"]').trigger('click')
    await flushPromises()
    // 再点菜单项「新建文件夹」
    await wrapper.find('[data-testid="api-new-folder"]').trigger('click')
    await flushPromises()

    const postCall = global.fetch.mock.calls.find(
      ([url, opts]) => url === '/api/admin/api-configs/nodes' && opts.method === 'POST'
    )
    expect(postCall).toBeTruthy()
    const body = JSON.parse(postCall[1].body)
    expect(body.node_type).toBe('folder')
    expect(body.parent_id).toBe(null)
    // 创建成功后进入 inline 重命名
    expect(wrapper.find('[data-testid="rename-input"]').exists()).toBe(true)
  })

  it('test_create_api_under_selected_folder 在选中文件夹下新建接口', async () => {
    const wrapper = await mountManager()

    // 点击文件夹节点使其成为选中节点
    await wrapper.find('[data-testid="tree-node-1"]').trigger('click')
    await flushPromises()
    // 先点开「+」弹出菜单
    await wrapper.find('[data-testid="api-new-trigger"]').trigger('click')
    await flushPromises()
    // 再点菜单项「新建接口」
    await wrapper.find('[data-testid="api-new-api"]').trigger('click')
    await flushPromises()

    const postCall = global.fetch.mock.calls.find(
      ([url, opts]) => url === '/api/admin/api-configs/nodes' && opts.method === 'POST'
    )
    expect(postCall).toBeTruthy()
    const body = JSON.parse(postCall[1].body)
    expect(body.node_type).toBe('api')
    expect(body.parent_id).toBe(1)
  })

  it('test_rename_node_calls_put 重命名提交调用 PUT', async () => {
    const wrapper = await mountManager()

    await wrapper.find('[data-testid="node-rename-3"]').trigger('click')
    await flushPromises()
    const input = wrapper.find('[data-testid="rename-input"]')
    await input.setValue('更新系统配置')
    await input.trigger('keydown.enter')
    await flushPromises()

    const putCall = global.fetch.mock.calls.find(
      ([url, opts]) => url === '/api/admin/api-configs/nodes/3' && opts.method === 'PUT'
    )
    expect(putCall).toBeTruthy()
    expect(JSON.parse(putCall[1].body).name).toBe('更新系统配置')
    expect(wrapper.text()).toContain('更新系统配置')
  })

  it('test_delete_api_node_calls_delete 删除接口节点调用 DELETE', async () => {
    const wrapper = await mountManager()

    await wrapper.find('[data-testid="node-delete-3"]').trigger('click')
    await flushPromises()

    const delCall = global.fetch.mock.calls.find(
      ([url, opts]) => url === '/api/admin/api-configs/nodes/3' && opts.method === 'DELETE'
    )
    expect(delCall).toBeTruthy()
    expect(wrapper.text()).not.toContain('更新配置')
  })

  it('test_delete_nonempty_folder_shows_error 删除非空文件夹展示后端 400 提示', async () => {
    const wrapper = await mountManager()

    await wrapper.find('[data-testid="node-delete-1"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="api-tree-error"]').text()).toContain('文件夹非空，无法删除')
    // 文件夹仍在树中
    expect(wrapper.text()).toContain('用户模块')
  })

  it('test_click_api_loads_config 点击接口节点加载配置', async () => {
    const wrapper = await mountManager()

    await wrapper.find('[data-testid="tree-node-2"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="api-method"]').element.value).toBe('POST')
    expect(wrapper.find('[data-testid="api-url"]').element.value).toBe('https://api.example.com/users')
    // Params 表格回填（行内容为 input，需断言 value 而非 text）
    const paramValues = wrapper.findAll('[data-testid="params-table"] tbody input').map((i) => i.element.value)
    expect(paramValues).toContain('调试开关')
    // 空态消失
    expect(wrapper.find('[data-testid="api-detail-empty"]').exists()).toBe(false)
  })

  it('test_subtab_switching 子 Tab 切换', async () => {
    const wrapper = await mountManager()
    await wrapper.find('[data-testid="tree-node-2"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="panel-params"]').exists()).toBe(true)

    await wrapper.find('[data-testid="subtab-body"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="panel-body"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="panel-params"]').exists()).toBe(false)

    await wrapper.find('[data-testid="subtab-headers"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="panel-headers"]').exists()).toBe(true)
    const headerValues = wrapper.findAll('[data-testid="headers-table"] tbody input').map((i) => i.element.value)
    expect(headerValues).toContain('Content-Type')

    await wrapper.find('[data-testid="subtab-mock"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="panel-mock"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="mock-rules"]').exists()).toBe(true)
  })

  it('test_body_type_switching Body 类型切换', async () => {
    const wrapper = await mountManager()
    await wrapper.find('[data-testid="tree-node-2"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-testid="subtab-body"]').trigger('click')
    await flushPromises()

    // 配置 body_type=json → 显示 textarea
    expect(wrapper.find('[data-testid="body-content"]').exists()).toBe(true)

    // 切到 none → 空态
    await wrapper.find('[data-testid="body-type-none"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="body-none"]').text()).toContain('该请求没有 Body')
    expect(wrapper.find('[data-testid="body-content"]').exists()).toBe(false)

    // 切到 form-data → key-value 表格
    await wrapper.find('[data-testid="body-type-form-data"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="form-fields-table"]').exists()).toBe(true)
  })

  it('test_params_add_and_remove 参数行增删', async () => {
    const wrapper = await mountManager()
    await wrapper.find('[data-testid="tree-node-2"]').trigger('click')
    await flushPromises()

    // 初始 1 行（debug）
    expect(wrapper.findAll('[data-testid="params-table"] tbody tr').length).toBe(1)

    await wrapper.find('[data-testid="param-add"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[data-testid="params-table"] tbody tr').length).toBe(2)

    await wrapper.find('[data-testid="param-remove-0"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[data-testid="params-table"] tbody tr').length).toBe(1)
  })

  it('test_mock_rule_add_and_remove Mock 规则增删', async () => {
    const wrapper = await mountManager()
    await wrapper.find('[data-testid="tree-node-2"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-testid="subtab-mock"]').trigger('click')
    await flushPromises()

    // 初始 1 条（status_code eq 200）
    expect(wrapper.findAll('[data-testid^="mock-rule-"]').filter((el) => el.attributes('data-testid').match(/^mock-rule-\d+$/)).length).toBe(1)

    await wrapper.find('[data-testid="mock-add"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="mock-rule-1"]').exists()).toBe(true)

    await wrapper.find('[data-testid="mock-rule-remove-0"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="mock-rule-1"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="mock-rule-0"]').exists()).toBe(true)
  })

  it('test_save_config_calls_put 保存配置调用 PUT 并规范化 expectations', async () => {
    const wrapper = await mountManager()
    await wrapper.find('[data-testid="tree-node-2"]').trigger('click')
    await flushPromises()

    // 修改 URL 触发 dirty
    await wrapper.find('[data-testid="api-url"]').setValue('https://api.example.com/v2/users')
    await wrapper.find('[data-testid="api-save-btn"]').trigger('click')
    await flushPromises()

    const putCall = global.fetch.mock.calls.find(
      ([url, opts]) => url === '/api/admin/api-configs/nodes/2/config' && opts.method === 'PUT'
    )
    expect(putCall).toBeTruthy()
    const body = JSON.parse(putCall[1].body)
    expect(body.url).toBe('https://api.example.com/v2/users')
    expect(body.method).toBe('POST')
    expect(body.body_type).toBe('json')
    expect(body.expectations).toEqual([{ type: 'status_code', operator: 'eq', value: 200 }])
    expect(wrapper.find('[data-testid="api-detail-message"]').text()).toContain('配置已保存')
  })

  it('test_send_shows_result 发送后展示结果区', async () => {
    const wrapper = await mountManager()
    await wrapper.find('[data-testid="tree-node-2"]').trigger('click')
    await flushPromises()

    await wrapper.find('[data-testid="api-send-btn"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="send-status"]').text()).toContain('200')
    expect(wrapper.find('[data-testid="send-duration"]').text()).toContain('123')
    expect(wrapper.find('[data-testid="send-check-badge"]').text()).toContain('正常')
    expect(wrapper.find('[data-testid="assertion-0"]').text()).toContain('status_code eq 200')
    expect(wrapper.find('[data-testid="response-preview"]').text()).toContain('{"ok":true}')
    // 发送历史刷新
    expect(wrapper.find('[data-testid="runs-list"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="run-5"]').exists()).toBe(true)
  })

  it('test_send_network_error_shows_message 发送网络错误展示 error_message', async () => {
    const wrapper = await mountManager()
    await wrapper.find('[data-testid="tree-node-2"]').trigger('click')
    await flushPromises()

    global.fetch = vi.fn(async (url, opts = {}) => {
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/api-configs/nodes/2/send') {
        return jsonResponse({ detail: '连接目标服务器失败' }, 502)
      }
      if (u.startsWith('/api/admin/api-configs/nodes/2/runs')) return jsonResponse({ runs: [] })
      return jsonResponse({})
    })

    await wrapper.find('[data-testid="api-send-btn"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="send-error"]').text()).toContain('连接目标服务器失败')
    expect(wrapper.find('[data-testid="send-check-badge"]').text()).toContain('异常')
  })

  it('test_toolbar_has_search_icon_and_new_trigger 工具栏呈现单行布局,搜索框带放大镜,+ 触发器存在', async () => {
    const wrapper = await mountManager()

    // 搜索框存在并带放大镜图标
    const search = wrapper.find('[data-testid="api-tree-search"]')
    expect(search.exists()).toBe(true)
    // 放大镜图标作为兄弟节点存在（.acm-search-icon）
    const toolbar = wrapper.find('.acm-toolbar')
    expect(toolbar.find('.acm-search-icon').exists()).toBe(true)
    // + 触发器存在
    const trigger = wrapper.find('[data-testid="api-new-trigger"]')
    expect(trigger.exists()).toBe(true)
    // 旧的两个独立按钮不再独立存在（被合并进菜单）
    // 菜单初始关闭
    expect(wrapper.find('[data-testid="api-new-menu"]').exists()).toBe(false)
  })

  it('test_new_menu_opens_and_closes 点击 + 触发器打开/关闭弹出菜单,菜单项触发 createNode', async () => {
    const wrapper = await mountManager()

    // 初始菜单隐藏
    expect(wrapper.find('[data-testid="api-new-menu"]').exists()).toBe(false)

    // 点击 + 打开菜单
    await wrapper.find('[data-testid="api-new-trigger"]').trigger('click')
    await flushPromises()
    const menu = wrapper.find('[data-testid="api-new-menu"]')
    expect(menu.exists()).toBe(true)
    // 菜单包含「新建文件夹」与「新建接口」两项
    expect(menu.text()).toContain('新建文件夹')
    expect(menu.text()).toContain('新建接口')
    expect(menu.findAll('[data-testid="api-new-folder"]').length).toBe(1)
    expect(menu.findAll('[data-testid="api-new-api"]').length).toBe(1)

    // 再次点击 + 关闭菜单
    await wrapper.find('[data-testid="api-new-trigger"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="api-new-menu"]').exists()).toBe(false)

    // 打开菜单后点击「新建文件夹」菜单项 → 触发 POST 并自动关闭菜单
    await wrapper.find('[data-testid="api-new-trigger"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-testid="api-new-folder"]').trigger('click')
    await flushPromises()

    const postCall = global.fetch.mock.calls.find(
      ([url, opts]) => url === '/api/admin/api-configs/nodes' && opts.method === 'POST'
    )
    expect(postCall).toBeTruthy()
    expect(JSON.parse(postCall[1].body).node_type).toBe('folder')
    // 菜单已自动关闭
    expect(wrapper.find('[data-testid="api-new-menu"]').exists()).toBe(false)
  })

  it('test_new_menu_closes_on_outside_click 点击工具栏外区域关闭菜单', async () => {
    const wrapper = await mountManager()

    // 打开菜单
    await wrapper.find('[data-testid="api-new-trigger"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="api-new-menu"]').exists()).toBe(true)

    // 直接在 document 上派发 click,target 指向工具栏外部(tree 区域),
    // 模拟「点击工具栏外区域」的真实 DOM 行为（vue-test-utils 的 trigger 不会冒泡到 document）
    const outsideTarget = wrapper.find('[data-testid="api-tree"]').element
    const outsideEvent = new MouseEvent('click', { bubbles: true })
    Object.defineProperty(outsideEvent, 'target', { value: outsideTarget, configurable: true })
    document.dispatchEvent(outsideEvent)
    await flushPromises()
    expect(wrapper.find('[data-testid="api-new-menu"]').exists()).toBe(false)
  })

  it('test_new_menu_closes_on_escape 按 Esc 关闭菜单', async () => {
    const wrapper = await mountManager()

    // 打开菜单
    await wrapper.find('[data-testid="api-new-trigger"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="api-new-menu"]').exists()).toBe(true)

    // 全局派发 Esc 键事件
    const escapeEvent = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })
    document.dispatchEvent(escapeEvent)
    await flushPromises()
    expect(wrapper.find('[data-testid="api-new-menu"]').exists()).toBe(false)
  })
})
