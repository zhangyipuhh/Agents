<script setup>
/**
 * UserSettingsDialog - 用户设置对话框组件
 * 支持分层面板导航：
 * - 普通用户（role='user'）：仅显示个人设置
 * - 管理员（role='admin'）：显示个人设置、用户管理、在线监控、会话查询
 */

import { ref, watch, computed, nextTick } from 'vue'
import {
  updatePassword,
  updateUsername,
  fetchUserList,
  deleteUser,
  kickUser,
  fetchOnlineUsers,
  fetchUserSessions,
  adminDeleteSession,
  searchSessionsByUsername
} from '../utils/api.js'

/**
 * 组件属性定义
 * @prop {boolean} visible - 对话框是否可见，支持 v-model:visible
 * @prop {string} role - 用户角色，'user' 或 'admin'
 * @prop {number} userId - 用户ID
 * @prop {string} username - 当前用户名
 * @prop {string} initialTab - 默认打开的标签页
 */
const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  role: {
    type: String,
    default: 'user',
    validator: (value) => ['user', 'admin'].includes(value)
  },
  userId: {
    type: Number,
    default: null
  },
  username: {
    type: String,
    default: ''
  },
  initialTab: {
    type: String,
    default: 'profile'
  },
  sidebarCollapsed: {
    type: Boolean,
    default: false
  }
})

/**
 * 组件事件定义
 * @event update:visible - 更新对话框可见状态，用于 v-model:visible
 * @event username-updated - 用户名修改成功时触发，参数: { username: string }
 */
const emit = defineEmits(['update:visible', 'username-updated'])

/* ---- 导航与视图状态 ---- */

/** @type {import('vue').Ref<string>} 当前激活的标签页 */
const activeTab = ref('profile')

/** @type {import('vue').Ref<boolean>} 是否管理员角色 */
const isAdmin = computed(() => props.role === 'admin')

/** 导航项列表 */
const navItems = computed(() => {
  const items = [{ id: 'profile', label: '个人设置', icon: 'M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z' }]
  if (isAdmin.value) {
    items.push(
      { id: 'user-management', label: '用户管理', icon: 'M9 6a3 3 0 11-6 0 3 3 0 016 0zM17 6a3 3 0 11-6 0 3 3 0 016 0zM12.93 17c.046-.327.07-.66.07-1a6.97 6.97 0 00-1.5-4.33A5 5 0 0119 16v1h-6.07zM6 11a5 5 0 015 5v1H1v-1a5 5 0 015-5z' },
      { id: 'online-monitor', label: '在线监控', icon: 'M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z' },
      { id: 'session-query', label: '会话查询', icon: 'M9 2a1 1 0 000 2h2a1 1 0 100-2H9zM4 5a2 2 0 012-2 3 3 0 003 3h2a3 3 0 003-3 2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2V5zm3 4a1 1 0 000 2h.01a1 1 0 100-2H7zm3 0a1 1 0 000 2h3a1 1 0 100-2h-3zm-3 4a1 1 0 100 2h.01a1 1 0 100-2H7zm3 0a1 1 0 100 2h3a1 1 0 100-2h-3z' }
    )
  }
  return items
})

/* ---- 修改密码相关状态 ---- */

const oldPassword = ref('')
const newPassword = ref('')
const confirmNewPassword = ref('')
const passwordError = ref('')
const passwordSuccess = ref('')

/* ---- 修改用户名相关状态 ---- */

const newUsername = ref('')
const usernameError = ref('')
const usernameSuccess = ref('')

/* ---- Admin 管理相关状态 ---- */

const loading = ref(false)
const userList = ref([])
const onlineUsers = ref([])
const searchUsername = ref('')
const sessionSearchResults = ref([])

/* ---- 通用状态 ---- */

const isSaving = ref(false)

/**
 * 切换标签页
 * @param {string} tabId - 标签页 ID
 */
function switchTab(tabId) {
  activeTab.value = tabId
  if (tabId === 'user-management') {
    loadUserList()
  } else if (tabId === 'online-monitor') {
    loadOnlineUsers()
  }
}

