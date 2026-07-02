<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import UserSettingsDialog from './UserSettingsDialog.vue'
import { fetchSessionList, deleteSession, fetchProjectList, updateSessionTitle, exportSessionMarkdown } from '../utils/api.js'

const props = defineProps({
  currentPage: {
    type: String,
    default: 'agent'
  },
  username: {
    type: String,
    default: '用户名'
  },
  userRole: {
    type: String,
    default: 'user'
  },
  userId: {
    type: Number,
    default: null
  },
  currentSessionId: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['toggle-sidebar', 'new-chat', 'page-change', 'logout', 'username-updated', 'session-switch'])

const isSidebarCollapsed = ref(false)
const isHistoryCollapsed = ref(false)
const isLabCollapsed = ref(false)
const activeMenu = ref('new-task')
const isUserMenuVisible = ref(false)
const userMenuRef = ref(null)
const menuPositionStyle = ref({})
const isSettingsDialogVisible = ref(false)
const settingsInitialTab = ref('profile')

const historySessions = ref([])
const isLoadingSessions = ref(false)

const projects = ref([])
const isLoadingProjects = ref(false)
const projectCollapsedMap = ref({})

/* ---- 右键菜单状态 ---- */
const contextMenuVisible = ref(false)
const contextMenuPosition = ref({ x: 0, y: 0 })
const contextMenuSession = ref(null)

/* ---- 行内重命名状态 ---- */
const editingSessionId = ref(null)
const editingTitle = ref('')
const editingInputRef = ref(null)

/**
 * 从后端加载会话列表
 */
const loadSessionList = async () => {
  if (!props.username || props.username === '用户名') return
  isLoadingSessions.value = true
  try {
    const data = await fetchSessionList()
    historySessions.value = (data.sessions || []).map(s => ({
      id: s.session_id,
      title: s.title || '新对话',
      time: formatTime(s.last_active_at || s.created_at),
      active: s.session_id === props.currentSessionId,
      sessionId: s.session_id,
      projectId: s.project_id
    }))
  } catch (err) {
    console.error('加载会话列表失败:', err)
    historySessions.value = []
  } finally {
    isLoadingSessions.value = false
  }
}

/**
 * 从后端加载项目列表
 */
const loadProjectList = async () => {
  if (!props.username || props.username === '用户名') return
  isLoadingProjects.value = true
  try {
    const data = await fetchProjectList()
    const list = data.projects || []
    projects.value = list
    // 初始化折叠状态：项目分组默认展开，但其下属会话默认折叠，避免一次性展示过多历史记录
    list.forEach(p => {
      if (!(p.id in projectCollapsedMap.value)) {
        projectCollapsedMap.value[p.id] = true
      }
    })
  } catch (err) {
    console.error('加载项目列表失败:', err)
    projects.value = []
  } finally {
    isLoadingProjects.value = false
  }
}

/**
 * 获取指定项目下的会话
 * @param {number} projectId - 项目 ID
 * @returns {Array} 会话列表
 */
const getProjectSessions = (projectId) => {
  return historySessions.value.filter(s => s.projectId === projectId)
}

/**
 * 获取未绑定项目的会话
 * @returns {Array} 会话列表
 */
const unprojectedSessions = computed(() => {
  return historySessions.value.filter(s => !s.projectId)
})

/**
 * 切换项目折叠状态
 * @param {number} projectId - 项目 ID
 */
const toggleProjectCollapsed = (projectId) => {
  projectCollapsedMap.value[projectId] = !projectCollapsedMap.value[projectId]
}

/**
 * 格式化时间显示
 * @param {string} dateStr - ISO 日期字符串
 * @returns {string} 格式化后的时间文本
 */
const formatTime = (dateStr) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now - date
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return '刚刚'
  if (diffMins < 60) return `${diffMins}分钟前`
  if (diffHours < 24) return `${diffHours}小时前`
  if (diffDays < 7) return `${diffDays}天前`
  return `${date.getMonth() + 1}/${date.getDate()}`
}

/**
 * 切换到历史会话
 * @param {Object} session - 会话对象
 */
const handleSessionClick = (session) => {
  emit('session-switch', session.sessionId)
}

/* ---- 删除会话：应用内确认弹窗状态 ---- */
/** @type {import('vue').Ref<string|null>} 待删除的会话 ID；为 null 时表示弹窗关闭 */
const pendingDeleteId = ref(null)
/** @type {import('vue').Ref<string>} 待删除的会话标题，用于弹窗正文展示 */
const pendingDeleteSessionTitle = ref('')

/**
 * 删除历史会话（点击垃圾桶按钮触发，仅打开应用内确认弹窗，不再用浏览器原生 confirm）
 * @param {string} sessionId - 会话 ID
 * @param {string} sessionTitle - 会话标题（用于弹窗正文）
 * @param {MouseEvent} event - 鼠标事件
 * @returns {void}
 */
const handleDeleteSession = (sessionId, sessionTitle, event) => {
  event.stopPropagation()
  pendingDeleteSessionTitle.value = sessionTitle || ''
  pendingDeleteId.value = sessionId
}

/**
 * 用户在应用内确认弹窗中点击「确认删除」：执行真正的删除逻辑
 * @returns {Promise<void>} 完成后无返回值；删除失败时通过 console.error 记录错误
 */
