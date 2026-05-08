<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { marked } from 'marked'
import VueOfficePdf from '@vue-office/pdf'
import VueOfficeDocx from '@vue-office/docx'
import VueOfficeExcel from '@vue-office/excel'
import '@vue-office/docx/lib/index.css'
import '@vue-office/excel/lib/index.css'
import { getAuthHeaders } from '../utils/api.js'

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

const officeSrc = ref(null)
const officeLoading = ref(false)
const officeError = ref('')
const pdfRef = ref(null)

const isPdfMode = computed(() => props.previewMode === 'pdf')

const zoomLevel = ref(1)
const isPanning = ref(false)
const panOffset = ref({ x: 0, y: 0 })
const isDragging = ref(false)
const dragStart = ref({ x: 0, y: 0 })

const contentTransform = computed(() => {
  if (isPdfMode.value) return 'none'
  const tx = panOffset.value.x / zoomLevel.value
  const ty = panOffset.value.y / zoomLevel.value
  return `scale(${zoomLevel.value}) translate(${tx}px, ${ty}px)`
})

const bodyStyle = computed(() => {
  if (isPdfMode.value) {
    return { overflow: 'auto', padding: '0' }
  }
  return {}
})

const zoomIn = () => {
  zoomLevel.value = Math.min(5, Math.round((zoomLevel.value + 0.2) * 10) / 10)
  if (isPdfMode.value && pdfRef.value) {
    nextTick(() => pdfRef.value.setScale(zoomLevel.value))
  }
}

const zoomOut = () => {
  zoomLevel.value = Math.max(0.2, Math.round((zoomLevel.value - 0.2) * 10) / 10)
  if (isPdfMode.value && pdfRef.value) {
    nextTick(() => pdfRef.value.setScale(zoomLevel.value))
  }
}

const resetZoom = () => {
  zoomLevel.value = 1
  panOffset.value = { x: 0, y: 0 }
  isPanning.value = false
  if (isPdfMode.value && pdfRef.value) {
    nextTick(() => pdfRef.value.setScale(1))
  }
}

const togglePan = () => {
  isPanning.value = !isPanning.value
  if (!isPanning.value) {
    panOffset.value = { x: 0, y: 0 }
  }
}

const handleMouseDown = (e) => {
  if (!isPanning.value) return
  isDragging.value = true
  dragStart.value = { x: e.clientX - panOffset.value.x, y: e.clientY - panOffset.value.y }
}

const handleMouseMove = (e) => {
  if (!isDragging.value) return
  panOffset.value = {
    x: e.clientX - dragStart.value.x,
    y: e.clientY - dragStart.value.y
  }
}

const handleMouseUp = () => {
  isDragging.value = false
}

const renderedContent = computed(() => {
  if (!props.content) return ''
  if (props.previewMode === 'markdown') {
    try {
      return marked.parse(props.content)
    } catch {
      return props.content.replace(/\n/g, '<br/>')
    }
  }
  return ''
})

const OFFICE_MODES = ['pdf', 'docx', 'excel']

const fetchOfficeFile = async (url) => {
  if (!url) {
    officeSrc.value = null
    return
  }
  officeLoading.value = true
  officeError.value = ''
  officeSrc.value = null
  try {
    const response = await fetch(url, { headers: getAuthHeaders() })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const arrayBuffer = await response.arrayBuffer()
    officeSrc.value = arrayBuffer
  } catch (error) {
    console.error('文件加载失败:', error)
    officeError.value = '文件加载失败，请稍后重试'
    officeSrc.value = null
  } finally {
    officeLoading.value = false
  }
}

watch(
  () => [props.fileUrl, props.previewMode],
  ([newUrl, newMode]) => {
    if (OFFICE_MODES.includes(newMode) && newUrl) {
      fetchOfficeFile(newUrl)
    } else {
      officeSrc.value = null
      officeError.value = ''
    }
  },
  { immediate: true }
)

watch(
  () => props.previewMode,
  () => {
    zoomLevel.value = 1
    panOffset.value = { x: 0, y: 0 }
    isPanning.value = false
  }
)

const handleOfficeRendered = () => {
  officeLoading.value = false
}

