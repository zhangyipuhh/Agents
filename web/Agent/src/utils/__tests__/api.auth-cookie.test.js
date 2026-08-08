/**
 * HttpOnly Cookie 认证模式契约测试
 *
 * 验证 api.js 在 Cookie 模式下的核心契约：
 * - 不再从 localStorage 读取/写入 auth_token
 * - 不再注入 Authorization 头
 * - 所有请求携带 X-Requested-With: XMLHttpRequest（CSRF 防护头）
 * - 401 时通过 /api/auth/refresh 静默刷新 Cookie 并重试原请求
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

describe('api.js HttpOnly Cookie 认证模式', () => {
  let originalFetch
  let originalLocalStorage

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage
    global.fetch = vi.fn()
    global.localStorage = {
      getItem: vi.fn((key) => {
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

  it('test_fetch_with_auth_no_authorization 不注入 Authorization 头', async () => {
    const { fetchWithAuth } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({ ok: true, status: 200 })
    await fetchWithAuth('/api/session/list')
    const headers = global.fetch.mock.calls[0][1].headers
    expect(headers.Authorization).toBeUndefined()
  })

  it('test_fetch_with_auth_sends_csrf_header 携带 CSRF 防护头', async () => {
    const { fetchWithAuth } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({ ok: true, status: 200 })
    await fetchWithAuth('/api/session/list')
    expect(global.fetch.mock.calls[0][1].headers['X-Requested-With']).toBe('XMLHttpRequest')
  })

  it('test_fetch_with_auth_keeps_session_header 保留 X-Session-ID 注入', async () => {
    const { fetchWithAuth } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({ ok: true, status: 200 })
    await fetchWithAuth('/api/session/list')
    expect(global.fetch.mock.calls[0][1].headers['X-Session-ID']).toBe('fake-session')
  })

  it('test_fetch_with_auth_401_refresh_retry 401 时刷新 Cookie 并重试原请求', async () => {
    const { fetchWithAuth } = await import('../api.js')
    global.fetch
      .mockResolvedValueOnce({ ok: false, status: 401 })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ access_token: 'new', token_type: 'Bearer', expires_in: 30 }) })
      .mockResolvedValueOnce({ ok: true, status: 200 })
    const resp = await fetchWithAuth('/api/session/list')
    expect(resp.status).toBe(200)
    expect(global.fetch.mock.calls[1][0]).toBe('/api/auth/refresh')
    expect(global.fetch.mock.calls[2][0]).toBe('/api/session/list')
  })

  it('test_validate_token_no_authorization validateToken 不再读 localStorage token', async () => {
    const { validateToken } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ username: 'admin', role: 'admin' }) })
    const data = await validateToken()
    expect(data.username).toBe('admin')
    const headers = global.fetch.mock.calls[0][1].headers
    expect(headers?.Authorization).toBeUndefined()
  })

  it('test_refresh_token_no_localstorage_write refreshToken 不写 localStorage', async () => {
    const { refreshToken } = await import('../api.js')
    global.fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ access_token: 'new', token_type: 'Bearer', expires_in: 30 }) })
    await refreshToken()
    expect(global.localStorage.setItem).not.toHaveBeenCalled()
  })

  it('test_clear_auth_ignores_auth_token clearAuth 不再操作 auth_token', async () => {
    const { clearAuth } = await import('../api.js')
    clearAuth()
    expect(global.localStorage.removeItem).not.toHaveBeenCalledWith('auth_token')
  })

  it('test_get_auth_headers_contract getAuthHeaders 仅含 CSRF 头与 Session 头', async () => {
    const { getAuthHeaders } = await import('../api.js')
    const headers = getAuthHeaders()
    expect(headers.Authorization).toBeUndefined()
    expect(headers['X-Requested-With']).toBe('XMLHttpRequest')
    expect(headers['X-Session-ID']).toBe('fake-session')
  })
})
