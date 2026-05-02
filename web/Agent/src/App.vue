<script setup>
import { ref } from 'vue'
import Sidebar from './components/Sidebar.vue'
import TopBar from './components/TopBar.vue'
import SkillTags from './components/SkillTags.vue'
import ChatArea from './components/ChatArea.vue'
import InputBox from './components/InputBox.vue'

// 当前会话标题
const currentTitle = ref('新对话')

// 处理新建聊天
const handleNewChat = () => {
  currentTitle.value = '新对话'
  console.log('新建聊天')
}

// 处理分享
const handleShare = () => {
  console.log('分享对话')
}

// 处理技能标签选择
const handleTagSelect = (tag, index) => {
  console.log('选择技能标签:', tag.label)
  // 可以在这里触发相关操作，如自动填充输入框等
}

// 处理发送消息
const handleSendMessage = (message) => {
  console.log('发送消息:', message)
  // 这里可以添加消息到列表的逻辑
}

// 处理全能模式切换
const handleTogglePower = (isFullPower) => {
  console.log('全能模式:', isFullPower ? '开启' : '关闭')
}

// 处理工具栏操作
const handleToolAction = (action) => {
  console.log('工具操作:', action)
}
</script>

<template>
  <div class="app-layout">
    <!-- 顶部栏 -->
    <TopBar
      :title="currentTitle"
      @new-chat="handleNewChat"
      @share="handleShare"
    />

    <!-- 主体内容区域 -->
    <div class="main-container">
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
          @toggle-power="handleTogglePower"
          @tool-action="handleToolAction"
        />
      </main>
    </div>
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100vh;
  background-color: var(--color-bg-secondary);
  overflow: hidden;
}

/* 主体容器 */
.main-container {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* 内容区域 */
.content-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: var(--color-bg-secondary);
}
</style>
