<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  files: { type: Array, default: () => [] },
  folders: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false }
})

const emit = defineEmits(['file-click'])

const expandedFolders = ref(new Set())

function toggleFolder(folderPath) {
  const newSet = new Set(expandedFolders.value)
  if (newSet.has(folderPath)) {
    newSet.delete(folderPath)
  } else {
    newSet.add(folderPath)
  }
  expandedFolders.value = newSet
}

function isFolderExpanded(folderPath) {
  return expandedFolders.value.has(folderPath)
}

function formatSize(bytes) {
  if (!bytes && bytes !== 0) return ''
  const num = Number(bytes)
  if (isNaN(num)) return bytes
  if (num < 1024) return num + ' B'
  if (num < 1024 * 1024) return (num / 1024).toFixed(1) + ' KB'
  return (num / (1024 * 1024)).toFixed(1) + ' MB'
}

function getFileExtension(name) {
  if (!name) return ''
  const parts = name.split('.')
  return parts.length > 1 ? parts.pop().toLowerCase() : ''
}

function getFileIconColor(name) {
  const ext = getFileExtension(name)
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
    html: '#F97316',
    css: '#8B5CF6',
    js: '#EAB308',
    ts: '#3B82F6',
    py: '#3B82F6',
    png: '#EC4899',
    jpg: '#EC4899',
    jpeg: '#EC4899',
    gif: '#EC4899',
    svg: '#F97316'
  }
  return colorMap[ext] || '#6366F1'
}

function onFileClick(file) {
  emit('file-click', file)
}

const hasContent = computed(() => {
  return props.files.length > 0 || props.folders.length > 0
})
</script>

<template>
  <div class="file-list">
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
    <div v-else class="file-list-content">
      <div v-for="folder in folders" :key="folder.path || folder.name" class="folder-group">
        <button class="folder-header" @click="toggleFolder(folder.path || folder.name)">
          <svg class="folder-chevron" :class="{ expanded: isFolderExpanded(folder.path || folder.name) }" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clip-rule="evenodd"/>
          </svg>
          <svg class="folder-icon" viewBox="0 0 20 20" fill="currentColor">
            <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z"/>
          </svg>
          <span class="folder-name">{{ folder.name }}</span>
          <span class="folder-count">{{ folder.children ? folder.children.length : 0 }}</span>
        </button>
        <div v-if="isFolderExpanded(folder.path || folder.name)" class="folder-children">
          <button
            v-for="file in (folder.children || [])"
            :key="file.path || file.name"
            class="file-item"
            @click="onFileClick(file)"
          >
            <svg class="file-type-icon" viewBox="0 0 20 20" fill="currentColor" :style="{ color: getFileIconColor(file.name) }">
              <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clip-rule="evenodd"/>
            </svg>
            <div class="file-info">
              <div class="file-info-top">
                <span class="file-name">{{ file.name }}</span>
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

      <button
        v-for="file in files"
        :key="file.path || file.name"
        class="file-item"
        @click="onFileClick(file)"
      >
        <svg class="file-type-icon" viewBox="0 0 20 20" fill="currentColor" :style="{ color: getFileIconColor(file.name) }">
          <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clip-rule="evenodd"/>
        </svg>
        <div class="file-info">
          <div class="file-info-top">
            <span class="file-name">{{ file.name }}</span>
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

.folder-chevron {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  color: var(--color-text-muted);
  transition: transform 0.2s ease;

  &.expanded {
    transform: rotate(90deg);
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
  white-space: nowrap;
  flex: 1;
  min-width: 0;
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
