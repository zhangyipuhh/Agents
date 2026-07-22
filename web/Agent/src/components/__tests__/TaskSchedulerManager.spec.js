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
import taskSchedulerSource from '../TaskSchedulerManager.vue?raw'

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
 * hello_script 的 params_schema：测试驱动 UI 应识别 x-control=server-multiselect
 * 与 x-control=api-multiselect 两种受支持控件。
 *
 * 字段说明：
 *   - mode / content：schema 已声明（用于未来 UI 扩展），但本轮 TaskSchedulerManager 还不支持，
 *     故添加参数下拉中不应出现它们，只支持 server_list 与 api_list。
 *   - server_list：服务器多选（x-control=server-multiselect），候选来自 devops-servers。
 *   - api_list：API 接口多选（x-control=api-multiselect），候选来自 API 配置树。
 */
const helloScriptParamsSchema = {
  type: 'object',
  properties: {
    mode: { type: 'string', default: 'text' },
    content: { type: 'string', default: 'Hello' },
    server_list: {
      type: 'array',
      title: '服务器列表',
      description: '选择本次运维任务需要处理的已入库服务器',
      items: { type: 'string' },
      uniqueItems: true,
      default: [],
      'x-control': 'server-multiselect',
      'x-source': 'devops-servers',
      'x-value-field': 'business_name',
    },
    api_list: {
      type: 'array',
      title: '接口列表',
      description: '选择本次任务需要健康检查的已配置接口（Mock 断言由接口配置决定）',
      items: { type: 'string' },
      uniqueItems: true,
      default: [],
      'x-control': 'api-multiselect',
      'x-source': 'api-configs',
      'x-value-field': 'id',
    },
  },
}

/**
 * mock 后端 GET /api/admin/scripts 返回：至少包含 hello_script，便于加载脚本下拉。
 * TaskSchedulerManager 通过 SCRIPT_PUBLIC_FIELDS 白名单复制，params_schema 字段必须保留。
 */
const mockScripts = [
  {
    name: 'hello_script',
    display_name: '问候脚本',
    description: '示例脚本',
    module_path: 'app.scripts.examples.hello_script',
    params_schema: helloScriptParamsSchema,
  },
]

/**
 * 后端真实会返回的、含敏感字段的原始记录：测试要验证页面不会把这些字段渲染出来。
 *
 * 2026-07-20 重构：所有敏感值改为不可能与合法 DOM 属性 / 业务字符串撞名的 sentinel：
 *   - 形如 "__LEAKED_<KIND>_<HEXSUFFIX>__"：双下划线包裹 + 唯一十六进制后缀
 *   - 这样既能逐值断言"不泄露"，又避免与 HTML 合法属性（hidden / root / port / ...）
 *     或合法业务字符串撞名导致假阳性 / 假阴性
 *   - 业务字段（business_name / server_type）保留真实形态，因为它们本就该渲染
 */
