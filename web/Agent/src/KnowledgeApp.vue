<script setup>
import { ref, onMounted } from 'vue'
import FileList from './components/FileList.vue'
import FilePreview from './components/FilePreview.vue'
import KnowledgeChat from './components/KnowledgeChat.vue'
import { fetchKnowledgeFiles, fetchFilePreview, createNewSession } from './utils/api.js'

const isPreviewOpen = ref(false)
const previewContent = ref('')
const previewLoading = ref(false)
const previewFileType = ref('')
const previewFileName = ref('')
const files = ref([])
const folders = ref([])
const filesLoading = ref(false)
const currentSessionId = ref('')
const isChatStreaming = ref(false)

onMounted(async () => {
  filesLoading.value = true
  try {
    const result = await fetchKnowledgeFiles()
    files.value = result.files || []
    folders.value = result.folders || []
  } catch (err) {
    console.error('加载文件失败:', err)
    // 使用模拟数据作为后备
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
  } finally {
    filesLoading.value = false
  }

  // 创建新会话
  try {
    const newId = await createNewSession()
    currentSessionId.value = newId
  } catch (err) {
    console.error('创建会话失败:', err)
  }
})

async function handleFileClick(file) {
  isPreviewOpen.value = true
  previewLoading.value = true
  previewContent.value = ''
  previewFileType.value = file.type || 'txt'
  previewFileName.value = file.name || ''
  try {
    const result = await fetchFilePreview(file.path || file.name)
    previewContent.value = result.content || result.preview || ''
  } catch (err) {
    previewContent.value = '预览加载失败: ' + err.message
  } finally {
    previewLoading.value = false
  }
}

function closePreview() {
  isPreviewOpen.value = false
  previewContent.value = ''
}

function handleNewChat() {
  // 新建聊天会话
  try {
    createNewSession().then(newId => {
      currentSessionId.value = newId
    })
  } catch (err) {
    console.error('新建会话失败:', err)
  }
}

function handleChatSend(message) {
  isChatStreaming.value = true
}

function handleChatStreamEnd() {
  isChatStreaming.value = false
}

async function refreshFiles() {
  filesLoading.value = true
  try {
    const result = await fetchKnowledgeFiles()
    files.value = result.files || []
    folders.value = result.folders || []
  } catch (err) {
    console.error('刷新文件失败:', err)
  } finally {
    filesLoading.value = false
  }
}

function uploadFile() {
  const input = document.createElement('input')
  input.type = 'file'
  input.multiple = true
  input.onchange = (e) => {
    const selectedFiles = Array.from(e.target.files)
    console.log('选择文件:', selectedFiles)
    alert(`选择了 ${selectedFiles.length} 个文件：\n${selectedFiles.map(f => f.name).join('\n')}`)
  }
  input.click()
}
</script>

<template>
  <div class="knowledge-page">
    <!-- 左侧：文件列表 30% -->
    <div class="file-list-panel">
      <div class="file-list-body">
        <FileList 
          :files="files" 
          :folders="folders" 
          :loading="filesLoading" 
          @file-click="handleFileClick" 
        />
      </div>
    </div>

    <!-- 中间：聊天 40% -->
    <KnowledgeChat
      :session-id="currentSessionId"
      :is-streaming="isChatStreaming"
      @new-chat="handleNewChat"
      @send="handleChatSend"
    />

    <!-- 右侧：文件预览 30% -->
    <FilePreview
      :isOpen="isPreviewOpen"
      :content="previewContent"
      :fileType="previewFileType"
      :fileName="previewFileName"
      :loading="previewLoading"
      @close="closePreview"
    />
  </div>
</template>

<style scoped>
.knowledge-page {
  display: flex;
  flex: 1;
  height: 100%;
  overflow: hidden;
  background-color: var(--color-bg-secondary);
}

.file-list-panel {
  flex: 0 0 35%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
  background-color: var(--color-bg-primary);
  border-right: 1px solid var(--color-border);
}

.file-list-header {
  flex-shrink: 0;
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-border-light);
  display: flex;
  align-items: center;
  justify-content: space-between;
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

.file-list-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: var(--transition-colors);
  border: none;
  background: transparent;
}

.btn-primary {
  background-color: var(--color-accent);
  color: white;
}

.btn-primary:hover {
  background-color: var(--color-accent-hover);
}

.btn-secondary {
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
}

.btn-secondary:hover {
  background-color: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.btn-icon {
  width: 16px;
  height: 16px;
}

.file-list-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.file-list-body::-webkit-scrollbar {
  width: 6px;
}

.file-list-body::-webkit-scrollbar-track {
  background: transparent;
}

.file-list-body::-webkit-scrollbar-thumb {
  background-color: var(--color-border);
  border-radius: 9999px;
}

.file-list-body::-webkit-scrollbar-thumb:hover {
  background-color: var(--color-text-muted);
}
</style>
