<script setup>
import { ref, reactive, nextTick, watch, onMounted, onBeforeUnmount, computed } from 'vue'
import { chatStream, createNewSession, refreshToken } from '../utils/api.js'
import { createAiMessage, processSSEEvent } from '../utils/sseParser.js'
import MessageBubble from './MessageBubble.vue'

const props = defineProps({
  sessionId: {
    type: String,
    default: ''
  },
  isStreaming: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['new-chat', 'send'])

const messages = reactive([])
const inputValue = ref('')
const textareaRef = ref(null)
const isFocused = ref(false)
const chatContainer = ref(null)
const internalStreaming = ref(false)
const showScrollButton = ref(false)
const unreadCount = ref(0)

const isCurrentlyStreaming = computed(() => props.isStreaming || internalStreaming.value)

const canSend = computed(() => {
  if (isCurrentlyStreaming.value) return false
  return inputValue.value.trim().length > 0
})

const autoResize = () => {
  const textarea = textareaRef.value
  if (textarea) {
    textarea.style.height = 'auto'
    const newHeight = Math.max(36, Math.min(textarea.scrollHeight, 120))
    textarea.style.height = newHeight + 'px'
  }
}

const handleInput = (event) => {
  inputValue.value = event.target.value
  autoResize()
}

const handleKeydown = (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleSend()
  }
}

const handleSend = async () => {
  if (!canSend.value) return

  const message = inputValue.value.trim()
  if (!message) return

  emit('send', message)

  inputValue.value = ''
  nextTick(() => autoResize())

  const userMsg = {
    id: Date.now(),
    type: 'user',
    content: message
  }
  messages.push(userMsg)

  const aiMsg = reactive(createAiMessage())
  messages.push(aiMsg)

  internalStreaming.value = true

  nextTick(() => scrollToBottom())

  try {
    await refreshToken()
  } catch (err) {
    aiMsg.error = '获取认证信息失败，请稍后重试'
    aiMsg.ended = true
    internalStreaming.value = false
    return
  }

  try {
    const stream = await chatStream(props.sessionId, message)
    const reader = stream.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const events = buffer.split('\n\n')
      buffer = events.pop()
      for (const event of events) {
        if (!event.startsWith('data: ')) continue
        try {
          const data = JSON.parse(event.slice(6))
          processSSEEvent(data, aiMsg)
        } catch {}
      }
      nextTick(() => scrollToBottom())
    }
  } catch (err) {
    aiMsg.error = '不好意思，刚刚出了点小故障，可以晚点再问我一遍。'
    aiMsg.ended = true
  } finally {
    internalStreaming.value = false
  }
}

const handleNewChat = async () => {
  try {
    await createNewSession()
  } catch (err) {
    console.error(err)
  }
  messages.splice(0, messages.length)
  emit('new-chat')
}

const scrollToBottom = (behavior = 'smooth') => {
  if (chatContainer.value) {
    chatContainer.value.scrollTo({
      top: chatContainer.value.scrollHeight,
      behavior
    })
    unreadCount.value = 0
  }
}

const handleScroll = () => {
  if (!chatContainer.value) return
  const { scrollTop, scrollHeight, clientHeight } = chatContainer.value
  const distanceFromBottom = scrollHeight - scrollTop - clientHeight
  if (isCurrentlyStreaming.value) {
    showScrollButton.value = false
    return
  }
  showScrollButton.value = distanceFromBottom > 150
  if (distanceFromBottom < 50) {
    unreadCount.value = 0
  }
}

watch(() => messages.length, (newLength, oldLength) => {
  if (!chatContainer.value) return
  const { scrollTop, scrollHeight, clientHeight } = chatContainer.value
  const distanceFromBottom = scrollHeight - scrollTop - clientHeight
  if (distanceFromBottom > 150 && newLength > oldLength) {
    unreadCount.value += 1
    showScrollButton.value = true
  } else {
    nextTick(() => scrollToBottom())
  }
})

watch(() => messages, () => {
  if (isCurrentlyStreaming.value) {
    nextTick(() => scrollToBottom())
  }
}, { deep: true })

onMounted(() => {
  setTimeout(() => scrollToBottom('auto'), 0)
  if (chatContainer.value) {
    chatContainer.value.addEventListener('scroll', handleScroll)
  }
})

onBeforeUnmount(() => {
  if (chatContainer.value) {
    chatContainer.value.removeEventListener('scroll', handleScroll)
  }
})
</script>

