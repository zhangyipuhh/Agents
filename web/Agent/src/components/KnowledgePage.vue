<script setup>
import { ref, onMounted } from 'vue'
import { fetchKnowledgeFiles, fetchFilePreview } from '../utils/api.js'
import FileList from './FileList.vue'
import FilePreview from './FilePreview.vue'
import KnowledgeChat from './KnowledgeChat.vue'

const emit = defineEmits(['new-chat', 'page-change'])

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
    console.error(err)
  } finally {
    filesLoading.value = false
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
    previewContent.value = '预览加载失败'
  } finally {
    previewLoading.value = false
  }
}

function closePreview() {
  isPreviewOpen.value = false
  previewContent.value = ''
}

function handleNewChat() {
  emit('new-chat')
}

function handleChatSend(message) {
  isChatStreaming.value = true
}

function handleChatStreamEnd() {
  isChatStreaming.value = false
}
</script>

<template>
  <div class="knowledge-page">
    <FilePreview
      :isOpen="isPreviewOpen"
      :content="previewContent"
      :fileType="previewFileType"
      :fileName="previewFileName"
      :loading="previewLoading"
      @close="closePreview"
    />

    <div class="file-list-panel">
      <div class="file-list-header">
        <h2 class="file-list-title">知识库文件</h2>
      </div>
      <div class="file-list-body">
        <FileList :files="files" :folders="folders" :loading="filesLoading" @file-click="handleFileClick" />
      </div>
    </div>

    <KnowledgeChat
      :session-id="currentSessionId"
      :is-streaming="isChatStreaming"
      @new-chat="handleNewChat"
      @send="handleChatSend"
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
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.file-list-header {
  flex-shrink: 0;
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-border-light);
}

.file-list-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  margin: 0;
}

.file-list-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;

  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background-color: var(--color-border);
    border-radius: var(--radius-full);

    &:hover {
      background-color: var(--color-text-muted);
    }
  }
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
