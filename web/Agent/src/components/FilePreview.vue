<script setup>
import { computed } from 'vue'
import { marked } from 'marked'

const props = defineProps({
  isOpen: {
    type: Boolean,
    default: false
  },
  content: {
    type: String,
    default: ''
  },
  fileType: {
    type: String,
    default: 'txt'
  },
  fileName: {
    type: String,
    default: ''
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['close'])

const isMarkdown = computed(() => {
  return ['md', 'markdown'].includes(props.fileType?.toLowerCase())
})

const renderedContent = computed(() => {
  if (!props.content) return ''
  if (isMarkdown.value) {
    try {
      return marked.parse(props.content)
    } catch {
      return props.content.replace(/\n/g, '<br/>')
    }
  }
  return ''
})
</script>

<template>
  <div v-if="isOpen" class="preview-panel">
    <div class="preview-header">
      <span class="preview-title">{{ fileName || '文件预览' }}</span>
      <button class="preview-close-btn" @click="emit('close')">
        <svg viewBox="0 0 20 20" fill="currentColor" class="close-icon">
          <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
        </svg>
      </button>
    </div>
    <div class="preview-body">
      <div v-if="loading" class="preview-loading">
        <div class="loading-spinner"></div>
        <span>加载中...</span>
      </div>
      <div v-else-if="isMarkdown" class="markdown-body" v-html="renderedContent"></div>
      <div v-else class="preview-content">{{ content || '暂无内容' }}</div>
    </div>
  </div>
</template>

<style scoped>
.preview-panel {
  width: 30%;
  min-width: 300px;
  height: 100%;
  overflow: hidden;
  background-color: var(--color-bg-primary);
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--color-border);
  flex-shrink: 0;
}

.preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

.preview-title {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-close-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: var(--transition-colors);

  &:hover {
    color: var(--color-text-primary);
    background-color: var(--color-bg-hover);
  }
}

.close-icon {
  width: 16px;
  height: 16px;
}

.preview-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;

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
}

.preview-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px;
  min-height: 200px;
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.preview-content {
  font-size: var(--font-size-sm);
  line-height: var(--line-height-relaxed);
  color: var(--color-text-primary);
  white-space: pre-wrap;
  word-break: break-word;
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

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
