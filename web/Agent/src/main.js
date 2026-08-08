import { createApp } from 'vue'
import './styles/main.css'
import './styles/layout.css'
import App from './App.vue'
import router from './router/index.js'
import { loadAppConfig, appConfig } from './config/portal.js'

/**
 * 启动主应用
 * 先异步加载运行时配置，再挂载 Vue 应用（含 vue-router 路由表）
 * 确保 LoginView / RegisterView 能读取到 app-config.json 的最新品牌配置
 */
async function bootstrap() {
  await loadAppConfig()
  if (appConfig.brandTitle) {
    document.title = appConfig.brandTitle
  }
  createApp(App).use(router).mount('#app')
}

bootstrap()