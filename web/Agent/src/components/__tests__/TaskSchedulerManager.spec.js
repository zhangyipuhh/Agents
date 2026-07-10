/**
 * TaskSchedulerManager 组件测试
 *
 * 覆盖：列表渲染、新增表单、保存任务、启停任务、立即运行、执行历史展示。
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

    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('周报任务')
    await inputs[1].setValue('0 10 * * 1')
    await wrapper.find('select').setValue('map_agent')
    await wrapper.find('textarea').setValue('生成周报')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    const postCall = global.fetch.mock.calls.find(([url, opts]) => url === '/api/admin/task-schedules' && opts.method === 'POST')
    expect(postCall).toBeTruthy()
    expect(JSON.parse(postCall[1].body).name).toBe('周报任务')
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
})