const confirmDeleteSession = async () => {
  const id = pendingDeleteId.value
  if (!id) return
  // 先关闭弹窗再执行删除，避免删除慢时 UI 显得卡顿
  pendingDeleteId.value = null
  pendingDeleteSessionTitle.value = ''
  try {
    await deleteSession(id)
    await loadSessionList()
  } catch (err) {
    console.error('删除会话失败:', err)
  }
}

/**
 * 用户在应用内确认弹窗中点击「取消」或点击遮罩：仅关闭弹窗
 * @returns {void}
 */
const cancelDeleteSession = () => {
  pendingDeleteId.value = null
  pendingDeleteSessionTitle.value = ''
}

const handleMenuClick = (menuId) => {
  activeMenu.value = menuId
  if (menuId === 'new-task') {
    emit('new-chat')
    emit('page-change', 'agent')
  }
  if (menuId === 'knowledge') {
    // 在浏览器新窗口中打开知识库页面
    const width = 1200
    const height = 800
    const left = (window.screen.width - width) / 2
    const top = (window.screen.height - height) / 2
    const windowName = 'knowledgeWindow_' + Date.now()
    window.open(
      '/knowledge.html',
      windowName,
      `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes,status=yes`
    )
  }
}

const toggleSidebar = () => {
  isSidebarCollapsed.value = !isSidebarCollapsed.value
  emit('toggle-sidebar', !isSidebarCollapsed.value)
}

const toggleHistory = () => {
  isHistoryCollapsed.value = !isHistoryCollapsed.value
}

const toggleLab = () => {
  isLabCollapsed.value = !isLabCollapsed.value
}

/**
 * 切换用户菜单显示状态
 * @param {MouseEvent} event - 鼠标事件对象
 */
const toggleUserMenu = (event) => {
  event.stopPropagation()
  isUserMenuVisible.value = !isUserMenuVisible.value
}

/**
 * 关闭用户菜单
 */
const closeUserMenu = () => {
  isUserMenuVisible.value = false
}

/**
 * 处理设置点击
 * 打开用户设置对话框并显示个人设置页
 */
const handleSetting = () => {
  closeUserMenu()
  settingsInitialTab.value = 'profile'
  isSettingsDialogVisible.value = true
}

/**
 * 处理管理后台点击
 * 打开用户设置对话框并显示管理功能页
 */
const handleAdminPanel = () => {
  closeUserMenu()
  settingsInitialTab.value = 'user-management'
  isSettingsDialogVisible.value = true
}

/**
 * 处理退出登录点击
 * 触发登出事件
 */
const handleLogout = () => {
  closeUserMenu()
  emit('logout')
}

/**
 * 处理用户名更新事件
 * @param {Object} data - 包含新用户名的数据
 */
const handleUsernameUpdated = (data) => {
  emit('username-updated', data)
}

/**
 * 更新用户菜单位置
 * 根据侧边栏折叠状态和头像位置计算菜单应该显示的位置
 */
const updateMenuPosition = () => {
  if (!userMenuRef.value) return

  const rect = userMenuRef.value.getBoundingClientRect()

  if (isSidebarCollapsed.value) {
    // 折叠状态：菜单显示在头像上方
    menuPositionStyle.value = {
      position: 'fixed',
      left: `${rect.left}px`,
      bottom: `${window.innerHeight - rect.top + 8}px`,
      width: '160px'
    }
  } else {
    // 展开状态：菜单显示在用户信息上方
    menuPositionStyle.value = {
      position: 'fixed',
      left: `${rect.left + 12}px`,
      bottom: `${window.innerHeight - rect.top + 8}px`,
      right: `${window.innerWidth - rect.right + 12}px`
    }
  }
}

/**
 * 处理窗口大小变化
 */
const handleResize = () => {
  if (isUserMenuVisible.value) {
    updateMenuPosition()
  }
}

/**
 * 处理点击外部关闭菜单
 * @param {MouseEvent} event - 鼠标事件对象
 */
const handleClickOutside = (event) => {
  // 检查点击是否在头像区域或菜单区域内
  const isClickOnAvatar = userMenuRef.value?.contains(event.target)
  const isClickOnMenu = event.target.closest('.user-menu')

  if (!isClickOnAvatar && !isClickOnMenu) {
    closeUserMenu()
  }

  // 点击会话右键菜单外部时关闭右键菜单
  const isClickOnSessionContextMenu = event.target.closest('.session-context-menu')
  if (!isClickOnSessionContextMenu) {
    closeContextMenu()
  }
}

/* ---- 会话右键菜单与行内重命名 ---- */

/**
 * 打开会话右键菜单
 * @param {Object} session - 会话对象
 * @param {MouseEvent} event - 鼠标事件对象
 */
const handleSessionContextMenu = (session, event) => {
  event.preventDefault()
  contextMenuSession.value = session
  contextMenuPosition.value = { x: event.clientX, y: event.clientY }
  contextMenuVisible.value = true
}

/**
 * 关闭会话右键菜单
 */
const closeContextMenu = () => {
  contextMenuVisible.value = false
  contextMenuSession.value = null
}

/**
 * 开始行内重命名会话
 * @param {Object} session - 会话对象
 */
const startRenameSession = (session) => {
  closeContextMenu()
  editingSessionId.value = session.sessionId
  editingTitle.value = session.title
  nextTick(() => {
    editingInputRef.value?.focus()
  })
}

