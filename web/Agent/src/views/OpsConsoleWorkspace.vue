<!--
  运维控制台 Workspace（智能运维中心）
  - 路由：/ops-console
  - 委托给 OpsConsoleApp 渲染（政务蓝 macOS 风格多窗口）
  - 关键点：onMounted 主动加载 ops-console 样式（单例守卫）
    原 App.vue::handlePageChange('ops-console') 触发 ensureOpsConsoleStyles 的
    链路被本组件接管
-->
<template>
  <OpsConsoleApp />
</template>

<script setup>
import { onMounted } from 'vue'
import OpsConsoleApp from '../components/ops-console/OpsConsoleApp.vue'
import { ensureOpsConsoleStyles } from '../utils/ops-console-styles.js'

onMounted(() => {
  ensureOpsConsoleStyles()
})
</script>