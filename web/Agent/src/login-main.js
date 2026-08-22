/**
 * 登录入口
 *
 * 职责：
 * - 加载运行时配置（品牌主题表、导航项等）
 * - 根据 URL ?theme=xxx + localStorage 'login_theme' 解析当前主题
 * - 挂载 LoginView 组件
 * - 监听 LoginView emit 的 login-success 事件
 * - 登录成功后按 URL ?redirect= 参数回跳，并把当前主题透传到 redirect（无 redirect 时跳到 /Agent/）
 *
 * 设计背景：/login 是承载 LoginView 的唯一入口，
 * App.vue（/Agent/）与 PortalApp.vue（/portal）不再渲染 LoginView / RegisterView，
 * 未登录时统一通过 redirectToLogin() 跳到 /login?redirect=<原页面>。
 */
import { createApp, h, ref } from 'vue'
import './styles/main.css'
import LoginView from './views/LoginView.vue'
import RegisterView from './views/RegisterView.vue'
import { loadAppConfig, appConfig, resolveThemeFromUrl, enforceJsAuthoritativeForPortal } from './config/portal.js'
import { safeRedirectUrl } from './utils/auth.js'
import { appendQueryParam } from './utils/url.js'

/**
 * 处理 LoginView 的 login-success 事件
 *
 * 优先按 URL 上的 redirect 参数回跳；无 redirect 时回 /Agent/。
 * 回跳时把当前主题 key（currentThemeKey）写入 redirect query，
 * 保证同一主题在跨页面时持续生效。
 *
 * @param {Object} data - 登录结果数据，包含 access_token、role、username、user_id
 * @returns {void}
 */
function handleLoginSuccess(data) {
  // 登录成功由后端 Set-Cookie 下发 Access Token，本端入口只负责回跳
  const rawRedirect = new URLSearchParams(window.location.search).get('redirect')
  const redirect = safeRedirectUrl(rawRedirect)
  const themeKey = appConfig.currentThemeKey
  // 仅在「非 default 且当前 URL 上尚无 theme」时写入；避免覆盖 URL 上显式传入的主题
  const shouldAppendTheme = themeKey && themeKey !== 'default'
  if (redirect) {
    const finalRedirect = shouldAppendTheme && !hasQueryParam(redirect, 'theme')
      ? appendQueryParam(redirect, 'theme', themeKey)
      : redirect
    window.location.href = finalRedirect
    return
  }
  // 没有 redirect 时回到 /Agent/ 主入口；携带主题以保证导航栏品牌一致
  const home = shouldAppendTheme
    ? appendQueryParam('/Agent/', 'theme', themeKey)
    : '/Agent/'
  window.location.href = home
}

/**
 * 简单判断 URL 中是否已有指定 query 参数
 *
 * @param {string} url - URL 字符串
 * @param {string} key - 参数名
 * @returns {boolean} 是否存在
 */
function hasQueryParam(url, key) {
  try {
    const qIdx = url.indexOf('?')
    if (qIdx < 0) return false
    return new URLSearchParams(url.slice(qIdx + 1)).has(key)
  } catch {
    return false
  }
}

/**
 * 启动登录入口
 * 1. 异步加载运行时配置（含 loginThemes 白名单）
 * 2. 解析当前主题（URL > localStorage > default），保证退出登录后仍是同一主题
 * 3. 同步 document.title 到当前主题
 * 4. 挂载 Vue 应用（LoginView / RegisterView 通过 getCurrentLoginTheme 渲染文案）
 *
 * @returns {Promise<void>}
 */
async function bootstrap() {
  await loadAppConfig()
  resolveThemeFromUrl()
  // 当 redirect=/portal 且 URL 上无 ?theme= 时，让 JS DEFAULT_LOGIN_THEME 成为唯一权威
  enforceJsAuthoritativeForPortal()
  const theme = appConfig.loginThemes[appConfig.currentThemeKey]
  if (theme && theme.brandTitle) {
    document.title = theme.brandTitle
  }
  const App = {
    setup() {
      const isRegister = ref(false)
      return () =>
        isRegister.value
          ? h(RegisterView, {
              onSwitchToLogin: () => {
                isRegister.value = false
              }
            })
          : h(LoginView, {
              onLoginSuccess: handleLoginSuccess,
              onSwitchToRegister: () => {
                isRegister.value = true
              }
            })
    }
  }
  createApp(App).mount('#app')
}

bootstrap()