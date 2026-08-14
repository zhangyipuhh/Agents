import { reactive } from 'vue'

/**
 * 门户运行时配置模块
 *
 * 职责：
 * - 从 /app-config.json 运行时加载门户配置（品牌标题、副标题、导航项、登录主题表）
 * - 提供响应式 appConfig 对象，供各组件直接绑定
 * - 解析失败或缺省时回退到内置默认值
 * - 提供登录主题（loginThemes）切换机制：URL ?theme=<key> > localStorage 'login_theme' > 内置 default
 *
 * 配置字段：
 * - brandTitle: string         品牌主标题（与 loginThemes.default.brandTitle 同步）
 * - brandDesc: string          品牌副标题（与 loginThemes.default.brandDesc 同步）
 * - loginThemes: object        主题表，key → LoginTheme
 * - currentThemeKey: string    当前生效的主题 key（默认 'default'）
 * - navItems: Array            导航项数组，字段同 NavItem
 *
 * LoginTheme 字段：
 * - brandTitle: string         品牌主标题（必填）
 * - brandDesc: string          品牌副标题/描述（可选）
 * - loginTitle: string         登录卡片主标题（如「欢迎登录」）
 * - loginSubtitle: string      登录卡片副标题（仅 password 阶段）
 * - registerSubtitle: string   注册卡片副标题
 * - footerText: string         底部链接前缀文案
 * - footerLink: string         底部链接显示文字
 * - copyright: string          卡片底部版权声明（空串则不渲染）
 *
 * NavItem 字段：
 * - key: string           唯一键（必填）
 * - label: string         显示文字（必填）
 * - type: 'placeholder' | 'iframe'  渲染方式（必填）
 * - url: string           type='iframe' 时必填；相对路径或绝对 URL
 * - targetOrigin: string  postMessage 的 targetOrigin；缺省时按 url 推断
 */

const DEFAULT_NAV_ITEMS = [
  { key: 'site-select', label: '智能选址', type: 'placeholder' },
  { key: 'pre-check', label: '智能预检', type: 'placeholder' },
  { key: 'rule-lib', label: '规则库', type: 'iframe', url: '/knowledge.html' }
]

/**
 * 内置默认主题：保证 loginThemes.default 始终存在；当前/历史 JSON 都允许不显式声明 default 主题。
 */
const DEFAULT_LOGIN_THEME = {
  brandTitle: '沈阳市自然资源和规划"一点通"',
  brandDesc: '智慧政务服务平台',
  loginTitle: '欢迎登录',
  loginSubtitle: '请输入您的账号信息',
  registerSubtitle: '请填写以下信息完成注册',
  footerText: '没有账号？',
  footerLink: '去注册',
  copyright: ''
}

/**
 * localStorage key：保存用户上次使用的主题 key
 * 设计目的：退出登录后从 /login 直访时（URL 无 theme 参数），仍能恢复同一主题。
 */
const LS_LOGIN_THEME_KEY = 'login_theme'

/**
 * 主题 key 合法性正则：允许字母（大小写）、数字、下划线、连字符，长度 1-32。
 * 与 safeRedirectUrl 拒绝危险协议策略一致：URL query 参数必须落在白名单内。
 * 大小写都允许是为了让业务方能用「YDT」「YDT-DEV」等大写项目缩写作为 key。
 */
const THEME_KEY_RE = /^[a-zA-Z0-9_-]{1,32}$/

/**
 * 门户运行时配置响应式对象
 * 加载前使用默认值，加载成功后自动更新
 */
export const appConfig = reactive({
  brandTitle: DEFAULT_LOGIN_THEME.brandTitle,
  brandDesc: DEFAULT_LOGIN_THEME.brandDesc,
  loginThemes: {
    default: { ...DEFAULT_LOGIN_THEME }
  },
  currentThemeKey: 'default',
  navItems: DEFAULT_NAV_ITEMS
})

/**
 * 校验并规整单个 NavItem
 * @param {Object} raw - 原始配置项
 * @param {number} index - 在数组中的下标（用于报错）
 * @returns {Object|null} 合法则返回规范化的项；非法返回 null
 */
function normalizeNavItem(raw, index) {
  if (!raw || typeof raw !== 'object') {
    console.warn(`[portal-config] 第 ${index} 项不是对象，已忽略`)
    return null
  }
  const { key, label, type, url, targetOrigin } = raw
  if (typeof key !== 'string' || !key.trim()) {
    console.warn(`[portal-config] 第 ${index} 项缺少有效 key，已忽略`)
    return null
  }
  if (typeof label !== 'string' || !label.trim()) {
    console.warn(`[portal-config] 第 ${index} 项 (${key}) 缺少有效 label，已忽略`)
    return null
  }
  if (type !== 'placeholder' && type !== 'iframe') {
    console.warn(`[portal-config] 第 ${index} 项 (${key}) 的 type 非法（应为 placeholder 或 iframe），已忽略`)
    return null
  }
  if (type === 'iframe') {
    if (typeof url !== 'string' || !url.trim()) {
      console.warn(`[portal-config] 第 ${index} 项 (${key}) type=iframe 但缺 url，已忽略`)
      return null
    }
  }
  const item = { key, label, type }
  if (url) item.url = url
  if (targetOrigin) item.targetOrigin = targetOrigin
  return item
}

