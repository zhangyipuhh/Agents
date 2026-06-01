<script setup>
import { ref, computed } from 'vue'
import { marked } from 'marked'

/**
 * 将 Markdown 文本转换为 HTML
 * @param {string} text - Markdown 格式的文本
 * @returns {string} 转换后的 HTML 字符串
 */
function renderMarkdown(text) {
  if (!text) return ''
  try {
    return marked.parse(text)
  } catch {
    return text.replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br/>').replace(/^/, '<p>').replace(/$/, '</p>')
  }
}

const props = defineProps({
  title: {
    type: String,
    default: '需要您的确认'
  },
  content: {
    type: String,
    default: ''
  },
  config: {
    type: Object,
    default: () => ({
      allow_ignore: false,
      allow_respond: true,
      allow_edit: false,
      allow_accept: true
    })
  },
  interaction_type: {
    type: String,
    default: 'input'
  },
  options: {
    type: Array,
    default: () => []
  },
  other_input: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['submit'])

const feedback = ref('')
const loading = ref(false)
const selectedOption = ref(null)

/**
 * 渲染后的 Markdown 内容
 * 使用 computed 缓存转换结果，避免重复解析
 */
const renderedContent = computed(() => renderMarkdown(props.content))

const isOptionsMode = computed(() => {
  return props.interaction_type === 'options' && props.options.length > 0
})

const showInput = computed(() => {
  if (isOptionsMode.value) return props.other_input
  return props.config.allow_respond || props.config.allow_edit
})

const canSubmit = computed(() => {
  if (loading.value) return false
  if (isOptionsMode.value) {
    if (selectedOption.value !== null) return true
    if (props.other_input && feedback.value.trim().length > 0) return true
    return false
  }
  if (showInput.value) {
    return feedback.value.trim().length > 0
  }
  return true
})

const handleOptionSelect = (option) => {
  selectedOption.value = option
}

const handleSubmit = (decision) => {
  if (!canSubmit.value && decision === 'approve') return
  loading.value = true
  if (isOptionsMode.value && selectedOption.value) {
    emit('submit', {
      decision: selectedOption.value.value,
      feedback: selectedOption.value.label
    })
  } else if (isOptionsMode.value && props.other_input && feedback.value.trim()) {
    emit('submit', {
      decision: 'other',
      feedback: feedback.value.trim()
    })
  } else {
    emit('submit', {
      decision,
      feedback: feedback.value.trim()
    })
  }
}
</script>

<template>
  <div class="approval-box-container">
    <div class="input-wrapper">
      <div class="approval-main">
        <div class="approval-header">
          <svg class="approval-icon" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd" />
          </svg>
          <span class="approval-title">{{ title }}</span>
        </div>

        <div class="approval-content markdown-body" v-html="renderedContent"></div>

        <div v-if="isOptionsMode" class="options-list">
          <button
            v-for="option in options"
            :key="option.value"
            class="option-btn"
            :class="{ selected: selectedOption && selectedOption.value === option.value }"
            :disabled="loading"
            @click="handleOptionSelect(option)"
          >
            {{ option.label }}
          </button>
        </div>

        <textarea
          v-if="showInput"
          v-model="feedback"
          class="approval-input"
          :placeholder="isOptionsMode ? '请输入其他内容...' : (config.allow_edit ? '请输入修改后的内容...' : '请输入您的反馈...')"
          rows="3"
        ></textarea>

        <div class="approval-actions">
          <button
            v-if="config.allow_ignore"
            class="action-btn ignore-btn"
            :disabled="loading"
            @click="handleSubmit('ignore')"
          >
            忽略
          </button>
          <button
            v-if="config.allow_accept !== false"
            class="action-btn confirm-btn"
            :class="{ disabled: !canSubmit }"
            :disabled="!canSubmit"
            @click="handleSubmit('approve')"
          >
            <span v-if="loading" class="loading-spinner"></span>
            <span v-else>确认</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.approval-box-container {
  padding: 16px 40px 24px;
  background-color: rgb(249, 250, 251);
}

.input-wrapper {
  max-width: 900px;
  margin: 0 auto;
}

.approval-main {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 20px;
  background-color: var(--color-bg-secondary);
  border: 2px solid var(--color-accent);
  border-radius: var(--radius-lg);
  transition: var(--transition-colors), var(--transition-shadow), border-color 0.25s ease;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15), 0 2px 6px rgba(0, 0, 0, 0.1);
}

.approval-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.approval-icon {
  width: 20px;
  height: 20px;
  color: var(--color-accent);
  flex-shrink: 0;
}

.approval-title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  line-height: var(--line-height-normal);
}

.approval-content {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  line-height: var(--line-height-normal);
  word-break: break-word;
}

/* Markdown 渲染样式 */
.markdown-body :deep(p) {
  margin-bottom: 10px;
  line-height: 1.7;
}

.markdown-body :deep(p):last-child {
  margin-bottom: 0;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  margin-top: 12px;
  margin-bottom: 8px;
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.markdown-body :deep(h1) {
  font-size: 1.3em;
}

.markdown-body :deep(h2) {
  font-size: 1.2em;
}

.markdown-body :deep(h3) {
  font-size: 1.1em;
}

.markdown-body :deep(h4) {
  font-size: 1em;
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
  margin-bottom: 10px;
}

.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
}

.markdown-body :deep(strong) {
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--color-accent);
  padding-left: 12px;
  margin: 8px 0;
  color: var(--color-text-secondary);
}

.markdown-body :deep(a) {
  color: var(--color-accent);
  text-decoration: none;
}

.markdown-body :deep(a:hover) {
  text-decoration: underline;
}

.approval-input {
  width: 100%;
  min-height: 80px;
  max-height: 160px;
  padding: 10px 12px;
  font-size: var(--font-size-base);
  line-height: var(--line-height-normal);
  color: var(--color-text-primary);
  background-color: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  resize: vertical;
  overflow-y: auto;
  transition: var(--transition-colors), border-color 0.2s ease;
}

.approval-input::placeholder {
  color: var(--color-text-muted);
}

.approval-input:focus {
  outline: none;
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.approval-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 4px;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 20px;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: var(--transition-colors), var(--transition-transform), var(--transition-shadow);
  border: none;
}

.action-btn:active:not(:disabled) {
  transform: scale(0.96);
}

.ignore-btn {
  background-color: transparent;
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border);
}

.ignore-btn:hover:not(:disabled) {
  background-color: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.confirm-btn {
  background-color: var(--color-accent);
  color: white;
}

.confirm-btn:hover:not(.disabled) {
  background-color: var(--color-accent-hover);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}

.confirm-btn.disabled {
  background-color: var(--color-border);
  cursor: not-allowed;
  opacity: var(--opacity-disabled);
}

.loading-spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.options-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 4px 0;
}

.option-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 8px 20px;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  background-color: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: var(--transition-colors), var(--transition-transform), var(--transition-shadow);
}

.option-btn:hover:not(:disabled) {
  background-color: var(--color-bg-hover);
  border-color: var(--color-accent);
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.15);
}

.option-btn.selected {
  background-color: var(--color-accent);
  color: white;
  border-color: var(--color-accent);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}

.option-btn:active:not(:disabled) {
  transform: scale(0.96);
}

.option-btn:disabled {
  opacity: var(--opacity-disabled);
  cursor: not-allowed;
}
</style>
