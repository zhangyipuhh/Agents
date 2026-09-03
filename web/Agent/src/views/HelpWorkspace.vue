<!--
  帮助 Workspace
  - 路由：/help
  - 委托给 HelpLayout 渲染（三栏 layout）
  - 引入帮助页专用 CSS（LangChain 风）
-->
<template>
  <HelpLayout />
</template>

<script setup>
import { onMounted } from 'vue'
import HelpLayout from '../components/help/HelpLayout.vue'
import '../styles/help.css'

onMounted(() => {
  // 帮助页样式已在 import 时按需加载，无需 ensure 模式
})
</script>