<template>
  <div class="knowledge-chat">
    <div class="chat-header">
      <span class="chat-title">知识库问答</span>
      <button class="new-chat-btn" @click="handleNewChat" title="新建任务">
        <svg viewBox="0 0 20 20" fill="currentColor" class="btn-icon">
          <path d="M10 5a1 1 0 011 1v3h3a1 1 0 110 2h-3v3a1 1 0 11-2 0v-3H6a1 1 0 110-2h3V6a1 1 0 011-1z"/>
        </svg>
        <span class="btn-text">新建任务</span>
      </button>
    </div>

    <div class="chat-body" ref="chatContainer">
      <div class="messages-container">
        <div v-if="messages.length === 0" class="empty-state">
          <div class="empty-icon">
            <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="32" cy="32" r="30" stroke="var(--color-border)" stroke-width="2"/>
              <path d="M32 20v24M20 32h24" stroke="var(--color-text-muted)" stroke-width="2.5" stroke-linecap="round"/>
            </svg>
          </div>
          <h3 class="empty-title">向知识库提问</h3>
          <p class="empty-description">输入问题，获取基于知识库的精准回答</p>
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
        />
      </div>

      <teleport to="body">
        <transition name="fade">
          <button
            v-show="showScrollButton"
            type="button"
            class="scroll-to-bottom-btn"
            @click="scrollToBottom('smooth')"
            :title="unreadCount > 0 ? `有 ${unreadCount} 条新消息` : '滚动到底部'"
          >
            <svg viewBox="0 0 20 20" fill="currentColor" class="scroll-icon">
              <path fill-rule="evenodd" d="M5.293 12.707a1 1 0 011.414 0L10 9.414l3.293 3.293a1 1 0 111.414-1.414l-4-4a1 1 0 01-1.414 0l-4 4a1 1 0 010 1.414z" clip-rule="evenodd"/>
            </svg>
            <span v-if="unreadCount > 0" class="unread-badge">{{ unreadCount > 99 ? '99+' : unreadCount }}</span>
          </button>
        </transition>
      </teleport>
    </div>

    <div class="chat-input-area">
      <div class="input-main" :class="{ focused: isFocused }">
        <textarea
          ref="textareaRef"
          v-model="inputValue"
          class="text-input"
          placeholder="输入问题，按 Enter 发送"
          rows="2"
          @input="handleInput"
          @keydown="handleKeydown"
          @focus="isFocused = true"
          @blur="isFocused = false"
        ></textarea>
        <div class="input-bottom-row">
          <span class="input-hint">Shift+Enter 换行</span>
          <button
            class="send-btn"
            :class="{ disabled: !canSend }"
            :disabled="!canSend"
            @click="handleSend"
            title="发送消息"
          >
            <svg viewBox="0 0 20 20" fill="currentColor" class="send-icon">
              <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z"/>
            </svg>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.knowledge-chat {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background-color: var(--color-bg-primary);
  border-left: 1px solid var(--color-border);
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

.chat-title {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.new-chat-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background-color: var(--color-accent);
  color: white;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  transition: var(--transition-colors), var(--transition-transform);

  &:hover {
    background-color: var(--color-accent-hover);
  }

  &:active {
    transform: scale(var(--scale-active));
  }
}

.btn-icon {
  width: 14px;
  height: 14px;
}

.btn-text {
  line-height: 1;
}

.chat-body {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 16px;
  position: relative;

  &::-webkit-scrollbar {
    width: 4px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background-color: var(--color-border);
    border-radius: var(--radius-full);
  }

  scrollbar-width: thin;
  scrollbar-color: var(--color-border) transparent;
}

.messages-container {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
  flex: 1;
  animation: fadeInUp 0.5s ease-out;
}

.empty-icon {
  width: 64px;
  height: 64px;
  margin-bottom: 20px;
  opacity: 0.5;

  svg {
    width: 100%;
    height: 100%;
  }
}

.empty-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0 0 8px;
}

.empty-description {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  line-height: var(--line-height-normal);
  max-width: 280px;
  margin: 0;
}

.scroll-to-bottom-btn {
  position: fixed;
  bottom: 160px;
  right: 48px;
  width: 36px;
  height: 36px;
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
  z-index: 1000;
  pointer-events: auto;

  &:hover {
    background-color: var(--color-accent);
    border-color: var(--color-accent);
    color: white;
    transform: translateY(-2px);
    box-shadow: var(--shadow-lg);
  }

  &:active {
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
}

.scroll-icon {
  width: 18px;
  height: 18px;
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

.chat-input-area {
  padding: 12px 16px 16px;
  border-top: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

.input-main {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  background-color: var(--color-bg-secondary);
  border: 2px solid var(--color-border);
  border-radius: var(--radius-md);
  transition: border-color 0.25s ease, box-shadow 0.25s ease;

  &.focused {
    border-color: var(--color-accent);
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
  }
}

.text-input {
  width: 100%;
  min-height: 36px;
  max-height: 120px;
  padding: 4px 0;
  font-size: var(--font-size-sm);
  line-height: var(--line-height-normal);
  color: var(--color-text-primary);
  background-color: transparent;
  resize: none;
  overflow-y: auto;
  font-family: inherit;

  &::placeholder {
    color: var(--color-text-muted);
  }

  &::-webkit-scrollbar {
    width: 4px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background-color: var(--color-border);
    border-radius: var(--radius-full);
  }

  &:focus {
    outline: none;
    box-shadow: none;
  }
}

.input-bottom-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.input-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.send-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  background-color: var(--color-accent);
  color: white;
  border-radius: 50%;
  cursor: pointer;
  flex-shrink: 0;
  transition: var(--transition-colors), var(--transition-transform);

  &:hover:not(.disabled) {
    background-color: var(--color-accent-hover);
    transform: scale(1.08);
  }

  &:active:not(.disabled) {
    transform: scale(0.95);
  }

  &.disabled {
    background-color: var(--color-border);
    cursor: not-allowed;
    opacity: var(--opacity-disabled);
  }
}

.send-icon {
  width: 14px;
  height: 14px;
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
</style>
