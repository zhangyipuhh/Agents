/**
 * 门户导航配置模块
 *
 * 职责：
 * - 从 Vite 环境变量 VITE_PORTAL_NAV_CONFIG 读取 JSON 字符串形式的导航配置
 * - 解析失败或缺省时回退到内置默认三项（与现状保持一致）
 *
 * 配置示例（写入 web/Agent/.env 或 .env.production）：
 * ```
 * VITE_PORTAL_NAV_CONFIG='[
 *   {"key":"site-select","label":"智能选址","type":"placeholder"},
 *   {"key":"pre-check","label":"智能预检","type":"placeholder"},
 *   {"key":"rule-lib","label":"规则库","type":"iframe","url":"/knowledge.html"},
 *   {"key":"third-party","label":"第三方应用","type":"iframe","url":"https://example.com/app","targetOrigin":"https://example.com"}
 * ]'
 * ```
 *
 * NavItem 字段：
 * - key: string           唯一键（必填）
 * - label: string         显示文字（必填）
 * - type: 'placeholder' | 'iframe'  渲染方式（必填）
 * - url: string           type='iframe' 时必填；相对路径或绝对 URL
 * - targetOrigin: string  postMessage 的 targetOrigin；缺省时按 url 推断
 *
 * 异常：
 * - JSON.parse 失败 → console.warn + 回退默认
 * - 字段缺失或类型错误 → console.warn + 回退默认
 * - 配置为空数组 → 回退默认（保证门户至少有 3 个入口）
 *
 * @returns {Array<{key: string, label: string, type: string, url?: string, targetOrigin?: string}>}
 *          解析后的导航项列表
 */
const DEFAULT_NAV_ITEMS = [
  { key: 'site-select', label: '智能选址', type: 'placeholder' },
  { key: 'pre-check', label: '智能预检', type: 'placeholder' },
  { key: 'rule-lib', label: '规则库', type: 'iframe', url: '/knowledge.html' }
]

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
 * 获取门户导航项配置
 *
 * 读取 import.meta.env.VITE_PORTAL_NAV_CONFIG 静态替换的 JSON 字符串。
 * 模块加载时执行一次，结果缓存避免重复解析。
 *
 * @returns {Array<Object>} 导航项列表
 */
let cachedNavItems = null

export function getNavItems() {
  if (cachedNavItems) return cachedNavItems

  const raw = import.meta.env.VITE_PORTAL_NAV_CONFIG
  if (!raw || typeof raw !== 'string') {
    cachedNavItems = DEFAULT_NAV_ITEMS
    return cachedNavItems
  }

  let parsed
  try {
    parsed = JSON.parse(raw)
  } catch (e) {
    console.warn('[portal-config] VITE_PORTAL_NAV_CONFIG 解析失败，回退默认:', e?.message)
    cachedNavItems = DEFAULT_NAV_ITEMS
    return cachedNavItems
  }

  if (!Array.isArray(parsed) || parsed.length === 0) {
    console.warn('[portal-config] VITE_PORTAL_NAV_CONFIG 不是非空数组，回退默认')
    cachedNavItems = DEFAULT_NAV_ITEMS
    return cachedNavItems
  }

  const normalized = parsed
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
