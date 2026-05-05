<script setup>
import { ref } from 'vue'
import Sidebar from './components/Sidebar.vue'
import SkillTags from './components/SkillTags.vue'
import ChatArea from './components/ChatArea.vue'
import InputBox from './components/InputBox.vue'

const chatAreaRef = ref(null)

const handleTagSelect = (tag, index) => {
  console.log('选择技能标签:', tag.label)
}

const handleSendMessage = (message, attachments = []) => {
  const newMessage = {
    id: Date.now(),
    type: 'user',
    content: message,
    attachments
  }
  if (chatAreaRef.value && chatAreaRef.value.addMessage) {
    chatAreaRef.value.addMessage(newMessage)
  }
  console.log('发送消息:', message, '附件:', attachments)
}

const handleToolAction = (action) => {
  console.log('工具操作:', action)
}
</script>

<template>
  <div class="app-layout">
    <Sidebar />

    <main class="content-area">
      <SkillTags @tag-select="handleTagSelect" />

      <ChatArea ref="chatAreaRef" />

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
