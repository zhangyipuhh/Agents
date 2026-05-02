<script setup>
import { ref } from 'vue'
import Sidebar from './components/Sidebar.vue'
import SkillTags from './components/SkillTags.vue'
import ChatArea from './components/ChatArea.vue'
import InputBox from './components/InputBox.vue'

const handleTagSelect = (tag, index) => {
  console.log('选择技能标签:', tag.label)
}

const handleSendMessage = (message) => {
  console.log('发送消息:', message)
}

const handleToolAction = (action) => {
  console.log('工具操作:', action)
}
</script>

<template>
  <div class="app-layout">
    <!-- 左侧边栏 -->
    <Sidebar />

    <!-- 右侧内容区 -->
    <main class="content-area">
      <!-- 技能标签栏 -->
      <SkillTags @tag-select="handleTagSelect" />

      <!-- 聊天消息区域 -->
      <ChatArea />

      <!-- 底部输入区域 -->
      <InputBox
        @send="handleSendMessage"
        @tool-action="handleToolAction"
      />
    </main>
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  width: 100%;
  height: 100vh;
  background-color: var(--color-bg-secondary);
  overflow: hidden;
}

.content-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: var(--color-bg-secondary);
}
</style>
