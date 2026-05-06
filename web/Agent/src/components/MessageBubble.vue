<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { marked } from 'marked'
import { formatFileSize, getFileExtension } from '../utils/api.js'

const props = defineProps({
  type: {
    type: String,
    default: 'user',
    validator: (value) => ['user', 'ai'].includes(value)
  },
  content: {
    type: [String, Object],
    default: ''
  },
  attachments: {
    type: Array,
    default: () => []
  },
  thinking: {
    type: Array,
    default: () => []
  },
  tools: {
    type: Array,
    default: () => []
  },
  text: {
    type: String,
    default: ''
  },
  ended: {
    type: Boolean,
    default: false
  },
  error: {
    type: String,
    default: ''
  },
  messageId: {
    type: [String, Number],
    default: ''
  }
})

const emit = defineEmits(['copy', 'regenerate', 'like', 'dislike'])

const isThinkingExpanded = ref(false)
const isToolsExpanded = ref(false)
const thinkingContainer = ref(null)

const isUserMessage = computed(() => props.type === 'user')
const hasAttachments = computed(() => props.attachments && props.attachments.length > 0)
const hasThinking = computed(() => props.thinking && props.thinking.length > 0)
const hasTools = computed(() => props.tools && props.tools.length > 0)
const hasText = computed(() => props.text && props.text.length > 0)
const hasError = computed(() => props.error && props.error.length > 0)
const isStreaming = computed(() => !props.ended && !hasError.value && hasThinking.value)

const renderedText = computed(() => {
  if (!hasText.value) return ''
  try {
    return marked.parse(props.text)
  } catch {
    return props.text.replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br/>').replace(/^/, '<p>').replace(/$/, '</p>')
  }
})

function formatThinkingItem(item) {
  if (typeof item === 'string') return item
  if (!item) return ''
  if (item.thinking) return item.thinking
  if (item.text) return item.text
  if (item.data) {
    const d = item.data
    const nodeName = Object.keys(d)[0]
    const nodeData = d[nodeName]
    if (!nodeData) return JSON.stringify(d, null, 2)
    if (typeof nodeData === 'string') return nodeData
    if (nodeData.messages && Array.isArray(nodeData.messages)) {
      return nodeData.messages.map(m => typeof m === 'string' ? m : JSON.stringify(m)).join('\n')
    }
    return JSON.stringify(nodeData, null, 2)
  }
  return JSON.stringify(item, null, 2)
}

function formatToolItem(item) {
  if (typeof item === 'string') return item
  if (!item) return ''
  if (item.data) return JSON.stringify(item.data)
  if (item.name || item.tool) return item.name || item.tool
  return JSON.stringify(item)
}

const toggleThinking = () => {
  isThinkingExpanded.value = !isThinkingExpanded.value
}

const toggleTools = () => {
  isToolsExpanded.value = !isToolsExpanded.value
}

const handleCopy = async () => {
  const textToCopy = props.text || ''
  try {
    await navigator.clipboard.writeText(textToCopy)
    emit('copy', { success: true, messageId: props.messageId })
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = textToCopy
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    emit('copy', { success: true, messageId: props.messageId })
  }
}

const handleRegenerate = () => {
  emit('regenerate', props.messageId)
}

const handleLike = () => {
  emit('like', props.messageId)
}

const handleDislike = () => {
  emit('dislike', props.messageId)
}

const getFileIconColor = (filename) => {
  const ext = getFileExtension(filename)
  const colorMap = {
    pdf: '#EF4444',
    doc: '#3B82F6', docx: '#3B82F6',
    xls: '#10B981', xlsx: '#10B981', csv: '#10B981',
    jpg: '#8B5CF6', jpeg: '#8B5CF6', png: '#8B5CF6', gif: '#8B5CF6',
    txt: '#6B7280', md: '#6B7280',
    ppt: '#F59E0B', pptx: '#F59E0B',
  }
  return colorMap[ext] || '#9CA3AF'
}
</script>

