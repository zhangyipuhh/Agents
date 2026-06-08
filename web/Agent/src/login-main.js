/**
 * 登录入口
 *
 * 职责：
 * - 加载运行时配置（品牌标题等）
 * - 挂载 LoginView 组件
 * - 监听 LoginView emit 的 login-success 事件
 * - 登录成功后按 URL ?redirect= 参数回跳；无 redirect 时跳到 /Agent/
 *
 * 设计背景：/login 是承载 LoginView 的唯一入口，
 * App.vue（/Agent/）与 PortalApp.vue（/portal）不再渲染 LoginView / RegisterView，
 * 未登录时统一通过 redirectToLogin() 跳到 /login?redirect=<原页面>。
 */
import { createApp, h } from 'vue'
import './styles/main.css'
import LoginView from './views/LoginView.vue'
import { loadAppConfig, appConfig } from './config/portal.js'
import { safeRedirectUrl } from './utils/auth.js'

/**
 * 处理 LoginView 的 login-success 事件
 * 优先按 URL 上的 redirect 参数回跳；无 redirect 时回 /Agent/
 * @param {Object} data - 登录结果数据，包含 access_token、role、username、user_id
 * @returns {void}
 */
function handleLoginSuccess(data) {
  // 登录成功本身由 LoginView 内部将 token 写入 localStorage，这里只负责回跳
  // 注：原 App.vue#handleLoginSuccess 还有 user_id 等兜底写入，本入口不重复 LoginView 已写过的字段
  const rawRedirect = new URLSearchParams(window.location.search).get('redirect')
  const redirect = safeRedirectUrl(rawRedirect)
  if (redirect) {
    window.location.href = redirect
    return
  }
  // 没有 redirect 时回到 /Agent/ 主入口
  window.location.href = '/Agent/'
}

/**
 * 启动登录入口
 * 先异步加载运行时配置，再挂载 Vue 应用
 * 确保 LoginView 能读取到 app-config.json 的最新品牌配置
 * @returns {Promise<void>}
 */
async function bootstrap() {
  await loadAppConfig()
  if (appConfig.brandTitle) {
    document.title = appConfig.brandTitle
  }
  // 用一个简单 Wrapper 组件桥接 LoginView 的 emit 到顶层 handleLoginSuccess
  // （h(LoginView, { onLoginSuccess: ... }) 是 Vue 编译器把 @login-success 转为 onLoginSuccess prop 的标准用法）
  const App = {
    setup() {
      return () => h(LoginView, { onLoginSuccess: handleLoginSuccess })
    }
  }
  createApp(App).mount('#app')
}

bootstrap()
