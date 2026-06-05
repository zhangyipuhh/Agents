<script setup>
import { ref, computed } from 'vue'
import FolderTree from './FolderTree.vue'

const props = defineProps({
  files: { type: Array, default: () => [] },
  folders: { type: Array, default: () => [] },
  loading: { type: Boolean, default: () => false }
})

const emit = defineEmits(['file-click'])

const searchQuery = ref('')

function matchesFile(file, query) {
  const q = query.toLowerCase()
  if (file.name && file.name.toLowerCase().includes(q)) return true
  if (file.summary && file.summary.toLowerCase().includes(q)) return true
  if (file.keywords && file.keywords.length) {
    return file.keywords.some(kw => kw.toLowerCase().includes(q))
  }
  return false
}

function filterFolder(folder, query) {
  const folderNameMatch = folder.name && folder.name.toLowerCase().includes(query.toLowerCase())
  if (folderNameMatch) return { ...folder }
  if (!folder.children || !folder.children.length) return null
  const matchedChildren = []
  for (const child of folder.children) {
    if (child.type === 'folder') {
      const filtered = filterFolder(child, query)
      if (filtered) matchedChildren.push(filtered)
    } else if (matchesFile(child, query)) {
      matchedChildren.push(child)
    }
  }
  if (!matchedChildren.length) return null
  return { ...folder, children: matchedChildren }
}

const filteredFiles = computed(() => {
  if (!searchQuery.value) return props.files
  return props.files.filter(f => matchesFile(f, searchQuery.value))
})

const filteredFolders = computed(() => {
  if (!searchQuery.value) return props.folders
  return props.folders
    .map(f => filterFolder(f, searchQuery.value))
    .filter(Boolean)
})

const hasFilteredContent = computed(() => {
  if (filteredFolders.value.length > 0) {
    return filteredFolders.value.some(f => f.children && f.children.length > 0)
  }
  return filteredFiles.value.length > 0
})

const hasContent = computed(() => {
  if (props.folders.length > 0) {
    return props.folders.some(f => f.children && f.children.length > 0)
  }
  return props.files.length > 0
})

function clearSearch() {
  searchQuery.value = ''
}

function onFileClick(file) {
  emit('file-click', file)
}

function formatSize(bytes) {
  if (!bytes && bytes !== 0) return ''
  const num = Number(bytes)
  if (isNaN(num)) return bytes
  if (num < 1024) return num + ' B'
  if (num < 1024 * 1024) return (num / 1024).toFixed(1) + ' KB'
  return (num / (1024 * 1024)).toFixed(1) + ' MB'
}

function getFileIconColor(name) {
  // 文件图标默认回退色：与登录页主色 #1E5AA8 保持一致
  if (!name) return '#1E5AA8'
  const parts = name.split('.')
  const ext = parts.length > 1 ? parts.pop().toLowerCase() : ''
  const colorMap = {
    md: '#6B7280',
    pdf: '#EF4444',
    doc: '#3B82F6',
    docx: '#3B82F6',
    csv: '#10B981',
    xlsx: '#10B981',
    xls: '#10B981',
    txt: '#9CA3AF',
    json: '#F59E0B',
    ppt: '#FF6B00',
    pptx: '#FF6B00'
  }
  return colorMap[ext] || '#1E5AA8'
}
</script>

