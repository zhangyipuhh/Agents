/**
 * TaskSchedulerManager 组件测试
 *
 * 覆盖：
 *  - 列表渲染、新增表单、保存任务、启停任务、立即运行、执行历史展示
 *  - 默认 Tab 为「编辑任务」
 *  - 切换到「服务器扫描入库」Tab 时按需拉取 /api/admin/devops-servers
 *  - 服务器列表只保留脱敏白名单字段（id / business_name / server_type / updated_at）
 *  - 不渲染 ip / port / username / password / blacklist / whitelist / 文件路径
 *  - 扫描按钮防重复提交
 *  - 扫描成功显示 scanning / loading / success / summary / empty 状态
 *  - 扫描成功后自动刷新服务器列表
 *  - 错误不得把后端敏感详情显示到页面
 *  - 切回任务 Tab 不再触发服务器请求
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import TaskSchedulerManager from '../TaskSchedulerManager.vue'

const mockSchedules = [
  {
    id: 1,
    name: '每日巡检',
    description: '每天检查',
    agent_name: 'map_agent',
    prompt: '检查今日任务',
    cron_expression: '0 9 * * *',
    timezone: 'Asia/Shanghai',
    enabled: true,
    context_overrides: {},
    next_run_at: '2026-07-11T09:00:00',
  },
]

const mockAgents = [
  { name: 'map_agent', display_name: '地图智能体', enabled: true },
  { name: 'disabled_agent', display_name: '禁用智能体', enabled: false },
]

const mockRuns = [
  { id: 7, status: 'success', trigger_type: 'manual', output_text: '执行完成', created_at: '2026-07-10T09:00:00' },
  { id: 8, status: 'failed', trigger_type: 'scheduled', error_message: 'boom', created_at: '2026-07-10T10:00:00' },
]

/**
 * 后端真实会返回的、含敏感字段的原始记录：测试要验证页面不会把这些字段渲染出来。
 */
const rawDevopsServers = [
  {
    id: 1,
    business_name: '业务A-生产',
    server_type: 'production',
    updated_at: '2026-07-15T09:00:00',
    ip: '10.0.0.1',
    port: 22,
    username: 'root',
    password: 'super-secret-password',
    blacklist: '/etc,/var/log',
    whitelist: '/home,/opt',
    file_path: '/srv/secret/host.json',
  },
  {
    id: 2,
    business_name: '业务B-测试',
    server_type: 'staging',
    updated_at: '2026-07-15T10:00:00',
    ip: '10.0.0.2',
    port: 2222,
    username: 'deploy',
    password: 'hidden',
    blacklist: '',
    whitelist: '',
    file_path: '/srv/secret/host2.json',
  },
]

function jsonResponse(data, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => data }
}

function emptyResponse(status = 204) {
  return { ok: true, status, json: async () => ({}) }
}

function setupFetchMock() {
  global.fetch = vi.fn(async (url, opts = {}) => {
    const method = (opts.method || 'GET').toUpperCase()
    const u = typeof url === 'string' ? url : url.url
    if (u === '/api/admin/task-schedules' && method === 'GET') return jsonResponse(mockSchedules)
    if (u === '/api/admin/task-schedules' && method === 'POST') return jsonResponse({ id: 2, ...JSON.parse(opts.body) }, 201)
    if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
    if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
    if (u === '/api/admin/task-schedules/1/enabled' && method === 'PUT') return jsonResponse({ ...mockSchedules[0], enabled: false })
    if (u === '/api/admin/task-schedules/1/trigger' && method === 'POST') return jsonResponse({ id: 9, status: 'pending' }, 202)
    if (u === '/api/admin/task-schedules/1' && method === 'DELETE') return emptyResponse()
    if (u === '/api/admin/task-schedules/1' && method === 'PUT') return jsonResponse({ ...mockSchedules[0], ...JSON.parse(opts.body) })
    if (u === '/api/admin/devops-servers' && method === 'GET') return jsonResponse(rawDevopsServers)
    if (u === '/api/admin/devops-servers/scan' && method === 'POST') {
      return jsonResponse({ scanned: 2, inserted: 1, updated: 1, failed: 0 })
    }
    return jsonResponse({})
  })
}

