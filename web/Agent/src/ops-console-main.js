/**
 * 运维控制台入口（独立 Vite 入口，对应 /ops-console.html）
 *
 * 职责：
 * - 挂载 OpsConsoleApp 根组件到 #app
 * - 引入运维控制台独立样式（政务蓝主题 + macOS 风格多窗口）
 *
 * 与主 Agent 入口（main.js）的差异：
 * - 不加载 loadAppConfig / brandTitle：运维控制台是独立桌面，不需要运行时品牌配置
 * - 不引入 src/styles/main.css：避免与政务蓝主题（ops-console.css）冲突
 * - 不依赖 src/utils/api.js：本次 UI 迁移阶段使用静态 mock 数据
 *
 * 设计背景：Sidebar.vue 已有跳转逻辑（handleMenuClick 'ops-console'），
 * 通过 window.open('/ops-console.html') 在新窗口打开本页。
 *
 * @returns {void}
 */
import { createApp } from 'vue'
import App from './components/ops-console/OpsConsoleApp.vue'
import './styles/ops-console.css'

createApp(App).mount('#app')
