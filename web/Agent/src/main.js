import { createApp } from 'vue'
import './styles/main.css'
import App from './App.vue'
import { loadAppConfig, appConfig } from './config/portal.js'

/**
 * 启动主应用
 * 先异步加载运行时配置，再挂载 Vue 应用
 * 确保 LoginView / RegisterView 能读取到 app-config.json 的最新品牌配置
 */
async function bootstrap() {
  await loadAppConfig()
  if (appConfig.brandTitle) {
    document.title = appConfig.brandTitle
  }
  createApp(App).mount('#app')
}

bootstrap()
