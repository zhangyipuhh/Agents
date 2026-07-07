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
  },
  // 2026-07-01 新增：会话名称与文件抽屉入口控制
  sessionName: {
    type: String,
    default: ''
  },
  showFileIcon: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['copy', 'regenerate', 'like', 'dislike', 'open-subagent-drawer', 'open-session-file-drawer'])

const chatContainer = ref(null)
const showScrollButton = ref(false)
const showScrollToTopButton = ref(false)
const unreadCount = ref(0)
const lastScrollHeight = ref(0)

/**
 * 滚动到消息列表底部
 * 2026-07-02 修复：移除 behavior 参数与 scrollTo 调用，改为直接赋值 scrollTop（瞬时滚动），
 *   避免与全局 html { scroll-behavior: smooth } 叠加导致 smooth 滚动被中断、scrollTop 回弹到原值。
 *   nextTick 包裹确保 Vue 重渲染完成后再读取最新 scrollHeight。
 */
const scrollToBottom = () => {
  if (!chatContainer.value) return
  nextTick(() => {
    if (!chatContainer.value) return
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    unreadCount.value = 0
  })
}

/**
 * 滚动到消息列表顶部
 * 2026-07-02 修复：与 scrollToBottom 保持一致的瞬时滚动策略，直接赋值 scrollTop = 0。
 */
const scrollToTop = () => {
  if (!chatContainer.value) return
  nextTick(() => {
    if (!chatContainer.value) return
    chatContainer.value.scrollTop = 0
  })
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
  // 2026-07-02 修复：scrollToBottom 已改为无参函数，移除 'auto' 参数
  setTimeout(() => {
    scrollToBottom()
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
  <div class="chat-area">
    <!-- 2026-07-01 新增：会话名称头部与文件抽屉入口；2026-07-02 修正：外层 div 撑满主区两侧，
         内层 chat-area-header-inner 与下方 messages-container 一致采用 max-width: 900px + margin: 0 auto 居中 -->
    <div v-if="sessionName" class="chat-area-header">
      <div class="chat-area-header-inner">
        <span class="chat-session-name" :title="sessionName">{{ sessionName }}</span>
        <button
          v-if="showFileIcon"
          type="button"
          class="chat-file-drawer-btn"
          title="打开会话文件空间"
          aria-label="打开会话文件空间"
          @click="emit('open-session-file-drawer')"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" class="file-drawer-icon">
            <rect x="3.5" y="3.5" width="17" height="17" rx="2" ry="2"/>
            <line x1="8.5" y1="3.5" x2="8.5" y2="20.5"/>
          </svg>
        </button>
      </div>
    </div>

    <div class="messages-container" ref="chatContainer">
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
        :download-info="message.downloadInfo"
        :sub-agents="message.subAgents"
        @copy="(e) => emit('copy', e)"
        @regenerate="(id) => emit('regenerate', id)"
        @like="(id) => emit('like', id)"
        @dislike="(id) => emit('dislike', id)"
        @open-subagent-drawer="(sa) => emit('open-subagent-drawer', sa)"
      />
    </div>

    <!-- 滚动按钮组 -->
    <!-- 2026-07-02 修复：去掉 <transition> 包裹，避免 leave 动画与 smooth scroll 的 reflow 竞态
         导致 scrollTop 中断回弹（用户反馈「会话跳了一下又回到原位」的根因）。
         改为依赖 v-show 的 display 切换（无动画），保证滚动行为稳定。 -->
    <div class="scroll-buttons-wrapper">
      <button
        v-show="showScrollToTopButton"
        type="button"
        class="scroll-btn scroll-to-top-btn"
        @click="scrollToTop"
        title="滚动到顶部"
        aria-label="滚动到顶部"
      >
        <svg viewBox="0 0 20 20" fill="currentColor" class="scroll-icon">
          <path fill-rule="evenodd" d="M14.707 12.707a1 1 0 01-1.414 0L10 9.414l-3.293 3.293a1 1 0 01-1.414-1.414l4-4a1 1 0 011.414 0l4 4a1 1 0 010 1.414z" clip-rule="evenodd"/>
        </svg>
      </button>

      <button
        v-show="showScrollButton"
        type="button"
        class="scroll-btn scroll-to-bottom-btn"
        @click="scrollToBottom"
        :title="unreadCount > 0 ? `有 ${unreadCount} 条新消息` : '滚动到底部'"
        :aria-label="unreadCount > 0 ? `有 ${unreadCount} 条新消息` : '滚动到底部'"
      >
        <svg viewBox="0 0 20 20" fill="currentColor" class="scroll-icon">
          <path fill-rule="evenodd" d="M5.293 12.707a1 1 0 011.414 0L10 9.414l3.293 3.293a1 1 0 111.414-1.414l-4-4a1 1 0 01-1.414 0l-4 4a1 1 0 010 1.414z" clip-rule="evenodd"/>
        </svg>
        <span v-if="unreadCount > 0" class="unread-badge">{{ unreadCount > 99 ? '99+' : unreadCount }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: var(--color-bg-secondary);
  position: relative;
}

/* 2026-07-01 新增：会话名称头部；2026-07-02 修正：与 .chat-area 采用 flex 纵向布局，
   避免 sticky 标题栏压盖滚动消息内容；2026-07-02 二次修正：外层 chat-area-header 撑满主区宽度
   与两侧连接(背景色铺满),内层 chat-area-header-inner 与下方 .messages-container 一致采用
   max-width: 900px + margin: 0 auto 居中,实现"外层连接两侧 + 内容向中间靠拢与聊天区对齐" */
.chat-area-header {
  flex-shrink: 0;
  margin: 0;
  padding: 8px 0;
  background-color: var(--color-bg-secondary);
}

.chat-area-header-inner {
  max-width: 900px;
  margin: 0 auto;
  padding: 0 40px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.chat-session-name {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

.chat-file-drawer-btn {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-left: 12px;
  padding: 0;
  background-color: rgba(30, 90, 168, 0.06);
  border: 0.5px solid rgba(30, 90, 168, 0.16);
  border-radius: 6px;
  color: #1E5AA8;
  cursor: pointer;
  transition: background-color 0.2s ease, border-color 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease;
  box-shadow: none;
}

.chat-file-drawer-btn:hover {
  background-color: rgba(30, 90, 168, 0.1);
  border-color: rgba(30, 90, 168, 0.28);
  transform: translateY(-1px);
  box-shadow: 0 1px 4px rgba(30, 90, 168, 0.1);
}

.chat-file-drawer-btn:active {
  transform: scale(var(--scale-active));
}

.file-drawer-icon {
  width: 14px;
  height: 14px;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 0 40px 24px;
  position: relative;
  max-width: 900px;
  margin: 0 auto;
  width: 100%;
  display: flex;
  flex-direction: column;

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

/* 2026-07-02 移除：旧的 .fade-* transition 规则与 smooth scroll 存在 reflow 竞态，
   当前模板已不再使用 <transition name="fade">，保留为空以避免被误用恢复原 bug。
   若未来需要按钮淡入淡出，请改用 transition-group + 单层 wrapper，避免 leave 动画
   与 in-flight scrollTo 在同一帧触发。 */

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
