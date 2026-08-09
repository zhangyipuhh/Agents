<!--
  运维控制台 Workspace（智能运维中心）
  - 路由：/ops-console
  - 委托给 OpsConsoleApp 渲染（政务蓝 macOS 风格多窗口）
  - 2026-08-09：新增「关闭整个运维控制台」出口
    - 新 Tab 场景（被 window.open 打开）：window.close() 优先
    - 直接访问场景：降级为 router.push('/')
-->
<template>
  <OpsConsoleApp @exit="handleExit" />
</template>

<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import OpsConsoleApp from '../components/ops-console/OpsConsoleApp.vue'
import { ensureOpsConsoleStyles } from '../utils/ops-console-styles.js'

const router = useRouter()

onMounted(() => {
  ensureOpsConsoleStyles()
})

/**
 * 关闭整个运维控制台。
 * 优先 window.close()（仅对被 window.open 打开的 Tab 有效）；
 * 失败/无 opener 时降级为同 Tab 路由跳 /，回到主会话界面。
 * @returns {void}
 */
function handleExit() {
  // 1) 尝试 window.close：仅在被脚本打开的 Tab 有效
  try {
    if (window.opener || (window.history && window.history.length === 1)) {
      window.close()
      return
    }
  } catch (_) { /* ignore */ }
  // 2) 降级：路由回主会话
  router.push('/')
}
</script>
