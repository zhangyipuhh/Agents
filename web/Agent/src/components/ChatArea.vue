<script setup>
import { ref, nextTick, onMounted, watch, onBeforeUnmount } from 'vue'
import MessageBubble from './MessageBubble.vue'

// 消息列表
const messages = ref([
  {
    id: 1,
    type: 'user',
    content: '你好，请介绍一下你的功能'
  },
  {
    id: 2,
    type: 'ai',
    content: ''
  }
])

// 聊天区域引用
const chatContainer = ref(null)

// 是否显示滚动到底部按钮
const showScrollButton = ref(false)

// 自动滚动到底部
const scrollToBottom = async () => {
  await nextTick()
  if (chatContainer.value) {
    chatContainer.value.scrollTo({
      top: chatContainer.value.scrollHeight,
      behavior: 'smooth'
    })
  }
}

// 监听滚动事件，控制滚动按钮显示
const handleScroll = () => {
  if (!chatContainer.value) return

  const { scrollTop, scrollHeight, clientHeight } = chatContainer.value
  const distanceFromBottom = scrollHeight - scrollTop - clientHeight

  // 当距离底部超过 200px 时显示按钮
  showScrollButton.value = distanceFromBottom > 200
}

// 监听消息变化，自动滚动
watch(messages, () => {
  scrollToBottom()
}, { deep: true })

// 组件挂载后滚动到底部
onMounted(() => {
  scrollToBottom()

  // 添加滚动监听
  if (chatContainer.value) {
    chatContainer.value.addEventListener('scroll', handleScroll)
  }
})

// 组件卸载前移除监听
onBeforeUnmount(() => {
  if (chatContainer.value) {
    chatContainer.value.removeEventListener('scroll', handleScroll)
  }
})

// 定义事件
const emit = defineEmits(['message-action'])
</script>

<template>
  <div class="chat-area" ref="chatContainer">
    <div class="messages-container">
      <!-- 空状态 -->
      <div v-if="messages.length === 0" class="empty-state">
        <div class="empty-icon">
          <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="32" cy="32" r="30" stroke="var(--color-border)" stroke-width="2"/>
            <path d="M32 20v24M20 32h24" stroke="var(--color-text-muted)" stroke-width="2.5" stroke-linecap="round"/>
          </svg>
        </div>
        <h3 class="empty-title">开始新对话</h3>
        <p class="empty-description">在下方输入框中输入你的问题，AI 助手将为你提供帮助</p>
      </div>

      <!-- 消息列表 -->
      <MessageBubble
        v-for="message in messages"
        :key="message.id"
        :type="message.type"
        :content="message.content"
      />
    </div>

    <!-- 滚动到底部按钮 -->
    <transition name="fade">
      <button
        v-if="showScrollButton"
        class="scroll-to-bottom-btn"
        @click="scrollToBottom"
        title="滚动到底部"
        aria-label="滚动到底部"
      >
        <svg viewBox="0 0 20 20" fill="currentColor" class="scroll-icon">
          <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/>
        </svg>
      </button>
    </transition>
  </div>
</template>

<style scoped>
.chat-area {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 24px 40px;
  background-color: var(--color-bg-secondary);
  position: relative;
  contain: layout style paint;

  /* 自定义滚动条样式 */
  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background-color: var(--color-border);
    border-radius: var(--radius-full);
    transition: background-color var(--transition-fast);

    &:hover {
      background-color: var(--color-text-muted);
    }
  }

  /* Firefox 滚动条 */
  scrollbar-width: thin;
  scrollbar-color: var(--color-border) transparent;
}

.messages-container {
  max-width: 900px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

/* 空状态样式 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 40px;
  text-align: center;
  animation: fadeInUp 0.5s ease-out;
}

.empty-icon {
  width: 80px;
  height: 80px;
  margin-bottom: 24px;
  opacity: 0.6;

  svg {
    width: 100%;
    height: 100%;
  }
}

.empty-title {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin-bottom: 8px;
}

.empty-description {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  line-height: var(--line-height-normal);
  max-width: 360px;
}

/* 滚动到底部按钮 */
.scroll-to-bottom-btn {
  position: absolute;
  bottom: 32px;
  right: 48px;
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background-color: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: 50%;
  box-shadow: var(--shadow-md);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: var(--transition-colors), var(--transition-transform), var(--transition-shadow);
  z-index: 10;

  &:hover {
    background-color: var(--color-accent);
    border-color: var(--color-accent);
    color: white;
    transform: translateY(-2px);
    box-shadow: var(--shadow-lg);
  }

  &:active:not(:disabled) {
    transform: scale(var(--scale-active)) translateY(0);
  }
}

.scroll-icon {
  width: 20px;
  height: 20px;
}

/* 淡入淡出动画 */
.fade-enter-active,
.fade-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(8px) scale(0.9);
}

/* 空状态入场动画 */
@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
