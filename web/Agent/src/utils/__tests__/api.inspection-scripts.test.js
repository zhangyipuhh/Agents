/**
 * 巡检脚本库 API 测试（2026-08-04 新增）
 *
 * 覆盖：updateInspectionScript / updateDevOpsServerInspectionScript URL /
 * 方法 / 请求体 / 失败抛错。
 * 列表 / 扫描 / 详情由 TaskSchedulerManager.spec.js 端到端覆盖。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

describe('巡检脚本库 API', () => {
  let originalFetch
  let originalLocalStorage

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
    global.fetch = vi.fn()
    global.localStorage = {
      getItem: vi.fn((key) => (key === 'auth_token' ? 'fake-token' : null)),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    }
  })

  afterEach(() => {
    global.fetch = originalFetch
    global.localStorage = originalLocalStorage
  })

  it('test_update_inspection_script_calls_put_url 正确调用 PUT /api/admin/inspection-scripts/{id}', async () => {
    const { updateInspectionScript } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: 1, name: 'linux-bash', display_name: 'Linux Bash' }),
    })
    await updateInspectionScript(1, { display_name: 'Linux Bash' })
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/admin/inspection-scripts/1',
      expect.objectContaining({ method: 'PUT' })
    )
  })

  it('test_update_inspection_script_sends_payload 提交时附带业务字段', async () => {
    const { updateInspectionScript } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: 1, name: 'linux-bash' }),
    })
    const payload = {
      display_name: 'Linux Bash',
      platform: 'linux',
      version: 'bash',
      inspection_parser: 'json',
      inspection_script: 'echo manual',
      inspection_fields: [],
    }
    await updateInspectionScript(1, payload)
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/admin/inspection-scripts/1',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify(payload),
      })
    )
  })

  it('test_update_inspection_script_404_throws 404 抛错且不回显 id', async () => {
    const { updateInspectionScript } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: async () => ({ detail: '脚本不存在' }),
    })
    await expect(
      updateInspectionScript(9999, { display_name: 'X' })
    ).rejects.toThrow('脚本不存在')
  })

  it('test_update_inspection_script_500_throws 500 抛错', async () => {
    const { updateInspectionScript } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'InspectionScriptService not initialized' }),
    })
    await expect(
      updateInspectionScript(1, { display_name: 'X' })
    ).rejects.toThrow('InspectionScriptService not initialized')
  })
})

/**
 * 巡检脚本下拉即时保存 API 测试（2026-08-04 新增）
 *
 * 覆盖：
 * - updateDevOpsServerInspectionScript URL / HTTP 方法 / Content-Type
 * - 数字 script_id 走 JSON 序列化原值
 * - null / undefined 走 null 解绑（与 ``??? null`` 语义一致）
 * - 非空失败响应回传后端 ``detail``，避免显示 "[object Object]"
 */
describe('服务器巡检脚本绑定 API', () => {
  let originalFetch
  let originalLocalStorage

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
    global.fetch = vi.fn()
    global.localStorage = {
      getItem: vi.fn((key) => (key === 'auth_token' ? 'fake-token' : null)),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    }
  })

  afterEach(() => {
    global.fetch = originalFetch
    global.localStorage = originalLocalStorage
  })

  it('test_bind_server_inspection_script_url_method 正确调用 PUT /api/admin/devops-servers/{serverId}/inspection-script', async () => {
    const { updateDevOpsServerInspectionScript } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        id: 1,
        business_name: 'alpha',
        server_type: 'linux',
        inspection_script_id: 42,
        inspection_script_name: 'linux-bash-alt',
        inspection_script_display_name: 'Linux Bash 巡检（备用）',
      }),
    })
    await updateDevOpsServerInspectionScript(1, 42)
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/admin/devops-servers/1/inspection-script',
      expect.objectContaining({ method: 'PUT' })
    )
  })

  it('test_bind_server_inspection_script_sends_number_id 数字 id 原样写入 body', async () => {
    const { updateDevOpsServerInspectionScript } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    })
    await updateDevOpsServerInspectionScript(7, 42)
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/admin/devops-servers/7/inspection-script',
      expect.objectContaining({
        method: 'PUT',
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ inspection_script_id: 42 }),
      })
    )
  })

  it('test_bind_server_inspection_script_null_for_unbind 传 null 解绑时写入 { inspection_script_id: null }', async () => {
    const { updateDevOpsServerInspectionScript } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    })
    await updateDevOpsServerInspectionScript(7, null)
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/admin/devops-servers/7/inspection-script',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ inspection_script_id: null }),
      })
    )
  })

  it('test_bind_server_inspection_script_undefined_for_unbind undefined 走 null', async () => {
    const { updateDevOpsServerInspectionScript } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    })
    await updateDevOpsServerInspectionScript(7, undefined)
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/admin/devops-servers/7/inspection-script',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ inspection_script_id: null }),
      })
    )
  })

  it('test_bind_server_inspection_script_404_throws 404 回传后端 detail（巡检脚本不存在）', async () => {
    const { updateDevOpsServerInspectionScript } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: async () => ({ detail: '巡检脚本不存在' }),
    })
    await expect(updateDevOpsServerInspectionScript(1, 9999)).rejects.toThrow('巡检脚本不存在')
  })

  it('test_bind_server_inspection_script_500_throws 500 回传后端 detail', async () => {
    const { updateDevOpsServerInspectionScript } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ detail: '更新巡检脚本失败' }),
    })
    await expect(updateDevOpsServerInspectionScript(1, 42)).rejects.toThrow('更新巡检脚本失败')
  })

  it('test_bind_server_inspection_script_invalid_server_id_throws 前端校验阻断请求，错误信息不回显 serverId', async () => {
    const { updateDevOpsServerInspectionScript } = await import('../api.js')
    await expect(updateDevOpsServerInspectionScript(null, 42)).rejects.toThrow(/serverId 不能为空/)
    expect(global.fetch).not.toHaveBeenCalled()
  })
})