/**
 * 确认保存重命名后的标题
 * @returns {Promise<void>}
 */
const confirmRename = async () => {
  const id = editingSessionId.value
  const newTitle = editingTitle.value.trim()
  editingSessionId.value = null

  if (!id || !newTitle) return

  // 乐观更新本地标题
  const session = historySessions.value.find(s => s.sessionId === id)
  const oldTitle = session ? session.title : ''
  if (session) session.title = newTitle

  try {
    await updateSessionTitle(id, newTitle)
  } catch (err) {
    console.error('重命名失败:', err)
    // 失败时回滚
    if (session) session.title = oldTitle
    await loadSessionList()
  }
}

/**
 * 取消行内重命名
 */
const cancelRename = () => {
  editingSessionId.value = null
  editingTitle.value = ''
}

/**
 * 导出会话为 Markdown 文件
 * @param {Object} session - 会话对象
 * @returns {Promise<void>}
 */
const exportSession = async (session) => {
  closeContextMenu()
  try {
    const { text, filename } = await exportSessionMarkdown(session.sessionId)
    const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (err) {
    console.error('导出失败:', err)
    alert('导出失败，请重试')
  }
}

// 监听菜单显示状态变化，更新位置
watch(isUserMenuVisible, (visible) => {
  if (visible) {
    nextTick(updateMenuPosition)
  }
})

// 监听侧边栏折叠状态变化，更新菜单位置
watch(isSidebarCollapsed, () => {
  if (isUserMenuVisible.value) {
    nextTick(updateMenuPosition)
  }
})

// 监听当前会话ID变化，更新历史记录高亮
watch(() => props.currentSessionId, (newId) => {
  historySessions.value.forEach(s => {
    s.active = s.sessionId === newId
  })
})

// 暴露 loadSessionList 方法给父组件调用
defineExpose({ loadSessionList })

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
  window.addEventListener('resize', handleResize)
  loadSessionList()
  loadProjectList()
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
  window.removeEventListener('resize', handleResize)
})
</script>

