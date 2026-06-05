<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { validateToken, refreshToken, logout, clearAuth } from './utils/api.js'
import { redirectToLogin } from './utils/auth.js'
import LoginView from './views/LoginView.vue'
import RegisterView from './views/RegisterView.vue'

/**
 * 导航栏高度（像素）
 */
const NAV_HEIGHT = 52

/**
 * 登录状态标识
 */
const isLoggedIn = ref(false)

/**
 * 未登录态下的视图类型：'login' | 'register'
 * 用于在门户页内切换登录与注册视图，登录成功后会切换为已登录态
 */
const authView = ref('login')

/**
 * 当前登录用户信息
 * @type {import('vue').Ref<{username: string, role: string}>}
 */
const currentUser = ref({ username: '', role: '' })

/**
 * 当前选中的导航项
 */
const activeNav = ref('规则库')

/**
 * 用户下拉菜单是否可见
 */
const isUserMenuVisible = ref(false)

/**
 * 用户菜单触发器 DOM 引用
 */
const userMenuTriggerRef = ref(null)

/**
 * 导航项列表
 */
const navItems = ['智能选址', '智能预检', '规则库']

/**
 * 角色代码映射到中文角色名称
 * @param {string} role - 角色代码，如 'admin'、'user'
 * @returns {string} 中文角色名称
 */
function mapRoleName(role) {
  const roleMap = {
    admin: '系统管理员',
    user: '普通用户'
  }
  return roleMap[role] || role
}

/**
 * 将用户数据应用到当前组件状态
 * @param {Object} data - 后端返回的用户数据，包含 username 和 role
 */
function applyUserData(data) {
  localStorage.setItem('user_role', data.role)
  localStorage.setItem('username', data.username)
  currentUser.value = {
    username: data.username,
    role: data.role
  }
  isLoggedIn.value = true
}

/**
 * 三段式认证检查
 * 1. 先调用 validateToken 验证当前 Token 是否有效
 * 2. 若失败则调用 refreshToken 刷新令牌，然后再次 validateToken
 * 3. 若再次失败则调用 redirectToLogin 跳转到登录页（带 redirect 参数回到当前 portal URL）
 *    注意：不再主动 clearAuth()，保留本地 token 以便可能的下次重试。
 */
async function checkAuth() {
  const token = localStorage.getItem('auth_token')
  if (!token) {
    // 本地无 token：跳登录页（带 redirect = 当前 portal URL）
    redirectToLogin({ reason: 'portal_no_token' })
    return
  }
  try {
    const data = await validateToken()
    applyUserData(data)
  } catch {
    // validateToken 失败：尝试 refresh_token
    try {
      const newToken = await refreshToken()
      const data = await validateToken()
      localStorage.setItem('auth_token', newToken)
      applyUserData(data)
    } catch {
      // refresh 也失败：跳登录页（带 redirect = 当前 portal URL）
      redirectToLogin({ reason: 'portal_refresh_failed' })
    }
  }
}

/**
 * 切换用户下拉菜单的显示/隐藏状态
 * @param {MouseEvent} event - 鼠标事件对象，用于阻止事件冒泡
 */
function toggleUserMenu(event) {
  event.stopPropagation()
  isUserMenuVisible.value = !isUserMenuVisible.value
}

/**
 * 关闭用户下拉菜单
 */
function closeUserMenu() {
  isUserMenuVisible.value = false
}

/**
 * 处理点击页面外部关闭菜单
 * 参考 Sidebar.vue 的 handleClickOutside 逻辑
 * @param {MouseEvent} event - 鼠标事件对象
 */
function handleClickOutside(event) {
  const isClickOnTrigger = userMenuTriggerRef.value?.contains(event.target)
  const isClickOnMenu = event.target.closest('.user-dropdown-menu')
  if (!isClickOnTrigger && !isClickOnMenu) {
    closeUserMenu()
  }
}

/**
 * 处理键盘事件
 * 按 Escape 键时关闭用户下拉菜单
 * @param {KeyboardEvent} event - 键盘事件对象
 */
function handleKeydown(event) {
  if (event.key === 'Escape' && isUserMenuVisible.value) {
    closeUserMenu()
  }
}

/**
 * 处理退出登录
 * 调用 logout API，清除本地存储，最后刷新页面
 */
async function handleLogout() {
  closeUserMenu()
  await logout()
  isLoggedIn.value = false
  currentUser.value = { username: '', role: '' }
  localStorage.removeItem('user_id')
  window.location.reload()
}

/**
 * 处理 LoginView 的登录成功事件
 * 将认证信息写入 localStorage 并切换为已登录态
 * 注意：URL 中的 redirect 回跳由 LoginView 内部统一处理
 * @param {Object} data - 登录结果数据，包含 access_token、role、username、user_id
 */
function handleLoginSuccess(data) {
  if (data.access_token) {
    localStorage.setItem('auth_token', data.access_token)
  }
  if (data.role) {
    localStorage.setItem('user_role', data.role)
  }
  if (data.username) {
    localStorage.setItem('username', data.username)
  }
  if (data.user_id !== undefined && data.user_id !== null) {
    localStorage.setItem('user_id', String(data.user_id))
  }
  currentUser.value = {
    username: data.username || '',
    role: data.role || ''
  }
  isLoggedIn.value = true
  authView.value = 'login'
}

/**
 * 处理导航项切换
 * @param {string} item - 被点击的导航项名称
 */
function handleNavClick(item) {
  activeNav.value = item
}

