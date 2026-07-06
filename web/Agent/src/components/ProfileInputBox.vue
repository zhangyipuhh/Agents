<script setup>
import { ref, computed, nextTick } from 'vue'
import { uploadFileInChunks, formatFileSize, getFileExtension, refreshToken } from '../utils/api.js'

const SUPPORTED_EXTENSIONS = ['pdf', 'doc', 'docx', 'txt', 'md', 'csv', 'json']
const MAX_FILE_SIZE = 50 * 1024 * 1024

const props = defineProps({
  sessionId: {
    type: String,
    default: ''
  },
  isStreaming: {
    type: Boolean,
    default: false
  },
  // 2026-07-06 新增：停止按钮是否处于「中断待生效」状态。
  // 父组件 KnowledgeApp.vue 在用户点击停止且后端正在等工具完成时置 true，
  // 期间按钮显示 stop-pending 样式 + 旋转 badge + disabled 拦截重复点击。
  isStopPending: {
    type: Boolean,
    default: false
  }
})

const inputValue = ref('')
const textareaRef = ref(null)
const fileInputRef = ref(null)
const isFocused = ref(false)
const isDragging = ref(false)
const isRefreshingToken = ref(false)
const selectedFiles = ref([])

const canSend = computed(() => {
  if (props.isStreaming) return false
  // 2026-07-06 新增：中断待生效期间禁用发送按钮，
  // 避免用户在等待工具完成时重复点击导致状态混乱。
  if (props.isStopPending) return false
  if (isRefreshingToken.value) return false
  const hasText = inputValue.value.trim().length > 0
  const hasUploadedFiles = selectedFiles.value.some(f => f.status === 'success')
  return hasText || hasUploadedFiles
})

const autoResize = () => {
  const textarea = textareaRef.value
  if (textarea) {
    textarea.style.height = 'auto'
    const newHeight = Math.max(80, Math.min(textarea.scrollHeight, 200))
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

  isRefreshingToken.value = true
  try {
    await refreshToken()
  } catch (err) {
    alert('获取认证信息失败，请稍后重试')
    isRefreshingToken.value = false
    return
  }
  isRefreshingToken.value = false

  const uploadedFiles = selectedFiles.value
    .filter(f => f.status === 'success')
    .map(f => ({
      filename: f.uploadResult.filename,
      stored_path: f.uploadResult.stored_path,
      file_type: f.uploadResult.file_type,
      original_name: f.name,
      size: f.size
    }))

  emit('send', inputValue.value.trim(), uploadedFiles)

  inputValue.value = ''
  selectedFiles.value = []

  nextTick(() => {
    autoResize()
  })
}

/**
 * 发送/停止按钮统一点击处理（2026-07-06 新增）。
 * 与 InputBox.vue::handleSendBtnClick 同款三态分支：
 *   1. isStopPending=true → 直接 return（防御性，避免键盘 Enter 绕过 disabled）
 *   2. isStreaming=true    → emit('stop')
 *   3. 其余情况             → handleSend()
 * @returns {void}
 */
const handleSendBtnClick = () => {
  if (props.isStopPending) return
  if (props.isStreaming) {
    emit('stop')
    return
  }
  handleSend()
}

const handleFocus = () => {
  isFocused.value = true
}

const handleBlur = () => {
  isFocused.value = false
}

const handleAttachmentClick = () => {
  fileInputRef.value?.click()
}

const handleFileSelect = (event) => {
  const files = Array.from(event.target.files || [])
  addFiles(files)
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
  }
}

const addFiles = (files) => {
  for (const file of files) {
    const ext = getFileExtension(file.name)
    if (!SUPPORTED_EXTENSIONS.includes(ext)) {
      const fileItem = {
        id: `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`,
        file,
        name: file.name,
        size: file.size,
        type: file.type,
        extension: ext,
        status: 'error',
        progress: 0,
        uploadResult: null,
        errorMsg: `不支持的文件类型: .${ext}，仅支持 ${SUPPORTED_EXTENSIONS.map(e => '.' + e).join(', ')}`,
        cancelFn: null
      }
      selectedFiles.value.push(fileItem)
      continue
    }
    if (file.size > MAX_FILE_SIZE) {
      const fileItem = {
        id: `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`,
        file,
        name: file.name,
        size: file.size,
        type: file.type,
        extension: ext,
        status: 'error',
        progress: 0,
        uploadResult: null,
        errorMsg: `文件大小超过限制（最大 ${formatFileSize(MAX_FILE_SIZE)}）`,
        cancelFn: null
      }
      selectedFiles.value.push(fileItem)
      continue
    }
    const fileItem = {
      id: `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`,
      file,
      name: file.name,
      size: file.size,
      type: file.type,
      extension: ext,
      status: 'pending',
      progress: 0,
      uploadResult: null,
      errorMsg: '',
      cancelFn: null
    }
    selectedFiles.value.push(fileItem)
    startUpload(fileItem)
  }
}

