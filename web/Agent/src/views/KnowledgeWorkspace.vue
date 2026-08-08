<!--
  知识库 Workspace
  - 路由：/knowledge
  - 委托给 KnowledgePage 渲染（已有完整 UI 逻辑）
  - 隔离：KnowledgePage 不感知路由，通过 router-view 注入到此 workspace
-->
<template>
  <KnowledgePage @new-chat="handleNewChat" @open-subagent-drawer="handleOpenSubAgentDrawer" />
</template>

<script setup>
import KnowledgePage from '../components/KnowledgePage.vue'

// 2026-08-XX 接入 vue-router 后，KnowledgePage 不再 emit('page-change')；
// 「新建会话」与「打开子智能体抽屉」事件仍透传，App.vue 通过 provide 注入方法。
// 这里先占位（保留 emits 链路完整性），commit 7 清理 KnowledgePage 后移除。
const emit = defineEmits(['new-chat', 'open-subagent-drawer'])

function handleNewChat() {
  emit('new-chat')
}
function handleOpenSubAgentDrawer(payload) {
  emit('open-subagent-drawer', payload)
}
</script>