const handleOfficeError = (error) => {
  console.error('文件渲染失败:', error)
  officeError.value = '文件渲染失败，请稍后重试'
  officeLoading.value = false
}
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
    <div class="preview-body" :style="bodyStyle" @mousemove="handleMouseMove" @mouseup="handleMouseUp" @mouseleave="handleMouseUp">
      <div
        class="preview-content-wrapper"
        :style="{ transform: contentTransform, cursor: isPanning ? (isDragging ? 'grabbing' : 'grab') : 'default' }"
        @mousedown="handleMouseDown"
      >
      <div v-if="loading" class="preview-loading">
        <div class="loading-spinner"></div>
        <span>加载中...</span>
      </div>
      <template v-else>
        <div v-if="previewMode === 'pdf'" class="preview-office preview-pdf">
          <div v-if="officeLoading" class="preview-loading">
            <div class="loading-spinner"></div>
            <span>PDF 加载中...</span>
          </div>
          <div v-else-if="officeError" class="preview-error">
            <span>{{ officeError }}</span>
            <button class="retry-btn" @click="fetchOfficeFile(fileUrl)">重试</button>
          </div>
          <VueOfficePdf v-else-if="officeSrc" ref="pdfRef" :src="officeSrc" @rendered="handleOfficeRendered" @error="handleOfficeError" />
        </div>
        <div v-else-if="previewMode === 'docx'" class="preview-office preview-docx">
          <div v-if="officeLoading" class="preview-loading">
            <div class="loading-spinner"></div>
            <span>文档加载中...</span>
          </div>
          <div v-else-if="officeError" class="preview-error">
            <span>{{ officeError }}</span>
            <button class="retry-btn" @click="fetchOfficeFile(fileUrl)">重试</button>
          </div>
          <VueOfficeDocx v-else-if="officeSrc" :src="officeSrc" @rendered="handleOfficeRendered" @error="handleOfficeError" />
        </div>
        <div v-else-if="previewMode === 'excel'" class="preview-office preview-excel">
          <div v-if="officeLoading" class="preview-loading">
            <div class="loading-spinner"></div>
            <span>表格加载中...</span>
          </div>
          <div v-else-if="officeError" class="preview-error">
            <span>{{ officeError }}</span>
            <button class="retry-btn" @click="fetchOfficeFile(fileUrl)">重试</button>
          </div>
          <VueOfficeExcel v-else-if="officeSrc" :src="officeSrc" @rendered="handleOfficeRendered" @error="handleOfficeError" />
        </div>
        <div v-else-if="previewMode === 'markdown'" class="markdown-body" v-html="renderedContent"></div>
        <div v-else-if="previewMode === 'text'" class="preview-content">{{ content || '暂无内容' }}</div>
        <div v-else-if="previewMode === 'image'" class="preview-image">
          <img :src="fileUrl" />
        </div>
        <div v-else-if="previewMode === 'unsupported'" class="preview-unsupported">
          <span>该文件格式暂不支持预览</span>
        </div>
        <div v-else class="preview-content">{{ content || '暂无内容' }}</div>
      </template>
      </div>
    </div>
    <div class="preview-toolbar">
      <button class="toolbar-btn" @click="zoomIn" title="放大">
        <svg viewBox="0 0 20 20" fill="currentColor" width="20" height="20">
          <path fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8zm5 0a1 1 0 011-1h2V5a1 1 0 112 0v2h2a1 1 0 110 2h-2v2a1 1 0 11-2 0V9H8a1 1 0 01-1-1z" clip-rule="evenodd"/>
        </svg>
      </button>
      <span class="toolbar-zoom-label">{{ Math.round(zoomLevel * 100) }}%</span>
      <button class="toolbar-btn" @click="zoomOut" title="缩小">
        <svg viewBox="0 0 20 20" fill="currentColor" width="20" height="20">
          <path fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8zm5 0a1 1 0 011-1h4a1 1 0 110 2H8a1 1 0 01-1-1z" clip-rule="evenodd"/>
        </svg>
      </button>
      <div class="toolbar-divider"></div>
      <button class="toolbar-btn" :class="{ active: isPanning }" @click="togglePan" title="移动">
        <svg viewBox="0 0 20 20" fill="currentColor" width="20" height="20">
          <path fill-rule="evenodd" d="M10 1a1 1 0 011 1v2.586l1.293-1.293a1 1 0 111.414 1.414L11 7.414V9h1.586l2.707-2.707a1 1 0 111.414 1.414L13.414 9H16a1 1 0 110 2h-2.586l1.293 1.293a1 1 0 01-1.414 1.414L11 11.414V13h1.586l2.707 2.707a1 1 0 01-1.414 1.414L11 13.414V16a1 1 0 11-2 0v-2.586l-1.293 1.293a1 1 0 01-1.414-1.414L9 11.414V9H7.414l-2.707 2.707a1 1 0 01-1.414-1.414L5.586 9H3a1 1 0 110-2h2.586L4.293 5.707a1 1 0 011.414-1.414L9 6.586V5H7.414L4.707 2.293a1 1 0 011.414-1.414L9 4.586V2a1 1 0 011-1z" clip-rule="evenodd"/>
        </svg>
      </button>
      <div class="toolbar-divider"></div>
      <button class="toolbar-btn" @click="resetZoom" title="重置">
        <svg viewBox="0 0 20 20" fill="currentColor" width="20" height="20">
          <path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd"/>
        </svg>
      </button>
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
  position: relative;
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
  overflow: auto;
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
}

.preview-toolbar {
  position: absolute;
  bottom: 16px;
  right: 16px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background-color: var(--color-bg-secondary);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
  z-index: 10;
}

.toolbar-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: var(--transition-colors);
  border: none;
  background: none;

  &:hover {
    color: var(--color-text-primary);
    background-color: var(--color-bg-hover);
  }

  &.active {
    color: var(--color-accent);
    background-color: var(--color-bg-hover);
  }
}

.toolbar-zoom-label {
  font-size: 13px;
  color: var(--color-text-muted);
  min-width: 40px;
  text-align: center;
  user-select: none;
}

.toolbar-divider {
  width: 1px;
  height: 20px;
  background-color: var(--color-border-light);
  margin: 0 2px;
}

.preview-content-wrapper {
  transform-origin: top left;
  transition: transform 0.15s ease;
  min-height: 100%;
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

.preview-office {
  flex: 1;
  min-height: 0;
}

.preview-pdf {
  overflow: auto;
}

.preview-pdf :deep(.vue-office-pdf) {
  min-height: 100%;
}

.preview-docx {
  overflow-y: auto;
}

.preview-excel {
  overflow: auto;
}

.preview-image {
  display: flex;
  justify-content: center;
  align-items: flex-start;
  min-height: 200px;
}

.preview-image img {
  max-width: 100%;
}

.preview-unsupported {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.preview-error {
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

.retry-btn {
  padding: 6px 16px;
  border-radius: var(--radius-sm);
  background-color: var(--color-accent);
  color: white;
  cursor: pointer;
  font-size: var(--font-size-sm);
  border: none;
  transition: opacity 0.2s ease;

  &:hover {
    opacity: 0.9;
  }
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