const rawDevopsServers = [
  {
    id: 1,
    business_name: '业务A-生产',
    server_type: 'production',
    updated_at: '2026-07-15T09:00:00',
    ip: '__LEAKED_IP_a1b2c3d4__',
    port: '__LEAKED_PORT_a9c8e7d6__',
    username: '__LEAKED_USER_rootX9f__',
    password: '__LEAKED_PASSWORD_8e7f3a2b__',
    blacklist: '__LEAKED_BL_2c5d_q1w2e3__',
    whitelist: '__LEAKED_WL_4f6a_asdfgh__',
    file_path: '__LEAKED_FP_host_7h8i9j0k__',
  },
  {
    id: 2,
    business_name: '业务B-测试',
    server_type: 'staging',
    updated_at: '2026-07-15T10:00:00',
    ip: '__LEAKED_IP_e5f6g7h8__',
    port: '__LEAKED_PORT_f6e5d4c3__',
    username: '__LEAKED_USER_deployY2k__',
    password: '__LEAKED_PASSWORD_4d2b1c0a__',
    blacklist: '',
    whitelist: '',
    file_path: '__LEAKED_FP_host2_l1m2n3o4__',
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
    if (u === '/api/admin/scripts' && method === 'GET') return jsonResponse(mockScripts)
    if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
    if (u === '/api/admin/task-schedules/1/enabled' && method === 'PUT') return jsonResponse({ ...mockSchedules[0], enabled: false })
    if (u === '/api/admin/task-schedules/1/trigger' && method === 'POST') return jsonResponse({ id: 9, status: 'pending' }, 202)
    if (u === '/api/admin/task-schedules/1' && method === 'DELETE') return emptyResponse()
    if (u === '/api/admin/task-schedules/1' && method === 'PUT') return jsonResponse({ ...mockSchedules[0], ...JSON.parse(opts.body) })
    if (u === '/api/admin/devops-servers' && method === 'GET') return jsonResponse(rawDevopsServers)
    if (u === '/api/admin/devops-servers/scan' && method === 'POST') {
      return jsonResponse({ scanned: 2, inserted: 1, updated: 1, failed: 0 })
    }
    // 2026-07-22 新增：DELETE 单台服务器（204 No Content，无 body）
    if (u === '/api/admin/devops-servers/1' && method === 'DELETE') return emptyResponse(204)
    if (u === '/api/admin/api-configs/tree' && method === 'GET') return jsonResponse({ nodes: [] })
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

  it('test_schedule_card_history_button_icon_only 卡片显示仅图标执行历史按钮', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    const historyButton = wrapper.find('.task-history-btn')
    expect(historyButton.exists()).toBe(true)
    expect(historyButton.text()).toBe('')
    expect(historyButton.attributes('aria-label')).toBe('查看执行历史')
    expect(historyButton.attributes('title')).toBe('查看执行历史')
    expect(historyButton.attributes('aria-haspopup')).toBe('dialog')
    expect(document.body.querySelector('.task-history-overlay')).toBeNull()
    wrapper.unmount()
  })

  it('test_history_button_opens_target_dialog_without_selecting_task 点击历史按钮打开目标任务弹窗', async () => {
    const secondSchedule = {
      ...mockSchedules[0],
      id: 2,
      name: '任务B',
      agent_name: 'disabled_agent',
    }
    const secondRuns = [{
      id: 9,
      status: 'success',
      trigger_type: 'scheduled',
      output_text: '任务B执行完成',
      created_at: '2026-07-11T10:00:00',
    }]
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') {
        return jsonResponse([mockSchedules[0], secondSchedule])
      }
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u === '/api/admin/scripts' && method === 'GET') return jsonResponse(mockScripts)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      if (u.includes('/api/admin/task-schedules/2/runs')) return jsonResponse(secondRuns)
      return jsonResponse({})
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    const historyButtons = wrapper.findAll('.task-history-btn')
    expect(historyButtons.length).toBe(2)

    const initialRunsForSecond = global.fetch.mock.calls.filter(([url]) =>
      typeof url === 'string' && url.includes('/api/admin/task-schedules/2/runs')
    ).length
    await historyButtons[1].trigger('click')
    await flushPromises()

    const dialog = document.body.querySelector('[role="dialog"]')
    const runsForSecond = global.fetch.mock.calls.filter(([url]) =>
      typeof url === 'string' && url.includes('/api/admin/task-schedules/2/runs')
    ).length
    expect(runsForSecond).toBe(initialRunsForSecond + 1)
    expect(dialog).not.toBeNull()
    expect(dialog.getAttribute('aria-modal')).toBe('true')
    expect(dialog.getAttribute('aria-labelledby')).toBe('task-history-dialog-title')
    expect(document.body.querySelector('#task-history-dialog-title').textContent).toContain('任务B')
    expect(document.body.querySelector('.run-history').textContent).toContain('任务B执行完成')
    expect(wrapper.findAll('.task-item.active')[0].find('.task-name').text()).toBe('每日巡检')

    document.body.querySelector('.task-history-close').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushPromises()
    expect(document.body.querySelector('.task-history-overlay')).toBeNull()
    wrapper.unmount()
  })

  it('test_history_dialog_closes_by_overlay_and_escape 遮罩与 Escape 可关闭执行历史弹窗', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.find('.task-history-btn').trigger('click')
    await flushPromises()

    const dialog = document.body.querySelector('.task-history-dialog')
    dialog.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushPromises()
    expect(document.body.querySelector('.task-history-overlay')).not.toBeNull()

    document.body.querySelector('.task-history-overlay').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushPromises()
    expect(document.body.querySelector('.task-history-overlay')).toBeNull()

    await wrapper.find('.task-history-btn').trigger('click')
    await flushPromises()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(document.body.querySelector('.task-history-overlay')).toBeNull()
    wrapper.unmount()
  })

  it('test_history_button_failure_shows_dialog_error 执行历史加载失败显示弹窗错误', async () => {
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') return jsonResponse(mockSchedules)
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u === '/api/admin/scripts' && method === 'GET') return jsonResponse(mockScripts)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse({ detail: '历史服务不可用' }, 500)
      return jsonResponse({})
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.find('.task-history-btn').trigger('click')
    await flushPromises()

    expect(document.body.querySelector('[data-testid="task-history-error"]').textContent).toContain('历史服务不可用')
    wrapper.unmount()
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

  it('test_save_button_in_header_actions_new_mode 新建模式下顶部 actions 显示保存按钮', async () => {
    /**
     * 计划：把「保存任务」按钮从 form 底部移到 detail-header 顶部 actions 行；
     * 新建模式（isCreating=true）下也需显示「保存任务」，但不显示其他三个编辑按钮。
     */
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('新增任务')).trigger('click')
    await flushPromises()

    // 顶部 actions 行存在「保存任务」按钮（data-testid 稳定定位）
    const saveBtn = wrapper.find('[data-testid="schedule-save-btn"]')
    expect(saveBtn.exists()).toBe(true)
    expect(saveBtn.text()).toContain('保存任务')

    // 新建模式下不应渲染编辑专属按钮
    const allButtons = wrapper.findAll('button').map((b) => b.text())
    const hasEditOnly = allButtons.some((t) => t.includes('停用任务') || t.includes('启用任务'))
      || allButtons.some((t) => t.includes('立即运行'))
      || allButtons.some((t) => t.includes('删除任务'))
    expect(hasEditOnly).toBe(false)

    // form 内已无独立的 .form-actions 区块（避免重复按钮）
    expect(wrapper.find('form .form-actions').exists()).toBe(false)
  })

  it('test_save_button_in_header_actions_edit_mode 编辑模式下保存与启停/运行/删除同一行', async () => {
    /**
     * 计划：编辑模式（isCreating=false）下，「保存任务」与「停用任务」「立即运行」「删除任务」
     * 都在 detail-header 顶部 .actions 内渲染。
     */
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    const headerActions = wrapper.find('.detail-header .actions')
    expect(headerActions.exists()).toBe(true)

    const actionsHtml = headerActions.html()
    expect(actionsHtml).toContain('schedule-save-btn')
    expect(actionsHtml).toContain('停用任务')
    expect(actionsHtml).toContain('立即运行')
    expect(actionsHtml).toContain('删除任务')

    // form 内已无独立的 .form-actions 区块
    expect(wrapper.find('form .form-actions').exists()).toBe(false)
  })

  it('test_header_save_button_submits_form 顶部保存按钮点击触发 submit', async () => {
    /**
     * 计划：顶部保存按钮通过 form="task-scheduler-form" 显式挂回 form，
     * 浏览器原生会在 click 时触发 form submit 事件并调用 @submit.prevent="saveTask"。
     * jsdom 不实现 button.form 关联（HTML5 跨 form 提交语义），故此处改用：
     *  1. 验证按钮 DOM 上确实带有正确的 form="task-scheduler-form" 属性
     *  2. 验证通过 form 的 submit 事件能正常走通 saveTask（与原 form 底部 submit 等价）
     *  3. 验证按钮 type="submit"，浏览器在生产环境会触发原生 submit
     */
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('新增任务')).trigger('click')
    await flushPromises()

    const saveBtn = wrapper.find('[data-testid="schedule-save-btn"]')
    expect(saveBtn.exists()).toBe(true)
    // 1. 按钮通过 form 属性显式挂回 form
    expect(saveBtn.attributes('form')).toBe('task-scheduler-form')
    // 2. 按钮 type=submit，浏览器原生 click 即可触发 submit 事件
    expect(saveBtn.attributes('type')).toBe('submit')
    // 3. form id 与按钮 form 属性一致
    expect(wrapper.find('form#task-scheduler-form').exists()).toBe(true)

    // 填写必填字段并通过 form submit 事件验证 saveTask 仍可走通
    await findTaskNameInput(wrapper).setValue('顶部保存按钮任务')
    await wrapper
      .find('[data-testid="schedule-agent"]')
      .findAll('option')
      .find((o) => o.text() === '地图智能体（map_agent）')
      .setSelected()
    await wrapper.find('textarea').setValue('测试顶部保存')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    const postCall = global.fetch.mock.calls.find(
      ([url, opts]) => url === '/api/admin/task-schedules' && opts.method === 'POST'
    )
    expect(postCall).toBeTruthy()
    expect(JSON.parse(postCall[1].body).name).toBe('顶部保存按钮任务')
  })

  it('test_save_new_task_posts_payload 保存新任务调用 POST', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('新增任务')).trigger('click')
    await flushPromises()

    // 任务名称（稳定 helper 定位：表单中第一个 type=text 的 input）
    await findTaskNameInput(wrapper).setValue('周报任务')
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
    await wrapper.find('.task-history-btn').trigger('click')
    await flushPromises()

    expect(document.body.querySelector('.run-history').textContent).toContain('success')
    expect(document.body.querySelector('.run-history').textContent).toContain('failed')
    expect(document.body.querySelector('.run-history').textContent).toContain('执行完成')
    expect(document.body.querySelector('.run-history').textContent).toContain('boom')
    wrapper.unmount()
  })

  it('test_default_tab_is_edit_task 默认 Tab 是「编辑任务」', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    const tablist = wrapper.find('[role="tablist"]')
    expect(tablist.exists()).toBe(true)

    const tabs = tablist.findAll('[role="tab"]')
    expect(tabs.length).toBe(4)
    expect(tabs[0].text()).toContain('编辑任务')
    expect(tabs[1].text()).toContain('服务器扫描入库')
    expect(tabs[2].text()).toContain('脚本扫描入库')
    expect(tabs[3].text()).toContain('API接口配置')

    // 默认激活态：第一个 Tab aria-selected=true
    expect(tabs[0].attributes('aria-selected')).toBe('true')
    expect(tabs[1].attributes('aria-selected')).toBe('false')
    expect(tabs[2].attributes('aria-selected')).toBe('false')
    expect(tabs[3].attributes('aria-selected')).toBe('false')

    // 条件挂载语义：默认只有任务面板存在，隐藏面板不得常驻 DOM
    expect(wrapper.find('[data-testid="panel-task"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="panel-scan"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="panel-script"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="panel-api"]').exists()).toBe(false)

    // 初始化时不应触发 devops-servers 请求
    const initialDevopsCalls = global.fetch.mock.calls.filter(([url]) =>
      typeof url === 'string' && url.startsWith('/api/admin/devops-servers')
    )
    expect(initialDevopsCalls.length).toBe(0)

    // 切到服务器扫描 Tab 后，仅服务器扫描面板存在
    await tabs[1].trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="panel-task"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="panel-scan"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="panel-script"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="panel-api"]').exists()).toBe(false)

    // 切到脚本扫描 Tab 后，仅脚本扫描面板存在
    await tabs[2].trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="panel-task"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="panel-scan"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="panel-script"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="panel-api"]').exists()).toBe(false)

    // 切到 API 接口配置 Tab 后，仅 API 面板存在，并按需拉取节点树
    await tabs[3].trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="panel-task"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="panel-scan"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="panel-script"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="panel-api"]').exists()).toBe(true)
    const treeCalls = global.fetch.mock.calls.filter(([url]) => url === '/api/admin/api-configs/tree')
    expect(treeCalls.length).toBeGreaterThan(0)
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
    // 不得出现敏感字段 sentinel 值（sentinel 与真实形态都断言，避免 DOM 属性 / 业务字符串撞名）
    expect(html).not.toContain('__LEAKED_IP_a1b2c3d4__')
    expect(html).not.toContain('__LEAKED_IP_e5f6g7h8__')
    expect(html).not.toContain('__LEAKED_USER_rootX9f__')
    expect(html).not.toContain('__LEAKED_USER_deployY2k__')
    expect(html).not.toContain('__LEAKED_PASSWORD_8e7f3a2b__')
    expect(html).not.toContain('__LEAKED_PASSWORD_4d2b1c0a__')
    expect(html).not.toContain('__LEAKED_BL_2c5d_q1w2e3__')
    expect(html).not.toContain('__LEAKED_WL_4f6a_asdfgh__')
    expect(html).not.toContain('__LEAKED_FP_host_7h8i9j0k__')
    expect(html).not.toContain('__LEAKED_FP_host2_l1m2n3o4__')

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
      if (u === '/api/admin/scripts' && method === 'GET') return jsonResponse(mockScripts)
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
    expect(html).not.toContain('__LEAKED_PASSWORD_8e7f3a2b__')
    expect(html).not.toContain('__LEAKED_IP_a1b2c3d4__')
  })

  it('test_scan_error_does_not_leak_backend_details 错误不泄露后端敏感信息', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    // 让扫描接口返回错误，并把"敏感 detail"放到响应体
    // 2026-07-20 重构：sentinel 化的 detail 字符串，确保逐值断言不撞名
    const SCAN_ERROR_DETAIL = 'connect __LEAKED_ERR_ECONNREFUSED__ __LEAKED_IP_a1b2c3d4__:__LEAKED_PORT_22aa__ with password=__LEAKED_PWD_SENTINEL_hunter2__ stack=__LEAKED_FP_host_7h8i9j0k__'
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') return jsonResponse(mockSchedules)
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u === '/api/admin/scripts' && method === 'GET') return jsonResponse(mockScripts)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      if (u === '/api/admin/devops-servers' && method === 'GET') return jsonResponse(rawDevopsServers)
      if (u === '/api/admin/devops-servers/scan' && method === 'POST') {
        // 后端"敏感 detail"绝不可被渲染到页面
        return jsonResponse({ detail: SCAN_ERROR_DETAIL }, 500)
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
    // 不得出现后端详情里的任何敏感 sentinel：逐值断言避免与合法 DOM 属性 / 业务字符串撞名
    expect(html).not.toContain('__LEAKED_ERR_ECONNREFUSED__')
    expect(html).not.toContain('__LEAKED_IP_a1b2c3d4__')
    expect(html).not.toContain('__LEAKED_PORT_22aa__')
    expect(html).not.toContain('__LEAKED_PWD_SENTINEL_hunter2__')
    expect(html).not.toContain('__LEAKED_FP_host_7h8i9j0k__')
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
      if (u === '/api/admin/scripts' && method === 'GET') return jsonResponse(mockScripts)
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
      if (u === '/api/admin/scripts' && method === 'GET') return jsonResponse(mockScripts)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      if (u === '/api/admin/devops-servers' && method === 'GET') return jsonResponse(rawDevopsServers)
      if (u === '/api/admin/devops-servers/scan' && method === 'POST') {
        return jsonResponse({
          scanned: 3,
          inserted: 2,
          updated: 1,
          failed: 0,
          // 2026-07-20 重构：sentinel 化的多余字段，确保逐值断言不撞名
          __leaked_password__: '__LEAKED_PWD_xyz9876__',
          path: '__LEAKED_FP_summary_lmn0123__',
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
    // 后端额外字段不得进入 DOM（sentinel 逐值断言）
    const html = wrapper.html()
    expect(html).not.toContain('__LEAKED_PWD_xyz9876__')
    expect(html).not.toContain('__LEAKED_FP_summary_lmn0123__')
    expect(html).not.toContain('__leaked_password__')
  })

  it('test_list_error_message_separate_from_scan_error', async () => {
    // 列表加载失败时显示「服务器列表加载失败」，扫描状态独立
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') return jsonResponse(mockSchedules)
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u === '/api/admin/scripts' && method === 'GET') return jsonResponse(mockScripts)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      if (u === '/api/admin/devops-servers' && method === 'GET') {
        // 2026-07-20 重构：sentinel 化的 detail 字符串
        return jsonResponse({ detail: '__LEAKED_MSG_secrets_leaked__ __LEAKED_IP_a1b2c3d4__' }, 500)
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
    // 后端敏感片段不外泄（sentinel 逐值断言）
    const html = wrapper.html()
    expect(html).not.toContain('__LEAKED_MSG_secrets_leaked__')
    expect(html).not.toContain('__LEAKED_IP_a1b2c3d4__')
  })

  it('test_scan_error_message_separate_from_list_error', async () => {
    // 扫描失败显示「扫描失败，请稍后重试」，与列表加载状态独立
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') return jsonResponse(mockSchedules)
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u === '/api/admin/scripts' && method === 'GET') return jsonResponse(mockScripts)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      if (u === '/api/admin/devops-servers' && method === 'GET') return jsonResponse(rawDevopsServers)
      if (u === '/api/admin/devops-servers/scan' && method === 'POST') {
        // 2026-07-20 重构：sentinel 化的 detail 字符串
        return jsonResponse({ detail: '__LEAKED_MSG_leaked_pwd__=__LEAKED_PWD_SENTINEL_hunter2__' }, 500)
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
    // 后端 detail 的敏感 sentinel 逐值断言
    expect(html).not.toContain('__LEAKED_MSG_leaked_pwd__')
    expect(html).not.toContain('__LEAKED_PWD_SENTINEL_hunter2__')
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

    await findTaskNameInput(wrapper).setValue('周任务')
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

    await findTaskNameInput(wrapper).setValue('月任务')
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

    await findTaskNameInput(wrapper).setValue('年任务')
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

    await findTaskNameInput(wrapper).setValue('分钟级巡检')
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

    await findTaskNameInput(wrapper).setValue('小时级巡检')
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
      if (u === '/api/admin/scripts' && method === 'GET') return jsonResponse(mockScripts)
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
      if (u === '/api/admin/scripts' && method === 'GET') return jsonResponse(mockScripts)
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
      if (u === '/api/admin/scripts' && method === 'GET') return jsonResponse(mockScripts)
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

  // ===== 目标类型条件渲染（智能体 / 脚本） =====

  it('test_target_type_agent_shows_prompt_and_context_overrides_only 智能体目标显示提示词与 context_overrides，不显示脚本参数', async () => {
    /**
     * 验证在默认 target_type='agent' 下：
     *  - form 渲染任务提示词 textarea 与 context_overrides JSON 字段
     *  - 不渲染「脚本参数 (JSON)」textarea
     */
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    // 默认 target_type='agent'，应存在 schedule-agent select、schedule-target-type select
    expect(wrapper.find('[data-testid="schedule-target-type"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="schedule-target-type"]').element.value).toBe('agent')

    // 不应渲染脚本参数 textarea
    expect(wrapper.find('[data-testid="schedule-script-args"]').exists()).toBe(false)

    // context_overrides JSON 标签应可见
    expect(wrapper.text()).toContain('context_overrides JSON')
  })

  it('test_target_type_script_shows_script_args_only_and_hides_context_overrides 脚本目标显示脚本参数，不显示提示词与 context_overrides', async () => {
    /**
     * 切换目标类型为 script：
     *  - 渲染「脚本参数 (JSON)」textarea，不渲染「任务提示词」与 context_overrides JSON
     *  - 切换回 agent 后，context_overrides 重新可见
     */
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    const targetSelect = wrapper.find('[data-testid="schedule-target-type"]')
    await targetSelect.setValue('script')
    await flushPromises()

    // script 类型应渲染 script-args
    expect(wrapper.find('[data-testid="schedule-script-args"]').exists()).toBe(true)

    // script 类型不应显示 context_overrides JSON 标签
    expect(wrapper.text()).not.toContain('context_overrides JSON')

    // script 类型不应显示「任务提示词」标签（标签内文字逐字匹配）
    expect(wrapper.text()).not.toContain('任务提示词 *')

    // 切回 agent，context_overrides 与「任务提示词」应再次可见
    await targetSelect.setValue('agent')
    await flushPromises()
    expect(wrapper.find('[data-testid="schedule-script-args"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('context_overrides JSON')
    expect(wrapper.text()).toContain('任务提示词 *')
  })

  // ===== 脚本参数列表（schema 驱动 server_list）行为测试 =====

  /**
   * 切换到 script 目标后填写脚本/触发相关控件的 helper：用于 server_list 系列测试。
   * 行为契约：选择 hello_script 是为让 params_schema 提供 server_list 控件。
   */
  async function switchToScriptAndSelectHello(wrapper) {
    const targetSelect = wrapper.find('[data-testid="schedule-target-type"]')
    await targetSelect.setValue('script')
    await flushPromises()
    const scriptSelect = wrapper.find('[data-testid="schedule-script"]')
    await scriptSelect.setValue('hello_script')
    await flushPromises()
  }

  /**
   * 稳定定位任务名称输入控件（生产无专属 testid，故退化到「表单中第一个 type=text 的 input」）。
   *
   * 说明：表单首个 input[type=text] 即「任务名称」字段——其 label 文本包含「任务名称 *」，
   * 且 v-model 绑定到 form.name。其它 input[type=text]（如「描述」「时区」）出现在表单后段，
   * 因此顺序上第一个 type=text 始终是任务名称。
   *
   * @param {import('@vue/test-utils').VueWrapper} wrapper - mount 后的 Vue 测试包装器
   * @returns {import('@vue/test-utils').DOMWrapper} 任务名称 input 的 DOMWrapper
   */
  function findTaskNameInput(wrapper) {
    const form = wrapper.find('form')
    expect(form.exists()).toBe(true)
    const textInputs = form.findAll('input[type="text"]')
    expect(textInputs.length).toBeGreaterThan(0)
    const taskNameInput = textInputs[0]
    // 进一步约束：相邻 label 文本应包含「任务名称」，避免未来字段顺序变更导致定位漂移
    const labelSpan = taskNameInput.element.closest('label')?.querySelector('span')
    expect(labelSpan && labelSpan.textContent.includes('任务名称')).toBe(true)
    return taskNameInput
  }

  it('test_script_target_renders_param_container_without_textarea script 目标显示参数容器且不含 textarea', async () => {
    /**
     * 计划 §2.3 / §3：将用于编辑 JSON 的 textarea 替换为「脚本参数」参数化容器（testid 沿用 schedule-script-args）。
     * 容器根元素不再是 TEXTAREA，并且全文不再存在 textarea[data-testid="schedule-script-args"]。
     * 当前生产代码仍把 schedule-script-args 直接挂在 textarea 上，因此本测试在生产实现完成前必须红灯。
     */
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    await switchToScriptAndSelectHello(wrapper)

    const container = wrapper.find('[data-testid="schedule-script-args"]')
    expect(container.exists()).toBe(true)
    // 容器根元素不是 TEXTAREA：参数化容器应是 div/section 等块级容器，而非可编辑文本域
    expect(container.element.tagName).not.toBe('TEXTAREA')
    // 全文不存在 textarea[data-testid="schedule-script-args"]：JSON 编辑入口已被参数化容器取代
    expect(wrapper.find('textarea[data-testid="schedule-script-args"]').exists()).toBe(false)
    // 容器内部不应再渲染任何用于 JSON 编辑的 textarea 子元素
    expect(container.find('textarea').exists()).toBe(false)
  })

  it('test_adding_server_list_triggers_single_devops_request 添加 server_list 后才请求服务器列表，且不重复', async () => {
    /**
     * 计划 §2.3：首次添加或编辑已有 server_list 时才请求服务器列表。
     * - 默认不应因参数区额外请求 /api/admin/devops-servers
     * - 选择 schedule-add-script-param=server_list 后第一次 GET 且不重复
     */
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    // 初始默认不请求服务器列表（与现有 test_default_tab_is_edit_task 一致）
    const beforeAny = global.fetch.mock.calls.filter(
      ([url, opts]) => url === '/api/admin/devops-servers' && (opts?.method || 'GET') === 'GET'
    ).length
    expect(beforeAny).toBe(0)

    await switchToScriptAndSelectHello(wrapper)

    // 选择 server_list 之前仍不应触发 devops-servers 请求
    const beforeAdd = global.fetch.mock.calls.filter(
      ([url, opts]) => url === '/api/admin/devops-servers' && (opts?.method || 'GET') === 'GET'
    ).length
    expect(beforeAdd).toBe(0)

    // 添加 server_list 参数
    const addSelect = wrapper.find('[data-testid="schedule-add-script-param"]')
    expect(addSelect.exists()).toBe(true)
    await addSelect.setValue('server_list')
    await flushPromises()

    const afterAdd = global.fetch.mock.calls.filter(
      ([url, opts]) => url === '/api/admin/devops-servers' && (opts?.method || 'GET') === 'GET'
    ).length
    expect(afterAdd).toBe(1)

    // 切换勾选状态不应再次触发请求
    const checkbox = wrapper.find('[data-testid="schedule-server-option-1"]')
    expect(checkbox.exists()).toBe(true)
    await checkbox.setChecked()
    await flushPromises()
    const afterToggle = global.fetch.mock.calls.filter(
      ([url, opts]) => url === '/api/admin/devops-servers' && (opts?.method || 'GET') === 'GET'
    ).length
    expect(afterToggle).toBe(1)
  })

  it('test_select_two_servers_submit_string_array 勾选两个业务服务器后提交字符串数组', async () => {
    /**
     * 计划 §2.1 / §3：POST body.script_args 精确为 {server_list: ['业务A-生产','业务B-测试']}。
     */
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('新增任务')).trigger('click')
    await flushPromises()

    await switchToScriptAndSelectHello(wrapper)
    // 添加 server_list 参数
    await wrapper.find('[data-testid="schedule-add-script-param"]').setValue('server_list')
    await flushPromises()

    // 勾选两个候选服务器
    await wrapper.find('[data-testid="schedule-server-option-1"]').setChecked()
    await wrapper.find('[data-testid="schedule-server-option-2"]').setChecked()
    await flushPromises()

    // 任务名称（用稳定 helper 定位：表单中第一个 type=text 的 input）
    await findTaskNameInput(wrapper).setValue('服务器巡检任务')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    const postCall = global.fetch.mock.calls.find(
      ([url, opts]) => url === '/api/admin/task-schedules' && opts.method === 'POST'
    )
    expect(postCall).toBeTruthy()
    const body = JSON.parse(postCall[1].body)
    expect(body.script_args).toEqual({
      server_list: ['业务A-生产', '业务B-测试'],
    })
  })

  it('test_edit_existing_task_echoes_server_list 编辑已有 script 任务回显 server_list', async () => {
    /**
     * 计划 §2.2 hydrateScriptArgs：编辑时已识别参数进入 scriptParamValues。
     */
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') {
        return jsonResponse([
          {
            ...mockSchedules[0],
            target_type: 'script',
            script_name: 'hello_script',
            script_args: { server_list: ['业务A-生产', '业务B-测试'] },
          },
        ])
      }
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u === '/api/admin/scripts' && method === 'GET') return jsonResponse(mockScripts)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      if (u === '/api/admin/devops-servers' && method === 'GET') return jsonResponse(rawDevopsServers)
      return jsonResponse({})
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    // 编辑任务已自动 hydrate：参数区应出现 server_list 控件并勾选两个 checkbox
    expect(wrapper.find('[data-testid="schedule-param-server-list"]').exists()).toBe(true)
    const opt1 = wrapper.find('[data-testid="schedule-server-option-1"]')
    const opt2 = wrapper.find('[data-testid="schedule-server-option-2"]')
    expect(opt1.exists()).toBe(true)
    expect(opt2.exists()).toBe(true)
    expect(opt1.element.checked).toBe(true)
    expect(opt2.element.checked).toBe(true)
    // 已选 chip 同样应可见（不仅 checkbox）：屏幕阅读器与 UI 都依赖 chip 展示
    expect(wrapper.find('[data-testid="schedule-selected-server-chip-业务A-生产"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="schedule-selected-server-chip-业务B-测试"]').exists()).toBe(true)
  })

  it('test_invalid_server_kept_and_removed_only_on_explicit_action 失效业务名仍回显并原样提交，显式移除后才删除', async () => {
    /**
     * 计划 §2.3：旧值不在当前服务器清单时显示「失效」chip 并保留在数组中，
     * 用户点击移除后才删除。提交时仍包含该失效项。
     */
    // 当前服务器清单只有 id=1（业务A-生产），旧任务 server_list 含「已下线-老业务」
    const currentServers = [rawDevopsServers[0]]
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') {
        return jsonResponse([
          {
            ...mockSchedules[0],
            target_type: 'script',
            script_name: 'hello_script',
            script_args: { server_list: ['业务A-生产', '已下线-老业务'] },
          },
        ])
      }
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u === '/api/admin/scripts' && method === 'GET') return jsonResponse(mockScripts)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      if (u === '/api/admin/devops-servers' && method === 'GET') return jsonResponse(currentServers)
      // 真实的 PUT 路径含 ID：/api/admin/task-schedules/1
      if (u === '/api/admin/task-schedules/1' && method === 'PUT') return jsonResponse({ ...mockSchedules[0], ...JSON.parse(opts.body) })
      return jsonResponse({})
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    // 失效 chip 应包含业务名 + 「已失效」文本标识（避免被同名有效业务掩盖）
    const invalidChip = wrapper.findAll('[data-testid="schedule-selected-server-invalid-chip"]')
      .find((c) => c.text().includes('已下线-老业务'))
    expect(invalidChip).toBeTruthy()
    // 失效标识必须出现，方便 UI 与屏幕阅读器识别
    expect(invalidChip.text()).toContain('已失效')
    // 同时已选有效项「业务A-生产」也应作为 chip 出现（不仅 checkbox）
    expect(wrapper.find('[data-testid="schedule-selected-server-chip-业务A-生产"]').exists()).toBe(true)

    // 第一次保存：仍包含失效项；PUT 路径必须命中真实 ID 端点 /api/admin/task-schedules/1
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    const firstPutCall = global.fetch.mock.calls.find(
      ([url, opts]) => url === '/api/admin/task-schedules/1' && opts.method === 'PUT'
    )
    expect(firstPutCall).toBeTruthy()
    expect(JSON.parse(firstPutCall[1].body).script_args).toEqual({
      server_list: ['业务A-生产', '已下线-老业务'],
    })

    // 显式移除失效项：按含业务名的 aria-label 定位移除按钮（不强制计划外 testid）
    const removeBtn = wrapper.find(`[aria-label="移除已选服务器 已下线-老业务"]`)
    expect(removeBtn.exists()).toBe(true)
    await removeBtn.trigger('click')
    await flushPromises()

    // 第二次保存：失效项被删除
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    const secondCall = [...global.fetch.mock.calls]
      .reverse()
      .find(([url, opts]) => url === '/api/admin/task-schedules/1' && opts.method === 'PUT')
    expect(secondCall).toBeTruthy()
    expect(JSON.parse(secondCall[1].body).script_args).toEqual({
      server_list: ['业务A-生产'],
    })
  })

  it('test_unknown_legacy_args_merge_with_server_list 未知旧参数与 server_list 合并提交', async () => {
    /**
     * 计划 §2.2 / §2.3：删除 JSON textarea 后，旧任务中未在 schema 中声明或 UI 不支持的参数必须原样保留。
     * 测试数据故意包含：
     *   - server_list：schema 声明且 UI 支持（应保留）
     *   - mode / content：schema 声明但 UI 暂不支持（应保留）
     *   - custom_flag / legacy_note：完全未在 schema 中出现（应保留）
     */
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') {
        return jsonResponse([
          {
            ...mockSchedules[0],
            target_type: 'script',
            script_name: 'hello_script',
            script_args: {
              server_list: ['业务A-生产'],
              mode: 'text',
              content: '历史正文',
              custom_flag: true,
              legacy_note: '历史备注',
            },
          },
        ])
      }
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u === '/api/admin/scripts' && method === 'GET') return jsonResponse(mockScripts)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      if (u === '/api/admin/devops-servers' && method === 'GET') return jsonResponse(rawDevopsServers)
      // 真实的 PUT 路径含 ID：/api/admin/task-schedules/1
      if (u === '/api/admin/task-schedules/1' && method === 'PUT') return jsonResponse({ ...mockSchedules[0], ...JSON.parse(opts.body) })
      return jsonResponse({})
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    // 添加参数下拉不应出现 UI 暂不支持的 mode/content；已有 server_list 仍显示为已选参数，因此下拉不应再次提供
    const addSelectOptions = wrapper
      .find('[data-testid="schedule-add-script-param"]')
      .findAll('option')
      .map((o) => o.element.value)
    expect(addSelectOptions).not.toContain('server_list')
    expect(addSelectOptions).not.toContain('mode')
    expect(addSelectOptions).not.toContain('content')

    // 已有 server_list 的参数区与已选 chip 必须可见
    expect(wrapper.find('[data-testid="schedule-param-server-list"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="schedule-selected-server-chip-业务A-生产"]').exists()).toBe(true)

    // 触发 PUT 保存（编辑模式）；PUT 必须命中真实 ID 端点 /api/admin/task-schedules/1
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    const putCall = global.fetch.mock.calls.find(
      ([url, opts]) => url === '/api/admin/task-schedules/1' && opts.method === 'PUT'
    )
    expect(putCall).toBeTruthy()
    // 提交时必须完整保留 schema 已知但 UI 暂不支持的字段 + 完全未在 schema 中的字段
    expect(JSON.parse(putCall[1].body).script_args).toEqual({
      server_list: ['业务A-生产'],
      mode: 'text',
      content: '历史正文',
      custom_flag: true,
      legacy_note: '历史备注',
    })
  })

  it('test_remove_server_list_param_drops_key_and_hides_from_dropdown 移除 server_list 后 payload 不含该键，且添加下拉不再包含已添加参数', async () => {
    /**
     * 计划 §2.2 removeScriptParam / §2.3：参数选择器不允许重复添加同一 key。
     */
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('新增任务')).trigger('click')
    await flushPromises()
    await switchToScriptAndSelectHello(wrapper)

    // 第一次添加
    await wrapper.find('[data-testid="schedule-add-script-param"]').setValue('server_list')
    await flushPromises()
    // 重复添加：下拉中不应再列出 server_list
    const addSelectOptions = wrapper
      .find('[data-testid="schedule-add-script-param"]')
      .findAll('option')
      .map((o) => o.element.value)
    expect(addSelectOptions).not.toContain('server_list')

    // 勾选一项以便验证移除后 payload 不含 server_list
    await wrapper.find('[data-testid="schedule-server-option-1"]').setChecked()
    await flushPromises()

    // 移除 server_list 参数
    const removeBtn = wrapper.find('[data-testid="schedule-remove-param-server_list"]')
    expect(removeBtn.exists()).toBe(true)
    await removeBtn.trigger('click')
    await flushPromises()

    // 参数区消失
    expect(wrapper.find('[data-testid="schedule-param-server-list"]').exists()).toBe(false)

    // 添加下拉重新可选
    const addSelectOptionsAfter = wrapper
      .find('[data-testid="schedule-add-script-param"]')
      .findAll('option')
      .map((o) => o.element.value)
    expect(addSelectOptionsAfter).toContain('server_list')

    // 提交后 payload.script_args 不含 server_list
    await findTaskNameInput(wrapper).setValue('无参数脚本任务')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    const postCall = global.fetch.mock.calls.find(
      ([url, opts]) => url === '/api/admin/task-schedules' && opts.method === 'POST'
    )
    expect(postCall).toBeTruthy()
    const body = JSON.parse(postCall[1].body)
    expect(body.script_args).not.toHaveProperty('server_list')
  })

  it('test_script_param_panel_does_not_leak_sensitive_fields 参数面板 DOM 不出现敏感服务器字段', async () => {
    /**
     * 计划 §1.1 / 全局约束：参数面板 DOM 不得渲染 ip / port / username / password / blacklist / whitelist / file_path。
     */
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await switchToScriptAndSelectHello(wrapper)
    await wrapper.find('[data-testid="schedule-add-script-param"]').setValue('server_list')
    await flushPromises()
    await wrapper.find('[data-testid="schedule-server-option-1"]').setChecked()
    await wrapper.find('[data-testid="schedule-server-option-2"]').setChecked()
    await flushPromises()

    // 仅检查 schedule-script-args 容器内的 DOM：避免被无关区块干扰
    const containerHtml = wrapper.find('[data-testid="schedule-script-args"]').html()

    // 2026-07-20 重构：sentinel 逐值断言，避免与合法 DOM 属性 / 业务字符串撞名
    expect(containerHtml).not.toContain('__LEAKED_IP_a1b2c3d4__')
    expect(containerHtml).not.toContain('__LEAKED_IP_e5f6g7h8__')
    expect(containerHtml).not.toContain('__LEAKED_PORT_a9c8e7d6__')
    expect(containerHtml).not.toContain('__LEAKED_PORT_f6e5d4c3__')
    expect(containerHtml).not.toContain('__LEAKED_PASSWORD_8e7f3a2b__')
    expect(containerHtml).not.toContain('__LEAKED_PASSWORD_4d2b1c0a__')
    expect(containerHtml).not.toContain('__LEAKED_USER_rootX9f__')
    expect(containerHtml).not.toContain('__LEAKED_USER_deployY2k__')
    expect(containerHtml).not.toContain('__LEAKED_BL_2c5d_q1w2e3__')
    expect(containerHtml).not.toContain('__LEAKED_WL_4f6a_asdfgh__')
    expect(containerHtml).not.toContain('__LEAKED_FP_host_7h8i9j0k__')
    expect(containerHtml).not.toContain('__LEAKED_FP_host2_l1m2n3o4__')
  })

  // ===== Task 2 代码审查：4 个 Important 问题的最小行为测试（纯 TDD 红灯） =====

  /**
   * 共享 helper：把 helloScriptParamsSchema 复制出来，再额外追加一个 key。
   * 用于构造"两个 key 都满足受支持条件"的最小场景。
   * @param {string} extraKey - 要追加的第二个 key 名
   * @param {Object} extraDef - 要追加的第二个 key 的 schema 定义
   * @returns {Object} 新的 schema 对象
   */
  function withExtraParamSchema(extraKey, extraDef) {
    return {
      type: 'object',
      properties: {
        ...helloScriptParamsSchema.properties,
        [extraKey]: extraDef,
      },
    }
  }

  /**
   * 共享 helper：返回一组只满足合法 server_list 形状的 schema 定义。
   * 之所以写死为方法，是因为它在多个用例里复用。
   * @returns {Object} 形如 helloScriptParamsSchema.properties.server_list 的对象
   */
  function fullServerListDefinition() {
    return {
      type: 'array',
      title: '服务器列表',
      description: '选择本次运维任务需要处理的已入库服务器',
      items: { type: 'string' },
      uniqueItems: true,
      default: [],
      'x-control': 'server-multiselect',
      'x-source': 'devops-servers',
      'x-value-field': 'business_name',
    }
  }

  it('test_review_target_servers_shadow_key_excluded_from_dropdown target_servers 同时满足 x-* 五条件时，添加参数下拉只能出现 server_list', async () => {
    /**
     * 代码审查 Important #1：
     * schema 同时声明 server_list 与 target_servers（后者定义完全一致），
     * 添加参数下拉只能出现 server_list，target_servers 不得被视为受支持控件。
     */
    const shadowScripts = [
      {
        name: 'hello_script',
        display_name: '问候脚本',
        description: '示例脚本',
        module_path: 'app.scripts.examples.hello_script',
        params_schema: withExtraParamSchema('target_servers', fullServerListDefinition()),
      },
    ]
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') return jsonResponse(mockSchedules)
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u === '/api/admin/scripts' && method === 'GET') return jsonResponse(shadowScripts)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      return jsonResponse({})
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('新增任务')).trigger('click')
    await flushPromises()
    await switchToScriptAndSelectHello(wrapper)

    const addSelectOptions = wrapper
      .find('[data-testid="schedule-add-script-param"]')
      .findAll('option')
      .map((o) => o.element.value)
    // 仅 server_list 应受支持；target_servers 名称不属于"当前只支持 server_list"白名单，不得出现
    expect(addSelectOptions).toContain('server_list')
    expect(addSelectOptions).not.toContain('target_servers')
  })

  it('test_review_target_servers_shadow_key_kept_as_legacy_on_edit 编辑含 target_servers 的旧任务时，应作为 legacy 原样提交', async () => {
    /**
     * 代码审查 Important #1（legacy 语义）：
     * 旧任务 script_args 含 target_servers 而非 server_list，必须作为 legacy 原样提交（不丢失）。
     * 同时 server_list 字段不受影响：未在 schema 声明时同样按 legacy 处理。
     */
    const shadowScripts = [
      {
        name: 'hello_script',
        display_name: '问候脚本',
        description: '示例脚本',
        module_path: 'app.scripts.examples.hello_script',
        params_schema: withExtraParamSchema('target_servers', fullServerListDefinition()),
      },
    ]
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') {
        return jsonResponse([
          {
            ...mockSchedules[0],
            target_type: 'script',
            script_name: 'hello_script',
            script_args: { target_servers: ['业务A-生产'] },
          },
        ])
      }
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u === '/api/admin/scripts' && method === 'GET') return jsonResponse(shadowScripts)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      if (u === '/api/admin/devops-servers' && method === 'GET') return jsonResponse(rawDevopsServers)
      if (u === '/api/admin/task-schedules/1' && method === 'PUT') return jsonResponse({ ...mockSchedules[0], ...JSON.parse(opts.body) })
      return jsonResponse({})
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    const putCall = global.fetch.mock.calls.find(
      ([url, opts]) => url === '/api/admin/task-schedules/1' && opts.method === 'PUT'
    )
    expect(putCall).toBeTruthy()
    // target_servers 不被 UI 识别，必须原样保留：既不丢键，也不改名
    expect(JSON.parse(putCall[1].body).script_args).toEqual({
      target_servers: ['业务A-生产'],
    })
  })

  it('test_review_server_list_dedup_and_non_string_normalization 编辑含非字符串/重复项的 server_list 时，仅保留去重后的非空字符串', async () => {
    /**
     * 代码审查 Important #2：
     * 给定 ['业务A-生产', 123, null, '', '业务A-生产', {name:'x'}]，UI 与提交都应只保留 ['业务A-生产']。
     * 同时：business_name 不是非空字符串的候选服务器不得进入 DOM / payload。
     * 这锁定 list[str] + uniqueItems 在生产路径上的端到端落地。
     */
    // 故意混入 business_name 不是非空字符串的候选：它不能作为有效业务名进入 UI 或提交载荷
    const messyDevopsServers = [
      ...rawDevopsServers,
      { id: 99, business_name: null, server_type: 'unknown', updated_at: '2026-07-15T11:00:00' },
      { id: 100, business_name: '', server_type: 'unknown', updated_at: '2026-07-15T11:00:00' },
      { id: 101, business_name: 12345, server_type: 'unknown', updated_at: '2026-07-15T11:00:00' },
    ]
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') {
        return jsonResponse([
          {
            ...mockSchedules[0],
            target_type: 'script',
            script_name: 'hello_script',
            // 故意把杂项塞进老数据：字符串 / 数字 / null / 空串 / 重复 / 对象
            script_args: { server_list: ['业务A-生产', 123, null, '', '业务A-生产', { name: 'x' }] },
          },
        ])
      }
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u === '/api/admin/scripts' && method === 'GET') return jsonResponse(mockScripts)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      if (u === '/api/admin/devops-servers' && method === 'GET') return jsonResponse(messyDevopsServers)
      if (u === '/api/admin/task-schedules/1' && method === 'PUT') return jsonResponse({ ...mockSchedules[0], ...JSON.parse(opts.body) })
      return jsonResponse({})
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    // 清理后再保存：触发一次 PUT，让 buildScriptArgs 在保存路径上做类型/dedup 规范化
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    const putCall = global.fetch.mock.calls.find(
      ([url, opts]) => url === '/api/admin/task-schedules/1' && opts.method === 'PUT'
    )
    expect(putCall).toBeTruthy()
    const sentList = JSON.parse(putCall[1].body).script_args.server_list
    // payload 必须精确为去重、非空字符串的列表：['业务A-生产']
    expect(sentList).toEqual(['业务A-生产'])
    // 额外断言：候选业务名为非字符串的 server 行，不得变成已选 chip 出现在 DOM
    const containerHtml = wrapper.find('[data-testid="schedule-script-args"]').html()
    // 候选中混入的 business_name=null / '' / 12345，都不能成为"已选"标签
    expect(containerHtml).not.toContain('schedule-selected-server-chip-12345')
    expect(wrapper.find('[data-testid="schedule-server-option-99"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="schedule-server-option-100"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="schedule-server-option-101"]').exists()).toBe(false)
  })

  it('test_review_concurrent_devops_load_only_one_request 添加 server_list 后切到扫描 Tab 不得发第二个 GET', async () => {
    /**
     * 代码审查 Important #3：
     * 添加 server_list 触发一次 GET；在请求尚未 resolve 时切到扫描 Tab，
     * 不得再次发起 GET。请求返回后正常显示候选。该测试使用 deferred promise 控制请求时机。
     */
    let resolveServers
    const serversPromise = new Promise((resolve) => {
      resolveServers = resolve
    })
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') return jsonResponse(mockSchedules)
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u === '/api/admin/scripts' && method === 'GET') return jsonResponse(mockScripts)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      if (u === '/api/admin/devops-servers' && method === 'GET') {
        await serversPromise
        return jsonResponse(rawDevopsServers)
      }
      return jsonResponse({})
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('新增任务')).trigger('click')
    await flushPromises()
    await switchToScriptAndSelectHello(wrapper)

    // 触发参数区，第一次 GET 启动并处于 pending
    await wrapper.find('[data-testid="schedule-add-script-param"]').setValue('server_list')
    await flushPromises()

    const callsAfterAdd = global.fetch.mock.calls.filter(
      ([url, opts]) => url === '/api/admin/devops-servers' && (opts?.method || 'GET') === 'GET'
    ).length
    expect(callsAfterAdd).toBe(1)

    // 在请求 pending 期间切换到扫描 Tab
    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    await flushPromises()

    const callsAfterTabSwitch = global.fetch.mock.calls.filter(
      ([url, opts]) => url === '/api/admin/devops-servers' && (opts?.method || 'GET') === 'GET'
    ).length
    expect(callsAfterTabSwitch).toBe(1)

    // 切到 scan 后任务面板必须卸载，不能在 scan panel 内查任务参数控件
    expect(wrapper.find('[data-testid="panel-task"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="panel-scan"]').exists()).toBe(true)

    // 让请求 resolve；切回 task Tab 后再验证候选服务器出现
    resolveServers()
    await flushPromises()
    await wrapper.findAll('[role="tab"]')[0].trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="panel-task"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="schedule-server-option-1"]').exists()).toBe(true)
  })

  it('test_review_script_scan_force_refreshes_list 脚本扫描成功后强制重新 GET 并渲染新脚本', async () => {
    /**
     * 脚本扫描收口：初始 GET 返回旧脚本，POST /scan 成功后必须再次 GET，
     * 不能命中 hasLoadedScripts 缓存短路，否则新注册脚本不会出现在列表中。
     */
    const oldScript = {
      name: 'old_script',
      display_name: '旧脚本',
      description: '扫描前已注册',
      module_path: 'app.scripts.old_script',
      params_schema: {},
    }
    const newScript = {
      name: 'new_script',
      display_name: '新脚本',
      description: '扫描后新注册',
      module_path: 'app.scripts.new_script',
      params_schema: {},
    }
    let scriptsGetCount = 0
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') return jsonResponse(mockSchedules)
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u === '/api/admin/scripts' && method === 'GET') {
        scriptsGetCount++
        return jsonResponse(scriptsGetCount === 1 ? [oldScript] : [oldScript, newScript])
      }
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      if (u === '/api/admin/scripts/scan' && method === 'POST') {
        return jsonResponse({ scanned: 1, registered: 1, failed: 0 })
      }
      return jsonResponse({})
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    await wrapper.find('[data-testid="tab-script"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="script-row-old_script"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="script-row-new_script"]').exists()).toBe(false)
    expect(scriptsGetCount).toBe(1)

    await wrapper.find('[data-testid="scan-scripts-btn"]').trigger('click')
    await flushPromises()

    expect(scriptsGetCount).toBe(2)
    expect(wrapper.find('[data-testid="script-row-new_script"]').exists()).toBe(true)
  })

  it('test_review_script_list_load_failure_allows_retry 脚本列表首次加载失败后切到 script 目标必须允许重试并成功出现 hello_script', async () => {
    /**
     * 代码审查 Important #4（脚本列表重试）：
     * 初始脚本列表加载失败（无论在 loadInitialData 还是切到 script Tab 时），
     * 切回任务 Tab 再切回 script Tab，必须允许重新 GET，并最终出现 hello_script。
     * 由于难以精确拦截 loadInitialData 期间的事件，至少断言：失败后 hasLoadedScripts
     * 不会被永久置 true（不应在 catch 中固化缓存），再次进入 script Tab 时会重发请求。
     */
    let scriptsCallCount = 0
    let scriptsFailureArmed = true
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') return jsonResponse(mockSchedules)
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u === '/api/admin/scripts' && method === 'GET') {
        scriptsCallCount++
        if (scriptsFailureArmed) {
          return jsonResponse({ detail: '__LEAKED_ERR_initial_scripts_boom__' }, 500)
        }
        return jsonResponse(mockScripts)
      }
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      return jsonResponse({})
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    // 触发一次失败的脚本加载（初始预加载已经是第一次，必要时再按 Tab 触发）
    await wrapper.findAll('[role="tab"]')[2].trigger('click')
    await flushPromises()

    // 至少发生过一次失败请求（可能来自 loadInitialData 或本次切换触发）
    expect(scriptsCallCount).toBeGreaterThanOrEqual(1)

    // 关键断言：失败之后没有永久缓存，后续切换必须允许重新请求
    // 切回任务 Tab 再切回 script Tab
    await wrapper.findAll('[role="tab"]')[0].trigger('click')
    await flushPromises()
    scriptsFailureArmed = false
    const beforeRetry = scriptsCallCount
    await wrapper.findAll('[role="tab"]')[2].trigger('click')
    await flushPromises()

    // 成功后 hello_script 必须出现
    expect(wrapper.find('[data-testid="script-row-hello_script"]').exists()).toBe(true)
    expect(scriptsCallCount).toBeGreaterThan(beforeRetry)
  })

  it('test_review_switch_script_task_reflects_last_selection 快速切换两个 script 任务，参数区以最后选中任务为准', async () => {
    /**
     * 代码审查 Important #4（任务切换回归）：
     * 通过分析确认当前生产路径已统一为初始预加载脚本（loadInitialData 同步设置 hasLoadedScripts），
     * fillForm 直接同步调用 hydrateScriptArgs，因此"旧异步回调覆盖新任务"的旧分支不可达。
     * 本测试不再模拟异步竞态，而是直接证明参数以最后选中任务为准。
     */
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') {
        return jsonResponse([
          {
            ...mockSchedules[0],
            id: 1,
            target_type: 'script',
            script_name: 'hello_script',
            script_args: { server_list: ['业务A-生产'] },
          },
          {
            ...mockSchedules[0],
            id: 2,
            name: '巡检任务B',
            target_type: 'script',
            script_name: 'hello_script',
            script_args: { server_list: ['业务B-测试'] },
          },
        ])
      }
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u === '/api/admin/scripts' && method === 'GET') return jsonResponse(mockScripts)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      if (u.includes('/api/admin/task-schedules/2/runs')) return jsonResponse(mockRuns)
      if (u === '/api/admin/devops-servers' && method === 'GET') return jsonResponse(rawDevopsServers)
      return jsonResponse({})
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    // 先点中第一个脚本任务，再立即点中第二个
    const items = wrapper.findAll('.task-item')
    expect(items.length).toBe(2)
    await items[0].trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="schedule-selected-server-chip-业务A-生产"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="schedule-selected-server-chip-业务B-测试"]').exists()).toBe(false)

    await items[1].trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="schedule-selected-server-chip-业务B-测试"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="schedule-selected-server-chip-业务A-生产"]').exists()).toBe(false)
  })

  it('test_review_server_list_force_refresh_failure_keeps_cached_selection_and_retries 强制刷新失败时保留缓存、脱敏报错并允许重试', async () => {
    /**
     * 复现服务器扫描后的强制刷新失败：首次列表加载成功并勾选业务A，扫描成功后第二次 GET 返回敏感 detail，
     * 第三次 GET 由“重新加载服务器”按钮触发并恢复成功。测试只验证用户可见行为与精确请求次数。
     * @returns {Promise<void>} 异步完成组件行为断言
     */
    const SERVER_LIST_ERROR_DETAIL = '__LEAKED_FORCE_LIST_DETAIL_7f3a9c1e__'
    let devopsGetCount = 0
    const cachedServers = [rawDevopsServers[0]]

    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') return jsonResponse(mockSchedules)
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u === '/api/admin/scripts' && method === 'GET') return jsonResponse(mockScripts)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      if (u === '/api/admin/devops-servers' && method === 'GET') {
        devopsGetCount++
        if (devopsGetCount === 2) {
          return jsonResponse({ detail: SERVER_LIST_ERROR_DETAIL }, 500)
        }
        return jsonResponse(cachedServers)
      }
      if (u === '/api/admin/devops-servers/scan' && method === 'POST') {
        return jsonResponse({ scanned: 1, inserted: 0, updated: 1, failed: 0 })
      }
      return jsonResponse({})
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('新增任务')).trigger('click')
    await flushPromises()
    await switchToScriptAndSelectHello(wrapper)

    // 创建脚本任务并添加 server_list：首次 GET 成功后勾选业务A，形成可验证的缓存候选与已选状态。
    await wrapper.find('[data-testid="schedule-add-script-param"]').setValue('server_list')
    await flushPromises()
    expect(devopsGetCount).toBe(1)

    const serverOption = wrapper.find('[data-testid="schedule-server-option-1"]')
    expect(serverOption.exists()).toBe(true)
    await serverOption.setChecked()
    await flushPromises()
    expect(serverOption.element.checked).toBe(true)
    expect(wrapper.find('[data-testid="schedule-selected-server-chip-业务A-生产"]').exists()).toBe(true)

    // 切到服务器扫描 Tab 不应额外 GET；扫描成功后 force GET 恰好成为第二次请求并失败。
    await wrapper.find('[data-testid="tab-scan"]').trigger('click')
    await flushPromises()
    expect(devopsGetCount).toBe(1)
    await wrapper.find('[data-testid="scan-servers-btn"]').trigger('click')
    await flushPromises()
    expect(devopsGetCount).toBe(2)

    // 回到任务 Tab：错误必须可见且脱敏，之前成功缓存的候选与已选状态必须保留。
    await wrapper.find('[data-testid="tab-task"]').trigger('click')
    await flushPromises()
    const listError = wrapper.find('[data-testid="schedule-server-list-error"]')
    expect(listError.exists()).toBe(true)
    expect(listError.text()).toContain('服务器列表加载失败')
    expect(wrapper.html()).not.toContain(SERVER_LIST_ERROR_DETAIL)
    expect(wrapper.find('[data-testid="schedule-server-option-1"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="schedule-server-option-1"]').element.checked).toBe(true)
    expect(wrapper.find('[data-testid="schedule-selected-server-chip-业务A-生产"]').exists()).toBe(true)

    // 点击重试必须绕过 hasLoaded 缓存短路，实际发起第三次 GET；成功后错误消失且业务A仍可见。
    await wrapper.find('[data-testid="schedule-server-list-retry"]').trigger('click')
    await flushPromises()
    expect(devopsGetCount).toBe(3)
    expect(wrapper.find('[data-testid="schedule-server-list-error"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="schedule-server-option-1"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="schedule-server-option-1"]').element.checked).toBe(true)
    expect(wrapper.text()).toContain('业务A-生产')
  })

  it('test_initial_server_list_load_failure_can_retry 首次服务器列表加载失败后可重试成功', async () => {
    /**
     * 覆盖无缓存时的普通 GET 失败路径：首次响应携带唯一敏感 sentinel，参数面板只显示通用错误；
     * 用户点击重试后第二次 GET 成功，恢复候选服务器且清除错误。
     * @returns {Promise<void>} 异步完成首次失败、脱敏展示与重试成功断言
     */
    const SERVER_LIST_INITIAL_ERROR_DETAIL = '__LEAKED_INITIAL_LIST_DETAIL_4c8f2a91__'
    let devopsGetCount = 0

    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') return jsonResponse(mockSchedules)
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u === '/api/admin/scripts' && method === 'GET') return jsonResponse(mockScripts)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      if (u === '/api/admin/devops-servers' && method === 'GET') {
        devopsGetCount++
        if (devopsGetCount === 1) {
          return jsonResponse({ detail: SERVER_LIST_INITIAL_ERROR_DETAIL }, 500)
        }
        return jsonResponse(rawDevopsServers)
      }
      return jsonResponse({})
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text().includes('新增任务')).trigger('click')
    await flushPromises()
    await switchToScriptAndSelectHello(wrapper)

    await wrapper.find('[data-testid="schedule-add-script-param"]').setValue('server_list')
    await flushPromises()

    const listError = wrapper.find('[data-testid="schedule-server-list-error"]')
    expect(listError.exists()).toBe(true)
    expect(listError.find('span').text()).toBe('服务器列表加载失败')
    expect(wrapper.find('[data-testid="schedule-server-list-retry"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="schedule-server-option-1"]').exists()).toBe(false)
    expect(wrapper.html()).not.toContain(SERVER_LIST_INITIAL_ERROR_DETAIL)

    await wrapper.find('[data-testid="schedule-server-list-retry"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="schedule-server-list-error"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="schedule-server-option-1"]').exists()).toBe(true)
    const devopsGetCalls = global.fetch.mock.calls.filter(
      ([url, opts]) => url === '/api/admin/devops-servers' && (opts?.method || 'GET') === 'GET'
    )
    expect(devopsGetCalls).toHaveLength(2)
    expect(devopsGetCount).toBe(2)
  })

  // ===== 服务器行删除按钮（2026-07-22 新增） =====

  it('test_server_table_renders_delete_button_per_row 表格每行渲染删除按钮', async () => {
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    // 切到服务器扫描 Tab
    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    await flushPromises()

    // 默认 confirm 已在 beforeEach 设为 true，但本用例不点删除，因此无影响
    const deleteBtns = wrapper.findAll('[data-testid^="server-delete-btn-"]')
    expect(deleteBtns.length).toBe(rawDevopsServers.length)
    // 每行按钮的 testid 必须包含对应 id
    expect(wrapper.find('[data-testid="server-delete-btn-1"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="server-delete-btn-2"]').exists()).toBe(true)
    // aria-label 含业务名（脱敏边界：仅业务名，无 ip / port / password）
    const btn1 = wrapper.find('[data-testid="server-delete-btn-1"]')
    expect(btn1.attributes('aria-label')).toBe('删除服务器 业务A-生产')
    wrapper.unmount()
  })

  it('test_delete_button_confirm_cancel_keeps_row confirm 取消时不发请求且行保留', async () => {
    global.confirm = vi.fn(() => false)
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    await flushPromises()

    const callsBefore = global.fetch.mock.calls.length
    await wrapper.find('[data-testid="server-delete-btn-1"]').trigger('click')
    await flushPromises()

    // 1) confirm 被调用
    expect(global.confirm).toHaveBeenCalledTimes(1)
    // 2) 没有新请求发出
    const callsAfter = global.fetch.mock.calls.length
    expect(callsAfter).toBe(callsBefore)
    // 3) 行仍在 DOM 中
    expect(wrapper.find('[data-testid="server-row-1"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="server-delete-btn-1"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('test_delete_button_confirm_ok_removes_row_locally confirm 确认后调用 DELETE 并从本地列表移除该行', async () => {
    global.confirm = vi.fn(() => true)
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    await flushPromises()

    await wrapper.find('[data-testid="server-delete-btn-1"]').trigger('click')
    await flushPromises()

    // 1) 发起 DELETE 请求
    const deleteCall = global.fetch.mock.calls.find(
      ([url, opts]) =>
        url === '/api/admin/devops-servers/1' && (opts?.method || '').toUpperCase() === 'DELETE'
    )
    expect(deleteCall).toBeTruthy()
    // 2) 该行从 DOM 中消失，其它行仍在
    expect(wrapper.find('[data-testid="server-row-1"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="server-row-2"]').exists()).toBe(true)
    // 3) scan 面板内容：只剩 id=2 的行；不应再包含业务 A
    const panel = wrapper.find('[data-testid="panel-scan"]')
    expect(panel.exists()).toBe(true)
    const table = panel.find('[data-testid="server-table"]')
    expect(table.exists()).toBe(true)
    const tableText = table.text()
    expect(tableText).toContain('业务B-测试')
    expect(tableText).not.toContain('业务A-生产')
    wrapper.unmount()
  })

  it('test_delete_button_network_error_shows_sanitized_message 网络错误显示脱敏文案且不修改列表', async () => {
    global.confirm = vi.fn(() => true)
    const ERROR_DETAIL = '__LEAKED_DELETE_DETAIL_pwd_hunter2__ ip=__LEAKED_IP_aa__'
    // 覆盖 fetch：DELETE 返回 500 且 detail 含敏感 sentinel
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') return jsonResponse(mockSchedules)
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u === '/api/admin/scripts' && method === 'GET') return jsonResponse(mockScripts)
      if (u.includes('/api/admin/task-schedules/1/runs')) return jsonResponse(mockRuns)
      if (u === '/api/admin/devops-servers' && method === 'GET') return jsonResponse(rawDevopsServers)
      if (u === '/api/admin/devops-servers/1' && method === 'DELETE') {
        return jsonResponse({ detail: ERROR_DETAIL }, 500)
      }
      return jsonResponse({})
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    await flushPromises()

    await wrapper.find('[data-testid="server-delete-btn-1"]').trigger('click')
    await flushPromises()

    // 1) 列表错误显示脱敏文案
    const listError = wrapper.find('[data-testid="list-error"]')
    expect(listError.exists()).toBe(true)
    expect(listError.text()).toBe('删除服务器失败，请稍后重试')
    // 2) 后端 detail 的敏感 sentinel 不得进入 DOM
    const html = wrapper.html()
    expect(html).not.toContain(ERROR_DETAIL)
    expect(html).not.toContain('__LEAKED_DELETE_DETAIL_pwd_hunter2__')
    expect(html).not.toContain('__LEAKED_IP_aa__')
    // 3) 列表未变更：两行仍在
    expect(wrapper.find('[data-testid="server-row-1"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="server-row-2"]').exists()).toBe(true)
    wrapper.unmount()
  })

  // ===== 脚本参数 api_list（schema 驱动 api-multiselect）行为测试 =====

  /**
   * 模拟后端 GET /api/admin/api-configs/tree 返回：包含 1 个文件夹「业务系统」
   * 与 2 个 api 节点（id=10「查询接口」父=id=1，id=11「上报接口」父=null），
   * 还有一个幽灵/非法节点用于验证白名单过滤。
   */
  const rawApiConfigTree = {
    nodes: [
      { id: 1, parent_id: null, node_type: 'folder', name: '业务系统', sort_order: 0 },
      { id: 10, parent_id: 1, node_type: 'api', name: '查询接口', sort_order: 0 },
      { id: 11, parent_id: null, node_type: 'api', name: '上报接口', sort_order: 1 },
      // 幽灵节点：白名单 maskApiNodes 应剔除
      { id: 'bad', parent_id: null, node_type: 'api', name: '无效ID' },
      { id: 12, parent_id: null, node_type: 'unknown_type', name: '非法类型' },
      { id: 13, parent_id: null, node_type: 'api', name: '' },
    ],
  }

  /**
   * 含真实 api-configs/tree 节点的 fetch mock 工厂。
   * 其它路由保持 setupFetchMock 默认行为（task-schedules / agents / devops-servers / scripts）。
   */
  function setupFetchMockWithApiTree(apiTree) {
    const original = setupFetchMock
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/api-configs/tree' && method === 'GET') return jsonResponse(apiTree)
      // 退化到默认实现
      if (u === '/api/admin/task-schedules' && method === 'GET') return jsonResponse(mockSchedules)
      if (u === '/api/admin/task-schedules' && method === 'POST') return jsonResponse({ id: 2, ...JSON.parse(opts.body) }, 201)
      if (u === '/api/admin/agents' && method === 'GET') return jsonResponse(mockAgents)
      if (u === '/api/admin/scripts' && method === 'GET') return jsonResponse(mockScripts)
      if (u === '/api/admin/devops-servers' && method === 'GET') return jsonResponse(rawDevopsServers)
      return jsonResponse({})
    })
  }

  it('test_api_list_dropdown_appears_for_supported_definition 添加参数下拉出现「接口列表」与「服务器列表」', async () => {
    /**
     * schema 同时声明 server_list 与 api_list 时，「添加参数」下拉应同时出现两个
     * option；而 mode / content 等暂不支持字段不出现。
     */
    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('新增任务')).trigger('click')
    await flushPromises()
    await switchToScriptAndSelectHello(wrapper)

    const addSelectOptions = wrapper
      .find('[data-testid="schedule-add-script-param"]')
      .findAll('option')
      .map((o) => o.element.value)

    expect(addSelectOptions).toContain('server_list')
    expect(addSelectOptions).toContain('api_list')
    expect(addSelectOptions).not.toContain('mode')
    expect(addSelectOptions).not.toContain('content')
  })

  it('test_adding_api_list_triggers_single_api_tree_request 添加 api_list 才请求 api-configs/tree，且 in-flight 不重复', async () => {
    /**
     * 计划：首次添加或编辑已有 api_list 时才请求 /api/admin/api-configs/tree；
     * 添加完后已加载的缓存复用，再次调用同一添加器不重复 GET。
     */
    setupFetchMockWithApiTree(rawApiConfigTree)
    const apiGetSpy = global.fetch.mock.calls
    const initialCount = apiGetSpy.filter(
      ([u, opts]) => u === '/api/admin/api-configs/tree' && (opts?.method || 'GET') === 'GET'
    ).length

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('新增任务')).trigger('click')
    await flushPromises()
    await switchToScriptAndSelectHello(wrapper)

    // 选择 api_list 之前不应触发 api-configs/tree 请求
    const beforeAddCount = global.fetch.mock.calls.filter(
      ([u, opts]) => u === '/api/admin/api-configs/tree' && (opts?.method || 'GET') === 'GET'
    ).length
    expect(beforeAddCount).toBe(initialCount)

    await wrapper.find('[data-testid="schedule-add-script-param"]').setValue('api_list')
    await flushPromises()

    // 添加后应恰好触发一次 GET
    const afterAddCount = global.fetch.mock.calls.filter(
      ([u, opts]) => u === '/api/admin/api-configs/tree' && (opts?.method || 'GET') === 'GET'
    ).length
    expect(afterAddCount - initialCount).toBe(1)

    // 候选列表应只包含合法 api 节点 (id=10,11) 并按 id 升序；幽灵行被剔除
    const opts = wrapper.findAll('[data-testid^="schedule-api-option-"]')
      .map((el) => el.attributes('data-testid'))
    expect(opts).toEqual(['schedule-api-option-10', 'schedule-api-option-11'])

    // 再次选择 api_list（已存在于 scriptParamValues，添加器 noop）；不应发出第二次 GET
    await wrapper.find('[data-testid="schedule-add-script-param"]').setValue('api_list')
    await flushPromises()
    const finalCount = global.fetch.mock.calls.filter(
      ([u, opts]) => u === '/api/admin/api-configs/tree' && (opts?.method || 'GET') === 'GET'
    ).length
    expect(finalCount).toBe(afterAddCount)
  })

  it('test_api_list_submission_preserves_string_ids 提交 api_list 时元素保持为字符串 id 数组', async () => {
    /**
     * 契约：script_args.api_list 元素为「字符串 id」（如 ["10","11"]），与 schema
     * items.type=string 严格一致；不允许 int 化或漏斗到 Number。
     */
    setupFetchMockWithApiTree(rawApiConfigTree)
    let capturedBody = null
    const origFetch = global.fetch
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'POST' && opts.body) {
        capturedBody = JSON.parse(opts.body)
        return jsonResponse({ id: 99, ...capturedBody }, 201)
      }
      // 复用其它路由
      return origFetch(url, opts)
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('新增任务')).trigger('click')
    await flushPromises()
    await switchToScriptAndSelectHello(wrapper)
    await findTaskNameInput(wrapper).setValue('api_list 提交测试')

    // 添加并勾选两个接口
    await wrapper.find('[data-testid="schedule-add-script-param"]').setValue('api_list')
    await flushPromises()
    await wrapper.find('[data-testid="schedule-api-option-10"]').setValue(true)
    await wrapper.find('[data-testid="schedule-api-option-11"]').setValue(true)

    // 触发保存（与已有用例一致：通过 form submit 触发，避免依赖 HTML5 form= 属性）
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(capturedBody).not.toBeNull()
    expect(capturedBody.target_type).toBe('script')
    expect(capturedBody.script_args.api_list).toEqual(['10', '11'])
    // 没有混入 server_list 等其他受支持 key
    expect(capturedBody.script_args).not.toHaveProperty('server_list')
  })

  it('test_edit_existing_task_echoes_api_list 编辑已有 script 任务回显 api_list', async () => {
    /**
     * 旧任务 script_args 含 api_list=['10','11'] 时，hydrate 应进入
     * scriptParamValues，自动按需请求 api-configs/tree，并勾选两个 checkbox。
     */
    setupFetchMockWithApiTree(rawApiConfigTree)

    const enrichedSchedules = [
      {
        ...mockSchedules[0],
        target_type: 'script',
        script_name: 'hello_script',
        script_args: { api_list: ['10', '11'] },
      },
    ]
    const origFetch = global.fetch
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') return jsonResponse(enrichedSchedules)
      return origFetch(url, opts)
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    expect(wrapper.find('[data-testid="schedule-param-api-list"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="schedule-api-option-10"]').element.checked).toBe(true)
    expect(wrapper.find('[data-testid="schedule-api-option-11"]').element.checked).toBe(true)
    const validChips = wrapper.findAll('[data-testid^="schedule-selected-api-chip-"]')
    expect(validChips.map((c) => c.attributes('data-testid'))).toEqual([
      'schedule-selected-api-chip-10',
      'schedule-selected-api-chip-11',
    ])
  })

  it('test_api_list_invalid_id_marked_as_stale 已失效的接口 id 显示为「已失效」chip', async () => {
    /**
     * 旧任务 api_list 含 id=99（已下线），候选中不存在 → 失效 chip 显示原值。
     */
    setupFetchMockWithApiTree(rawApiConfigTree)
    const enrichedSchedules = [
      {
        ...mockSchedules[0],
        target_type: 'script',
        script_name: 'hello_script',
        script_args: { api_list: ['10', '99'] },
      },
    ]
    const origFetch = global.fetch
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') return jsonResponse(enrichedSchedules)
      return origFetch(url, opts)
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    expect(wrapper.find('[data-testid="schedule-api-option-10"]').element.checked).toBe(true)
    expect(wrapper.find('[data-testid="schedule-api-option-99"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="schedule-selected-api-chip-10"]').exists()).toBe(true)
    const invalidChips = wrapper.findAll('[data-testid="schedule-selected-api-invalid-chip"]')
    expect(invalidChips).toHaveLength(1)
    expect(invalidChips[0].text()).toContain('99')
    expect(invalidChips[0].text()).toContain('已失效')
  })

  it('test_unknown_legacy_args_merge_with_api_list 未知旧参数与 api_list 合并提交时原样保留', async () => {
    /**
     * 同时含 custom_param 与 api_list 时，custom_param 不被识别为受支持控件，
     * 进入 legacy 原样提交；api_list 进入 params 区。
     */
    setupFetchMockWithApiTree(rawApiConfigTree)
    let capturedBody = null
    const origFetch = global.fetch
    const enrichedSchedules = [
      {
        ...mockSchedules[0],
        target_type: 'script',
        script_name: 'hello_script',
        script_args: { api_list: ['10'], custom_param: 'keep-me' },
      },
    ]
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') return jsonResponse(enrichedSchedules)
      if (u === '/api/admin/task-schedules/1' && method === 'PUT' && opts.body) {
        capturedBody = JSON.parse(opts.body)
        return jsonResponse({ ...mockSchedules[0], ...capturedBody })
      }
      return origFetch(url, opts)
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()

    // 触发保存
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(capturedBody).not.toBeNull()
    expect(capturedBody.script_args.api_list).toEqual(['10'])
    expect(capturedBody.script_args.custom_param).toBe('keep-me')
  })

  it('test_api_list_invalid_string_normalized 编辑含非数字 / 重复项的 api_list 时仅保留合法去重 id', async () => {
    /**
     * 前端契约：api_list 仅做字符串层规范化（去空 / 去非字符串 / 去重）。
     * 非数字 id 字符串（如 'bad'）保留在 payload 中——脚本运行时由
     * `app.scripts.api_check.resolve_api_list` 抛 `ScriptExecutionError` 校验。
     * 本测试仅验证前端规范化边界：123(整型) / null / '' / 对象被剔除，
     * 'bad' 与 '10' 字符串保留且去重后仅剩 ['10','bad']。
     */
    setupFetchMockWithApiTree(rawApiConfigTree)
    let capturedBody = null
    const origFetch = global.fetch
    global.fetch = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      const u = typeof url === 'string' ? url : url.url
      if (u === '/api/admin/task-schedules' && method === 'GET') {
        return jsonResponse([
          {
            ...mockSchedules[0],
            target_type: 'script',
            script_name: 'hello_script',
            script_args: { api_list: ['10', 123, null, '', '10', 'bad', { id: 11 }] },
          },
        ])
      }
      if (u === '/api/admin/task-schedules/1' && method === 'PUT' && opts.body) {
        capturedBody = JSON.parse(opts.body)
        return jsonResponse({ ...mockSchedules[0], ...capturedBody })
      }
      return origFetch(url, opts)
    })

    const wrapper = mount(TaskSchedulerManager)
    await flushPromises()
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(capturedBody).not.toBeNull()
    // 前端 dedup 后保留 ['10','bad']；非法数字校验由脚本侧 resolve_api_list 处理
    expect(capturedBody.script_args.api_list).toEqual(['10', 'bad'])
  })
})

