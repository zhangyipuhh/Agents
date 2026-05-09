<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  folder: { type: Object, required: true },
  depth: { type: Number, default: 0 }
})

const emit = defineEmits(['file-click'])

const isExpanded = ref(false)

function toggleExpand() {
  isExpanded.value = !isExpanded.value
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
    json: '#F59E0B'
  }
  return colorMap[ext] || '#6366F1'
}

function formatSize(bytes) {
  if (!bytes && bytes !== 0) return ''
  const num = Number(bytes)
  if (isNaN(num)) return bytes
  if (num < 1024) return num + ' B'
  if (num < 1024 * 1024) return (num / 1024).toFixed(1) + ' KB'
  return (num / (1024 * 1024)).toFixed(1) + ' MB'
}

function onFileClick(file) {
  emit('file-click', file)
}

const childFolders = computed(() => {
  if (!props.folder.children) return []
  return props.folder.children.filter(child => child.type === 'folder')
})

const childFiles = computed(() => {
  if (!props.folder.children) return []
  return props.folder.children.filter(child => child.type !== 'folder')
})

const totalFileCount = computed(() => {
  function countFiles(folder) {
    if (!folder.children) return 0
    let count = 0
    for (const child of folder.children) {
      if (child.type === 'folder') {
        count += countFiles(child)
      } else {
        count += 1
      }
    }
    return count
  }
  return countFiles(props.folder)
})

const paddingLeft = computed(() => `${props.depth * 12}px`)
</script>

<template>
  <div class="folder-tree-item" :style="{ '--depth': depth }">
    <button class="folder-header" @click="toggleExpand">
      <svg class="folder-icon" viewBox="0 0 20 20" fill="currentColor">
        <path v-if="isExpanded" d="M6 10l4 4 4-4" stroke="currentColor" stroke-width="2" fill="none"/>
        <path v-else d="M10 6l4 4-4 4"/>
        <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z"/>
      </svg>
      <span class="folder-name">{{ folder.name }}</span>
      <span class="folder-count">{{ totalFileCount }}</span>
    </button>
    
    <div v-if="isExpanded && (childFolders.length > 0 || childFiles.length > 0)" class="folder-children">
      <div v-for="subFolder in childFolders" :key="subFolder.path || subFolder.name" class="sub-folder">
        <FolderTree :folder="subFolder" :depth="depth + 1" @file-click="onFileClick" />
      </div>
      
      <button
        v-for="file in childFiles"
        :key="file.path || file.name"
        class="file-item"
        :style="{ '--depth': depth }"
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
.folder-tree-item {
  display: flex;
  flex-direction: column;
}

.folder-header {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 0;
  padding-left: var(--depth);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: var(--transition-colors);
  background: none;
  border: none;
  text-align: left;
}

.folder-header:hover {
  background-color: var(--color-bg-hover);
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
  padding-left: var(--depth);
}

.sub-folder {
  display: flex;
  flex-direction: column;
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
  background: none;
  border: none;
}

.file-item:hover {
  background-color: var(--color-bg-hover);
}

.file-item:active {
  transform: scale(var(--scale-active));
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
</style>