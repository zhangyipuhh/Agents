import { createApp } from 'vue'
import './styles/main.css'
import './styles/layout.css'
import App from './App.vue'
import router from './router/index.js'
import { loadAppConfig, appConfig, resolveThemeFromUrl } from './config/portal.js'

/**
 * 启动主应用
 *
 * 1. 加载运行时配置（含 loginThemes 白名单）
 * 2. 解析当前主题（URL ?theme= > localStorage 'login_theme' > default）
 * 3. 同步 document.title
 * 4. 挂载 Vue 应用（含 vue-router 路由表）
 */
async function bootstrap() {
  await loadAppConfig()
  resolveThemeFromUrl()
  if (appConfig.brandTitle) {
    document.title = appConfig.brandTitle
  }
  createApp(App).use(router).mount('#app')
}

bootstrap()