<template>
  <aside class="sidebar" :class="{ collapsed: isSidebarCollapsed }">
    <!-- Logo 区域 -->
    <div class="sidebar-logo">
      <div class="logo-container">
        <svg class="logo-icon" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect width="32" height="32" rx="8" fill="var(--color-accent)"/>
          <path d="M16 8L22 12V20L16 24L10 20V12L16 8Z" stroke="white" stroke-width="2" stroke-linejoin="round"/>
          <circle cx="16" cy="16" r="3" fill="white"/>
        </svg>
      </div>
      <button class="sidebar-toggle" @click="toggleSidebar" :title="isSidebarCollapsed ? '展开侧栏' : '收起侧栏'">
        <svg viewBox="0 0 20 20" fill="currentColor" class="toggle-icon" :class="{ rotated: isSidebarCollapsed }">
          <path fill-rule="evenodd" d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z" clip-rule="evenodd"/>
        </svg>
      </button>
    </div>

    <!-- 主导航区域 -->
    <div class="sidebar-nav">
      <!-- 新建任务 -->
      <button
        class="menu-item menu-item-primary"
        :class="{ active: activeMenu === 'new-task' }"
        data-tooltip="新建任务"
        @click="handleMenuClick('new-task')"
      >
        <svg class="menu-icon" viewBox="0 0 20 20" fill="currentColor">
          <path d="M10 5a1 1 0 011 1v3h3a1 1 0 110 2h-3v3a1 1 0 11-2 0v-3H6a1 1 0 110-2h3V6a1 1 0 011-1z"/>
        </svg>
        <span v-show="!isSidebarCollapsed" class="menu-text">新建任务</span>
        <kbd v-show="!isSidebarCollapsed" class="shortcut">Ctrl+K</kbd>
      </button>
    </div>

    <!-- 分组：项目 -->
    <div class="sidebar-group" :class="{ 'collapsed-group': isSidebarCollapsed }">
      <button
        class="group-header"
        :class="{ 'collapsed-header': isSidebarCollapsed }"
        data-tooltip="项目"
        @click="toggleLab"
      >
        <svg
          v-show="!isSidebarCollapsed"
          class="group-collapse-icon"
          :class="{ collapsed: isLabCollapsed }"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path fill-rule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clip-rule="evenodd"/>
        </svg>
        <svg
          v-show="isSidebarCollapsed"
          class="group-icon"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path fill-rule="evenodd" d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" clip-rule="evenodd"/>
        </svg>
        <span v-show="!isSidebarCollapsed" class="group-title">项目</span>
      </button>
      <transition name="slide">
        <div v-show="!isLabCollapsed && !isSidebarCollapsed" class="group-items">
          <div v-if="isLoadingProjects" class="history-loading">加载中...</div>
          <div v-else-if="projects.length === 0" class="history-empty">暂无项目</div>
          <!-- 每个项目是一个子分组 -->
          <div
            v-for="project in projects"
            :key="project.id"
            class="project-item"
          >
            <button
              class="project-header"
              @click.stop="toggleProjectCollapsed(project.id)"
            >
              <svg
                class="project-collapse-icon"
                :class="{ collapsed: projectCollapsedMap[project.id] }"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path fill-rule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clip-rule="evenodd"/>
              </svg>
              <svg class="project-folder-icon" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" clip-rule="evenodd"/>
              </svg>
              <span class="project-name">{{ project.name }}</span>
            </button>
            <transition name="slide">
              <div
                v-show="!projectCollapsedMap[project.id]"
                class="project-sessions"
              >
                <div
                  v-for="session in getProjectSessions(project.id)"
                  :key="session.id"
                  class="history-item"
                  :class="{ active: session.active }"
                  @click="handleSessionClick(session)"
                  @contextmenu.prevent="handleSessionContextMenu(session, $event)"
                >
                  <div class="history-content">
                    <input
                      v-if="editingSessionId === session.sessionId"
                      ref="editingInputRef"
                      v-model="editingTitle"
                      class="history-title-input"
                      type="text"
                      @blur="confirmRename"
                      @keydown.enter="confirmRename"
                      @keydown.esc="cancelRename"
                    />
                    <span v-else class="history-title-text">{{ session.title }}</span>
                    <div class="history-meta">
                      <span class="history-time">{{ session.time }}</span>
                      <button class="history-delete-btn" @click="handleDeleteSession(session.sessionId, session.title, $event)" title="删除会话">
                        <svg viewBox="0 0 20 20" fill="currentColor" width="14" height="14">
                          <path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd"/>
                        </svg>
                      </button>
                    </div>
                  </div>
                </div>
                <div v-if="getProjectSessions(project.id).length === 0" class="history-empty">
                  暂无会话
                </div>
              </div>
            </transition>
          </div>
        </div>
      </transition>
    </div>

    <!-- 任务记录区（可折叠） -->
    <div class="sidebar-history" :class="{ 'collapsed-history': isSidebarCollapsed }">
      <button
        class="history-header"
        :class="{ 'collapsed-header': isSidebarCollapsed }"
        data-tooltip="任务记录"
        @click="toggleHistory"
      >
        <svg
          v-show="!isSidebarCollapsed"
          class="collapse-icon"
          :class="{ collapsed: isHistoryCollapsed }"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path fill-rule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clip-rule="evenodd"/>
        </svg>
        <svg
          v-show="isSidebarCollapsed"
          class="history-icon"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clip-rule="evenodd"/>
        </svg>
        <span v-show="!isSidebarCollapsed" class="history-title">任务记录</span>
      </button>

      <transition name="slide">
        <div v-show="!isHistoryCollapsed && !isSidebarCollapsed" class="history-list">
          <div v-if="isLoadingSessions" class="history-loading">加载中...</div>
          <div v-else-if="unprojectedSessions.length === 0" class="history-empty">暂无会话记录</div>
          <div
            v-for="session in unprojectedSessions"
            :key="session.id"
            class="history-item"
            :class="{ active: session.active }"
            @click="handleSessionClick(session)"
            @contextmenu.prevent="handleSessionContextMenu(session, $event)"
          >
            <div class="history-content">
              <input
                v-if="editingSessionId === session.sessionId"
                ref="editingInputRef"
                v-model="editingTitle"
                class="history-title-input"
                type="text"
                @blur="confirmRename"
                @keydown.enter="confirmRename"
                @keydown.esc="cancelRename"
              />
              <span v-else class="history-title-text">{{ session.title }}</span>
              <div class="history-meta">
                <span class="history-time">{{ session.time }}</span>
                <button class="history-delete-btn" @click="handleDeleteSession(session.sessionId, session.title, $event)" title="删除会话">
                  <svg viewBox="0 0 20 20" fill="currentColor" width="14" height="14">
                    <path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd"/>
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      </transition>
    </div>

    <!-- 底部用户信息 -->
    <div ref="userMenuRef" class="sidebar-user" :class="{ 'user-menu-active': isUserMenuVisible }" @click="toggleUserMenu($event)">
      <div class="user-avatar">
        <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect width="40" height="40" rx="20" fill="var(--color-accent-light)"/>
          <path d="M20 20C23.866 20 27 16.866 27 13C27 9.13401 23.866 6 20 6C16.134 6 13 9.13401 13 13C13 16.866 16.134 20 20 20Z" fill="var(--color-accent)"/>
          <path d="M20 22C14.477 22 10 26.477 10 32V34H30V32C30 26.477 25.523 22 20 22Z" fill="var(--color-accent)"/>
        </svg>
      </div>
      <div v-show="!isSidebarCollapsed" class="user-info">
        <span class="user-name">{{ username }}</span>
      </div>
    </div>

    <!-- 用户菜单 - 使用 Teleport 移动到 body 层级，避免被父容器 overflow 裁剪 -->
    <Teleport to="body">
      <div v-show="isUserMenuVisible" class="user-menu" :class="{ 'is-collapsed': isSidebarCollapsed }" :style="menuPositionStyle">
        <div v-if="userRole === 'admin'" class="user-menu-item" @click.stop="handleAdminPanel">
          <svg class="menu-item-icon" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-6-3a2 2 0 11-4 0 2 2 0 014 0zm-2 4a5 5 0 00-4.546 2.916A5.986 5.986 0 0010 16a5.986 5.986 0 004.546-2.084A5 5 0 0010 11z" clip-rule="evenodd"/>
          </svg>
          <span>管理后台</span>
        </div>
        <div v-if="userRole !== 'admin'" class="user-menu-item" @click.stop="handleSetting">
          <svg class="menu-item-icon" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd"/>
          </svg>
          <span>设置</span>
        </div>
        <div class="user-menu-item" @click.stop="handleLogout">
          <svg class="menu-item-icon" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M3 3a1 1 0 00-1 1v12a1 1 0 102 0V4a1 1 0 00-1-1zm10.293 9.293a1 1 0 001.414 1.414l3-3a1 1 0 000-1.414l-3-3a1 1 0 10-1.414 1.414L14.586 9H7a1 1 0 100 2h7.586l-1.293 1.293z" clip-rule="evenodd"/>
          </svg>
          <span>退出登录</span>
        </div>
      </div>
    </Teleport>

    <!-- 用户设置对话框 -->
    <UserSettingsDialog
      v-model:visible="isSettingsDialogVisible"
      :role="userRole"
      :user-id="userId"
      :username="username"
      :initial-tab="settingsInitialTab"
      :sidebar-collapsed="isSidebarCollapsed"
      @username-updated="handleUsernameUpdated"
    />
    <!--
      2026-07-02 改动：移除 @open-subagent-drawer 透传。
      UserSettingsDialog 不再向外 emit open-subagent-drawer 事件。
      历史会话弹窗内的 subagent 卡片在弹窗内就地打开抽屉，不再冒泡到 App.vue。
      如未来需要再次冒泡，恢复本绑定即可。
    -->

    <!--
      删除会话确认弹窗 - 使用 Teleport 挂载到 body 层级
      原因：sidebar 容器设置 overflow: hidden，若不 Teleport 弹窗会被裁剪
    -->
    <Teleport to="body">
      <Transition name="delete-confirm">
        <div
          v-if="pendingDeleteId"
          class="delete-confirm-overlay"
          @click.self="cancelDeleteSession"
        >
          <div class="delete-confirm-container" role="alertdialog" aria-modal="true">
            <div class="delete-confirm-header">
              <svg class="delete-confirm-icon" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd"/>
              </svg>
              <h3 class="delete-confirm-title">确认删除会话</h3>
            </div>
            <div class="delete-confirm-body">
              即将移除「<strong>{{ pendingDeleteSessionTitle || '该会话' }}</strong>」，此操作无法撤销。
            </div>
            <div class="delete-confirm-footer">
              <button class="btn-cancel" @click="cancelDeleteSession">取消</button>
              <button class="btn-confirm" @click="confirmDeleteSession">确认删除</button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!--
      会话右键菜单 - 使用 Teleport 挂载到 body 层级
      原因：sidebar 容器设置 overflow: hidden，若不 Teleport 菜单会被裁剪
    -->
    <Teleport to="body">
      <div
        v-if="contextMenuVisible"
        class="session-context-menu"
        :style="{ top: `${contextMenuPosition.y}px`, left: `${contextMenuPosition.x}px` }"
        @click.stop
      >
        <div class="session-context-menu-item" @click="startRenameSession(contextMenuSession)">
          <svg class="menu-item-icon" viewBox="0 0 20 20" fill="currentColor">
            <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z"/>
          </svg>
          <span>重命名</span>
        </div>
        <div class="session-context-menu-item" @click="exportSession(contextMenuSession)">
          <svg class="menu-item-icon" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clip-rule="evenodd"/>
          </svg>
          <span>导出为 Markdown</span>
        </div>
      </div>
    </Teleport>
  </aside>