const startUpload = (fileItem) => {
  fileItem.status = 'uploading'
  fileItem.progress = 0
  fileItem.errorMsg = ''

  uploadFileInChunks(
    fileItem.file,
    (progress) => {
      const item = selectedFiles.value.find(f => f.id === fileItem.id)
      if (item) item.progress = progress
    },
    (cancelFn) => {
      const item = selectedFiles.value.find(f => f.id === fileItem.id)
      if (item) item.cancelFn = cancelFn
    }
  ).then(result => {
    const item = selectedFiles.value.find(f => f.id === fileItem.id)
    if (item) {
      item.status = 'success'
      item.progress = 100
      item.uploadResult = result.files?.[0] || result
    }
  }).catch(err => {
    const item = selectedFiles.value.find(f => f.id === fileItem.id)
    if (item) {
      if (err.message === '上传已取消') {
        const idx = selectedFiles.value.findIndex(f => f.id === fileItem.id)
        if (idx !== -1) selectedFiles.value.splice(idx, 1)
      } else {
        item.status = 'error'
        item.errorMsg = err.message
      }
    }
  })
}

const removeFile = (fileItem) => {
  if (fileItem.status === 'uploading' && fileItem.cancelFn) {
    fileItem.cancelFn()
  }
  const idx = selectedFiles.value.findIndex(f => f.id === fileItem.id)
  if (idx !== -1) selectedFiles.value.splice(idx, 1)
}

const retryUpload = (fileItem) => {
  if (!SUPPORTED_EXTENSIONS.includes(fileItem.extension)) {
    return
  }
  if (fileItem.size > MAX_FILE_SIZE) {
    return
  }
  fileItem.status = 'pending'
  fileItem.errorMsg = ''
  startUpload(fileItem)
}

const handleDragOver = (event) => {
  event.preventDefault()
  isDragging.value = true
}

const handleDragLeave = (event) => {
  event.preventDefault()
  isDragging.value = false
}

const handleDrop = (event) => {
  event.preventDefault()
  isDragging.value = false
  const files = Array.from(event.dataTransfer?.files || [])
  if (files.length > 0) {
    addFiles(files)
  }
}

const handleToolAction = (action) => {
  emit('tool-action', action)
}

const handleNewChat = () => {
  emit('new-chat')
}

const getFileIconColor = (ext) => {
  const colorMap = {
    pdf: '#EF4444',
    doc: '#3B82F6', docx: '#3B82F6',
    xls: '#10B981', xlsx: '#10B981', csv: '#10B981',
    jpg: '#8B5CF6', jpeg: '#8B5CF6', png: '#8B5CF6', gif: '#8B5CF6', svg: '#8B5CF6', webp: '#8B5CF6',
    txt: '#6B7280', md: '#6B7280',
    ppt: '#F59E0B', pptx: '#F59E0B',
    zip: '#6B7280', rar: '#6B7280', '7z': '#6B7280',
  }
  return colorMap[ext] || '#9CA3AF'
}

const emit = defineEmits(['send', 'tool-action', 'new-chat', 'stop'])
</script>

