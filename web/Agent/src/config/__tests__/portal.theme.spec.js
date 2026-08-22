// -*- coding:utf-8 -*-
/**
 * config/portal.js 主题解析单测
 *
 * 覆盖契约：
 * - resolveThemeFromUrl 三层优先级：URL ?theme= > localStorage 'login_theme' > default
 * - setLoginTheme 校验白名单 + 同步 localStorage
 * - getCurrentLoginTheme 在 currentThemeKey 失效时回退 default
 * - loadAppConfig 加载机制：JSON 仅补 JS DEFAULT_LOGIN_THEME 未声明字段
 * - 「JS DEFAULT_LOGIN_THEME 全局优先」(2026-08-20)：
 *   JS 已声明字段对 JSON 同名字段硬覆盖；JS 为空占位时 JSON 可接管
 *
 * 设计目标：保证「同一访问保持同一主题」在主题切换链路（URL/localStorage）的所有边界路径上正确，
 * 以及「JS 主配置源 / JSON 兜底」契约在双向场景下都可逆。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'

// 在 import portal.js 之前 stub window，避免 happy-dom 默认值影响测试
const windowMock = {
  location: { search: '', origin: 'http://localhost' },
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

    // default 主题必须存在（缺失时由 JS 兜底）
    expect(portal.appConfig.loginThemes.default).toBeTruthy()
    // 「JS DEFAULT_LOGIN_THEME 全局优先」(2026-08-20)：
    // JSON 顶层 brandTitle/brandDesc 与 loginThemes.default 同名字段不得覆盖 JS 已声明字段
    expect(portal.appConfig.loginThemes.default.brandTitle).toBe(portal.DEFAULT_LOGIN_THEME.brandTitle)
    expect(portal.appConfig.brandTitle).toBe(portal.DEFAULT_LOGIN_THEME.brandTitle)
    // navItems 仍按旧逻辑解析（导航项不参与 JS 全局优先契约）
    expect(portal.appConfig.navItems.length).toBeGreaterThan(0)
  })

  it('test_load_app_config_parses_login_themes loginThemes 解析为 map 且 JSON 全权', async () => {
    // 2026-08-21 反转契约：JSON 是主配置源，default 主题的 8 字段由 JSON 全权控制
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

    // 非 default 主题由 JSON 全权控制
    expect(portal.appConfig.loginThemes.shenyang.brandTitle).toBe('沈阳')
    expect(Object.keys(portal.appConfig.loginThemes).length).toBe(2)
    // default 主题的 brandTitle 由 JSON 提供（不再被 JS 字面量覆盖）
    expect(portal.appConfig.loginThemes.default.brandTitle).toBe('Default')
    // 顶层 brandTitle 也由 JSON 提供
    expect(portal.appConfig.brandTitle).toBe('Default')
  })

  it('test_json_takes_precedence_over_js_default 常规路径下 JSON 全权胜出', async () => {
    // 2026-08-21 反转契约：常规路径（非 portal redirect）下 JSON 是主配置源；
    // JSON 提供 brandTitle='X员工'，期望 X员工胜出，JS 字段不生效
    const jsonData = {
      brandTitle: 'X员工',
      brandDesc: '内测',
      loginThemes: {
        default: {
          brandTitle: 'X员工',
          brandDesc: '内测',
          loginTitle: 'JSON-LoginTitle',
          loginSubtitle: 'JSON-LoginSubtitle',
          registerSubtitle: 'JSON-RegisterSubtitle',
          footerText: 'JSON-FooterText',
          footerLink: 'JSON-FooterLink',
          copyright: 'JSON-Copyright'
        }
      },
      navItems: []
    }
    globalThis.fetch = vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve(jsonData)
    }))

    const portal = await import('../portal.js')
    await portal.loadAppConfig()

    // 顶层 brandTitle/brandDesc 由 JSON 写入
    expect(portal.appConfig.brandTitle).toBe('X员工')
    expect(portal.appConfig.brandDesc).toBe('内测')
    // loginThemes.default 字段全部来自 JSON
    expect(portal.appConfig.loginThemes.default.brandTitle).toBe('X员工')
    expect(portal.appConfig.loginThemes.default.brandDesc).toBe('内测')
    expect(portal.appConfig.loginThemes.default.loginTitle).toBe('JSON-LoginTitle')
    expect(portal.appConfig.loginThemes.default.loginSubtitle).toBe('JSON-LoginSubtitle')
    expect(portal.appConfig.loginThemes.default.copyright).toBe('JSON-Copyright')
  })

  it('test_js_empty_default_lets_json_take_over JS 默认为空占位时 JSON 接管（保留用例）', async () => {
    // 2026-08-21 反转契约：即便 JS DEFAULT_LOGIN_THEME.brandTitle 为空占位，JSON 也能接管；
    // 新契约下这条用例不再需要"JS 空才接管"的限制，但仍可作为回归保险保留
    const portal = await import('../portal.js')
    const jsonData = {
      brandTitle: 'JSON-Wins-Now',
      brandDesc: 'JSON-Desc-Wins-Now',
      loginThemes: {},
      navItems: []
    }
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve(jsonData)
    }))

    await portal.loadAppConfig()

    // 顶层 brandTitle/brandDesc 被 JSON 接管（2026-08-21 反转后无条件接管）
    expect(portal.appConfig.brandTitle).toBe('JSON-Wins-Now')
    expect(portal.appConfig.brandDesc).toBe('JSON-Desc-Wins-Now')
    // loginThemes.default.brandTitle 来自 JS DEFAULT_LOGIN_THEME spread（兜底）
    expect(portal.appConfig.loginThemes.default.brandTitle).toBe(portal.DEFAULT_LOGIN_THEME.brandTitle)
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
    // 2026-08-21 反转契约：JSON 是主配置源，default.brandTitle 由 JSON 提供
    expect(portal.appConfig.brandTitle).toBe('Default')
    expect(portal.appConfig.loginThemes.default.brandTitle).toBe('Default')
  })

  // ===== 2026-08-21 新增：redirect=/portal 强制 JS 接管（保留 URL ?theme=）=====

  it('test_portal_redirect_enforces_js_authoritative_when_no_url_theme redirect=/portal 且 URL 无 theme 时 JS 接管', async () => {
    // 用户从 /portal 被踢回登录页，浏览器残留 localStorage login_theme=YDT
    // 应丢弃 JSON 的非 default 主题、清空 localStorage、强制 default
    windowMock.location.search = '?redirect=%2Fportal'
    windowMock.localStorage.setItem('login_theme', 'YDT')

    const jsonData = {
      brandTitle: 'Should-Be-Ignored',
      brandDesc: 'Should-Be-Ignored',
      loginThemes: {
        default: { brandTitle: 'Should-Be-Ignored', brandDesc: '', loginTitle: 'ignored', loginSubtitle: '', registerSubtitle: '', footerText: '', footerLink: '', copyright: '' },
        YDT: { brandTitle: 'YDT', brandDesc: 'YDT desc', loginTitle: '', loginSubtitle: '', registerSubtitle: '', footerText: '', footerLink: '', copyright: '' },
        shenyang: { brandTitle: '沈阳', brandDesc: '', loginTitle: '', loginSubtitle: '', registerSubtitle: '', footerText: '', footerLink: '', copyright: '' }
      },
      navItems: []
    }
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(jsonData) }))

    const portal = await import('../portal.js')
    await portal.loadAppConfig()
    portal.resolveThemeFromUrl()
    portal.enforceJsAuthoritativeForPortal()

    // 强制 default
    expect(portal.appConfig.currentThemeKey).toBe('default')
    // 非 default 主题被丢弃
    expect(portal.appConfig.loginThemes.YDT).toBeUndefined()
    expect(portal.appConfig.loginThemes.shenyang).toBeUndefined()
    // default 主题保留（PortalApp 顶部导航依赖 brandTitle）
    expect(portal.appConfig.loginThemes.default).toBeTruthy()
    // localStorage 被清空
    expect(windowMock.localStorage.getItem('login_theme')).toBeNull()
    // brandTitle 为 JS 默认
    expect(portal.appConfig.brandTitle).toBe(portal.DEFAULT_LOGIN_THEME.brandTitle)
  })

  it('test_portal_redirect_preserves_url_theme URL ?theme=YDT 优先于 JS 接管（核心回归用例）', async () => {
    // 用户反馈（2026-08-21）：之前的实现把 URL ?theme= 也吃掉了，需要保证 URL 仍胜出
    windowMock.location.search = '?redirect=%2Fportal&theme=YDT'
    windowMock.localStorage.setItem('login_theme', 'YDT')

    const jsonData = {
      brandTitle: 'Should-Be-Ignored',
      brandDesc: '',
      loginThemes: {
        default: { brandTitle: 'Should-Be-Ignored', brandDesc: '', loginTitle: '', loginSubtitle: '', registerSubtitle: '', footerText: '', footerLink: '', copyright: '' },
        YDT: { brandTitle: 'YDT', brandDesc: 'YDT desc', loginTitle: '', loginSubtitle: '', registerSubtitle: '', footerText: '', footerLink: '', copyright: '' }
      },
      navItems: []
    }
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(jsonData) }))

    const portal = await import('../portal.js')
    await portal.loadAppConfig()
    portal.resolveThemeFromUrl()
    portal.enforceJsAuthoritativeForPortal()

    // URL ?theme=YDT 胜出：currentThemeKey 必须是 YDT，不被强制回 default
    expect(portal.appConfig.currentThemeKey).toBe('YDT')
    // YDT 主题保留
    expect(portal.appConfig.loginThemes.YDT).toBeTruthy()
    expect(portal.appConfig.loginThemes.YDT.brandTitle).toBe('YDT')
    // brandTitle 是 YDT 文案
    expect(portal.appConfig.brandTitle).toBe('YDT')
  })

  it('test_non_portal_redirect_keeps_json_full_control 非 portal redirect 时 JSON 完全控制', async () => {
    // 场景：redirect=/Agent/ 时新函数必须早退，行为完全不变
    windowMock.location.search = '?redirect=%2FAgent%2F'
    windowMock.localStorage.setItem('login_theme', 'YDT')

    const jsonData = {
      brandTitle: '',
      brandDesc: '',
      loginThemes: {
        default: { brandTitle: 'JS-Default', brandDesc: '', loginTitle: '', loginSubtitle: '', registerSubtitle: '', footerText: '', footerLink: '', copyright: '' },
        YDT: { brandTitle: 'YDT', brandDesc: 'YDT desc', loginTitle: '', loginSubtitle: '', registerSubtitle: '', footerText: '', footerLink: '', copyright: '' }
      },
      navItems: []
    }
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(jsonData) }))

    const portal = await import('../portal.js')
    await portal.loadAppConfig()
    portal.resolveThemeFromUrl()
    portal.enforceJsAuthoritativeForPortal()

    // localStorage 仍生效 → YDT
    expect(portal.appConfig.currentThemeKey).toBe('YDT')
    // YDT 主题保留（JSON 未被丢弃）
    expect(portal.appConfig.loginThemes.YDT).toBeTruthy()
    // localStorage 未被清空（非 portal redirect）
    expect(windowMock.localStorage.getItem('login_theme')).toBe('YDT')
  })

  it('test_portal_redirect_invalid_url_theme_fallsback_to_js_url_theme 非法值不构成合法主题，应被接管', async () => {
    // URL ?theme=NOT-EXIST 不在白名单 → resolveThemeFromUrl 会忽略，
    // 此后 enforceJsAuthoritativeForPortal 应正常接管
    windowMock.location.search = '?redirect=%2Fportal&theme=NOT-EXIST'
    windowMock.localStorage.setItem('login_theme', 'YDT')

    const jsonData = {
      brandTitle: '',
      brandDesc: '',
      loginThemes: {
        default: { brandTitle: 'JS-Default', brandDesc: '', loginTitle: '', loginSubtitle: '', registerSubtitle: '', footerText: '', footerLink: '', copyright: '' },
        YDT: { brandTitle: 'YDT', brandDesc: '', loginTitle: '', loginSubtitle: '', registerSubtitle: '', footerText: '', footerLink: '', copyright: '' }
      },
      navItems: []
    }
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(jsonData) }))

    const portal = await import('../portal.js')
    await portal.loadAppConfig()
    portal.resolveThemeFromUrl()
    // URL theme=NOT-EXIST 不在白名单 → resolveThemeFromUrl 走 localStorage=YDT
    expect(portal.appConfig.currentThemeKey).toBe('YDT')
    portal.enforceJsAuthoritativeForPortal()

    // URL theme 非法 → 不构成"URL 指定合法主题"条件 → JS 应接管
    expect(portal.appConfig.currentThemeKey).toBe('default')
    expect(portal.appConfig.loginThemes.YDT).toBeUndefined()
  })
})