</template>

<style scoped>
.sidebar {
  width: var(--sidebar-width);
  height: 100%;
  background-color: var(--color-bg-primary);
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow: hidden;
  transition: width 0.3s ease;
}

/* 折叠状态：强制窄宽度 — 使用 !important 覆盖所有竞争规则 */
.sidebar.collapsed {
  width: 60px !important;
  min-width: 60px !important;
  max-width: 60px !important;
}

/* 折叠状态下的 Logo 区域 */
.sidebar.collapsed .sidebar-logo {
  justify-content: center;
  position: relative;
  cursor: pointer;
}

.sidebar.collapsed .sidebar-logo .logo-container {
  transition: opacity 0.2s ease;
}

.sidebar.collapsed .sidebar-logo .sidebar-toggle {
  position: absolute;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.sidebar.collapsed .sidebar-logo:hover .logo-container {
  opacity: 0;
}

.sidebar.collapsed .sidebar-logo:hover .sidebar-toggle {
  opacity: 1;
}

/* 折叠状态下的用户信息 */
.sidebar.collapsed .sidebar-user {
  justify-content: center;
  padding: 6px;
  margin-top: auto;
}

/* Logo 区域 */
.sidebar-logo {
  flex-shrink: 0;
  padding: 8px 12px 6px;
  border-bottom: 1px solid var(--color-border-light);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sidebar-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: var(--transition-colors), var(--transition-transform);
  flex-shrink: 0;

  &:hover {
    color: var(--color-text-primary);
    background-color: var(--color-bg-hover);
  }

  &:active {
    transform: scale(0.95);
  }
}

.toggle-icon {
  width: 16px;
  height: 16px;
  transition: transform 0.3s ease;

  &.rotated {
    transform: rotate(180deg);
  }
}

.logo-container {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-icon {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
}

.logo-text {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  letter-spacing: -0.02em;
}

/* 导航区域 */
.sidebar-nav {
  flex-shrink: 0;
  padding: 12px 8px;
}

/* 菜单项通用样式 */
.menu-item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-base);
  color: var(--color-text-secondary);
  text-align: left;
  position: relative;
  transition: var(--transition-colors), var(--transition-shadow);
  will-change: transform;

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

  &:active {
    transform: scale(var(--scale-active));
  }

  &.active {
    background-color: var(--color-accent-light);
    color: var(--color-accent);

    .menu-icon {
      color: var(--color-accent);
    }

    &::before {
      opacity: 0;
    }
  }

  /* Ensure content is above pseudo-element */
  > * {
    position: relative;
    z-index: 1;
  }
}

