import { createApp } from 'vue'
import './styles/main.css'
import PortalApp from './PortalApp.vue'
import { loadAppConfig, appConfig, resolveThemeFromUrl, enforceJsAuthoritativeForPortal } from './config/portal.js'

/**
 * 启动门户应用
 *
 * 1. 加载运行时配置（含 loginThemes 白名单）
 * 2. 解析当前主题（URL ?theme= > localStorage 'login_theme' > default）
 * 3. 同步 document.title 与 PortalApp 顶部品牌标题
 * 4. 挂载 Vue 应用
 */
async function bootstrap() {
  await loadAppConfig()
  resolveThemeFromUrl()
  // portal 直访时 redirect 通常为空 → 函数早退不生效；保留对称性以备未来场景
  enforceJsAuthoritativeForPortal()
  if (appConfig.brandTitle) {
    document.title = appConfig.brandTitle
  }
  createApp(PortalApp).mount('#app')
}

bootstrap()