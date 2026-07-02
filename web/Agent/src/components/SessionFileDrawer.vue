<script setup>
/**
 * SessionFileDrawer - 会话文件空间抽屉（2026-07-01 新增）
 *
 * 位于 ChatArea 右侧，点击蓝色双矩形图标后展开。
 * 展示当前会话/项目对应的原文件目录。
 * 点击文件时向父组件抛出 file-click 事件，由父组件打开文件预览弹窗。
 *
 * Props:
 *   visible: boolean
 *   fileTree: Object | null   // 来自 /api/session/{id}/files/tree 的 tree 根节点
 *   loading: boolean
 *   error: string
 *
 * Emits:
 *   close
 *   file-click(file)
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import FolderTree from './FolderTree.vue'

/**
 * 获取文件扩展名
 * @param {string} name - 文件名
 * @returns {string} 扩展名小写
 */
function getFileExtension(name) {
  if (!name) return ''
  const parts = name.split('.')
  return parts.length > 1 ? parts.pop().toLowerCase() : ''
}

/**
 * 根据文件扩展名获取图标颜色
 * @param {string} name - 文件名
 * @returns {string} 图标颜色
 */
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
  return colorMap[ext] || '#1E5AA8'
}

/**
 * 格式化文件大小
 * @param {number} bytes - 字节数
 * @returns {string} 格式化后的大小字符串
 */
function formatSize(bytes) {
  if (!bytes && bytes !== 0) return ''
  const num = Number(bytes)
  if (isNaN(num)) return bytes
  if (num < 1024) return num + ' B'
  if (num < 1024 * 1024) return (num / 1024).toFixed(1) + ' KB'
  return (num / (1024 * 1024)).toFixed(1) + ' MB'
}

// 抽屉宽度相关常量（单位：px）
const DEFAULT_DRAWER_WIDTH = 380
const MIN_DRAWER_WIDTH = 280
const MAX_DRAWER_WIDTH = 720
const CLOSE_THRESHOLD_WIDTH = 160
const STORAGE_KEY = 'session-file-drawer-width'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  fileTree: {
    type: Object,
    default: null
  },
  loading: {
    type: Boolean,
    default: false
  },
  error: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['close', 'file-click'])

const drawerRef = ref(null)
const drawerWidth = ref(DEFAULT_DRAWER_WIDTH)
const isResizing = ref(false)

function handleClose() {
  emit('close')
}

function handleFileClick(file) {
  emit('file-click', file)
}

/**
 * 将抽屉宽度限制在合法区间内
 * @param {number} width - 原始宽度
 * @returns {number} 限制后的宽度
 */
function clampDrawerWidth(width) {
  const maxAllowed = Math.min(MAX_DRAWER_WIDTH, window.innerWidth - 200)
  return Math.max(MIN_DRAWER_WIDTH, Math.min(width, maxAllowed))
}

/**
 * 从 localStorage 读取保存的抽屉宽度
 * @returns {number} 抽屉宽度
 */
function loadDrawerWidth() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      const parsed = parseInt(saved, 10)
      if (!isNaN(parsed)) {
        return clampDrawerWidth(parsed)
      }
    }
  } catch {
    // localStorage 不可用时使用默认值
  }
  return DEFAULT_DRAWER_WIDTH
}

/**
 * 将当前抽屉宽度持久化到 localStorage
 */
function saveDrawerWidth() {
  try {
    localStorage.setItem(STORAGE_KEY, String(drawerWidth.value))
  } catch {
    // 忽略写入失败
  }
}

/**
 * 开始拖拽调整宽度
 * @param {MouseEvent} e - 鼠标按下事件
 */
function startResize(e) {
  e.preventDefault()
  isResizing.value = true
  document.body.style.userSelect = 'none'
}

/**
 * 拖拽过程中实时计算抽屉宽度
 * 抽屉位于最右侧，宽度 = 抽屉右边界 x - 当前鼠标 x
 */
function handleResizeMove(e) {
  if (!isResizing.value) return
  const rect = drawerRef.value?.getBoundingClientRect()
  if (!rect) return
  const newWidth = rect.right - e.clientX
  drawerWidth.value = clampDrawerWidth(newWidth)
}

/**
 * 拖拽结束：若宽度小于关闭阈值则自动收起抽屉；否则保存宽度
 */
function stopResize() {
  if (!isResizing.value) return
  isResizing.value = false
  document.body.style.userSelect = ''
  if (drawerWidth.value < CLOSE_THRESHOLD_WIDTH) {
    emit('close')
    drawerWidth.value = loadDrawerWidth()
  } else {
    saveDrawerWidth()
  }
}

onMounted(() => {
  drawerWidth.value = loadDrawerWidth()
  window.addEventListener('mousemove', handleResizeMove)
  window.addEventListener('mouseup', stopResize)
})

onUnmounted(() => {
  window.removeEventListener('mousemove', handleResizeMove)
  window.removeEventListener('mouseup', stopResize)
})

const drawerStyle = computed(() => ({
  '--drawer-width': drawerWidth.value + 'px'
}))

