<script setup>
import { ref, onMounted } from 'vue'
import { fetchKnowledgeFiles, fetchFilePreview } from '../utils/api.js'
import FileList from './FileList.vue'
import FilePreview from './FilePreview.vue'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:visible', 'close'])

const loading = ref(false)
const files = ref([])
const folders = ref([])
const isPreviewOpen = ref(false)
const previewContent = ref('')
const previewLoading = ref(false)
const previewFileType = ref('')
const previewFileName = ref('')
const previewMode = ref('text')
const previewFileUrl = ref('')

// 模拟数据 - 实际项目中应该从API获取
onMounted(() => {
  loadFiles()
})

function loadFiles() {
  loading.value = true
  // 模拟API调用
  setTimeout(() => {
    folders.value = [
      {
        name: '文档资料',
        path: '/docs',
        children: [
          { name: '项目说明.md', size: 1024, date: '2024-01-15', keywords: ['项目', '文档'] },
          { name: '需求分析.pdf', size: 2048000, date: '2024-01-14', keywords: ['需求'] },
        ]
      },
      {
        name: '代码文件',
        path: '/code',
        children: [
          { name: 'main.py', size: 5120, date: '2024-01-13', keywords: ['Python', '主程序'] },
          { name: 'utils.js', size: 3072, date: '2024-01-12', keywords: ['工具'] },
        ]
      }
    ]
    files.value = [
      { name: 'README.md', size: 2048, date: '2024-01-10', summary: '项目说明文档', keywords: ['说明'] },
      { name: 'config.json', size: 512, date: '2024-01-09', keywords: ['配置'] },
    ]
    loading.value = false
  }, 500)
}

function handleClose() {
  emit('update:visible', false)
  emit('close')
}

async function handleFileClick(file) {
  isPreviewOpen.value = true
  previewLoading.value = true
  previewContent.value = ''
  previewFileType.value = file.type || 'txt'
  previewFileName.value = file.name || ''
  previewMode.value = 'text'
  previewFileUrl.value = ''
  try {
    const result = await fetchFilePreview(file.path || file.name)
    previewContent.value = result.content || ''
    previewMode.value = result.preview_mode || 'text'
    previewFileUrl.value = result.file_url || ''
  } catch (err) {
    previewContent.value = '预览加载失败'
  } finally {
    previewLoading.value = false
  }
}

function closePreview() {
  isPreviewOpen.value = false
  previewContent.value = ''
  previewMode.value = 'text'
  previewFileUrl.value = ''
}

function handleUpload() {
  // 触发文件上传
  const input = document.createElement('input')
  input.type = 'file'
  input.multiple = true
  input.onchange = (e) => {
    const selectedFiles = Array.from(e.target.files)
    console.log('选择文件:', selectedFiles)
    // 这里添加上传逻辑
  }
  input.click()
}

function handleRefresh() {
  loadFiles()
}
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="visible" class="modal-overlay" @click.self="handleClose">
        <div class="modal-container">
          <!-- 头部 -->
          <div class="modal-header">
            <div class="header-title">
              <svg class="title-icon" viewBox="0 0 20 20" fill="currentColor">
                <path d="M9 4.804A7.968 7.968 0 005.5 4c-1.255 0-2.443.29-3.5.804v10A7.969 7.969 0 015.5 14c1.669 0 3.218.51 4.5 1.385A7.962 7.962 0 0114.5 14c1.255 0 2.443.29 3.5.804v-10A7.968 7.968 0 0014.5 4c-1.255 0-2.443.29-3.5.804V12a1 1 0 11-2 0V4.804z"/>
              </svg>
              <h2 class="title-text">档案管理</h2>
            </div>
            <div class="header-actions">
              <button class="action-btn" @click="handleRefresh" title="刷新">
                <svg viewBox="0 0 20 20" fill="currentColor">
                  <path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd"/>
                </svg>
              </button>
              <button class="action-btn" @click="handleUpload" title="上传文件">
                <svg viewBox="0 0 20 20" fill="currentColor">
                  <path fill-rule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM6.293 6.707a1 1 0 010-1.414l3-3a1 1 0 011.414 0l3 3a1 1 0 01-1.414 1.414L11 5.414V13a1 1 0 11-2 0V5.414L7.707 6.707a1 1 0 01-1.414 0z" clip-rule="evenodd"/>
                </svg>
              </button>
              <button class="action-btn close-btn" @click="handleClose" title="关闭">
                <svg viewBox="0 0 20 20" fill="currentColor">
                  <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
                </svg>
              </button>
            </div>
          </div>

          <!-- 内容区 -->
          <div class="modal-body">
            <div v-if="isPreviewOpen" class="preview-container">
              <FilePreview
                :isOpen="true"
                :content="previewContent"
                :fileType="previewFileType"
                :fileName="previewFileName"
                :loading="previewLoading"
                :previewMode="previewMode"
                :fileUrl="previewFileUrl"
                @close="closePreview"
              />
            </div>
            <FileList
              v-else
              :files="files"
              :folders="folders"
              :loading="loading"
              @file-click="handleFileClick"
            />
          </div>

          <!-- 底部 -->
          <div class="modal-footer">
            <span class="footer-info">共 {{ files.length }} 个文件，{{ folders.length }} 个文件夹</span>
            <button class="footer-close" @click="handleClose">关闭</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.modal-container {
  background-color: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  width: 100%;
  max-width: 800px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.title-icon {
  width: 24px;
  height: 24px;
  color: var(--color-accent);
}

.title-text {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: var(--transition-colors);
}

.action-btn:hover {
  background-color: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.action-btn svg {
  width: 18px;
  height: 18px;
}

.close-btn:hover {
  background-color: var(--color-error-light);
  color: var(--color-error);
}

.modal-body {
  flex: 1;
  overflow: hidden;
  padding: 16px 20px;
  min-height: 400px;
}

.modal-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-top: 1px solid var(--color-border);
  flex-shrink: 0;
}

.footer-info {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.footer-close {
  padding: 8px 20px;
  border-radius: var(--radius-sm);
  background-color: var(--color-bg-secondary);
  color: var(--color-text-primary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: var(--transition-colors);
}

.footer-close:hover {
  background-color: var(--color-bg-hover);
}

/* 过渡动画 */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.3s ease;
}

.modal-enter-active .modal-container,
.modal-leave-active .modal-container {
  transition: transform 0.3s ease, opacity 0.3s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-from .modal-container,
.modal-leave-to .modal-container {
  transform: scale(0.95);
  opacity: 0;
}

.preview-container {
  width: 100%;
  height: 100%;
}

.preview-container :deep(.preview-panel) {
  width: 100%;
  min-width: unset;
  border-left: none;
}
</style>