/**
 * 关闭对话框
 */
function closeDialog() {
  resetForms()
  emit('update:visible', false)
  nextTick(() => {
    activeTab.value = 'profile'
  })
}

/**
 * 重置所有表单状态
 */
function resetForms() {
  oldPassword.value = ''
  newPassword.value = ''
  confirmNewPassword.value = ''
  newUsername.value = ''
  passwordError.value = ''
  passwordSuccess.value = ''
  usernameError.value = ''
  usernameSuccess.value = ''
  searchUsername.value = ''
  sessionSearchResults.value = []
}

/* ---- 个人设置逻辑 ---- */

function hasPasswordIntent() {
  return !!(oldPassword.value || newPassword.value || confirmNewPassword.value)
}

function hasUsernameIntent() {
  return !!(newUsername.value.trim())
}

function validatePasswordForm() {
  if (!oldPassword.value) {
    passwordError.value = '请输入旧密码'
    return false
  }
  if (!newPassword.value) {
    passwordError.value = '请输入新密码'
    return false
  }
  if (newPassword.value.length < 6) {
    passwordError.value = '新密码至少6个字符'
    return false
  }
  if (newPassword.value !== confirmNewPassword.value) {
    passwordError.value = '两次输入的新密码不一致'
    return false
  }
  if (oldPassword.value === newPassword.value) {
    passwordError.value = '新密码不能与旧密码相同'
    return false
  }
  return true
}

function validateUsernameForm() {
  if (!newUsername.value.trim()) {
    usernameError.value = '请输入新用户名'
    return false
  }
  if (newUsername.value.trim().length < 3) {
    usernameError.value = '用户名至少3个字符'
    return false
  }
  if (newUsername.value.trim() === props.username) {
    usernameError.value = '新用户名不能与当前用户名相同'
    return false
  }
  return true
}

async function handleSave() {
  passwordError.value = ''
  passwordSuccess.value = ''
  usernameError.value = ''
  usernameSuccess.value = ''

  const passwordIntent = hasPasswordIntent()
  const usernameIntent = hasUsernameIntent()

  if (!passwordIntent && !usernameIntent) {
    passwordError.value = '请至少填写一项修改内容'
    return
  }

  if (passwordIntent && !validatePasswordForm()) return
  if (usernameIntent && !validateUsernameForm()) return

  const currentUserId = props.userId || parseInt(localStorage.getItem('user_id'), 10)
  if (!currentUserId) {
    passwordError.value = '用户ID无效，请重新登录'
    return
  }

  isSaving.value = true
  try {
    const promises = []

    if (passwordIntent) {
      promises.push(
        (async () => {
          try {
            await updatePassword(currentUserId, oldPassword.value, newPassword.value)
            passwordSuccess.value = '密码修改成功'
            oldPassword.value = ''
            newPassword.value = ''
            confirmNewPassword.value = ''
          } catch (err) {
            passwordError.value = err.message || '修改密码失败'
          }
        })()
      )
    }

    if (usernameIntent) {
      promises.push(
        (async () => {
          try {
            const data = await updateUsername(currentUserId, newUsername.value.trim())
            usernameSuccess.value = '用户名修改成功'
            emit('username-updated', { username: data.new_username || newUsername.value.trim() })
            localStorage.setItem('username', data.new_username || newUsername.value.trim())
            newUsername.value = ''
          } catch (err) {
            usernameError.value = err.message || '修改用户名失败'
          }
        })()
      )
    }

    await Promise.all(promises)
  } finally {
    isSaving.value = false
  }
}

/* ---- Admin 用户管理逻辑 ---- */

async function loadUserList() {
  loading.value = true
  try {
    const data = await fetchUserList()
    userList.value = data || []
  } catch (err) {
    console.error('加载用户列表失败:', err)
    alert(err.message || '加载用户列表失败')
  } finally {
    loading.value = false
  }
}

async function handleDeleteUser(userId) {
  if (!confirm('确定删除该用户？此操作不可恢复。')) return
  try {
    await deleteUser(userId)
    alert('删除成功')
    loadUserList()
  } catch (err) {
    alert(err.message || '删除失败')
  }
}