onMounted(() => {
  checkAuth()
  document.addEventListener('click', handleClickOutside)
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <!-- 未登录：直接渲染登录页，顶部 nav 不显示 -->
  <LoginView
    v-if="!isLoggedIn && authView === 'login'"
    @login-success="handleLoginSuccess"
    @switch-to-register="authView = 'register'"
  />
  <RegisterView
    v-else-if="!isLoggedIn && authView === 'register'"
    @switch-to-login="authView = 'login'"
  />

  <!-- 已登录：显示导航栏 + 主内容区 -->
  <div v-else class="portal-wrapper">
    <!-- 顶部蓝色导航栏 -->
    <nav class="top-nav" :style="{ height: `${NAV_HEIGHT}px` }">
      <!-- 左侧：系统标题 -->
      <div class="nav-left">
        <span class="system-title">沈阳市自然资源和规划'一点通'</span>
      </div>

      <!-- 中间：导航项 -->
      <div class="nav-center">
        <button
          v-for="item in navItems"
          :key="item"
          class="nav-item"
          :class="{ active: activeNav === item }"
          @click="handleNavClick(item)"
        >
          {{ item }}
        </button>
      </div>

      <!-- 右侧：用户状态区 -->
      <div class="nav-right">
        <div ref="userMenuTriggerRef" class="user-info-trigger" @click="toggleUserMenu">
          <svg class="user-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z" />
          </svg>
          <span class="user-name-text">{{ currentUser.username }} {{ mapRoleName(currentUser.role) }}</span>
        </div>

        <!-- 用户下拉菜单 -->
        <Transition name="menu">
          <div v-show="isUserMenuVisible" class="user-dropdown-menu">
            <div class="dropdown-item" @click.stop="closeUserMenu">
              设置
            </div>
            <div class="dropdown-item logout-item" @click.stop="handleLogout">
              退出登录
            </div>
          </div>
        </Transition>
      </div>
    </nav>

    <!-- 主内容区 -->
    <main
      class="main-content"
      :style="{ marginTop: `${NAV_HEIGHT}px`, height: `calc(100vh - ${NAV_HEIGHT}px)` }"
    >
      <!-- 规则库：通过 iframe 加载知识库页面 -->
      <template v-if="activeNav === '规则库'">
        <iframe
          src="/knowledge.html"
          width="100%"
          height="100%"
          frameborder="0"
          title="规则库"
        ></iframe>
      </template>

      <!-- 智能选址 / 智能预检：占位提示 -->
      <template v-else>
        <div class="placeholder-wrap">
          <svg class="cloud-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M2.25 15a4.5 4.5 0 004.5 4.5H18a3.75 3.75 0 001.332-7.257 3 3 0 00-3.758-3.848 5.25 5.25 0 00-10.233 2.33A4.502 4.502 0 002.25 15z"
            />
          </svg>
          <p class="placeholder-text">功能开发中...</p>
        </div>
      </template>
    </main>
  </div>
</template>

<style scoped>
/* 全局重置：消除 body 与 #app 的默认边距和滚动条 */
:global(body) {
  margin: 0;
  padding: 0;
  overflow: hidden;
}

:global(#app) {
  margin: 0;
  padding: 0;
  overflow: hidden;
}

/* 门户外层容器 */
.portal-wrapper {
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* 顶部导航栏 */
.top-nav {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: linear-gradient(90deg, #1e40af 0%, #3b82f6 100%);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

/* 左侧标题区 */
.nav-left {
  flex-shrink: 0;
}

.system-title {
  color: #ffffff;
  font-weight: 600;
  font-size: 17px;
  white-space: nowrap;
  letter-spacing: 0.02em;
}

/* 中间导航区 */
.nav-center {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 8px;
}

.nav-item {
  padding: 6px 16px;
  font-size: 14px;
  color: #ffffff;
  background-color: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.2s ease;
  white-space: nowrap;
  /* 固定按钮宽度使"智能选址 / 智能预检 / 规则库"三个按钮视觉等宽；
     88px = 水平 padding 32px + 4 个中文字符约 56px，与 4 字按钮自然宽度一致 */
  width: 88px;
  text-align: center;        /* 宽度统一后文字居中对齐 */
  box-sizing: border-box;    /* 让 width 包含 padding，避免 content-box 下实际宽度溢出 */
}

.nav-item:hover {
  background-color: rgba(255, 255, 255, 0.15);
}

.nav-item.active {
  background-color: rgba(255, 255, 255, 0.2);
}

/* 右侧用户区 */
.nav-right {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  position: relative;
}

/* 已登录时的用户信息触发器 */
.user-info-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.2s ease;
  color: #ffffff;
  font-size: 14px;
  user-select: none;
  position: relative;
}

.user-info-trigger:hover {
  background-color: rgba(255, 255, 255, 0.15);
}

.user-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  opacity: 0.9;
}

.user-name-text {
  white-space: nowrap;
}

/* 用户下拉菜单 */
.user-dropdown-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  min-width: 140px;
  background-color: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  padding: 6px;
  z-index: 200;
  overflow: hidden;
}

.dropdown-item {
  padding: 10px 14px;
  font-size: 14px;
  color: #374151;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.15s ease;
  white-space: nowrap;
}

.dropdown-item:hover {
  background-color: #f3f4f6;
}

.logout-item {
  color: #ef4444;
}

.logout-item:hover {
  background-color: #fef2f2;
}

/* 菜单出现/消失的过渡动画 */
.menu-enter-active,
.menu-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.menu-enter-from,
.menu-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* 主内容区 */
.main-content {
  width: 100%;
  background-color: #f3f4f6;
  overflow: hidden;
}

.main-content iframe {
  display: block;
  width: 100%;
  height: 100%;
  border: none;
}

/* 占位提示 */
.placeholder-wrap {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
}

.cloud-icon {
  width: 64px;
  height: 64px;
  color: #d1d5db;
}

.placeholder-text {
  font-size: 16px;
  color: #9ca3af;
  margin: 0;
}
</style>
