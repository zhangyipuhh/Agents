import { reactive } from 'vue'

/**
 * 门户运行时配置模块
 *
 * 职责：
 * - 从 /app-config.json 运行时加载门户配置（品牌标题、副标题、导航项）
 * - 提供响应式 appConfig 对象，供各组件直接绑定
 * - 解析失败或缺省时回退到内置默认值
 *
 * 配置字段：
 * - brandTitle: string   品牌主标题（显示在导航栏、登录页、注册页）
 * - brandDesc: string    品牌副标题/描述（显示在登录页品牌区）
 * - navItems: Array      导航项数组，字段同 NavItem
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
 * 门户运行时配置响应式对象
 * 加载前使用默认值，加载成功后自动更新
 */
export const appConfig = reactive({
  brandTitle: '沈阳市自然资源和规划"一点通"',
  brandDesc: '智慧政务服务平台',
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
 * 异步加载门户运行时配置
 * 从 /app-config.json 获取配置并合并到 appConfig
 * 失败时保留默认值，不影响页面渲染
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

    if (typeof data.brandTitle === 'string' && data.brandTitle.trim()) {
      appConfig.brandTitle = data.brandTitle
    }
    if (typeof data.brandDesc === 'string' && data.brandDesc.trim()) {
      appConfig.brandDesc = data.brandDesc
    }
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
