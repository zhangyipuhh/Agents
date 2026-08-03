/**
 * 巡检脚本库 API 测试（2026-08-04 新增）
 *
 * 覆盖：updateInspectionScript URL / 方法 / 请求体 / 失败抛错。
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