async function handleKickUser(userId, username) {
  if (!confirm(`确定强制用户 "${username}" 下线？该用户需要重新登录。`)) return
  try {
    const result = await kickUser(userId)
    alert(result.message || '已强制下线')
    loadUserList()
    if (activeTab.value === 'online-monitor') {
      loadOnlineUsers()
    }
  } catch (err) {
    alert(err.message || '强制下线失败')
  }
}

/* ---- Admin 在线监控逻辑 ---- */

async function loadOnlineUsers() {
  loading.value = true
  try {
    const data = await fetchOnlineUsers()
    onlineUsers.value = data.online_users || []
  } catch (err) {
    console.error('加载在线用户失败:', err)
    alert(err.message || '加载在线用户失败')
  } finally {
    loading.value = false
  }
}

/* ---- Admin 会话查询逻辑 ---- */

async function handleSearchSessions() {
  if (!searchUsername.value.trim()) {
    alert('请输入用户名')
    return
  }
  loading.value = true
  try {
    const data = await searchSessionsByUsername(searchUsername.value.trim())
    sessionSearchResults.value = data.sessions || []
  } catch (err) {
    console.error('搜索会话失败:', err)
    alert(err.message || '搜索会话失败')
  } finally {
    loading.value = false
  }
}

async function handleAdminDeleteSession(sessionId) {
  if (!confirm(`确定删除会话 "${sessionId}"？此操作不可恢复。`)) return
  try {
    await adminDeleteSession(sessionId)
    alert('会话删除成功')
    if (searchUsername.value.trim()) {
      handleSearchSessions()
    }
  } catch (err) {
    alert(err.message || '删除会话失败')
  }
}

