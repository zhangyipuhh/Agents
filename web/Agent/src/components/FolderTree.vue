<script setup>
import { ref, computed } from 'vue'
import { fetchWithAuth } from '../utils/api.js'

const props = defineProps({
  folder: { type: Object, required: true },
  depth: { type: Number, default: 0 },
  // 2026-07-07 新增：当前会话 ID，透传给子 FolderTree 与 download URL 拼接
  sessionId: { type: String, default: '' }
})

const emit = defineEmits(['file-click'])

const isExpanded = ref(false)

function toggleExpand() {
  isExpanded.value = !isExpanded.value
}

/**
 * 触发单个文件下载。
 * 通过后端 GET /api/session/{sessionId}/files/download?stored_path=... 拉取原文件。
 * 设计与 SessionFileDrawer.vue 同：传完整 stored_path 而非 UUID；
 * 必须用 fetchWithAuth 携带 Authorization 头（<a download> 触发 401 实测 2026-07-07）。
 * @param {MouseEvent} event - 用于 stopPropagation 防止冒泡触发父级预览
 * @param {Object} file - 文件树节点，至少包含 name / path / stored_path
 */
async function handleDownload(event, file) {
  event.stopPropagation()
  event.preventDefault()
  const storedPath = (file && (file.stored_path || file.path)) || ''
  if (!storedPath) {
    console.warn('[FolderTree] 文件缺少有效 stored_path / path，无法下载:', file)
    return
  }
  if (!props.sessionId) {
    console.warn('[FolderTree] 缺少 sessionId，无法拼下载 URL')
    return
  }
  const url = `/api/session/${encodeURIComponent(props.sessionId)}/files/download?stored_path=${encodeURIComponent(storedPath)}`
  let blobUrl = null
  try {
    const response = await fetchWithAuth(url, { method: 'GET' })
    if (!response.ok) {
      const text = await response.text().catch(() => '')
      throw new Error(`下载失败: HTTP ${response.status} ${text}`)
    }
    const blob = await response.blob()
    // 尝试从 Content-Disposition 头解析后端设置的 filename（含中文）
    const cdHeader = response.headers.get('content-disposition') || ''
    let downloadName = (file && file.name) || 'download'
    const utf8Match = cdHeader.match(/filename\*=UTF-8''([^;]+)/i)
    const asciiMatch = cdHeader.match(/filename="?([^";]+)"?/i)
    if (utf8Match) {
      try { downloadName = decodeURIComponent(utf8Match[1]) } catch { /* 保持 fallback */ }
    } else if (asciiMatch) {
      downloadName = asciiMatch[1]
    }
    blobUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = blobUrl
    link.download = downloadName
    link.rel = 'noopener'
    link.style.display = 'none'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    setTimeout(() => {
      if (blobUrl) URL.revokeObjectURL(blobUrl)
    }, 1000)
  } catch (err) {
    console.error('[FolderTree] 下载文件失败:', err, file)
    if (blobUrl) URL.revokeObjectURL(blobUrl)
  }
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
  // 文件图标默认回退色：与登录页主色 #1E5AA8 保持一致
  return colorMap[ext] || '#1E5AA8'
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
        <FolderTree :folder="subFolder" :depth="depth + 1" :session-id="sessionId" @file-click="onFileClick" />
      </div>
      
      <div
        v-for="file in childFiles"
        :key="file.path || file.name"
        class="file-item"
        :style="{ '--depth': depth }"
        role="button"
        tabindex="0"
        @click="onFileClick(file)"
        @keydown.enter="onFileClick(file)"
        @keydown.space.prevent="onFileClick(file)"
      >
        <div class="file-row">
          <div class="file-row-main">
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
          </div>
          <button
            class="download-btn"
            type="button"
            :aria-label="`下载 ${file.name}`"
            :title="`下载 ${file.name}`"
            @click="handleDownload($event, file)"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                 stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
          </button>
        </div>
      </div>
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
  outline: none;
}

.file-item:focus-visible {
  box-shadow: 0 0 0 2px var(--color-accent, #1E5AA8);
  background-color: var(--color-bg-hover);
}

/* 文件行容器：左主信息 + 右下载按钮（2026-07-07 新增） */
.file-row {
  display: flex;
  align-items: flex-start;
  width: 100%;
  gap: 8px;
}

.file-row-main {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  flex: 1;
  min-width: 0;
}

/* 下载按钮（2026-07-07 新增） */
.download-btn {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.15s ease;
  margin-top: 2px;
}

.download-btn:hover {
  background-color: var(--color-accent-light);
  color: var(--color-accent);
  border-color: var(--color-accent);
}

.download-btn:active {
  transform: scale(var(--scale-active));
}

.download-btn:focus-visible {
  outline: 2px solid var(--color-accent, #1E5AA8);
  outline-offset: 1px;
}

.download-btn svg {
  width: 16px;
  height: 16px;
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