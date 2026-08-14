// -*- coding:utf-8 -*-
/**
 * config/portal.js 主题解析单测
 *
 * 覆盖契约：
 * - resolveThemeFromUrl 三层优先级：URL ?theme= > localStorage 'login_theme' > default
 * - setLoginTheme 校验白名单 + 同步 localStorage
 * - getCurrentLoginTheme 在 currentThemeKey 失效时回退 default
 * - loadAppConfig 向后兼容旧配置（仅含 brandTitle/brandDesc）
 *
 * 设计目标：保证「同一访问保持同一主题」在主题切换链路（URL/localStorage）的所有边界路径上正确。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'

// 在 import portal.js 之前 stub window，避免 happy-dom 默认值影响测试
const windowMock = {
  location: { search: '' },
  localStorage: (() => {
    const store = new Map()
    return {
      getItem: vi.fn((k) => (store.has(k) ? store.get(k) : null)),
      setItem: vi.fn((k, v) => { store.set(k, v) }),
      removeItem: vi.fn((k) => { store.delete(k) }),
      clear: vi.fn(() => { store.clear() })
    }
  })()
}

vi.stubGlobal('window', windowMock)
vi.stubGlobal('localStorage', windowMock.localStorage)

// 每个测试重置 localStorage 与 URL search
beforeEach(() => {
  windowMock.location.search = ''
  windowMock.localStorage.clear()
  vi.resetModules()
})

describe('config/portal.js 主题解析', () => {
  it('test_resolve_from_url_priority URL theme 优先于 localStorage', async () => {
    // localStorage 已存 xemployee，URL 指定 shenyang → URL 胜出
    windowMock.localStorage.setItem('login_theme', 'xemployee')
    windowMock.location.search = '?theme=shenyang'

    const portal = await import('../portal.js')
    // 加载默认 themes（不调 fetch），手动注入模拟 themes
    portal.appConfig.loginThemes = {
      default: portal.appConfig.loginThemes.default,
      shenyang: { brandTitle: '沈阳', brandDesc: '', loginTitle: '', loginSubtitle: '', registerSubtitle: '', footerText: '', footerLink: '', copyright: '' },
      xemployee: { brandTitle: 'X员工', brandDesc: '', loginTitle: '', loginSubtitle: '', registerSubtitle: '', footerText: '', footerLink: '', copyright: '' }
    }

    const result = portal.resolveThemeFromUrl()
    expect(result).toBe('shenyang')
    expect(portal.appConfig.currentThemeKey).toBe('shenyang')
  })

  it('test_resolve_fallback_to_localstorage URL 无 theme 时回退 localStorage', async () => {
    windowMock.localStorage.setItem('login_theme', 'xemployee')
    windowMock.location.search = ''

    const portal = await import('../portal.js')
    portal.appConfig.loginThemes = {
      default: portal.appConfig.loginThemes.default,
      xemployee: { brandTitle: 'X员工', brandDesc: '', loginTitle: '', loginSubtitle: '', registerSubtitle: '', footerText: '', footerLink: '', copyright: '' }
    }

    const result = portal.resolveThemeFromUrl()
    expect(result).toBe('xemployee')
    expect(portal.appConfig.currentThemeKey).toBe('xemployee')
  })

  it('test_resolve_invalid_url_theme_fallsback_to_localstorage URL 非法 theme 走 localStorage', async () => {
    windowMock.localStorage.setItem('login_theme', 'xemployee')
    windowMock.location.search = '?theme=NOT-EXIST'

    const portal = await import('../portal.js')
    portal.appConfig.loginThemes = {
      default: portal.appConfig.loginThemes.default,
      xemployee: { brandTitle: 'X员工', brandDesc: '', loginTitle: '', loginSubtitle: '', registerSubtitle: '', footerText: '', footerLink: '', copyright: '' }
    }

    const result = portal.resolveThemeFromUrl()
    expect(result).toBe('xemployee')
  })

  it('test_resolve_default_when_no_source 都没有时回退 default', async () => {
    windowMock.location.search = ''
    const portal = await import('../portal.js')
    // loginThemes 仅含 default
    portal.appConfig.loginThemes = { default: portal.appConfig.loginThemes.default }

    const result = portal.resolveThemeFromUrl()
    expect(result).toBe('default')
  })

  it('test_set_login_theme_persists_to_localstorage setLoginTheme 写入 localStorage', async () => {
    const portal = await import('../portal.js')
    portal.appConfig.loginThemes = {
      default: portal.appConfig.loginThemes.default,
      xemployee: { brandTitle: 'X员工', brandDesc: '', loginTitle: '', loginSubtitle: '', registerSubtitle: '', footerText: '', footerLink: '', copyright: '' }
    }

    const ok = portal.setLoginTheme('xemployee')
    expect(ok).toBe(true)
    expect(portal.appConfig.currentThemeKey).toBe('xemployee')
    expect(windowMock.localStorage.getItem('login_theme')).toBe('xemployee')
    // brandTitle 同步到 appConfig.brandTitle（PortalApp 顶部导航依赖）
    expect(portal.appConfig.brandTitle).toBe('X员工')
  })

  it('test_set_login_theme_rejects_invalid_key 非法 key 不写入', async () => {
    const portal = await import('../portal.js')
    const before = portal.appConfig.currentThemeKey

    const ok = portal.setLoginTheme('NOT-EXIST')
    expect(ok).toBe(false)
    expect(portal.appConfig.currentThemeKey).toBe(before)
  })

  it('test_get_current_login_theme_fallback 当前 key 失效时回退 default', async () => {
    const portal = await import('../portal.js')
    portal.appConfig.loginThemes = { default: portal.appConfig.loginThemes.default }
    portal.appConfig.currentThemeKey = 'NOT-EXIST'

    const theme = portal.getCurrentLoginTheme()
    expect(theme).toBeTruthy()
    expect(theme.brandTitle).toBe(portal.appConfig.loginThemes.default.brandTitle)
  })

  it('test_load_app_config_backward_compatible_old_schema 仅含 brandTitle/brandDesc 的旧 JSON 仍能加载', async () => {
    // mock fetch 返回旧 schema
    const oldData = {
      brandTitle: 'Legacy Brand',
      brandDesc: 'Legacy Desc',
      navItems: [
        { key: 'rule-lib', label: '规则库', type: 'iframe', url: '/knowledge.html' }
      ]
    }
    globalThis.fetch = vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve(oldData)
    }))

    const portal = await import('../portal.js')
    await portal.loadAppConfig()

    // default 主题必须存在且 brandTitle 与顶层 brandTitle 一致
    expect(portal.appConfig.loginThemes.default).toBeTruthy()
    expect(portal.appConfig.loginThemes.default.brandTitle).toBe('Legacy Brand')
    expect(portal.appConfig.brandTitle).toBe('Legacy Brand')
    // navItems 仍按旧逻辑解析
    expect(portal.appConfig.navItems.length).toBeGreaterThan(0)
  })

  it('test_load_app_config_parses_login_themes loginThemes 解析为 map', async () => {
    const newData = {
      brandTitle: 'Default',
      brandDesc: '',
      loginThemes: {
        default: { brandTitle: 'Default', brandDesc: '', loginTitle: '', loginSubtitle: '', registerSubtitle: '', footerText: '', footerLink: '', copyright: '' },
        shenyang: { brandTitle: '沈阳', brandDesc: '', loginTitle: '', loginSubtitle: '', registerSubtitle: '', footerText: '', footerLink: '', copyright: '' }
      },
      navItems: []
    }
    globalThis.fetch = vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve(newData)
    }))

    const portal = await import('../portal.js')
    await portal.loadAppConfig()

    expect(portal.appConfig.loginThemes.shenyang.brandTitle).toBe('沈阳')
    expect(Object.keys(portal.appConfig.loginThemes).length).toBe(2)
  })

  it('test_load_app_config_rejects_invalid_theme_key 非法 key 不入 map', async () => {
    const data = {
      brandTitle: 'Default',
      brandDesc: '',
      loginThemes: {
        default: { brandTitle: 'Default', brandDesc: '', loginTitle: '', loginSubtitle: '', registerSubtitle: '', footerText: '', footerLink: '', copyright: '' },
        'Bad Key!': { brandTitle: 'should be ignored', brandDesc: '', loginTitle: '', loginSubtitle: '', registerSubtitle: '', footerText: '', footerLink: '', copyright: '' }
      },
      navItems: []
    }
    globalThis.fetch = vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve(data)
    }))

    const portal = await import('../portal.js')
    await portal.loadAppConfig()

    expect(portal.appConfig.loginThemes['Bad Key!']).toBeUndefined()
  })

  it('test_resolve_accepts_uppercase_theme_key 大写主题 key 应当被允许（业务项目缩写）', async () => {
    // 业务场景：项目缩写用大写（如 YDT = 一点通），THEME_KEY_RE 必须兼容大小写
    windowMock.location.search = '?theme=YDT'

    const portal = await import('../portal.js')
    portal.appConfig.loginThemes = {
      default: portal.appConfig.loginThemes.default,
      YDT: { brandTitle: '沈阳市自然资源和规划\"一点通\"', brandDesc: '智慧政务服务平台', loginTitle: '', loginSubtitle: '', registerSubtitle: '', footerText: '', footerLink: '', copyright: '' }
    }

    const result = portal.resolveThemeFromUrl()
    expect(result).toBe('YDT')
    expect(portal.appConfig.currentThemeKey).toBe('YDT')
    expect(portal.appConfig.brandTitle).toBe('沈阳市自然资源和规划"一点通"')
  })

  it('test_load_app_config_accepts_uppercase_theme_key loadAppConfig 解析大写 key', async () => {
    const data = {
      brandTitle: 'Default',
      brandDesc: '',
      loginThemes: {
        default: { brandTitle: 'Default', brandDesc: '', loginTitle: '', loginSubtitle: '', registerSubtitle: '', footerText: '', footerLink: '', copyright: '' },
        YDT: { brandTitle: 'YDT', brandDesc: '', loginTitle: '', loginSubtitle: '', registerSubtitle: '', footerText: '', footerLink: '', copyright: '' },
        'ydt-dev': { brandTitle: 'YDT-DEV', brandDesc: '', loginTitle: '', loginSubtitle: '', registerSubtitle: '', footerText: '', footerLink: '', copyright: '' }
      },
      navItems: []
    }
    globalThis.fetch = vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve(data)
    }))

    const portal = await import('../portal.js')
    await portal.loadAppConfig()

    expect(portal.appConfig.loginThemes.YDT.brandTitle).toBe('YDT')
    expect(portal.appConfig.loginThemes['ydt-dev'].brandTitle).toBe('YDT-DEV')
  })

  it('test_load_app_config_resets_stale_theme_key 删除主题后 currentThemeKey 回退 default', async () => {
    // 模拟场景：旧配置有 YDT，新配置删除了 YDT
    // 浏览器侧内存里 currentThemeKey 仍指向 YDT（来自上次访问），
    // loadAppConfig 必须把 currentThemeKey 纠正回 default，否则 LoginView 会拿到"无效主题"
    const first = {
      brandTitle: 'Default',
      brandDesc: '',
      loginThemes: {
        default: { brandTitle: 'Default', brandDesc: '', loginTitle: '', loginSubtitle: '', registerSubtitle: '', footerText: '', footerLink: '', copyright: '' },
        YDT: { brandTitle: 'YDT', brandDesc: '', loginTitle: '', loginSubtitle: '', registerSubtitle: '', footerText: '', footerLink: '', copyright: '' }
      },
      navItems: []
    }
    const second = {
      brandTitle: 'Default',
      brandDesc: '',
      loginThemes: {
        default: { brandTitle: 'Default', brandDesc: '', loginTitle: '', loginSubtitle: '', registerSubtitle: '', footerText: '', footerLink: '', copyright: '' }
      },
      navItems: []
    }
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => first })
      .mockResolvedValueOnce({ ok: true, json: async () => second })

    const portal = await import('../portal.js')
    // 第一次加载：模拟"用户已使用 YDT 主题"
    await portal.loadAppConfig()
    portal.setLoginTheme('YDT')
    expect(portal.appConfig.currentThemeKey).toBe('YDT')

    // 第二次加载：模拟运维把 YDT 删了
    await portal.loadAppConfig()

    expect(portal.appConfig.currentThemeKey).toBe('default')
    expect(portal.appConfig.loginThemes.YDT).toBeUndefined()
    // brandTitle 同步到 default 的 brandTitle
    expect(portal.appConfig.brandTitle).toBe('Default')
  })
})