<template>
  <div class="profile-input-box-container">
    <div class="input-wrapper">
      <div
        class="input-main"
        :class="{ focused: isFocused, dragging: isDragging }"
        @dragover="handleDragOver"
        @dragleave="handleDragLeave"
        @drop="handleDrop"
      >
        <input
          ref="fileInputRef"
          type="file"
          multiple
          accept=".pdf,.doc,.docx,.txt,.md,.csv,.json"
          style="display: none"
          @change="handleFileSelect"
        />

        <div v-if="selectedFiles.length > 0" class="file-tags-container">
          <div
            v-for="fileItem in selectedFiles"
            :key="fileItem.id"
            class="file-tag"
            :class="[fileItem.status]"
          >
            <svg
              class="file-type-icon"
              viewBox="0 0 20 20"
              fill="currentColor"
              :style="{ color: getFileIconColor(fileItem.extension) }"
            >
              <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clip-rule="evenodd"/>
            </svg>

            <div class="file-info">
              <span class="file-name" :title="fileItem.name">{{ fileItem.name }}</span>
              <span class="file-size">{{ formatFileSize(fileItem.size) }}</span>
            </div>

            <div v-if="fileItem.status === 'uploading'" class="progress-area">
              <div class="progress-bar">
                <div class="progress-fill" :style="{ width: fileItem.progress + '%' }"></div>
              </div>
              <span class="progress-text">{{ fileItem.progress }}%</span>
            </div>

            <svg
              v-if="fileItem.status === 'success'"
              class="status-icon success-icon"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/>
            </svg>

            <svg
              v-if="fileItem.status === 'error' && SUPPORTED_EXTENSIONS.includes(fileItem.extension) && fileItem.size <= MAX_FILE_SIZE"
              class="status-icon error-icon"
              viewBox="0 0 20 20"
              fill="currentColor"
              @click="retryUpload(fileItem)"
              title="点击重试"
            >
              <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>
            </svg>

            <svg
              v-if="fileItem.status === 'error' && (!SUPPORTED_EXTENSIONS.includes(fileItem.extension) || fileItem.size > MAX_FILE_SIZE)"
              class="status-icon error-icon"
              viewBox="0 0 20 20"
              fill="currentColor"
              :title="fileItem.errorMsg"
            >
              <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>
            </svg>

            <span v-if="fileItem.status === 'error' && fileItem.errorMsg" class="error-msg" :title="fileItem.errorMsg">{{ fileItem.errorMsg }}</span>

            <button class="remove-btn" @click="removeFile(fileItem)" :title="fileItem.status === 'uploading' ? '取消上传' : '移除文件'">
              <svg viewBox="0 0 20 20" fill="currentColor" class="remove-icon">
                <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
              </svg>
            </button>
          </div>
        </div>

        <textarea
          ref="textareaRef"
          v-model="inputValue"
          class="text-input"
          placeholder="请输入你的需求，按「Enter」发送"
          rows="3"
          @input="handleInput"
          @keydown="handleKeydown"
          @focus="handleFocus"
          @blur="handleBlur"
        ></textarea>

        <div class="bottom-row">
          <div class="toolbar">
            <button
              class="tool-btn"
              title="新建会话"
              @click="handleNewChat"
            >
              <svg viewBox="0 0 20 20" fill="currentColor" class="tool-icon">
                <path d="M10 5a1 1 0 011 1v3h3a1 1 0 110 2h-3v3a1 1 0 11-2 0v-3H6a1 1 0 110-2h3V6a1 1 0 011-1z"/>
              </svg>
            </button>

            <button
              class="tool-btn"
              title="附件"
              @click="handleAttachmentClick"
            >
              <svg viewBox="0 0 20 20" fill="currentColor" class="tool-icon">
                <path fill-rule="evenodd" d="M8 4a3 3 0 00-3 3v4a5 5 0 0010 0V7a1 1 0 112 0v4a7 7 0 11-14 0V7a5 5 0 0110 0v4a3 3 0 11-6 0V7a1 1 0 012 0v4a1 1 0 102 0V7a3 3 0 00-3-3z" clip-rule="evenodd"/>
              </svg>
            </button>
          </div>

          <button
            class="send-btn"
            :class="{
              'send-mode': !isStreaming && !isStopPending,
              'stop-mode': isStreaming && !isStopPending,
              'stop-pending-mode': isStopPending,
              'disabled': !canSend && !isStreaming && !isStopPending
            }"
            :disabled="!canSend && !isStreaming && !isStopPending"
            :title="isStopPending
              ? '中断中，等待工具完成...'
              : (isStreaming ? '停止生成' : '发送消息')"
            @click="handleSendBtnClick"
          >
            <!-- 发送模式：纸飞机图标 -->
            <svg v-if="!isStreaming && !isStopPending" viewBox="0 0 20 20" fill="currentColor" class="send-icon">
              <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z"/>
            </svg>
            <!-- 2026-07-06 新增：中断待生效模式：旋转圆环图标 -->
            <svg v-else-if="isStopPending" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" class="stop-pending-inner-icon">
              <circle cx="10" cy="10" r="6" stroke-dasharray="20 8" />
            </svg>
            <!-- 停止模式：实心方块图标 -->
            <svg v-else viewBox="0 0 20 20" fill="currentColor" class="stop-icon">
              <rect x="5" y="5" width="10" height="10" rx="1.5" />
            </svg>
            <!-- 2026-07-06 新增：中断待生效右上角旋转 badge -->
            <span v-if="isStopPending" class="stop-pending-badge" aria-label="中断中"></span>
          </button>
        </div>
      </div>
    </div>

    <p class="disclaimer">内容由AI生成，重要信息请务必核查</p>
  </div>