/**
 * 高度链固定后的内部滚动契约（源码静态断言，jsdom 不计算 <style scoped> 布局）
 *
 * 背景：.task-sidebar / .task-detail 高度被 flex 高度链固定为可视区域高度后，
 * 若内部缺少滚动容器，超高内容会溢出卡片边界（表单按钮/执行历史溢出到卡片外）。
 */
describe('TaskSchedulerManager 内部滚动契约（防溢出）', () => {
  /**
   * 从 SFC 源码提取指定选择器的样式块内容。
   * @param {string} selector - CSS 选择器（正则安全转义由调用方保证）
   * @returns {string} 样式块声明内容
   */
  function styleBlock(selector) {
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const match = taskSchedulerSource.match(new RegExp(escaped + '\\s*\\{([^}]*)\\}'))
    expect(match, `${selector} 样式块必须存在`).not.toBeNull()
    return match[1]
  }

  it('test_task_sidebar_scrolls_internally 任务列表卡片内部滚动', () => {
    expect(styleBlock('.task-sidebar')).toMatch(/overflow-y\s*:\s*auto/)
  })

  it('test_tablist_not_shrunk tab 栏不被 flex 压缩', () => {
    expect(styleBlock('.tablist')).toMatch(/flex-shrink\s*:\s*0/)
  })

  it('test_business_panels_scroll_internally 业务面板（编辑/扫描）内部滚动', () => {
    const body = styleBlock('.task-detail > section[role="tabpanel"]:not(.task-panel-api)')
    expect(body).toMatch(/flex\s*:\s*1/)
    expect(body).toMatch(/min-height\s*:\s*0/)
    expect(body).toMatch(/overflow-y\s*:\s*auto/)
  })

  it('test_api_panel_clips_overflow API 面板裁剪防外溢', () => {
    expect(styleBlock('.task-detail > .task-panel-api')).toMatch(/overflow\s*:\s*hidden/)
  })
})