describe('TaskSchedulerManager 组件', () => {
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
    expect(TaskSchedulerManager).toBeDefined()
  })

  it('test_renders_schedule_list 渲染定时任务列表', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    expect(wrapper.text()).toContain('每日巡检')
    expect(wrapper.text()).toContain('map_agent')
    expect(wrapper.findAll('.task-item').length).toBe(1)
  })

  it('test_new_task_button_shows_form 点击新增任务显示表单', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    const button = wrapper.findAll('button').find((b) => b.text().includes('新增任务'))

    await button.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('保存任务')
    expect(wrapper.find('textarea').exists()).toBe(true)
  })

  it('test_save_new_task_posts_payload 保存新任务调用 POST', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('新增任务')).trigger('click')
    await flushPromises()

    // 任务名称（第一个 input）
    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('周报任务')
    // 执行频率=每周（SCHEDULE_TYPES[1] = weekly）
    await wrapper.find('[data-testid="schedule-type"]').findAll('option')[1].setSelected()
    // 星期几=周一（WEEKDAYS[0] = 周一, value=1）
    await wrapper.find('[data-testid="schedule-weekday"]').findAll('option')[0].setSelected()
    // 时=10（HOURS[10] = 10）
    await wrapper.find('[data-testid="schedule-hour"]').findAll('option')[10].setSelected()
    // 分=0（MINUTES[0] = 0）
    await wrapper.find('[data-testid="schedule-minute"]').findAll('option')[0].setSelected()
    // 目标智能体
    await wrapper
      .find('[data-testid="schedule-agent"]')
      .findAll('option')
      .find((o) => o.text() === '地图智能体（map_agent）')
      .setSelected()
    await wrapper.find('textarea').setValue('生成周报')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    const postCall = global.fetch.mock.calls.find(([url, opts]) => url === '/api/admin/task-schedules' && opts.method === 'POST')
    expect(postCall).toBeTruthy()
    const body = JSON.parse(postCall[1].body)
    expect(body.name).toBe('周报任务')
    // 每周一 10:00 → '0 10 * * 1'
    expect(body.cron_expression).toBe('0 10 * * 1')
  })

  it('test_toggle_task_calls_enabled_api 启停任务调用 enabled API', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('停用任务')).trigger('click')
    await flushPromises()

    const call = global.fetch.mock.calls.find(([url]) => url === '/api/admin/task-schedules/1/enabled')
    expect(call).toBeTruthy()
    expect(JSON.parse(call[1].body).enabled).toBe(false)
  })

  it('test_trigger_task_calls_trigger_api 立即运行调用 trigger API', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('立即运行')).trigger('click')
    await flushPromises()

    const call = global.fetch.mock.calls.find(([url]) => url === '/api/admin/task-schedules/1/trigger')
    expect(call).toBeTruthy()
  })

  it('test_runs_render_success_and_failed_status 渲染执行历史状态', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    expect(wrapper.text()).toContain('success')
    expect(wrapper.text()).toContain('failed')
    expect(wrapper.text()).toContain('执行完成')
    expect(wrapper.text()).toContain('boom')
  })

  it('test_default_tab_is_edit_task 默认 Tab 是「编辑任务」', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    const tablist = wrapper.find('[role="tablist"]')
    expect(tablist.exists()).toBe(true)

    const tabs = tablist.findAll('[role="tab"]')
    expect(tabs.length).toBe(3)
    expect(tabs[0].text()).toContain('编辑任务')
    expect(tabs[1].text()).toContain('服务器扫描入库')
    expect(tabs[2].text()).toContain('脚本扫描入库')

    // 默认激活态：第一个 Tab aria-selected=true
    expect(tabs[0].attributes('aria-selected')).toBe('true')
    expect(tabs[1].attributes('aria-selected')).toBe('false')
    expect(tabs[2].attributes('aria-selected')).toBe('false')

    // 默认显示编辑面板
    expect(wrapper.find('[role="tabpanel"]').exists()).toBe(true)

    // 初始化时不应触发 devops-servers 请求
    const devopsCalls = global.fetch.mock.calls.filter(([url]) =>
      typeof url === 'string' && url.startsWith('/api/admin/devops-servers')
    )
    expect(devopsCalls.length).toBe(0)
  })

  it('test_switch_tab_loads_servers_on_demand 切换 Tab 按需加载服务器列表', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    const tabs = wrapper.findAll('[role="tab"]')
    await tabs[1].trigger('click')
    await flushPromises()

    const devopsCalls = global.fetch.mock.calls.filter(([url, opts]) =>
      url === '/api/admin/devops-servers' && (opts?.method || 'GET') === 'GET'
    )
    expect(devopsCalls.length).toBeGreaterThan(0)

    // 列表渲染：只保留脱敏字段
    expect(wrapper.text()).toContain('业务A-生产')
    expect(wrapper.text()).toContain('业务B-测试')
    expect(wrapper.text()).toContain('production')
    expect(wrapper.text()).toContain('staging')
  })

  it('test_server_list_keeps_only_whitelisted_fields 列表仅保留脱敏白名单字段', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    const tabs = wrapper.findAll('[role="tab"]')
    await tabs[1].trigger('click')
    await flushPromises()

    const html = wrapper.html()
    // 不得出现敏感字段值
    expect(html).not.toContain('super-secret-password')
    expect(html).not.toContain('hidden')
    expect(html).not.toContain('10.0.0.1')
    expect(html).not.toContain('10.0.0.2')
    expect(html).not.toContain('root')
    expect(html).not.toContain('deploy')
    expect(html).not.toContain('/etc,/var/log')
    expect(html).not.toContain('/home,/opt')
    expect(html).not.toContain('/srv/secret/host.json')
    expect(html).not.toContain('/srv/secret/host2.json')

    // 不应渲染敏感字段列头
    expect(html).not.toMatch(/>\s*IP\s*</)
    expect(html).not.toMatch(/>\s*端口\s*</)
    expect(html).not.toMatch(/>\s*用户名\s*</)
    expect(html).not.toMatch(/>\s*密码\s*</)
    expect(html).not.toMatch(/>\s*文件路径\s*</)
  })

  it('test_scan_button_prevents_duplicate_submit 扫描按钮防重复提交', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    // 准备：让扫描接口延迟返回，验证防重复
    let resolveScan
    const scanPromise = new Promise((resolve) => {
      resolveScan = resolve
    })
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') return jsonResponse(mockSchedules)
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      if (u === '/api/admin/devops-servers' && method === 'GET') return jsonResponse(rawDevopsServers)
      if (u === '/api/admin/devops-servers/scan' && method === 'POST') {
        await scanPromise
        return jsonResponse({ scanned: 1, inserted: 1, updated: 0, failed: 0 })
      }
      return jsonResponse({})
    })

    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    await flushPromises()

    const scanButton = wrapper.find('[data-testid="scan-servers-btn"]')
    expect(scanButton.exists()).toBe(true)

    // 第一次点击：进入 scanning 态
    await scanButton.trigger('click')
    await flushPromises()

    const scanCallsBefore = global.fetch.mock.calls.filter(([url]) =>
      url === '/api/admin/devops-servers/scan'
    ).length
    expect(scanCallsBefore).toBe(1)

    // scanning 状态下按钮应 disabled，再次点击不再发起新请求
    expect(scanButton.attributes('disabled')).toBeDefined()
    await scanButton.trigger('click')
    await scanButton.trigger('click')
    await flushPromises()

    const scanCallsAfter = global.fetch.mock.calls.filter(([url]) =>
      url === '/api/admin/devops-servers/scan'
    ).length
    expect(scanCallsAfter).toBe(1)

    // 释放扫描 promise，让扫描完成
    resolveScan()
    await flushPromises()
  })

  it('test_scan_success_shows_summary_and_refreshes_list 扫描成功显示统计并刷新列表', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    // 切到扫描 Tab 并加载初始列表
    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    await flushPromises()

    const initialListCalls = global.fetch.mock.calls.filter(([url, opts]) =>
      url === '/api/admin/devops-servers' && (opts?.method || 'GET') === 'GET'
    ).length
    expect(initialListCalls).toBeGreaterThan(0)

    // 触发扫描
    const scanButton = wrapper.find('[data-testid="scan-servers-btn"]')
    await scanButton.trigger('click')
    await flushPromises()

    // 扫描成功后应当显示统计 summary
    const summary = wrapper.find('[data-testid="scan-summary"]')
    expect(summary.exists()).toBe(true)
    // summary 内出现后端返回字段（扫描 / 新增 / 更新 / 失败）
    const summaryText = summary.text()
    expect(summaryText).toContain('扫描')
    expect(summaryText).toContain('新增')
    expect(summaryText).toContain('更新')
    expect(summaryText).toContain('失败')

    // 扫描完成且无错误时显示 success 标识
    expect(wrapper.find('[data-testid="scan-status"]').exists()).toBe(true)

    // 扫描成功后应当额外调用一次 GET /api/admin/devops-servers 刷新列表
    const afterScanCalls = global.fetch.mock.calls.filter(([url, opts]) =>
      url === '/api/admin/devops-servers' && (opts?.method || 'GET') === 'GET'
    ).length
    expect(afterScanCalls).toBeGreaterThan(initialListCalls)

    // 仍然只渲染脱敏字段
    const html = wrapper.html()
    expect(html).not.toContain('super-secret-password')
    expect(html).not.toContain('10.0.0.1')
  })

  it('test_scan_error_does_not_leak_backend_details 错误不泄露后端敏感信息', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    // 让扫描接口返回错误，并把"敏感 detail"放到响应体
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') return jsonResponse(mockSchedules)
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      if (u === '/api/admin/devops-servers' && method === 'GET') return jsonResponse(rawDevopsServers)
      if (u === '/api/admin/devops-servers/scan' && method === 'POST') {
        // 后端"敏感 detail"绝不可被渲染到页面
        return jsonResponse(
          { detail: 'connect ECONNREFUSED 10.0.0.1:22 with password=hunter2 stack=/srv/secret/host.json' },
          500
        )
      }
      return jsonResponse({})
    })

    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    await flushPromises()

    const scanButton = wrapper.find('[data-testid="scan-servers-btn"]')
    await scanButton.trigger('click')
    await flushPromises()

    const errorBanner = wrapper.find('[data-testid="scan-error"]')
    expect(errorBanner.exists()).toBe(true)

    const html = wrapper.html()
    // 不得出现后端详情里的敏感片段
    expect(html).not.toContain('hunter2')
    expect(html).not.toContain('10.0.0.1:22')
    expect(html).not.toContain('/srv/secret/host.json')
    expect(html).not.toContain('ECONNREFUSED')
  })

  it('test_scan_empty_state 扫描结果空时显示空态', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    // 第一次获取列表返回空
    let listCallCount = 0
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') return jsonResponse(mockSchedules)
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      if (u === '/api/admin/devops-servers' && method === 'GET') {
        listCallCount++
        return jsonResponse([])
      }
      if (u === '/api/admin/devops-servers/scan' && method === 'POST') return jsonResponse({ scanned: 0, inserted: 0, updated: 0, failed: 0 })
      return jsonResponse({})
    })

    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    await flushPromises()

    // 空态存在
    expect(wrapper.find('[data-testid="scan-empty"]').exists()).toBe(true)

    // 触发扫描后仍然空态
    const scanButton = wrapper.find('[data-testid="scan-servers-btn"]')
    await scanButton.trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="scan-empty"]').exists()).toBe(true)
    expect(listCallCount).toBeGreaterThanOrEqual(2)
  })

  it('test_switch_back_to_task_tab_no_devops_request 切回任务 Tab 不再触发 devops 请求', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    // 切到扫描 Tab
    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    await flushPromises()

    const before = global.fetch.mock.calls.filter(([url]) =>
      typeof url === 'string' && url.startsWith('/api/admin/devops-servers')
    ).length

    // 切回任务 Tab
    await wrapper.findAll('[role="tab"]')[0].trigger('click')
    await flushPromises()

    const after = global.fetch.mock.calls.filter(([url]) =>
      typeof url === 'string' && url.startsWith('/api/admin/devops-servers')
    ).length
    expect(after).toBe(before)

    // 任务 Tab 应仍然显示原本的内容
    expect(wrapper.text()).toContain('每日巡检')
    expect(wrapper.find('form').exists()).toBe(true)
  })

  it('test_scan_post_has_no_content_type_header_and_no_body', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    await flushPromises()

    const scanButton = wrapper.find('[data-testid="scan-servers-btn"]')
    await scanButton.trigger('click')
    await flushPromises()

    const scanCall = global.fetch.mock.calls.find(([url]) =>
      url === '/api/admin/devops-servers/scan'
    )
    expect(scanCall).toBeTruthy()
    const opts = scanCall[1] || {}
    expect(opts.method).toBe('POST')
    // 不应显式声明 Content-Type / 不应携带 body
    expect(opts.headers?.['Content-Type']).toBeUndefined()
    expect(opts.headers?.['content-type']).toBeUndefined()
    expect(opts.body).toBeUndefined()
  })

  it('test_server_table_does_not_render_id_column', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    await flushPromises()

    const html = wrapper.html()
    // 不应渲染 ID 列头 / ID 列内容（即便 rawDevopsServers 含 id 字段）
    expect(html).not.toMatch(/>\s*ID\s*</)
  })

  it('test_summary_only_contains_four_whitelisted_numbers', async () => {
    // 后端可能附带多余敏感字段；前端必须只渲染 scanned/inserted/updated/failed
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') return jsonResponse(mockSchedules)
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      if (u === '/api/admin/devops-servers' && method === 'GET') return jsonResponse(rawDevopsServers)
      if (u === '/api/admin/devops-servers/scan' && method === 'POST') {
        return jsonResponse({
          scanned: 3,
          inserted: 2,
          updated: 1,
          failed: 0,
          leaked_password: 'hunter2xyz',
          path: '/srv/secret/host.json',
        })
      }
      return jsonResponse({})
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    await flushPromises()
    await wrapper.find('[data-testid="scan-servers-btn"]').trigger('click')
    await flushPromises()

    const summaryText = wrapper.find('[data-testid="scan-summary"]').text()
    // 只接受白名单数字标签
    expect(summaryText).toContain('扫描 3')
    expect(summaryText).toContain('新增 2')
    expect(summaryText).toContain('更新 1')
    expect(summaryText).toContain('失败 0')
    // 后端额外字段不得进入 DOM
    const html = wrapper.html()
    expect(html).not.toContain('hunter2xyz')
    expect(html).not.toContain('/srv/secret/host.json')
    expect(html).not.toContain('leaked_password')
  })

  it('test_list_error_message_separate_from_scan_error', async () => {
    // 列表加载失败时显示「服务器列表加载失败」，扫描状态独立
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') return jsonResponse(mockSchedules)
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      if (u === '/api/admin/devops-servers' && method === 'GET') {
        return jsonResponse({ detail: 'secrets leaked 10.0.0.1' }, 500)
      }
      if (u === '/api/admin/devops-servers/scan' && method === 'POST') {
        return jsonResponse({ scanned: 0, inserted: 0, updated: 0, failed: 0 })
      }
      return jsonResponse({})
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    await flushPromises()

    const listError = wrapper.find('[data-testid="list-error"]')
    expect(listError.exists()).toBe(true)
    expect(listError.text()).toBe('服务器列表加载失败')
    // 扫描错误不应混入列表错误文案
    expect(wrapper.find('[data-testid="scan-error"]').exists()).toBe(false)
    // 后端敏感片段不外泄
    const html = wrapper.html()
    expect(html).not.toContain('10.0.0.1')
    expect(html).not.toContain('secrets leaked')
  })

  it('test_scan_error_message_separate_from_list_error', async () => {
    // 扫描失败显示「扫描失败，请稍后重试」，与列表加载状态独立
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') return jsonResponse(mockSchedules)
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      if (u === '/api/admin/devops-servers' && method === 'GET') return jsonResponse(rawDevopsServers)
      if (u === '/api/admin/devops-servers/scan' && method === 'POST') {
        return jsonResponse({ detail: 'leaked password=hunter2' }, 500)
      }
      return jsonResponse({})
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    await flushPromises()

    await wrapper.find('[data-testid="scan-servers-btn"]').trigger('click')
    await flushPromises()

    const scanError = wrapper.find('[data-testid="scan-error"]')
    expect(scanError.exists()).toBe(true)
    expect(scanError.text()).toBe('扫描失败，请稍后重试')
    // 列表错误不应混入
    expect(wrapper.find('[data-testid="list-error"]').exists()).toBe(false)
    const html = wrapper.html()
    expect(html).not.toContain('hunter2')
    expect(html).not.toContain('leaked password')
  })

  it('test_second_visit_to_scan_tab_does_not_re_fetch_servers', async () => {
    // 第一次进入扫描 Tab 后置 hasLoaded；再次切到扫描 Tab 不再重复 GET
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    await flushPromises()
    const firstCount = global.fetch.mock.calls.filter(
      ([url, opts]) => url === '/api/admin/devops-servers' && (opts?.method || 'GET') === 'GET'
    ).length

    // 切回任务 Tab 再切回扫描 Tab
    await wrapper.findAll('[role="tab"]')[0].trigger('click')
    await flushPromises()
    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    await flushPromises()

    const secondCount = global.fetch.mock.calls.filter(
      ([url, opts]) => url === '/api/admin/devops-servers' && (opts?.method || 'GET') === 'GET'
    ).length
    expect(secondCount).toBe(firstCount)
  })

  // ===== 预设调度 UI 测试 =====

  it('test_layout_agent_select_appears_before_schedule_type 目标智能体 select 在执行频率 select 之前', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    const agentSelect = wrapper.find('[data-testid="schedule-agent"]')
    const typeSelect = wrapper.find('[data-testid="schedule-type"]')

    expect(agentSelect.exists()).toBe(true)
    expect(typeSelect.exists()).toBe(true)
    expect(
      agentSelect.element.compareDocumentPosition(typeSelect.element) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy()
  })

  it('test_default_schedule_config_is_daily_9am 新增任务时默认每天 09:00', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('新增任务')).trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="schedule-type"]').element.value).toBe('daily')
    expect(wrapper.find('[data-testid="schedule-hour"]').element.value).toBe('9')
    expect(wrapper.find('[data-testid="schedule-minute"]').element.value).toBe('0')
  })

  it('test_weekly_mode_generates_correct_cron 每周三 14:30 生成 30 14 * * 3', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('新增任务')).trigger('click')
    await flushPromises()

    // schedule-type=weekly（SCHEDULE_TYPES[1]）
    await wrapper.find('[data-testid="schedule-type"]').findAll('option')[1].setSelected()
    // schedule-weekday=3（WEEKDAYS[2]=周三, value=3）
    await wrapper.find('[data-testid="schedule-weekday"]').findAll('option')[2].setSelected()
    // schedule-hour=14（HOURS[14]）
    await wrapper.find('[data-testid="schedule-hour"]').findAll('option')[14].setSelected()
    // schedule-minute=30（MINUTES[30]）
    await wrapper.find('[data-testid="schedule-minute"]').findAll('option')[30].setSelected()

    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('周任务')
    await wrapper
      .find('[data-testid="schedule-agent"]')
      .findAll('option')
      .find((o) => o.text() === '地图智能体（map_agent）')
      .setSelected()
    await wrapper.find('textarea').setValue('周报')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    const postCall = global.fetch.mock.calls.find(([url, opts]) => url === '/api/admin/task-schedules' && opts.method === 'POST')
    expect(JSON.parse(postCall[1].body).cron_expression).toBe('30 14 * * 3')
  })

  it('test_monthly_mode_generates_correct_cron 每月 15 日 08:00 生成 0 8 15 * *', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('新增任务')).trigger('click')
    await flushPromises()

    // schedule-type=monthly（SCHEDULE_TYPES[2]）
    await wrapper.find('[data-testid="schedule-type"]').findAll('option')[2].setSelected()
    // schedule-day=15（MONTH_DAYS[14]=15）
    await wrapper.find('[data-testid="schedule-day"]').findAll('option')[14].setSelected()
    // schedule-hour=8（HOURS[8]）
    await wrapper.find('[data-testid="schedule-hour"]').findAll('option')[8].setSelected()
    // schedule-minute=0（MINUTES[0]）
    await wrapper.find('[data-testid="schedule-minute"]').findAll('option')[0].setSelected()

    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('月任务')
    await wrapper
      .find('[data-testid="schedule-agent"]')
      .findAll('option')
      .find((o) => o.text() === '地图智能体（map_agent）')
      .setSelected()
    await wrapper.find('textarea').setValue('月报')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    const postCall = global.fetch.mock.calls.find(([url, opts]) => url === '/api/admin/task-schedules' && opts.method === 'POST')
    expect(JSON.parse(postCall[1].body).cron_expression).toBe('0 8 15 * *')
  })

  it('test_yearly_mode_generates_correct_cron 每年 3 月 1 日 09:00 生成 0 9 1 3 *', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('新增任务')).trigger('click')
    await flushPromises()

    // schedule-type=yearly（SCHEDULE_TYPES[3]）
    await wrapper.find('[data-testid="schedule-type"]').findAll('option')[3].setSelected()
    // schedule-month=3（MONTHS[2]=3）
    await wrapper.find('[data-testid="schedule-month"]').findAll('option')[2].setSelected()
    // schedule-day=1（MONTH_DAYS[0]=1）
    await wrapper.find('[data-testid="schedule-day"]').findAll('option')[0].setSelected()
    // schedule-hour=9（HOURS[9]）
    await wrapper.find('[data-testid="schedule-hour"]').findAll('option')[9].setSelected()
    // schedule-minute=0（MINUTES[0]）
    await wrapper.find('[data-testid="schedule-minute"]').findAll('option')[0].setSelected()

    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('年任务')
    await wrapper
      .find('[data-testid="schedule-agent"]')
      .findAll('option')
      .find((o) => o.text() === '地图智能体（map_agent）')
      .setSelected()
    await wrapper.find('textarea').setValue('年报')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    const postCall = global.fetch.mock.calls.find(([url, opts]) => url === '/api/admin/task-schedules' && opts.method === 'POST')
    expect(JSON.parse(postCall[1].body).cron_expression).toBe('0 9 1 3 *')
  })

  it('test_interval_minutes_mode_generates_correct_cron 每隔 5 分钟生成 */5 * * * *', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('新增任务')).trigger('click')
    await flushPromises()

    // schedule-type = interval_minutes（SCHEDULE_TYPES[4]）
    await wrapper.find('[data-testid="schedule-type"]').findAll('option')[4].setSelected()
    await wrapper.find('[data-testid="schedule-interval"]').setValue('5')

    await wrapper.findAll('input')[0].setValue('分钟级巡检')
    await wrapper
      .find('[data-testid="schedule-agent"]')
      .findAll('option')
      .find((o) => o.text() === '地图智能体（map_agent）')
      .setSelected()
    await wrapper.find('textarea').setValue('每分钟检查')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    const postCall = global.fetch.mock.calls.find(
      ([url, opts]) => url === '/api/admin/task-schedules' && opts.method === 'POST'
    )
    expect(JSON.parse(postCall[1].body).cron_expression).toBe('*/5 * * * *')
  })

  it('test_interval_hours_mode_generates_correct_cron 每隔 3 小时生成 0 */3 * * *', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('新增任务')).trigger('click')
    await flushPromises()

    // schedule-type = interval_hours（SCHEDULE_TYPES[5]）
    await wrapper.find('[data-testid="schedule-type"]').findAll('option')[5].setSelected()
    await wrapper.find('[data-testid="schedule-interval"]').setValue('3')

    await wrapper.findAll('input')[0].setValue('小时级巡检')
    await wrapper
      .find('[data-testid="schedule-agent"]')
      .findAll('option')
      .find((o) => o.text() === '地图智能体（map_agent）')
      .setSelected()
    await wrapper.find('textarea').setValue('每几小时检查')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    const postCall = global.fetch.mock.calls.find(
      ([url, opts]) => url === '/api/admin/task-schedules' && opts.method === 'POST'
    )
    expect(JSON.parse(postCall[1].body).cron_expression).toBe('0 */3 * * *')
  })

  it('test_edit_existing_task_fills_schedule_config 编辑 daily 任务时 UI 回显每天 09:00', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    // mockSchedules[0] cron_expression='0 9 * * *'，默认选中
    expect(wrapper.find('[data-testid="schedule-type"]').element.value).toBe('daily')
    expect(wrapper.find('[data-testid="schedule-hour"]').element.value).toBe('9')
    expect(wrapper.find('[data-testid="schedule-minute"]').element.value).toBe('0')
  })

  it('test_edit_weekly_task_fills_weekday 编辑 weekly 任务时 UI 回显每周三 14:30', async () => {
    // 用 weekly cron 替换 mockSchedules 第一条
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') {
        return jsonResponse([{ ...mockSchedules[0], cron_expression: '30 14 * * 3' }])
      }
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      return jsonResponse({})
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    expect(wrapper.find('[data-testid="schedule-type"]').element.value).toBe('weekly')
    expect(wrapper.find('[data-testid="schedule-weekday"]').element.value).toBe('3')
    expect(wrapper.find('[data-testid="schedule-hour"]').element.value).toBe('14')
    expect(wrapper.find('[data-testid="schedule-minute"]').element.value).toBe('30')
  })

  it('test_edit_interval_minutes_task_fills_interval 编辑 */20 * * * * 回显每隔 20 分钟', async () => {
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') {
        return jsonResponse([{ ...mockSchedules[0], cron_expression: '*/20 * * * *' }])
      }
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      return jsonResponse({})
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    expect(wrapper.find('[data-testid="schedule-type"]').element.value).toBe('interval_minutes')
    expect(wrapper.find('[data-testid="schedule-interval"]').element.value).toBe('20')
  })

  it('test_unparseable_cron_falls_back_to_daily_9am 编辑含逗号的 cron 时 UI 回退为每天 09:00', async () => {
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') {
        return jsonResponse([{ ...mockSchedules[0], cron_expression: '0 9,10 * * *' }])
      }
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      return jsonResponse({})
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    expect(wrapper.find('[data-testid="schedule-type"]').element.value).toBe('daily')
    expect(wrapper.find('[data-testid="schedule-hour"]').element.value).toBe('9')
    expect(wrapper.find('[data-testid="schedule-minute"]').element.value).toBe('0')
  })

  // ===== 「执行时间」字段条件渲染（interval 模式隐藏） =====

  it('test_daily_shows_time_field daily 模式展示「执行时间」字段', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('新增任务')).trigger('click')
    await flushPromises()

    // 默认 type='daily'，「执行时间」字段必须可见
    expect(wrapper.find('[data-testid="schedule-type"]').element.value).toBe('daily')
    expect(wrapper.find('[data-testid="schedule-time"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="schedule-hour"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="schedule-minute"]').exists()).toBe(true)
  })

  it('test_interval_minutes_hides_time_field interval_minutes 模式隐藏「执行时间」字段', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('新增任务')).trigger('click')
    await flushPromises()

    // 切到 interval_minutes（SCHEDULE_TYPES[4]）
    await wrapper.find('[data-testid="schedule-type"]').findAll('option')[4].setSelected()
    await flushPromises()

    expect(wrapper.find('[data-testid="schedule-type"]').element.value).toBe('interval_minutes')
    // 「执行时间」字段必须不可见，但「间隔（分钟）」仍可见
    expect(wrapper.find('[data-testid="schedule-time"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="schedule-hour"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="schedule-minute"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="schedule-interval"]').exists()).toBe(true)

    // 切回 daily，「执行时间」字段重新可见
    await wrapper.find('[data-testid="schedule-type"]').findAll('option')[0].setSelected()
    await flushPromises()
    expect(wrapper.find('[data-testid="schedule-time"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="schedule-hour"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="schedule-minute"]').exists()).toBe(true)
  })

  it('test_interval_hours_hides_time_field interval_hours 模式隐藏「执行时间」字段', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('新增任务')).trigger('click')
    await flushPromises()

    // 切到 interval_hours（SCHEDULE_TYPES[5]）
    await wrapper.find('[data-testid="schedule-type"]').findAll('option')[5].setSelected()
    await flushPromises()

    expect(wrapper.find('[data-testid="schedule-type"]').element.value).toBe('interval_hours')
    expect(wrapper.find('[data-testid="schedule-time"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="schedule-hour"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="schedule-minute"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="schedule-interval"]').exists()).toBe(true)
  })
})