.menu-item-primary {
  background-color: var(--color-accent);
  color: white;

  .menu-icon {
    color: white;
    opacity: 1;
  }

  &:hover {
    background-color: var(--color-accent-hover);
    color: white;

    .menu-icon {
      color: white;
      opacity: 1;
    }
  }

  &.active {
    background-color: var(--color-accent-hover);
    color: white;

    .menu-icon {
      color: white;
      opacity: 1;
    }
  }
}

.menu-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  opacity: 0.8;
}

.menu-text {
  flex: 1;
  font-weight: var(--font-weight-medium);
}

.menu-item-sm {
  padding: 8px 12px;
  font-size: var(--font-size-sm);
  gap: 10px;

  .menu-icon {
    width: 18px;
    height: 18px;
  }
}

.shortcut {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px 6px;
  font-size: var(--font-size-xs);
  font-family: inherit;
  background-color: rgba(255, 255, 255, 0.2);
  border-radius: 4px;
  color: inherit;
  opacity: 0.8;

  .menu-item:not(.menu-item-primary) & {
    background-color: var(--color-bg-tertiary);
    color: var(--color-text-muted);
  }
}

/* 标签样式 */
.tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: var(--font-weight-semibold);
  border-radius: var(--radius-sm);
  letter-spacing: 0.02em;
  line-height: 1.2;
}

.tag-beta {
  background-color: var(--color-tag-beta);
  color: var(--color-tag-beta-text);
}

.tag-new {
  background-color: var(--color-tag-new);
  color: var(--color-tag-new-text);
}

.tag-free {
  background-color: var(--color-tag-free);
  color: var(--color-tag-free-text);
}

/* 分组样式 */
.sidebar-group {
  flex-shrink: 0;
  margin-top: 8px;
  padding: 0 8px;
}

.group-header {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
  width: 100%;
  padding: 8px 12px 6px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border);
  background-color: var(--color-bg-secondary);
  cursor: pointer;
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  text-align: left;
  letter-spacing: 0.02em;
  transition: var(--transition-colors), var(--transition-shadow);

  &:hover {
    color: var(--color-text-primary);
    background-color: var(--color-bg-hover);
    border-color: var(--color-text-muted);
  }

  &:active {
    transform: scale(var(--scale-active));
  }
}

.group-collapse-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  transition: transform var(--transition);

  &.collapsed {
    transform: rotate(-90deg);
  }
}

.group-title {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  color: inherit;
  letter-spacing: 0.02em;
}

.group-items {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

/* 历史记录区域 */
.sidebar-history {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--color-border-light);
  padding: 12px 8px 0;
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border);
  background-color: var(--color-bg-secondary);
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  text-align: left;
  letter-spacing: 0.02em;
  transition: var(--transition-colors), var(--transition-shadow);

  &:hover {
    color: var(--color-text-primary);
    background-color: var(--color-bg-hover);
    border-color: var(--color-text-muted);
  }

  &:active {
    transform: scale(var(--scale-active));
  }
}

.collapse-icon {
  width: 16px;
  height: 16px;
  transition: transform var(--transition);

  &.collapsed {
    transform: rotate(-90deg);
  }
}

.history-title {
  flex: 1;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  color: inherit;
  letter-spacing: 0.02em;
}

.history-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 4px;
  padding-bottom: 12px;

  &::-webkit-scrollbar {
    width: 4px;
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

.history-item {
  display: block;
  width: 100%;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  text-align: left;
  transition: var(--transition);

  &:hover {
    background-color: var(--color-bg-hover);
  }

  &.active {
    background-color: var(--color-accent-light);
  }
}

.history-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.history-title-text {
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  font-weight: var(--font-weight-medium);
  line-height: 1.3;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;

  .history-item.active & {
    color: var(--color-accent);
  }
}

.history-time {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.history-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}

.history-delete-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  opacity: 0;
  transition: opacity 0.15s ease, color 0.15s ease, background-color 0.15s ease;
  flex-shrink: 0;

  &:hover {
    color: var(--color-accent);
    background-color: var(--color-bg-hover);
  }
}

.history-item:hover .history-delete-btn {
  opacity: 1;
}