/**
 * 校验并规整单个 LoginTheme
 *
 * - brandTitle 必填且为非空字符串；非法则丢弃该主题（不替换）
 * - 其他字段缺省时由内置 DEFAULT_LOGIN_THEME 对应字段兜底
 *
 * @param {Object} raw - 原始主题对象
 * @returns {Object|null} 合法则返回规范化主题；非法返回 null
 */
function normalizeLoginTheme(raw) {
  if (!raw || typeof raw !== 'object') return null
  const brandTitle = typeof raw.brandTitle === 'string' && raw.brandTitle.trim()
    ? raw.brandTitle.trim()
    : ''
  if (!brandTitle) return null
  const out = { brandTitle, ...DEFAULT_LOGIN_THEME }
  for (const k of Object.keys(DEFAULT_LOGIN_THEME)) {
    if (typeof raw[k] === 'string') out[k] = raw[k]
  }
  out.brandTitle = brandTitle
  return out
}

/**
 * 同步 appConfig.brandTitle / brandDesc 为当前主题的 brandTitle / brandDesc
 * 保留旧字段（PortalApp 顶部导航栏与 document.title 仍直接读 appConfig.brandTitle），
 * 这样老组件无需重写即可跟随主题切换。
 *
 * @returns {void}
 */
function syncBrandFields() {
  const t = appConfig.loginThemes[appConfig.currentThemeKey]
  if (t) {
    appConfig.brandTitle = t.brandTitle
    appConfig.brandDesc = t.brandDesc || ''
  }
}

/**
 * 设置当前主题
 *
 * - 校验主题 key 是否在 loginThemes 白名单内；
 * - 同步写入 localStorage（供下次直访登录页时使用）；
 * - 同步更新 appConfig.brandTitle/brandDesc。
 *
 * @param {string} key - 主题 key
 * @returns {boolean} 是否成功切换
 */
export function setLoginTheme(key) {
  if (typeof key !== 'string' || !appConfig.loginThemes[key]) {
    console.warn(`[portal-config] 主题 ${key} 不存在或非法，保持当前 ${appConfig.currentThemeKey}`)
    return false
  }
  appConfig.currentThemeKey = key
  try {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(LS_LOGIN_THEME_KEY, key)
    }
  } catch (e) {
    // localStorage 不可用（如隐私模式）不影响内存态
  }
  syncBrandFields()
  return true
}

/**
 * 从 URL query 与 localStorage 解析当前主题
 *
 * 优先级：
 * 1. URL ?theme=<key>（操作员/运维主动指定，最高优先）
 * 2. localStorage 'login_theme'（保证退出登录后仍是同一主题）
 * 3. 内置 'default'
 *
 * 必须在 loadAppConfig() 之后调用（依赖 loginThemes 白名单）。
 *
 * @returns {string} 最终选用的主题 key
 */
export function resolveThemeFromUrl() {
  if (typeof window === 'undefined') return appConfig.currentThemeKey
  try {
    const urlTheme = new URLSearchParams(window.location.search).get('theme')
    if (urlTheme && THEME_KEY_RE.test(urlTheme) && appConfig.loginThemes[urlTheme]) {
      setLoginTheme(urlTheme)
      return urlTheme
    }
    if (urlTheme && !appConfig.loginThemes[urlTheme]) {
      console.warn(`[portal-config] URL theme=${urlTheme} 不在白名单，忽略`)
    }
  } catch (e) {
    // URLSearchParams 解析异常不影响后续步骤
  }
  try {
    const stored = localStorage.getItem(LS_LOGIN_THEME_KEY)
    if (stored && appConfig.loginThemes[stored]) {
      setLoginTheme(stored)
      return stored
    }
  } catch (e) {
    // localStorage 不可用（隐私模式/无痕）→ 走 default
  }
  // 兜底：确保 currentThemeKey 指向有效主题
  if (!appConfig.loginThemes[appConfig.currentThemeKey]) {
    appConfig.currentThemeKey = 'default'
  }
  return appConfig.currentThemeKey
}

/**
 * 获取当前主题对象（始终返回有效主题；currentThemeKey 失效时回退 default）
 *
 * @returns {Object} 当前主题对象
 */
export function getCurrentLoginTheme() {
  const t = appConfig.loginThemes[appConfig.currentThemeKey]
  if (t) return t
  return appConfig.loginThemes.default
}