<template>
  <div class="message-bubble" :class="[type]">
    <!-- 用户消息 -->
    <div v-if="isUserMessage" class="user-message">
      <div class="bubble-content">
        <div v-if="hasAttachments" class="bubble-attachments">
          <div
            v-for="(att, idx) in attachments"
            :key="idx"
            class="bubble-attachment-tag"
          >
            <svg class="att-icon" viewBox="0 0 20 20" fill="currentColor" :style="{ color: getFileIconColor(att.original_name || att.filename) }">
              <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clip-rule="evenodd"/>
            </svg>
            <span class="att-name">{{ att.original_name || att.filename }}</span>
            <span v-if="att.size" class="att-size">{{ formatFileSize(att.size) }}</span>
          </div>
        </div>
        <div v-if="content" class="bubble-text">{{ content }}</div>
      </div>
    </div>

    <!-- AI 消息 -->
    <div v-else class="ai-message">
      <!-- 思考过程 -->
      <div v-if="hasThinking" class="thinking-section">
        <div class="thinking-header" @click="toggleThinking">
          <span class="thinking-icon">🧠</span>
          <span class="thinking-label">思考过程</span>
          <svg
            class="expand-icon"
            :class="{ expanded: isThinkingExpanded }"
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/>
          </svg>
        </div>
        <div v-if="isThinkingExpanded" class="thinking-body" ref="thinkingContainer">
          <div
            v-for="(item, index) in thinking"
            :key="index"
            class="thinking-item"
          >
            <pre class="thinking-content">{{ formatThinkingItem(item) }}</pre>
          </div>
        </div>
      </div>

      <!-- 工具调用 -->
      <div v-if="hasTools" class="tools-section">
        <div class="tools-header" @click="toggleTools">
          <span class="tools-icon">🔧</span>
          <span class="tools-label">工具调用 ({{ tools.length }})</span>
          <svg
            class="expand-icon"
            :class="{ expanded: isToolsExpanded }"
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/>
          </svg>
        </div>
        <div v-if="isToolsExpanded" class="tools-body">
          <div
            v-for="(item, index) in tools"
            :key="'tool-' + index"
            class="tool-item"
          >
            <span class="tool-icon">🔧</span>
            <span class="tool-text">{{ formatToolItem(item) }}</span>
          </div>
        </div>
      </div>

      <!-- 正文内容 -->
      <div v-if="hasText" class="text-section">
        <div class="markdown-body" v-html="renderedText"></div>
        <span v-if="!ended && !error" class="streaming-cursor">▌</span>
      </div>

      <!-- 错误信息 -->
      <div v-if="hasError" class="error-section">
        <span class="error-icon">❌</span>
        <span class="error-text">{{ error }}</span>
      </div>

      <!-- 加载状态（无任何内容时） -->
      <div v-if="!hasThinking && !hasText && !hasError" class="loading-section">
        <span class="loading-dot">●</span>
        <span class="loading-dot" style="animation-delay: 0.2s">●</span>
        <span class="loading-dot" style="animation-delay: 0.4s">●</span>
      </div>

      <!-- 操作按钮 -->
      <div v-if="props.ended && (hasText || hasError)" class="message-actions">
        <button class="action-btn" title="复制" @click="handleCopy">
          <svg class="action-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
            <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
          </svg>
        </button>
        <button class="action-btn" title="重新生成" @click="handleRegenerate">
          <svg class="action-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="23 4 23 10 17 10"/>
            <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
          </svg>
        </button>
        <button class="action-btn" title="喜欢" @click="handleLike">
          <svg class="action-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3zM7 22H4a2 2 0 01-2-2v-7a2 2 0 012-2h3"/>
          </svg>
        </button>
        <button class="action-btn" title="不喜欢" @click="handleDislike">
          <svg class="action-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M10 15v4a3 3 0 003 3l4-9V2H5.72a2 2 0 00-2 1.7l-1.38 9a2 2 0 002 2.3zm7-13h3a2 2 0 012 2v7a2 2 0 01-2 2h-3"/>
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.message-bubble {
  width: 100%;
  margin-bottom: 24px;
  animation: messageSlideIn 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  contain: layout style paint;

  &:last-child {
    margin-bottom: 0;
  }
}

@keyframes messageSlideIn {
  from {
    opacity: 0;
    transform: translateY(16px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 用户消息 */
.user-message {
  display: flex;
  justify-content: flex-end;
  width: 100%;
}

.bubble-content {
  max-width: 70%;
  padding: 12px 16px;
  background-color: var(--color-accent);
  color: white;
  border-radius: 12px 12px 4px 12px;
  font-size: var(--font-size-base);
  line-height: var(--line-height-normal);
  word-wrap: break-word;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.15);
  transition: var(--transition-shadow);
}

.bubble-content:hover {
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.25);
}

.bubble-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.bubble-attachment-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  background-color: rgba(255, 255, 255, 0.2);
  border-radius: 6px;
  font-size: 12px;
}

.att-icon {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
}