.history-loading,
.history-empty {
  padding: 16px 12px;
  text-align: center;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

/* 用户信息区域 */
.sidebar-user {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 12px;
  border-top: 1px solid var(--color-border-light);
  background-color: var(--color-bg-secondary);
  position: relative;
  cursor: pointer;
  transition: box-shadow 0.2s ease, background-color 0.2s ease;

  /* 用户菜单展开时的激活状态样式 */
  &.user-menu-active {
    box-shadow: 0 -4px 12px rgba(0, 0, 0, 0.1);
    background-color: var(--color-bg-hover);
  }
}

.user-avatar {
  width: 25px;
  height: 25px;
  border-radius: var(--radius-full);
  overflow: hidden;
  flex-shrink: 0;

  svg {
    width: 100%;
    height: 100%;
  }
}

.user-info {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
}

.user-name {
  font-size: calc(var(--font-size-base) * 0.9);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-user .tag {
  font-size: 8px;
  padding: 1px 6px;
}

/* 用户菜单样式 - 使用 fixed 定位，通过 Teleport 挂载到 body 层级 */
.user-menu {
  background-color: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  padding: 6px;
  z-index: 1000;
  animation: menuFadeIn 0.2s ease;
}

@keyframes menuFadeIn {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.user-menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: var(--transition-colors);
}

.user-menu-item:hover {
  background-color: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.user-menu-item:active {
  transform: scale(var(--scale-active));
}

.menu-item-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  opacity: 0.8;
}

/* 侧边栏折叠状态下的菜单适配 - 现在通过动态计算位置实现 */
.user-menu.is-collapsed {
  /* 折叠状态下的样式通过 menuPositionStyle 动态设置 */
}

/* 过渡动画 */
.slide-enter-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}

.slide-leave-active {
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}

.slide-enter-from,
.slide-leave-to {
  max-height: 0;
  opacity: 0;
  transform: translateY(-8px);
}

.slide-enter-to,
.slide-leave-from {
  max-height: 400px;
  opacity: 1;
  transform: translateY(0);
}

/* 折叠状态下的主导航区域 */
.sidebar.collapsed .sidebar-nav {
  display: flex !important;
  flex-direction: column !important;
  width: 100% !important;
  gap: 4px;
  padding: 12px 6px;
  min-height: 60px;
}

.sidebar.collapsed .sidebar-nav .menu-item {
  display: flex !important;
  justify-content: center !important;
  align-items: center !important;
  padding: 10px !important;
  min-width: 40px !important;
  min-height: 40px !important;
  width: 100% !important;
  gap: 0 !important;
}

.sidebar.collapsed .sidebar-nav .menu-icon {
  width: 20px !important;
  height: 20px !important;
  color: var(--color-text-secondary) !important;
  opacity: 1 !important;
  flex-shrink: 0;
}

.sidebar.collapsed .sidebar-nav .menu-item:hover .menu-icon {
  color: var(--color-text-primary) !important;
}

.sidebar.collapsed .sidebar-nav .menu-item.active .menu-icon {
  color: var(--color-accent) !important;
}

.sidebar.collapsed .sidebar-nav .menu-item.menu-item-primary {
  background-color: var(--color-accent) !important;
}

.sidebar.collapsed .sidebar-nav .menu-item.menu-item-primary .menu-icon {
  color: white !important;
  opacity: 1 !important;
}

/* 折叠状态下导航按钮 Tooltip 样式 */
.sidebar.collapsed .sidebar-nav .menu-item[data-tooltip] {
  position: relative;
}

/* Tooltip 内容 */
.sidebar.collapsed .sidebar-nav .menu-item[data-tooltip]::after {
  content: attr(data-tooltip);
  position: absolute;
  left: calc(100% + 12px);
  top: 50%;
  transform: translateY(-50%) scale(0.95);
  padding: 8px 12px;
  background-color: var(--color-bg-primary);
  color: var(--color-text-primary);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  white-space: nowrap;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.2s ease, transform 0.2s ease, visibility 0.2s;
  z-index: 1000;
  pointer-events: none;
}

/* Tooltip 箭头 */
.sidebar.collapsed .sidebar-nav .menu-item[data-tooltip]::before {
  content: '';
  position: absolute;
  left: calc(100% + 6px);
  top: 50%;
  transform: translateY(-50%);
  border: 6px solid transparent;
  border-right-color: var(--color-bg-primary);
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.2s ease, visibility 0.2s;
  z-index: 1001;
  pointer-events: none;
}

/* 悬停时显示 Tooltip */
.sidebar.collapsed .sidebar-nav .menu-item[data-tooltip]:hover::after,
.sidebar.collapsed .sidebar-nav .menu-item[data-tooltip]:hover::before {
  opacity: 1;
  visibility: visible;
}

.sidebar.collapsed .sidebar-nav .menu-item[data-tooltip]:hover::after {
  transform: translateY(-50%) scale(1);
}

/* 折叠状态下分组标题和历史标题的样式 */
.sidebar.collapsed .sidebar-group,
.sidebar.collapsed .sidebar-history {
  padding: 6px;
  margin-top: 4px;
}

.sidebar.collapsed .group-header,
.sidebar.collapsed .history-header {
  justify-content: center;
  padding: 10px;
  border: none;
  background-color: transparent;
}

.sidebar.collapsed .group-header:hover,
.sidebar.collapsed .history-header:hover {
  background-color: var(--color-bg-hover);
}

.sidebar.collapsed .group-icon,
.sidebar.collapsed .history-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  color: var(--color-text-secondary);
}

/* 折叠状态下分组标题和历史标题的 Tooltip 样式 */
.sidebar.collapsed .group-header[data-tooltip],
.sidebar.collapsed .history-header[data-tooltip] {
  position: relative;
}

