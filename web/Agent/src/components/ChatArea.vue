<script setup>
import { ref, nextTick, onMounted, watch, onBeforeUnmount, computed } from 'vue'
import MessageBubble from './MessageBubble.vue'

const props = defineProps({
  messages: {
    type: Array,
    default: () => []
  },
  isStreaming: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['copy', 'regenerate', 'like', 'dislike'])

const chatContainer = ref(null)
const showScrollButton = ref(false)
const showScrollToTopButton = ref(false)
const unreadCount = ref(0)
const lastScrollHeight = ref(0)

const scrollToBottom = (behavior = 'smooth') => {
  console.log('scrollToBottom called, chatContainer:', chatContainer.value)
  if (chatContainer.value) {
    const scrollHeight = chatContainer.value.scrollHeight
    console.log('Scrolling to:', scrollHeight)
    chatContainer.value.scrollTo({
      top: scrollHeight,
      behavior
    })
    unreadCount.value = 0
  }
}

// 处理按钮点击事件
const handleScrollToBottomClick = (event) => {
  console.log('Button clicked!', event)
  scrollToBottom('smooth')
}

// 滚动到顶部
const scrollToTop = (behavior = 'smooth') => {
  if (chatContainer.value) {
    chatContainer.value.scrollTo({
      top: 0,
      behavior
    })
  }
}

const handleScroll = () => {
  if (!chatContainer.value) return

  const { scrollTop, scrollHeight, clientHeight } = chatContainer.value
  const distanceFromBottom = scrollHeight - scrollTop - clientHeight

  if (props.isStreaming) {
    showScrollButton.value = false
    return
  }

  // 当距离底部超过 150px 时显示按钮
  const shouldShow = distanceFromBottom > 150
  showScrollButton.value = shouldShow

  // 如果滚动到底部附近，重置未读计数
  if (distanceFromBottom < 50) {
    unreadCount.value = 0
  }

  // 当距离顶部超过 200px 时显示"滚动到顶部"按钮
  showScrollToTopButton.value = scrollTop > 200
}

// 监听新消息
watch(() => props.messages.length, (newLength, oldLength) => {
  if (!chatContainer.value) return

  const { scrollTop, scrollHeight, clientHeight } = chatContainer.value
  const distanceFromBottom = scrollHeight - scrollTop - clientHeight

  // 如果用户正在查看历史消息（不在底部），且收到新消息
  if (distanceFromBottom > 150 && newLength > oldLength) {
    unreadCount.value += 1
    showScrollButton.value = true
  } else {
    // 否则自动滚动到底部
    nextTick(() => scrollToBottom())
  }
})

watch(() => props.messages, () => {
  if (props.isStreaming) {
    nextTick(() => scrollToBottom())
  }
}, { deep: true })

// 键盘快捷键处理
const handleKeyDown = (e) => {
  const activeElement = document.activeElement
  const isInputFocused = activeElement && (activeElement.tagName === 'INPUT' || activeElement.tagName === 'TEXTAREA')

  // End 键滚动到底部
  if (e.key === 'End' && !e.ctrlKey && !e.altKey && !e.shiftKey && !e.metaKey) {
    // 如果不在输入框中，则响应快捷键
    if (!isInputFocused) {
      scrollToBottom()
    }
  }

  // Home 键滚动到顶部
  if (e.key === 'Home' && !e.ctrlKey && !e.altKey && !e.shiftKey && !e.metaKey) {
    // 如果不在输入框中，则响应快捷键
    if (!isInputFocused) {
      scrollToTop()
    }
  }
}

onMounted(() => {
  // 使用 setTimeout 确保 DOM 完全渲染后再滚动
  setTimeout(() => {
    scrollToBottom('auto')
  }, 0)
  if (chatContainer.value) {
    chatContainer.value.addEventListener('scroll', handleScroll)
  }
  document.addEventListener('keydown', handleKeyDown)
})

onBeforeUnmount(() => {
  if (chatContainer.value) {
    chatContainer.value.removeEventListener('scroll', handleScroll)
  }
  document.removeEventListener('keydown', handleKeyDown)
})

// 暴露方法给父组件
defineExpose({
  scrollToBottom
})
</script>

<template>
  <div class="chat-area" ref="chatContainer">
    <div class="messages-container">
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

      <MessageBubble
        v-for="message in messages"
        :key="message.id"
        :type="message.type"
        :content="message.content"
        :attachments="message.attachments"
        :timeline="message.timeline"
        :thinking="message.thinking"
        :tools="message.tools"
        :text="message.text"
        :ended="message.ended"
        :error="message.error"
        :message-id="message.id"
        :is-thinking-active="message.isThinkingActive"
        @copy="(e) => emit('copy', e)"
        @regenerate="(id) => emit('regenerate', id)"
        @like="(id) => emit('like', id)"
        @dislike="(id) => emit('dislike', id)"
      />
    </div>

    <!-- 滚动按钮组 -->
    <div class="scroll-buttons-wrapper">
      <transition name="fade">
        <button
          v-show="showScrollToTopButton"
          type="button"
          class="scroll-btn scroll-to-top-btn"
          @click="scrollToTop('smooth')"
          title="滚动到顶部"
          aria-label="滚动到顶部"
        >
          <svg viewBox="0 0 20 20" fill="currentColor" class="scroll-icon">
            <path fill-rule="evenodd" d="M14.707 12.707a1 1 0 01-1.414 0L10 9.414l-3.293 3.293a1 1 0 01-1.414-1.414l4-4a1 1 0 011.414 0l4 4a1 1 0 010 1.414z" clip-rule="evenodd"/>
          </svg>
        </button>
      </transition>

      <transition name="fade">
        <button
          v-show="showScrollButton"
          type="button"
          class="scroll-btn scroll-to-bottom-btn"
          @click="handleScrollToBottomClick"
          :title="unreadCount > 0 ? `有 ${unreadCount} 条新消息` : '滚动到底部'"
          :aria-label="unreadCount > 0 ? `有 ${unreadCount} 条新消息` : '滚动到底部'"
        >
          <svg viewBox="0 0 20 20" fill="currentColor" class="scroll-icon">
            <path fill-rule="evenodd" d="M5.293 12.707a1 1 0 011.414 0L10 9.414l3.293 3.293a1 1 0 111.414-1.414l-4-4a1 1 0 01-1.414 0l-4 4a1 1 0 010 1.414z" clip-rule="evenodd"/>
          </svg>
          <span v-if="unreadCount > 0" class="unread-badge">{{ unreadCount > 99 ? '99+' : unreadCount }}</span>
        </button>
      </transition>
    </div>
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

.scroll-buttons-wrapper {
  position: absolute;
  right: 20px;
  bottom: 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  z-index: 100;
}

.scroll-btn {
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
  pointer-events: auto;

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

.unread-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  background-color: #EF4444;
  color: white;
  font-size: 11px;
  font-weight: 600;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 4px rgba(239, 68, 68, 0.3);
  animation: badgePulse 2s ease-in-out infinite;
}

.scroll-icon {
  width: 20px;
  height: 20px;
}

.fade-enter-active,
.fade-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(8px) scale(0.9);
}

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

@keyframes badgePulse {
  0%, 100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.1);
  }
}
</style>
