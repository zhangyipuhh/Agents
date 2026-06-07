import { createApp } from 'vue'
import './styles/main.css'
import PortalApp from './PortalApp.vue'
import { loadAppConfig, appConfig } from './config/portal.js'

/**
 * 启动门户应用
 * 先异步加载运行时配置，再挂载 Vue 应用
 */
async function bootstrap() {
  await loadAppConfig()
  if (appConfig.brandTitle) {
    document.title = appConfig.brandTitle
  }
  createApp(PortalApp).mount('#app')
}

bootstrap()