/**
 * 异步加载门户运行时配置
 * 从 /app-config.json 获取配置并合并到 appConfig
 * 失败时保留默认值，不影响页面渲染
 *
 * 升级点：
 * - 解析 loginThemes map（key 必须匹配 THEME_KEY_RE）
 * - 若 JSON 未含 loginThemes 或全部校验失败 → 用顶层 brandTitle/brandDesc 合成 default 主题（向后兼容旧配置）
 * - 始终保证 loginThemes.default 存在（缺失则用内置 DEFAULT_LOGIN_THEME）
 *
 * @returns {Promise<void>}
 */
export async function loadAppConfig() {
  try {
    const response = await fetch(`/app-config.json?t=${Date.now()}`)
    if (!response.ok) {
      console.warn('[portal-config] /app-config.json 加载失败，使用默认配置')
      return
    }
    const data = await response.json()

    // 顶层 brandTitle/brandDesc：作为 default 主题的语义化别名
    if (typeof data.brandTitle === 'string' && data.brandTitle.trim()) {
      appConfig.brandTitle = data.brandTitle
    }
    if (typeof data.brandDesc === 'string' && data.brandDesc.trim()) {
      appConfig.brandDesc = data.brandDesc
    }

    // 解析 loginThemes
    const themesMap = {}
    if (data.loginThemes && typeof data.loginThemes === 'object') {
      for (const [key, raw] of Object.entries(data.loginThemes)) {
        if (!THEME_KEY_RE.test(key)) {
          console.warn(`[portal-config] 主题 key "${key}" 非法（仅允许小写字母/数字/_/-，长度 1-32），已忽略`)
          continue
        }
        const t = normalizeLoginTheme(raw)
        if (t) {
          themesMap[key] = t
        } else {
          console.warn(`[portal-config] 主题 "${key}" 缺少有效 brandTitle，已忽略`)
        }
      }
    }

    // 兜底：若 JSON 未提供 default 主题 → 用顶层 brandTitle/brandDesc 合成
    if (!themesMap.default) {
      themesMap.default = normalizeLoginTheme({
        brandTitle: appConfig.brandTitle,
        brandDesc: appConfig.brandDesc,
        loginTitle: '欢迎登录',
        loginSubtitle: '请输入您的账号信息',
        registerSubtitle: '请填写以下信息完成注册',
        footerText: '没有账号？',
        footerLink: '去注册',
        copyright: ''
      }) || { ...DEFAULT_LOGIN_THEME }
    }

    if (Object.keys(themesMap).length > 0) {
      appConfig.loginThemes = themesMap
    } else {
      console.warn('[portal-config] loginThemes 全部校验失败，使用内置默认主题')
      appConfig.loginThemes = { default: { ...DEFAULT_LOGIN_THEME } }
    }

    // 加载配置后，重置 currentThemeKey：若当前 key 已不在新的 themes map 中 → 回退 default
    // 场景：JSON 中删除了 YDT 主题但浏览器仍以 YDT 进入，内存态 currentThemeKey 需及时纠正，
    // 避免 LoginView 渲染到 default 时仍携带旧的 brandTitle/brandDesc（已被 syncBrandFields 写过的旧值）。
    if (!appConfig.loginThemes[appConfig.currentThemeKey]) {
      console.warn(`[portal-config] 当前主题 ${appConfig.currentThemeKey} 不在新 themes map 中，回退 default`)
      appConfig.currentThemeKey = 'default'
    }

    // 解析 navItems
    if (Array.isArray(data.navItems) && data.navItems.length > 0) {
      const normalized = data.navItems
        .map((item, i) => normalizeNavItem(item, i))
        .filter(Boolean)
      if (normalized.length > 0) {
        appConfig.navItems = normalized
      } else {
        console.warn('[portal-config] app-config.json 中的 navItems 全部校验失败，使用默认导航')
      }
    }

    // 同步 brandTitle/brandDesc 到当前主题
    syncBrandFields()
  } catch (e) {
    console.warn('[portal-config] 加载运行时配置失败，使用默认配置:', e?.message)
  }
}

/**
 * 获取门户导航项配置
 *
 * 优先读取已加载的 appConfig.navItems；
 * 若未加载或全部校验失败，回退到内置默认三项。
 *
 * @returns {Array<Object>} 导航项列表
 */
let cachedNavItems = null

export function getNavItems() {
  if (cachedNavItems) return cachedNavItems

  const items = appConfig.navItems
  if (!Array.isArray(items) || items.length === 0) {
    cachedNavItems = DEFAULT_NAV_ITEMS
    return cachedNavItems
  }

  const normalized = items
    .map((item, i) => normalizeNavItem(item, i))
    .filter(Boolean)

  if (normalized.length === 0) {
    console.warn('[portal-config] 全部配置项均不合法，回退默认')
    cachedNavItems = DEFAULT_NAV_ITEMS
    return cachedNavItems
  }

  cachedNavItems = normalized
  return cachedNavItems
}