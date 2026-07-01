<script setup>
/**
 * FilePreviewModal - 文件预览弹窗组件（2026-07-01 新增）
 *
 * 在会话文件抽屉中点击文件时弹出，复用 FilePreview 组件展示文件内容。
 * 支持点击遮罩层关闭、按 ESC 键关闭。
 *
 * Props:
 *   isOpen: boolean
 *   content: string
 *   fileType: string
 *   fileName: string
 *   loading: boolean
 *   previewMode: string
 *   fileUrl: string
 *
 * Emits:
 *   close
 */
import { watch, onMounted, onUnmounted } from 'vue'
import FilePreview from './FilePreview.vue'

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
  },
  previewMode: {
    type: String,
    default: 'text'
  },
  fileUrl: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['close'])

function handleClose() {
  emit('close')
}

function handleBackdropClick(e) {
  // 仅点击遮罩层本身时关闭，避免点击弹窗内容误关
  if (e.target === e.currentTarget) {
    handleClose()
  }
}

function handleKeyDown(e) {
  if (e.key === 'Escape' && props.isOpen) {
    handleClose()
  }
}

watch(() => props.isOpen, (open) => {
  if (typeof document === 'undefined') return
  if (open) {
    document.body.style.overflow = 'hidden'
  } else {
    document.body.style.overflow = ''
  }
})

onMounted(() => {
  document.addEventListener('keydown', handleKeyDown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeyDown)
  if (typeof document !== 'undefined') {
    document.body.style.overflow = ''
  }
})
</script>

<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div
        v-if="isOpen"
        class="file-preview-modal"
        @click="handleBackdropClick"
        role="dialog"
        aria-modal="true"
        aria-label="文件预览"
      >
        <div class="modal-panel">
          <div class="modal-header">
            <span class="modal-title">{{ fileName || '文件预览' }}</span>
            <button class="modal-close-btn" @click="handleClose" aria-label="关闭预览">
              <svg viewBox="0 0 20 20" fill="currentColor" class="close-icon">
                <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
              </svg>
            </button>
          </div>

          <div class="modal-body">
            <FilePreview
              :is-open="true"
              :content="content"
              :file-type="fileType"
              :file-name="fileName"
              :loading="loading"
              :preview-mode="previewMode"
              :file-url="fileUrl"
              @close="handleClose"
            />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.file-preview-modal {
  position: fixed;
  inset: 0;
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background-color: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(2px);
}

.modal-panel {
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 960px;
  height: min(720px, calc(100vh - 48px));
  background-color: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.25);
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

.modal-title {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.modal-close-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: var(--transition-colors);
  border: none;
  background: none;
}

.modal-close-btn:hover {
  color: var(--color-text-primary);
  background-color: var(--color-bg-hover);
}

.close-icon {
  width: 18px;
  height: 18px;
}

.modal-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* 覆盖 FilePreview 内部样式，使其在弹窗内占满 */
.modal-body :deep(.preview-panel) {
  width: 100% !important;
  height: 100%;
  border-left: none;
}

.modal-body :deep(.preview-toolbar) {
  right: 24px;
  bottom: 24px;
}

/* 弹窗淡入淡出动画 */
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.25s ease;
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}
</style>
