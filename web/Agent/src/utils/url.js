/**
 * URL 操作工具
 *
 * 提供 query string 拼接、append 等能力，与 auth.js 的 safeRedirectUrl（防御开放重定向）
 * 协同：safeRedirectUrl 负责「校验 URL 是否可信任」，本工具负责「在不破坏既有 query 的前提下
 * 追加/覆盖单个 key」。
 *
 * 当前用途：PortalApp / App 退出登录时把当前主题 key（如 shenyang / xemployee）写入
 * redirect 目标的 query，保证回到 /login 后 LoginView 仍命中同一主题；下次回到 /portal
 * 时也能继续命中。
 */

/**
 * 在 URL 中追加/覆盖单个 query 参数
 *
 * 设计要点：
 * - 同时支持纯路径、带 search、带 hash、两者皆有的输入
 * - 已有同名 key → 覆盖（而不是追加，避免 /login?theme=a&theme=b 双值歧义）
 * - 不修改原字符串（不可变）
 * - 不对 value 做额外 URL 编码校验，由 URLSearchParams 负责编码
 *
 * @param {string} input - 原始 URL（可含 search/hash；非字符串视为空）
 * @param {string} key - query 参数名
 * @param {string} value - query 参数值
 * @returns {string} 处理后的 URL；输入非法时返回空串
 */
export function appendQueryParam(input, key, value) {
  if (typeof input !== 'string') return ''
  // 拆分 pathname / search / hash：lookahead 保证 ? 与 # 都成为独立分组
  const match = input.match(/^([^?#]*)(\?[^#]*)?(#.*)?$/)
  const pathname = match && match[1] ? match[1] : ''
  const search = match && match[2] ? match[2] : ''
  const hash = match && match[3] ? match[3] : ''

  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  params.set(key, value)
  const nextSearch = params.toString()
  return pathname + (nextSearch ? '?' + nextSearch : '') + hash
}

/**
 * 从 URL 中安全读取单个 query 参数值（始终返回 string|null，不抛错）
 *
 * @param {string} input - 原始 URL
 * @param {string} key - query 参数名
 * @returns {string|null} 参数值；不存在或解析失败返回 null
 */
export function readQueryParam(input, key) {
  if (typeof input !== 'string') return null
  const qIdx = input.indexOf('?')
  if (qIdx < 0) return null
  const search = input.slice(qIdx + 1)
  try {
    const params = new URLSearchParams(search)
    return params.get(key)
  } catch (e) {
    return null
  }
}