.att-name {
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.att-size {
  opacity: 0.7;
  font-size: 11px;
}

.bubble-text {
  white-space: pre-wrap;
}

/* AI 消息 */
.ai-message {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  width: 100%;
}

/* 思考过程 */
.thinking-section {
  max-width: 85%;
  margin-bottom: 12px;
}

.thinking-header {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background-color: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 0.875em;
  color: var(--color-text-secondary);
  transition: background-color 0.2s ease;
  user-select: none;
}

.thinking-header:hover {
  background-color: var(--color-bg-hover);
}

.thinking-icon {
  font-size: 14px;
}

.thinking-label {
  font-size: 0.875em;
}

.expand-icon {
  width: 14px;
  height: 14px;
  color: var(--color-text-muted);
  transition: transform 0.2s ease;
}

.expand-icon.expanded {
  transform: rotate(180deg);
}

.thinking-body {
  margin-top: 8px;
  padding: 12px 16px;
  background-color: var(--color-bg-tertiary);
  border-radius: var(--radius-md);
  max-height: 200px;
  overflow-y: auto;
  font-size: 0.875em;
  color: var(--color-text-secondary);
  animation: expandIn 0.3s cubic-bezier(0.4, 0, 0.2, 1);

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

.thinking-item {
  margin-bottom: 8px;

  &:last-child {
    margin-bottom: 0;
  }
}

.thinking-content {
  font-size: 0.875em;
  color: var(--color-text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-family: inherit;
  line-height: 1.6;
}

/* 工具调用 */
.tools-section {
  max-width: 85%;
  margin-bottom: 10px;
}

.tools-header {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background-color: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 0.875em;
  color: var(--color-text-secondary);
  transition: background-color 0.2s ease;
  user-select: none;
}

.tools-header:hover {
  background-color: var(--color-bg-hover);
}

.tools-icon {
  font-size: 14px;
}

.tools-label {
  font-size: 0.875em;
}

.tools-body {
  margin-top: 8px;
  padding: 12px 16px;
  background-color: var(--color-bg-tertiary);
  border-radius: var(--radius-md);
  max-height: 200px;
  overflow-y: auto;
  animation: expandIn 0.3s cubic-bezier(0.4, 0, 0.2, 1);

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

.tool-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 0.875em;
  color: var(--color-text-secondary);
  line-height: 1.5;
  margin-bottom: 4px;
}

.tool-icon {
  font-size: 14px;
  flex-shrink: 0;
  margin-top: 1px;
}

.tool-text {
  word-break: break-all;
  opacity: 0.85;
}

/* 正文 */
.text-section {
  max-width: 85%;
  font-size: var(--font-size-base);
  line-height: 1.6;
  color: var(--color-text-primary);
}

.markdown-body {
  display: inline;
}

.markdown-body :deep(p) {
  margin-bottom: 10px;
  line-height: 1.7;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  margin-top: 16px;
  margin-bottom: 8px;
  font-weight: var(--font-weight-semibold);
}

.markdown-body :deep(h2) {
  font-size: 1.2em;
}

.markdown-body :deep(h3) {
  font-size: 1.1em;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 20px;
  margin-bottom: 10px;
}

.markdown-body :deep(li) {
  margin-bottom: 4px;
}

.markdown-body :deep(code) {
  background-color: var(--color-bg-tertiary);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
}

.markdown-body :deep(pre) {
  background-color: var(--color-bg-tertiary);
  padding: 12px 16px;
  border-radius: var(--radius-md);
  overflow-x: auto;
  margin-bottom: 12px;
}

.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
}

.markdown-body :deep(strong) {
  font-weight: var(--font-weight-semibold);
}

.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--color-accent);
  padding-left: 12px;
  margin: 8px 0;
  color: var(--color-text-secondary);
}

.streaming-cursor {
  display: inline;
  color: var(--color-accent);
  animation: blink 1s step-end infinite;
  font-size: 1em;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* 错误 */
.error-section {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background-color: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: var(--radius-sm);
  font-size: 0.875em;
  color: var(--color-error);
  max-width: 85%;
}

.error-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.error-text {
  word-break: break-word;
}

/* 加载动画 */
.loading-section {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px 0;
}

.loading-dot {
  font-size: 12px;
  color: var(--color-text-muted);
  animation: dotPulse 1.4s ease-in-out infinite;
}

@keyframes dotPulse {
  0%, 80%, 100% {
    opacity: 0.3;
    transform: scale(0.8);
  }
  40% {
    opacity: 1;
    transform: scale(1);
  }
}

/* 展开动画 */
@keyframes expandIn {
  from {
    opacity: 0;
    max-height: 0;
  }
  to {
    opacity: 1;
    max-height: 200px;
  }
}

/* 消息操作按钮 */
.message-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 8px;
  padding-left: 2px;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  background-color: transparent;
  border: none;
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: var(--transition-colors), var(--transition-transform);

  &:hover {
    color: var(--color-text-secondary);
    background-color: var(--color-bg-hover);
  }

  &:active {
    transform: scale(0.92);
  }
}

.action-icon {
  width: 16px;
  height: 16px;
}
</style>