</template>

<style scoped>
.profile-input-box-container {
  padding: 16px 40px 24px;
  background-color: rgb(249, 250, 251);
  contain: layout style paint;
}

.input-wrapper {
  max-width: 900px;
  margin: 0 auto;
}

.input-main {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px 16px;
  background-color: var(--color-bg-secondary);
  border: 2px solid var(--color-accent);
  border-radius: var(--radius-lg);
  transition: var(--transition-colors), var(--transition-shadow), border-color 0.25s ease;
  position: relative;
  max-width: 900px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15), 0 2px 6px rgba(0, 0, 0, 0.1);

  &:hover:not(.focused):not(.dragging) {
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2), 0 4px 10px rgba(0, 0, 0, 0.15);
  }

  &.focused {
    box-shadow: 0 8px 24px rgba(99, 102, 241, 0.3), 0 4px 10px rgba(99, 102, 241, 0.2), 0 0 0 4px rgba(99, 102, 241, 0.15);
  }

  &.dragging {
    box-shadow: 0 8px 24px rgba(99, 102, 241, 0.35), 0 4px 10px rgba(99, 102, 241, 0.25), 0 0 0 4px rgba(99, 102, 241, 0.2);
    background-color: var(--color-accent-light);
  }
}

.file-tags-container {
  display: flex;
  flex-direction: row;
  gap: 8px;
  padding: 4px 0;
  overflow-x: auto;
  overflow-y: hidden;
  flex-shrink: 0;

  &::-webkit-scrollbar {
    height: 4px;
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

.file-tag {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background-color: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  flex-shrink: 0;
  min-width: 0;
  transition: var(--transition-colors), border-color 0.2s ease;
  position: relative;

  &.uploading {
    border-color: var(--color-accent);
  }

  &.success {
    border-color: var(--color-success);
  }

  &.error {
    border-color: var(--color-error);
  }
}

.file-type-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.file-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 2px;
}

.file-name {
  font-size: 12px;
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.3;
}

.file-size {
  font-size: 11px;
  color: var(--color-text-muted);
  line-height: 1.2;
}

.progress-area {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 60px;
}

.progress-bar {
  width: 40px;
  height: 3px;
  background-color: var(--color-bg-tertiary);
  border-radius: 2px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background-color: var(--color-accent);
  border-radius: 2px;
  transition: width 0.2s ease;
}

.progress-text {
  font-size: 11px;
  color: var(--color-accent);
  font-weight: var(--font-weight-medium);
  white-space: nowrap;
  min-width: 28px;
}

.status-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;

  &.success-icon {
    color: var(--color-success);
  }

  &.error-icon {
    color: var(--color-error);
    cursor: pointer;

    &:hover {
      opacity: 0.8;
    }
  }
}

.error-msg {
  font-size: 10px;
  color: var(--color-error);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.2;
}

.remove-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--color-text-muted);
  border-radius: var(--radius-sm);
  flex-shrink: 0;
  transition: var(--transition-colors);

  &:hover {
    color: var(--color-error);
    background-color: var(--color-bg-hover);
  }
}

.remove-icon {
  width: 12px;
  height: 12px;
}

.bottom-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 8px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
}

.tool-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 6px 10px;
  background-color: transparent;
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: var(--transition-colors), var(--transition-transform), var(--transition-shadow);
  position: relative;

  &::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: inherit;
    background-color: var(--color-bg-hover);
    opacity: 0;
    transition: opacity var(--transition-fast);
  }

  &:hover {
    color: var(--color-text-primary);

    &::before {
      opacity: 1;
    }
  }

  &:active:not(:disabled) {
    transform: scale(0.95);
  }

  > * {
    position: relative;
    z-index: 1;
  }

  &.text-btn {
    font-size: var(--font-size-sm);
    font-weight: var(--font-weight-medium);
    padding: 6px 12px;
  }

}