<template>
  <div class="file-list">
    <div v-if="!loading && hasContent" class="search-box-wrapper">
      <div class="search-box">
        <svg class="search-icon" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clip-rule="evenodd"/>
        </svg>
        <input
          type="text"
          class="search-input"
          placeholder="搜索文件..."
          v-model="searchQuery"
        />
        <button v-if="searchQuery" class="search-clear-btn" @click="clearSearch">
          <svg viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>
          </svg>
        </button>
      </div>
    </div>

    <div v-if="loading" class="file-list-loading">
      <div class="loading-spinner"></div>
      <span>加载中...</span>
    </div>
    <div v-else-if="!hasContent" class="file-list-empty">
      <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" class="empty-icon">
        <circle cx="32" cy="32" r="30" stroke="var(--color-border)" stroke-width="2"/>
        <path d="M32 20v24M20 32h24" stroke="var(--color-text-muted)" stroke-width="2.5" stroke-linecap="round"/>
      </svg>
      <p class="empty-text">暂无知识库文件</p>
    </div>
    <div v-else-if="searchQuery && !hasFilteredContent" class="file-list-empty">
      <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" class="empty-icon">
        <circle cx="32" cy="32" r="30" stroke="var(--color-border)" stroke-width="2"/>
        <path d="M22 22l20 20M42 22L22 42" stroke="var(--color-text-muted)" stroke-width="2.5" stroke-linecap="round"/>
      </svg>
      <p class="empty-text">未找到匹配的文件</p>
    </div>
    <div v-else class="file-list-content">
      <div v-for="folder in filteredFolders" :key="folder.path || folder.name" class="folder-group">
        <FolderTree :folder="folder" :depth="0" @file-click="onFileClick" />
      </div>

      <button
        v-for="file in filteredFiles"
        :key="file.path || file.name"
        class="file-item"
        :style="{ '--depth': 0 }"
        @click="onFileClick(file)"
      >
        <svg class="file-type-icon" viewBox="0 0 20 20" fill="currentColor" :style="{ color: getFileIconColor(file.name) }">
          <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clip-rule="evenodd"/>
        </svg>
        <div class="file-info">
          <div class="file-info-top">
            <span class="file-name" :title="file.name">{{ file.name }}</span>
            <span v-if="file.size" class="file-size">{{ formatSize(file.size) }}</span>
          </div>
          <div v-if="file.summary" class="file-summary">{{ file.summary }}</div>
          <div class="file-meta">
            <span v-if="file.date" class="file-date">{{ file.date }}</span>
            <div v-if="file.keywords && file.keywords.length" class="file-keywords">
              <span v-for="kw in file.keywords" :key="kw" class="keyword-tag">{{ kw }}</span>
            </div>
          </div>
        </div>
      </button>
    </div>
  </div>
</template>

<style scoped>
.file-list {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
}

.search-box-wrapper {
  padding: 0 0 8px 0;
  flex-shrink: 0;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 6px;
  background-color: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 0 10px;
  transition: var(--transition-colors), var(--transition-shadow);
}

.search-box:focus-within {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.12);
}

.search-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  color: var(--color-text-muted);
  transition: var(--transition-colors);
}

.search-box:focus-within .search-icon {
  color: var(--color-accent);
}

.search-input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  padding: 8px 0;
  font-family: var(--font-family);
  caret-color: var(--caret-color);
}

.search-input::placeholder {
  color: var(--color-text-muted);
}

.search-clear-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  border: none;
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-full);
  cursor: pointer;
  padding: 0;
  transition: var(--transition-colors);

  svg {
    width: 12px;
    height: 12px;
    color: var(--color-text-muted);
  }

  &:hover {
    background: var(--color-bg-active);

    svg {
      color: var(--color-text-secondary);
    }
  }
}

.file-list-loading,
.file-list-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--color-text-muted);
}

.empty-icon {
  width: 64px;
  height: 64px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.empty-text {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.file-list-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.folder-group {
  display: flex;
  flex-direction: column;
}

.folder-header {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 0;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: var(--transition-colors);

  &:hover {
    background-color: var(--color-bg-hover);
  }
}

.folder-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  color: #F59E0B;
}

.folder-name {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  flex: 1;
  text-align: left;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.folder-count {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  background-color: var(--color-bg-tertiary);
  padding: 1px 6px;
  border-radius: var(--radius-full);
  flex-shrink: 0;
}

.folder-children {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-left: 12px;
}

.file-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: 100%;
  padding: 10px 0;
  padding-left: calc(var(--depth) + 12px);
  border-radius: var(--radius-sm);
  text-align: left;
  cursor: pointer;
  transition: var(--transition-colors);

  &:hover {
    background-color: var(--color-bg-hover);
  }

  &:active {
    transform: scale(var(--scale-active));
  }
}

.file-type-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  margin-top: 2px;
}

.file-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  flex: 1;
}

.file-info-top {
  display: flex;
  align-items: center;
  gap: 8px;
}

.file-name {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  word-break: break-all;
  flex: 1;
  min-width: 0;
  line-height: 1.4;
}

.file-size {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.file-summary {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  line-height: var(--line-height-normal);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.file-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.file-date {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.file-keywords {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.keyword-tag {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: var(--radius-full);
  background-color: var(--color-accent-light);
  color: var(--color-accent);
  white-space: nowrap;
}

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: 12px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
