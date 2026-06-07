/**
 * 统一登录跳转与 token 缓存兜底工具
 *
 * 解决以下场景：
 * 1. 用户从任意入口（/Agent/、/Agent/knowledge.html、/Agent/portal.html）跳到登录页时，
 *    登录成功后能自动回到原页面，而不是被统一重定向到 /Agent/。
 * 2. localStorage 中存在 auth_token 时，优先尝试 refresh_token 静默刷新；
 *    仅当 token 完全失效（refresh 也失败）时才跳登录页，避免无谓的"踢回登录页"。
 * 3. 提供 safeRedirectUrl 防御开放重定向漏洞（拒绝 javascript:、data: 等危险协议）。
 */

import { refreshToken } from './api.js'

/**
 * 当前入口是否在登录页
 * @returns {boolean} 当前 URL 是否已经位于登录页
 */
function isAlreadyOnLoginPage() {
  if (typeof window === 'undefined') return false
  const path = window.location.pathname.toLowerCase()
  // 主应用的登录页就是 /Agent/ 或 /Agent/index.html（大小写不敏感）
  return path === '/agent/' || path === '/agent' || path === '/agent/index.html'
}

/**
 * 安全校验重定向目标 URL
 *
 * 规则：
 * 1. 空值返回 null。
 * 2. 拒绝 javascript:、data:、vbscript:、file: 等危险协议。
 * 3. 同源相对路径（以 / 开头但不是 // 开头）允许。
 * 4. 绝对 URL 必须与当前 origin 匹配。
 * 5. 其它非字符串值一律拒绝。
 *
 * @param {string|undefined|null} target - 原始 redirect 参数
 * @returns {string|null} 通过校验的 URL；未通过返回 null
 */
export function safeRedirectUrl(target) {
  if (!target || typeof target !== 'string') return null
  const trimmed = target.trim()
  if (!trimmed) return null

  // 拒绝危险协议（不区分大小写）
  const lower = trimmed.toLowerCase()
  if (
    lower.startsWith('javascript:') ||
    lower.startsWith('data:') ||
    lower.startsWith('vbscript:') ||
    lower.startsWith('file:') ||
    lower.startsWith('about:')
  ) {
    return null
  }

  // 同源相对路径：以单斜杠开头，但不是双斜杠（//example.com 被视为跨域）
  if (trimmed.startsWith('/') && !trimmed.startsWith('//')) {
    return trimmed
  }

  // 绝对 URL：校验 origin
  try {
    const url = new URL(trimmed, window.location.origin)
    if (url.origin === window.location.origin) {
      // 规整为 pathname + search + hash
      return url.pathname + url.search + url.hash
    }
  } catch {
    return null
  }

  return null
}

/**
 * 根据当前入口和重定向路径拼装登录页 URL
 *
 * 集中放置，避免在多个组件中重复路径判断。
 *
 * @param {string} [redirectPath] - 登录成功后回到的路径
 * @returns {string} 登录页完整 URL
 */
export function buildLoginUrl(redirectPath) {
  if (typeof window === 'undefined') return '/Agent/'
  const base = window.location.origin
  const safe = safeRedirectUrl(redirectPath)
  if (!safe) {
    return `${base}/Agent/`
  }
  return `${base}/Agent/?redirect=${encodeURIComponent(safe)}`
}

/**
 * 跳转到登录页（带 redirect 参数回到原页面）
 *
 * 特性：
 * - 若当前已经在登录页则不重复跳转（避免无限循环）。
 * - 自动把当前 pathname + search + hash 作为 redirect。
 * - 支持传入自定义 redirect 路径覆盖默认值。
 *
 * @param {Object} [options] - 配置项
 * @param {string} [options.redirect] - 自定义重定向目标；默认使用当前 URL
 * @param {string} [options.reason] - 跳转原因（用于日志/调试）
 * @returns {void}
 */
export function redirectToLogin(options = {}) {
  if (typeof window === 'undefined') return

  // 避免在登录页内重复跳转
  if (isAlreadyOnLoginPage()) {
    return
  }

  const target = options.redirect || (window.location.pathname + window.location.search + window.location.hash)
  const loginUrl = buildLoginUrl(target)

  if (options.reason) {
    console.warn(`[auth] redirectToLogin reason=${options.reason}, from=${window.location.pathname}`)
  }
  window.location.href = loginUrl
}

/**
 * 在 401 兜底时调用：先尝试 refresh_token，失败再跳登录页
 *
 * 替代 App.vue 中"捕获到错误信息含未登录/过期就置 isLoggedIn=false"的强退逻辑。
 *
 * 行为：
 * - 若 localStorage 中没有 auth_token：直接 redirectToLogin。
 * - 若有：调用 refreshToken()，成功则返回 true；失败则 redirectToLogin。
 *
 * @returns {Promise<boolean>} true 表示刷新成功（可重试原请求），false 表示已跳转登录页
 */
export async function tryRefreshOrRedirect() {
  const token = (typeof window !== 'undefined') ? window.localStorage.getItem('auth_token') : null

  // 本地无 token：直接跳登录页
  if (!token) {
    redirectToLogin({ reason: 'no_local_token' })
    return false
  }

  try {
    // 静态导入：auth.js 与 api.js 之间不存在循环依赖（api.js 不引用 auth.js）
    await refreshToken()
    return true
  } catch (err) {
    console.warn('[auth] tryRefreshOrRedirect 失败:', err)
    redirectToLogin({ reason: 'refresh_failed' })
    return false
  }
}

/**
 * 判断本地是否存在可用的 auth_token 缓存
 *
 * 用于第三方/iframe 调用场景的快速判断：
 * - 有缓存 → 调用方可以直接发起请求，由 fetchWithAuth 内部处理 401。
 * - 无缓存 → 调用方应先引导用户登录。
 *
 * @returns {boolean} 是否存在 auth_token 缓存
 */
export function hasLocalAuthToken() {
  if (typeof window === 'undefined') return false
  const token = window.localStorage.getItem('auth_token')
  return Boolean(token && token !== 'undefined' && token !== 'null')
}

/**
 * 从当前 URL 中提取 redirect 参数（自动 URL 解码并通过安全校验）
 *
 * @returns {string|null} 通过校验的 redirect 路径；不存在或非法返回 null
 */
export function getRedirectParam() {
  if (typeof window === 'undefined') return null
  const params = new URLSearchParams(window.location.search)
  const raw = params.get('redirect')
  return safeRedirectUrl(raw)
}