/* Tooltip 内容 */
.sidebar.collapsed .group-header[data-tooltip]::after,
.sidebar.collapsed .history-header[data-tooltip]::after {
  content: attr(data-tooltip);
  position: absolute;
  left: calc(100% + 12px);
  top: 50%;
  transform: translateY(-50%) scale(0.95);
  padding: 8px 12px;
  background-color: var(--color-bg-primary);
  color: var(--color-text-primary);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  white-space: nowrap;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.2s ease, transform 0.2s ease, visibility 0.2s;
  z-index: 1000;
  pointer-events: none;
}

/* Tooltip 箭头 */
.sidebar.collapsed .group-header[data-tooltip]::before,
.sidebar.collapsed .history-header[data-tooltip]::before {
  content: '';
  position: absolute;
  left: calc(100% + 6px);
  top: 50%;
  transform: translateY(-50%);
  border: 6px solid transparent;
  border-right-color: var(--color-bg-primary);
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.2s ease, visibility 0.2s;
  z-index: 1001;
  pointer-events: none;
}

/* 悬停时显示 Tooltip */
.sidebar.collapsed .group-header[data-tooltip]:hover::after,
.sidebar.collapsed .group-header[data-tooltip]:hover::before,
.sidebar.collapsed .history-header[data-tooltip]:hover::after,
.sidebar.collapsed .history-header[data-tooltip]:hover::before {
  opacity: 1;
  visibility: visible;
}

.sidebar.collapsed .group-header[data-tooltip]:hover::after,
.sidebar.collapsed .history-header[data-tooltip]:hover::after {
  transform: translateY(-50%) scale(1);
}

/* =============================================
   删除会话确认弹窗（应用内，替代浏览器原生 confirm）
   - 通过 Teleport 挂载到 body 层级，scoped style 仍能作用（Vue 3 保留 scope id）
   - 不再出现 "localhost:5173 显示" 这种系统前缀
   ============================================= */
.delete-confirm-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal, 300);
}

.delete-confirm-container {
  background-color: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  width: 360px;
  max-width: calc(100vw - 32px);
  padding: 20px 24px;
  font-family: var(--font-family);
}

.delete-confirm-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.delete-confirm-icon {
  width: 20px;
  height: 20px;
  color: var(--color-error);
  flex-shrink: 0;
}

.delete-confirm-title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  line-height: var(--line-height-tight);
}

.delete-confirm-body {
  font-size: var(--font-size-base);
  line-height: var(--line-height-relaxed);
  color: var(--color-text-secondary);
  margin-bottom: 20px;

  & strong {
    color: var(--color-text-primary);
    font-weight: var(--font-weight-medium);
  }
}

.delete-confirm-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.btn-cancel,
.btn-confirm {
  font-family: inherit;
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  padding: 8px 16px;
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  cursor: pointer;
  transition: var(--transition-colors);

  &:active {
    transform: scale(var(--scale-active));
  }
}

.btn-cancel {
  background-color: var(--color-bg-primary);
  border-color: var(--color-border);
  color: var(--color-text-secondary);

  &:hover {
    background-color: var(--color-bg-hover);
    color: var(--color-text-primary);
  }
}

.btn-confirm {
  background-color: var(--color-error);
  color: var(--color-text-inverse);

  &:hover {
    background-color: #DC2626;
  }
}

/* 过渡动画：与 FileManagerModal 的 modal-* 同款 */
.delete-confirm-enter-active,
.delete-confirm-leave-active {
  transition: opacity 0.2s ease;
}

.delete-confirm-enter-active .delete-confirm-container,
.delete-confirm-leave-active .delete-confirm-container {
  transition: transform 0.2s ease, opacity 0.2s ease;
}

.delete-confirm-enter-from,
.delete-confirm-leave-to {
  opacity: 0;
}

.delete-confirm-enter-from .delete-confirm-container,
.delete-confirm-leave-to .delete-confirm-container {
  transform: scale(0.96);
  opacity: 0;
}

/* =============================================
   项目分组样式
   ============================================= */
.project-item {
  display: flex;
  flex-direction: column;
}

.project-header {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
  width: 100%;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  background-color: transparent;
  cursor: pointer;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  text-align: left;
  transition: var(--transition-colors), var(--transition-shadow);

  &:hover {
    color: var(--color-text-primary);
    background-color: var(--color-bg-hover);
  }

  &:active {
    transform: scale(var(--scale-active));
  }
}

.project-collapse-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  transition: transform var(--transition);

  &.collapsed {
    transform: rotate(-90deg);
  }
}

.project-folder-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  color: var(--color-text-muted);
}

.project-name {
  flex: 1;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: inherit;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-sessions {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-left: 20px;
}

.project-sessions .history-item {
  padding: 8px 10px;
}

/* =============================================
   会话右键菜单
   - 通过 Teleport 挂载到 body，避免 sidebar overflow:hidden 裁剪
   ============================================= */
.session-context-menu {
  position: fixed;
  z-index: 1000;
  min-width: 160px;
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  padding: 6px;
  animation: menuFadeIn 0.15s ease;
}

.session-context-menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: var(--transition-colors);
}

.session-context-menu-item:hover {
  background-color: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.session-context-menu-item:active {
  transform: scale(var(--scale-active));
}

/* 行内重命名输入框 */
.history-title-input {
  width: 100%;
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  background: transparent;
  border: 1px solid var(--color-accent);
  border-radius: var(--radius-sm);
  padding: 2px 6px;
  outline: none;
}

.history-title-input:focus {
  background-color: var(--color-bg-secondary);
}
</style>