function formatTime(dateStr) {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now - date
  const diffMins = Math.floor(diffMs / 60000)
  if (diffMins < 1) return '刚刚'
  if (diffMins < 60) return `${diffMins}分钟前`
  const diffHours = Math.floor(diffMs / 3600000)
  if (diffHours < 24) return `${diffHours}小时前`
  return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}`
}

function handleOverlayClick(event) {
  if (event.target === event.currentTarget) {
    closeDialog()
  }
}

watch(() => props.visible, (newVal) => {
  if (newVal) {
    resetForms()
    activeTab.value = props.initialTab || 'profile'
    if (activeTab.value === 'user-management') {
      loadUserList()
    } else if (activeTab.value === 'online-monitor') {
      loadOnlineUsers()
    }
  }
})
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="visible" class="dialog-overlay" @click="handleOverlayClick">
        <div class="dialog-card" :class="{ 'sidebar-collapsed': sidebarCollapsed }" @click.stop>
          <!-- 对话框头部 -->
          <div class="dialog-header">
            <h2 class="dialog-title">{{ isAdmin ? '用户设置与管理' : '用户设置' }}</h2>
            <button class="dialog-close" @click="closeDialog" aria-label="关闭">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M15 5L5 15M5 5l10 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </button>
          </div>

          <!-- 对话框内容 -->
          <div class="dialog-body" :class="{ 'dialog-body-horizontal': isAdmin }">
            <!-- 左侧导航（admin 显示） -->
            <div v-if="isAdmin" class="dialog-nav">
              <button
                v-for="item in navItems"
                :key="item.id"
                class="nav-item"
                :class="{ active: activeTab === item.id }"
                @click="switchTab(item.id)"
              >
                <svg class="nav-icon" viewBox="0 0 20 20" fill="currentColor">
                  <path :d="item.icon" />
                </svg>
                <span class="nav-label">{{ item.label }}</span>
              </button>
            </div>

            <!-- 右侧内容区域 -->
            <div class="dialog-content">
              <!-- 个人设置 -->
              <div v-show="activeTab === 'profile'">
                <form @submit.prevent="handleSave">
                  <div class="settings-section">
                    <h3 class="section-title">修改密码</h3>
                    <div class="form-group">
                      <label class="form-label" for="settings-old-password">旧密码</label>
                      <input
                        id="settings-old-password"
                        v-model="oldPassword"
                        type="password"
                        class="form-input"
                        placeholder="请输入旧密码"
                        autocomplete="current-password"
                        :disabled="isSaving"
                      />
                    </div>
                    <div class="form-group">
                      <label class="form-label" for="settings-new-password">新密码</label>
                      <input
                        id="settings-new-password"
                        v-model="newPassword"
                        type="password"
                        class="form-input"
                        placeholder="请输入新密码（至少6个字符）"
                        autocomplete="new-password"
                        :disabled="isSaving"
                      />
                    </div>
                    <div class="form-group">
                      <label class="form-label" for="settings-confirm-new-password">确认新密码</label>
                      <input
                        id="settings-confirm-new-password"
                        v-model="confirmNewPassword"
                        type="password"
                        class="form-input"
                        placeholder="请再次输入新密码"
                        autocomplete="new-password"
                        :disabled="isSaving"
                      />
                    </div>
                    <div v-if="passwordError" class="error-message">{{ passwordError }}</div>
                    <div v-if="passwordSuccess" class="success-message">{{ passwordSuccess }}</div>
                  </div>

                  <div class="section-divider"></div>

                  <div class="settings-section">
                    <h3 class="section-title">修改用户名</h3>
                    <p class="section-desc">当前用户名：<strong>{{ username }}</strong></p>
                    <div class="form-group">
                      <label class="form-label" for="settings-new-username">新用户名</label>
                      <input
                        id="settings-new-username"
                        v-model="newUsername"
                        type="text"
                        class="form-input"
                        placeholder="请输入新用户名（至少3个字符）"
                        autocomplete="off"
                        :disabled="isSaving"
                      />
                    </div>
                    <div v-if="usernameError" class="error-message">{{ usernameError }}</div>
                    <div v-if="usernameSuccess" class="success-message">{{ usernameSuccess }}</div>
                  </div>

                  <button type="submit" class="action-button" :disabled="isSaving">
                    <span v-if="isSaving" class="button-loading">
                      <span class="loading-spinner"></span>
                      保存中...
                    </span>
                    <span v-else>保存设置</span>
                  </button>
                </form>
              </div>

              <!-- 用户管理（admin） -->
              <div v-show="activeTab === 'user-management'">
                <div class="admin-section">
                  <div class="admin-header">
                    <h3 class="section-title">用户管理</h3>
                    <span class="admin-count">共 {{ userList.length }} 位用户</span>
                  </div>
                  <div v-if="loading" class="admin-loading">加载中...</div>
                  <div v-else-if="userList.length === 0" class="admin-empty">暂无用户数据</div>
                  <table v-else class="admin-table">
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>用户名</th>
                        <th>角色</th>
                        <th>创建时间</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="user in userList" :key="user.id">
                        <td>{{ user.id }}</td>
                        <td>{{ user.username }}</td>
                        <td>
                          <span class="role-tag" :class="user.role">{{ user.role }}</span>
                        </td>
                        <td>{{ formatTime(user.created_at) }}</td>
                        <td>
                          <button class="table-btn btn-kick" @click="handleKickUser(user.id, user.username)">强制下线</button>
                          <button class="table-btn btn-danger" @click="handleDeleteUser(user.id)">删除</button>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <!-- 在线监控（admin） -->
              <div v-show="activeTab === 'online-monitor'">
                <div class="admin-section">
                  <div class="admin-header">
                    <h3 class="section-title">在线监控</h3>
                    <button class="table-btn btn-refresh" @click="loadOnlineUsers">刷新</button>
                  </div>
                  <div v-if="loading" class="admin-loading">加载中...</div>
                  <div v-else-if="onlineUsers.length === 0" class="admin-empty">当前无在线用户</div>
                  <table v-else class="admin-table">
                    <thead>
                      <tr>
                        <th>用户ID</th>
                        <th>用户名</th>
                        <th>会话数</th>
                        <th>最后活跃</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="user in onlineUsers" :key="user.user_id">
                        <td>{{ user.user_id }}</td>
                        <td>{{ user.username }}</td>
                        <td>{{ user.session_count }}</td>
                        <td>{{ formatTime(user.last_active_at) }}</td>
                        <td>
                          <button class="table-btn btn-kick" @click="handleKickUser(user.user_id, user.username)">强制下线</button>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <!-- 会话查询（admin） -->
              <div v-show="activeTab === 'session-query'">
                <div class="admin-section">
                  <div class="admin-header">
                    <h3 class="section-title">会话查询</h3>
                  </div>
                  <div class="search-bar">
                    <input
                      v-model="searchUsername"
                      type="text"
                      class="form-input search-input"
                      placeholder="输入用户名搜索会话"
                      @keyup.enter="handleSearchSessions"
                    />
                    <button class="action-button search-btn" @click="handleSearchSessions" :disabled="loading">
                      搜索
                    </button>
                  </div>
                  <div v-if="loading" class="admin-loading">加载中...</div>
                  <div v-else-if="sessionSearchResults.length === 0 && searchUsername" class="admin-empty">未找到匹配会话</div>
                  <table v-else-if="sessionSearchResults.length > 0" class="admin-table">
                    <thead>
                      <tr>
                        <th>会话ID</th>
                        <th>用户名</th>
                        <th>标题</th>
                        <th>最后活跃</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="session in sessionSearchResults" :key="session.session_id">
                        <td class="session-id" :title="session.session_id">{{ session.session_id.slice(0, 8) }}...</td>
                        <td>{{ session.username }}</td>
                        <td>{{ session.title || '新对话' }}</td>
                        <td>{{ formatTime(session.last_active_at) }}</td>
                        <td>
                          <button class="table-btn btn-danger" @click="handleAdminDeleteSession(session.session_id)">删除</button>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* 遮罩层 */
.dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  background-color: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
}

/* 对话框卡片 */
.dialog-card {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  left: var(--sidebar-width);
  width: auto;
  height: auto;
  background-color: var(--color-bg-primary);
  border-radius: 0;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 侧边栏折叠时调整面板位置 */
.dialog-card.sidebar-collapsed {
  left: 60px;
}

/* 对话框头部 */
.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-lg) var(--space-xl);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}

.dialog-title {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.dialog-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  transition: var(--transition-colors), var(--transition-transform);
}

.dialog-close:hover {
  background-color: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.dialog-close:active {
  transform: scale(var(--scale-active));
}

/* 对话框内容区域 */
.dialog-body {
  padding: var(--space-xl);
  overflow-y: auto;
  flex: 1;
}

.dialog-body-horizontal {
  display: flex;
  padding: 0;
  overflow: hidden;
}

/* 左侧导航 */
.dialog-nav {
  width: 160px;
  flex-shrink: 0;
  border-right: 1px solid var(--color-border);
  padding: var(--space-lg) 0;
  background-color: var(--color-bg-secondary);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  text-align: left;
  transition: var(--transition-colors);
  border-left: 3px solid transparent;
}

.nav-item:hover {
  background-color: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.nav-item.active {
  background-color: var(--color-accent-light);
  color: var(--color-accent);
  border-left-color: var(--color-accent);
}

.nav-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}

.nav-label {
  font-weight: var(--font-weight-medium);
}

/* 右侧内容 */
.dialog-content {
  flex: 1;
  padding: var(--space-xl);
  overflow-y: auto;
  min-width: 0;
}

/* 设置分区 */
.settings-section {
  margin-bottom: var(--space-lg);
}

.settings-section:last-child {
  margin-bottom: 0;
}

.section-title {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin-bottom: var(--space-base);
}

.section-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-base);
}

.section-desc strong {
  color: var(--color-accent);
  font-weight: var(--font-weight-medium);
}

.section-divider {
  height: 1px;
  background-color: var(--color-border);
  margin: var(--space-lg) 0;
}

.form-group {
  margin-bottom: var(--space-base);
}

.form-label {
  display: block;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  margin-bottom: var(--space-xs);
}

.form-input {
  width: 100%;
  height: 40px;
  padding: 0 var(--space-base);
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  background-color: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  transition: var(--transition-colors), var(--transition-shadow);
}

.form-input:hover {
  border-color: var(--color-text-muted);
}

.form-input:focus {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px var(--color-accent-light);
  background-color: var(--color-bg-primary);
  outline: none;
}

.form-input::placeholder {
  color: var(--color-text-muted);
}

.form-input:disabled {
  opacity: var(--opacity-disabled);
  cursor: not-allowed;
}

.error-message {
  padding: var(--space-sm) var(--space-base);
  margin-bottom: var(--space-base);
  font-size: var(--font-size-sm);
  color: var(--color-error);
  background-color: #FEF2F2;
  border-radius: var(--radius-sm);
  border: 1px solid #FECACA;
  line-height: var(--line-height-normal);
}

.success-message {
  padding: var(--space-sm) var(--space-base);
  margin-bottom: var(--space-base);
  font-size: var(--font-size-sm);
  color: var(--color-success);
  background-color: #ECFDF5;
  border-radius: var(--radius-sm);
  border: 1px solid #A7F3D0;
  line-height: var(--line-height-normal);
}

.action-button {
  width: 100%;
  height: 40px;
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-inverse);
  background-color: var(--color-accent);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: var(--transition-colors), var(--transition-transform);
  border: none;
}

.action-button:hover:not(:disabled) {
  background-color: var(--color-accent-hover);
  transform: scale(var(--scale-hover-button));
}

.action-button:active:not(:disabled) {
  transform: scale(var(--scale-active));
}

.action-button:disabled {
  opacity: var(--opacity-disabled);
  cursor: not-allowed;
}

.button-loading {
  display: inline-flex;
  align-items: center;
  gap: var(--space-sm);
}

.loading-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

/* Admin 管理区域样式 */
.admin-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-base);
}

.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.admin-count {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.admin-loading,
.admin-empty {
  padding: var(--space-xl);
  text-align: center;
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.admin-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.admin-table th,
.admin-table td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid var(--color-border);
}

.admin-table th {
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  background-color: var(--color-bg-secondary);
}

.admin-table td {
  color: var(--color-text-secondary);
}

.admin-table tr:hover td {
  background-color: var(--color-bg-hover);
}

.role-tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: var(--font-weight-semibold);
  border-radius: var(--radius-sm);
}

.role-tag.admin {
  background-color: #FEF3C7;
  color: #D97706;
}

.role-tag.user {
  background-color: #E0E7FF;
  color: #4F46E5;
}

.table-btn {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: var(--font-weight-medium);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: var(--transition-colors);
  border: none;
  margin-right: 6px;
}

.table-btn:last-child {
  margin-right: 0;
}

.btn-kick {
  background-color: #FEF3C7;
  color: #B45309;
}

.btn-kick:hover {
  background-color: #FDE68A;
}

.btn-danger {
  background-color: #FEE2E2;
  color: #DC2626;
}

.btn-danger:hover {
  background-color: #FECACA;
}

.btn-refresh {
  background-color: var(--color-accent-light);
  color: var(--color-accent);
}

.btn-refresh:hover {
  background-color: #C7D2FE;
}

.search-bar {
  display: flex;
  gap: var(--space-base);
  align-items: center;
}

.search-input {
  flex: 1;
}

.search-btn {
  width: auto;
  padding: 0 20px;
}

.session-id {
  font-family: monospace;
  font-size: 11px;
}

/* 对话框过渡动画 */
.dialog-fade-enter-active {
  transition: opacity 0.25s ease;
}

.dialog-fade-leave-active {
  transition: opacity 0.2s ease;
}

.dialog-fade-enter-from,
.dialog-fade-leave-to {
  opacity: 0;
}

.dialog-fade-enter-active .dialog-card {
  animation: dialog-scale-in 0.25s ease;
}

.dialog-fade-leave-active .dialog-card {
  animation: dialog-scale-out 0.2s ease;
}

@keyframes dialog-scale-in {
  from {
    transform: scale(0.95);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}

@keyframes dialog-scale-out {
  from {
    transform: scale(1);
    opacity: 1;
  }
  to {
    transform: scale(0.95);
    opacity: 0;
  }
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>