/**
 * 把后端返回树中的"原文件"文件夹展开，将其内部子节点提升到根级展示。
 * 同时过滤掉"解析缓存"等后端内部目录，避免暴露临时文件。
 * @returns {Array} 提升后需要展示的根级节点列表
 */
const displayNodes = computed(() => {
  if (!props.fileTree || !Array.isArray(props.fileTree.children)) return []

  const result = []
  for (const child of props.fileTree.children) {
    if (child.type !== 'folder') {
      result.push(child)
      continue
    }
    if (child.name === '解析缓存') {
      continue
    }
    if (child.name === '原文件' && Array.isArray(child.children)) {
      result.push(...child.children)
    } else {
      result.push(child)
    }
  }
  return result
})

/**
 * 需要展示的文件夹节点（根级，已去掉"原文件"这一层）
 * @returns {Array} 文件夹节点列表
 */
const displayFolders = computed(() => {
  return displayNodes.value.filter(child => child.type === 'folder')
})

/**
 * 根目录下直接挂载的文件（兜底）
 * @returns {Array} 根级文件列表
 */
const displayFiles = computed(() => {
  return displayNodes.value.filter(child => child.type !== 'folder')
})

const hasChildren = computed(() => displayNodes.value.length > 0)
</script>

<template>
  <aside
    ref="drawerRef"
    v-show="visible"
    class="session-file-drawer"
    :class="{ visible, resizing: isResizing }"
    :style="drawerStyle"
    role="complementary"
    aria-label="工作空间"
  >
    <!-- 左侧拖拽条：用于调整抽屉宽度 -->
    <div
      class="resize-handle"
      :class="{ active: isResizing }"
      @mousedown="startResize"
      aria-label="调整抽屉宽度"
      role="separator"
    ></div>

    <!-- 头部 -->
    <div class="drawer-header">
      <div class="drawer-title">
        <svg class="title-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M2 6a2 2 0 012-2h5l2 2h9a2 2 0 012 2v9a2 2 0 01-2 2H4a2 2 0 01-2-2V6z"/>
        </svg>
        <span>工作空间</span>
      </div>
      <button class="close-btn" @click="handleClose" aria-label="关闭抽屉">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </div>

    <!-- 文件树内容区 -->
    <div class="drawer-body">
      <div v-if="loading" class="drawer-state">
        <div class="state-spinner"></div>
        <span>加载文件列表...</span>
      </div>

      <div v-else-if="error" class="drawer-state drawer-error">
        <span>{{ error }}</span>
      </div>

      <div v-else-if="!hasChildren" class="drawer-state">
        <span>暂无文件</span>
      </div>

      <div v-else class="tree-wrapper">
        <FolderTree
          v-for="folder in displayFolders"
          :key="folder.path || folder.name"
          :folder="folder"
          :depth="0"
          @file-click="handleFileClick"
        />

        <button
          v-for="file in displayFiles"
          :key="file.path || file.name"
          class="file-item"
          :style="{ '--depth': 0 }"
          @click="handleFileClick(file)"
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
  </aside>
</template>

<style scoped>
/* Push Drawer 根容器 - 与 SubAgentDrawer 同布局机制 */
.session-file-drawer {
  position: relative;
  flex: 0 0 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  height: 100%;
  width: var(--drawer-width, 380px);
  max-width: min(720px, calc(100vw - 200px));
  background: #ffffff;
  border-left: 1px solid transparent;
  transition: flex-basis 0.3s ease, border-color 0.3s ease;
  flex-shrink: 0;
}

.session-file-drawer.visible {
  flex-basis: var(--drawer-width, 380px);
  border-left-color: var(--color-border);
}

.session-file-drawer.resizing {
  transition: none;
}

/* 左侧拖拽条 */
.resize-handle {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 6px;
  cursor: col-resize;
  z-index: 10;
  background: transparent;
  transition: background-color 0.2s ease;
}

.resize-handle:hover,
.resize-handle.active {
  background: var(--color-accent, #1E5AA8);
}

/* 头部 */
.drawer-header {
  padding: 8px 16px 6px;
  border-bottom: 1px solid #e0e0e0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
}

.drawer-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.title-icon {
  width: 20px;
  height: 20px;
  color: var(--color-accent, #1E5AA8);
}

.close-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  color: var(--color-text-muted);
  transition: all 0.2s ease;
}

.close-btn:hover {
  background-color: var(--color-bg-hover);
  color: var(--color-text-secondary);
}

.close-btn svg {
  width: 18px;
  height: 18px;
}

/* 内容区 */
.drawer-body {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 12px 16px 16px;
}

.drawer-body::-webkit-scrollbar {
  width: 6px;
}

.drawer-body::-webkit-scrollbar-track {
  background: transparent;
}

.drawer-body::-webkit-scrollbar-thumb {
  background-color: var(--color-border);
  border-radius: var(--radius-full);
}

.drawer-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 20px;
  gap: 12px;
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.drawer-error {
  color: #ef4444;
}

.state-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.tree-wrapper {
  display: flex;
  flex-direction: column;
  gap: 2px;
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

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