.tool-icon {
  width: 18px;
  height: 18px;
}

.text-input {
  width: 100%;
  height: 80px;
  min-height: 80px;
  max-height: 200px;
  padding: 8px 0;
  font-size: var(--font-size-base);
  line-height: var(--line-height-normal);
  color: var(--color-text-primary);
  background-color: transparent;
  resize: none;
  overflow-y: auto;

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

.send-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background-color: var(--color-accent);
  color: white;
  border-radius: 50%;
  cursor: pointer;
  transition: var(--transition-colors), var(--transition-transform), var(--transition-shadow);
  flex-shrink: 0;
  position: relative;

  &::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: inherit;
    background: linear-gradient(135deg, rgba(255, 255, 255, 0.1) 0%, transparent 100%);
    opacity: 0;
    transition: opacity var(--transition-fast);
  }

  &:hover:not(.disabled) {
    background-color: var(--color-accent-hover);
    transform: scale(1.08);
    box-shadow:
      0 4px 12px rgba(99, 102, 241, 0.3),
      0 2px 4px rgba(99, 102, 241, 0.2);

    &::before {
      opacity: 1;
    }
  }

  &:active:not(.disabled) {
    transform: scale(0.95);
  }

  &.disabled {
    background-color: var(--color-border);
    cursor: not-allowed;
    opacity: var(--opacity-disabled);

    &:hover {
      box-shadow: none;
      transform: none;
    }
  }
}

.send-icon {
  width: 16px;
  height: 16px;
}

/* 2026-06-15 新增：停止模式样式（与发送按钮同色系，通过缩放+阴影脉冲传达「生成中」状态） */
.send-btn.stop-mode {
  background-color: var(--color-accent);  /* 与发送模式同色 */
  cursor: pointer;
  animation: stopPulse 1.2s ease-in-out infinite;
}

.send-btn.stop-mode:hover {
  background-color: var(--color-accent-hover);  /* 与发送模式 hover 同色 */
  transform: scale(1.08);
  box-shadow:
    0 4px 12px rgba(99, 102, 241, 0.3),  /* 与发送模式 hover 同色阴影 */
    0 2px 4px rgba(99, 102, 241, 0.2);
}

.send-btn.stop-mode::before {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.1) 0%, transparent 100%);
}

.stop-icon {
  width: 14px;
  height: 14px;
  color: white;
}

/* 2026-07-06 新增：中断待生效模式（isStopPending=true 时）
   与 InputBox.vue 同款：背景灰、cursor not-allowed、内嵌旋转圆环 + 右上角橙色 badge。 */
.send-btn.stop-pending-mode {
  background-color: var(--color-text-muted);
  cursor: not-allowed;
  opacity: 0.7;
}

.send-btn.stop-pending-mode:hover {
  background-color: var(--color-text-muted);
  transform: none;
  box-shadow: none;
}

.send-btn.stop-pending-mode::before {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.05) 0%, transparent 100%);
}

.stop-pending-inner-icon {
  width: 16px;
  height: 16px;
  color: white;
  animation: stopPendingSpin 0.9s linear infinite;
}

.stop-pending-badge {
  position: absolute;
  top: -2px;
  right: -2px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #f59e0b;
  border: 2px solid var(--color-bg-secondary);
  box-sizing: content-box;
  animation: stopPendingSpin 0.9s linear infinite;
  pointer-events: none;
}

@keyframes stopPendingSpin {
  to {
    transform: rotate(360deg);
  }
}

/* 缩放+阴影脉冲动画：背景色不变，仅缩放与阴影扩散传达「生成中」语义 */
@keyframes stopPulse {
  0%, 100% {
    transform: scale(1);
    box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3),
                0 2px 4px rgba(99, 102, 241, 0.2),
                0 0 0 0 rgba(99, 102, 241, 0.4);
  }
  50% {
    transform: scale(1.06);
    box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3),
                0 2px 4px rgba(99, 102, 241, 0.2),
                0 0 0 8px rgba(99, 102, 241, 0);
  }
}

.disclaimer {
  text-align: center;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  margin: 12px 0 0;
  line-height: 1.4;
  letter-spacing: 0.01em;
  transition: var(--transition-opacity);

  &:hover {
    color: var(--color-text-secondary);
  }
}
</style>
