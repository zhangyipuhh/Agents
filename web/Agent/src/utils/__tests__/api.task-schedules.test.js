/**
 * 智能体定时任务 API 测试
 *
 * 覆盖：任务列表、新建、更新、删除、启停、立即运行、执行历史查询。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

describe('智能体定时任务 API', () => {
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

  it('test_fetch_task_schedules_calls_correct_url 获取任务列表调用正确地址', async () => {
    const { fetchTaskSchedules } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [{ id: 1, name: '每日巡检' }],
    })

    const result = await fetchTaskSchedules()

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/admin/task-schedules',
      expect.objectContaining({ method: 'GET' })
    )
    expect(result).toEqual([{ id: 1, name: '每日巡检' }])
  })

  it('test_create_task_schedule_posts_body 新建任务提交请求体', async () => {
    const { createTaskSchedule } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({ ok: true, status: 201, json: async () => ({ id: 1 }) })
    const payload = { name: '每日巡检', agent_name: 'map_agent', prompt: '检查', cron_expression: '0 9 * * *' }

    await createTaskSchedule(payload)

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/admin/task-schedules',
      expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) })
    )
  })

  it('test_update_task_schedule_puts_body 更新任务提交请求体', async () => {
    const { updateTaskSchedule } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ id: 1, name: '更新巡检' }) })
    const payload = { name: '更新巡检' }

    await updateTaskSchedule(1, payload)

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/admin/task-schedules/1',
      expect.objectContaining({ method: 'PUT', body: JSON.stringify(payload) })
    )
  })

  it('test_delete_task_schedule_uses_delete 删除任务使用 DELETE', async () => {
    const { deleteTaskSchedule } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({ ok: true, status: 204 })

    await deleteTaskSchedule(1)

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/admin/task-schedules/1',
      expect.objectContaining({ method: 'DELETE' })
    )
  })

  it('test_set_task_schedule_enabled_puts_enabled 启停任务提交 enabled', async () => {
    const { setTaskScheduleEnabled } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ id: 1, enabled: false }) })

    await setTaskScheduleEnabled(1, false)

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/admin/task-schedules/1/enabled',
      expect.objectContaining({ method: 'PUT', body: JSON.stringify({ enabled: false }) })
    )
  })

  it('test_trigger_task_schedule_posts_trigger 立即运行任务调用 trigger', async () => {
    const { triggerTaskSchedule } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({ ok: true, status: 202, json: async () => ({ id: 9, status: 'pending' }) })

    const result = await triggerTaskSchedule(1)

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/admin/task-schedules/1/trigger',
      expect.objectContaining({ method: 'POST' })
    )
    expect(result.id).toBe(9)
  })

  it('test_fetch_task_runs_calls_limit 查询执行历史带 limit', async () => {
    const { fetchTaskRuns } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({ ok: true, json: async () => [{ id: 1, status: 'success' }] })

    await fetchTaskRuns(1, 20)

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/admin/task-schedules/1/runs?limit=20',
      expect.objectContaining({ method: 'GET' })
    )
  })

  it('test_fetch_task_schedules_throws_detail 接口错误时抛出 detail', async () => {
    const { fetchTaskSchedules } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ detail: '服务不可用' }),
    })

    await expect(fetchTaskSchedules()).rejects.toThrow(/服务不可用/)
  })
})
