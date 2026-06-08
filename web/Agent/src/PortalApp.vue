<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { validateToken, refreshToken, logout, clearAuth, issuePortalRefreshToken } from './utils/api.js'
import { redirectToLogin } from './utils/auth.js'
import { getNavItems, appConfig } from './config/portal.js'

/**
 * 导航栏高度（像素）
 */
const NAV_HEIGHT = 52

/**
 * 登录状态标识
 */
const isLoggedIn = ref(false)

/**
 * 认证状态检查是否就绪；用于在 checkAuth 完成前显示 loading 占位，
 * 避免因异步资源加载造成"页面内容闪烁两次"的视觉问题
 */
const authReady = ref(false)

/**
 * 当前登录用户信息
 * @type {import('vue').Ref<{username: string, role: string}>}
 */
const currentUser = ref({ username: '', role: '' })

/**
 * 导航项列表（从 VITE_PORTAL_NAV_CONFIG 解析，缺省回退默认三项）
 */
const navItems = getNavItems()

/**
 * 当前选中的导航项 key（默认第一项；iframe 类型优先于 placeholder）
 */
const activeNav = ref(navItems[0]?.key ?? '')

/**
 * iframe DOM 引用
 */
const iframeRef = ref(null)

/**
 * 用户下拉菜单是否可见
 */
const isUserMenuVisible = ref(false)

/**
 * 用户菜单触发器 DOM 引用
 */
const userMenuTriggerRef = ref(null)

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
 * 两段式认证检查
 * 1. 先调用 refreshToken 刷新令牌（会查服务端数据库，能实时感知 token 被删除/踢人）
 * 2. 刷新成功后再 validateToken 验证并应用用户数据
 * 3. 若 refresh 或 validate 失败则调用 redirectToLogin 跳转到 /login 入口（带 redirect 参数回到当前 portal URL）
 *
 * 注意：未登录时**不**渲染 LoginView，而是直接通过 redirectToLogin 跳转到 /login 入口。
 * /login 是承载 LoginView 的唯一入口。这样可以避免：
 *   - 在 /portal 短暂渲染 LoginView 后又被浏览器卸载（造成"登录页闪烁两次"）
 *   - LoginView.onMounted 触发的 /api/auth/captcha 请求被取消（造成"captcha 调两次，第一次失败"）
 */
async function checkAuth() {
  const token = localStorage.getItem('auth_token')
  if (!token) {
    // 本地无 token：直接跳到 /Agent/?redirect=/portal，由登录页统一接管
    // 不设置 authReady.value = true，避免渲染 LoginView 触发额外的 captcha 请求
    redirectToLogin({ reason: 'portal_no_token' })
    return
  }
  try {
    // 先尝试 refresh：refresh 会查服务端数据库，能实时感知 token 被删除/踢人
    const newToken = await refreshToken()
    localStorage.setItem('auth_token', newToken)
    const data = await validateToken()
    applyUserData(data)
    // 已登录：标记为就绪，Vue 将渲染门户导航栏与主内容区
    authReady.value = true
  } catch {
    // refresh 或 validate 失败（典型场景：被 admin 强制下线后 refresh_token 已被服务端删除）
    // 清除本地 token，跳登录页（带 redirect = 当前 portal URL）
    // 注意：失败路径**不**置 authReady.value = true，避免在跳转前渲染 LoginView
    clearAuth()
    redirectToLogin({ reason: 'portal_auth_failed' })
  }
}

// 兜底：若 checkAuth 在 5 秒内未完成且仍处于"未登录"状态（例如 redirectToLogin 未触发跳转），
// 强制将 authReady 置为 true，避免页面卡死在占位符
// 注：失败路径下不修改 authReady，但保留此兜底防止异常死锁
setTimeout(() => {
  if (!authReady.value) {
    authReady.value = true
  }
}, 5000)

/**
 * 获取当前激活的导航项对象
 * @returns {Object|null} 当前 navItem；找不到时返回 null
 */
function getActiveItem() {
  return navItems.find((n) => n.key === activeNav.value) || null
}

/**
 * 计算 postMessage 的 targetOrigin
 *
 * 优先使用 navItem 中显式配置的 targetOrigin；否则根据 url 推断：
 * - 相对路径（如 /knowledge.html）→ 当前页面 origin
 * - 绝对 URL → URL 的 origin
 *
 * @param {Object} item - navItem 对象
 * @returns {string} targetOrigin
 */
function resolveTargetOrigin(item) {
  if (item.targetOrigin) return item.targetOrigin
  try {
    return new URL(item.url, window.location.origin).origin
  } catch {
    // 解析失败时回退到当前 origin（保守策略，避免把 token 泄给未知源）
    return window.location.origin
  }
}

/**
 * 防止 sendAuthToIframe 并发执行的标志锁
 */
let isIssuingPortalToken = false

/**
 * 向当前激活的 iframe 推送门户子 refresh_token
 *
 * 流程：
 * 1. 查找当前激活的 navItem，type 必须为 'iframe'
 * 2. 调 /api/auth/issue-portal-refresh-token 拿子 token
 * 3. 通过 postMessage 推送 PORTAL_AUTH 消息给 iframe.contentWindow
 *
 * 失败时不抛错，仅 console.error；保证不影响门户 UI。
 *
 * @returns {Promise<void>}
 */
async function sendAuthToIframe() {
  if (isIssuingPortalToken) {
    console.log('[PortalApp] sendAuthToIframe 正在执行中，跳过重复调用')
    return
  }
  isIssuingPortalToken = true

  console.log('[PortalApp] sendAuthToIframe 开始')
  const item = getActiveItem()
  console.log('[PortalApp] 当前激活项:', { key: item?.key, type: item?.type, url: item?.url })
  if (!item || item.type !== 'iframe') {
    console.warn('[PortalApp] 当前激活项不是 iframe 类型，跳过发送')
    isIssuingPortalToken = false
    return
  }
  const iframe = iframeRef.value
  if (!iframe) {
    console.warn('[PortalApp] iframeRef.value 为 null，无法获取 iframe DOM')
    isIssuingPortalToken = false
    return
  }
  if (!iframe.contentWindow) {
    console.warn('[PortalApp] iframe.contentWindow 不可用')
    isIssuingPortalToken = false
    return
  }
  console.log('[PortalApp] iframe DOM 存在，contentWindow 可用')

  const targetOrigin = resolveTargetOrigin(item)
  console.log('[PortalApp] targetOrigin 解析结果:', targetOrigin)

  console.log('[PortalApp] 开始调用 issuePortalRefreshToken')
  let tokenInfo
  try {
    tokenInfo = await issuePortalRefreshToken()
  } catch (e) {
    console.error('[PortalApp] 颁发门户子 refresh_token 失败:', e)
    isIssuingPortalToken = false
    return
  }

  const tokenPreview = tokenInfo.portal_refresh_token ? tokenInfo.portal_refresh_token.substring(0, 8) + '...' : '空'
  console.log('[PortalApp] 获取到 portal_refresh_token:', tokenPreview, 'expires_in:', tokenInfo.expires_in)

  const payload = {
    type: 'PORTAL_AUTH',
    refreshToken: tokenInfo.portal_refresh_token,
    username: localStorage.getItem('username') || '',
    userId: localStorage.getItem('user_id') || '',
    userRole: localStorage.getItem('user_role') || '',
    apiBaseUrl: '/',
    issuedAt: Date.now(),
    expiresIn: tokenInfo.expires_in
  }
  console.log('[PortalApp] 即将通过 postMessage 发送 PORTAL_AUTH 到 origin:', targetOrigin, 'payload:', {
    type: payload.type,
    username: payload.username,
    userId: payload.userId,
    userRole: payload.userRole,
    refreshToken: tokenPreview,
    issuedAt: payload.issuedAt,
    expiresIn: payload.expiresIn
  })
  iframe.contentWindow.postMessage(payload, targetOrigin)
  console.log('[PortalApp] postMessage 发送完成')
  isIssuingPortalToken = false
}

/**
 * iframe 加载完成事件处理：推送 PORTAL_AUTH
 * @returns {void}
 */
function onIframeLoad() {
  console.log('[PortalApp] iframe load 事件触发，准备发送 PORTAL_AUTH')
  sendAuthToIframe()
}

/**
 * 监听第三方 iframe 的 postMessage 消息
 *
 * 安全策略：
 * - 仅响应 event.source === 当前 iframe.contentWindow 的消息（防冒用）
 * - 仅处理 type === 'PORTAL_AUTH_REQUEST' 的请求
 *
 * @param {MessageEvent} event - postMessage 事件
 * @returns {void}
 */
function handlePortalMessage(event) {
  console.log('[PortalApp] 收到 message 事件，origin:', event.origin, 'type:', event.data?.type)
  const iframe = iframeRef.value
  if (!iframe || !iframe.contentWindow) {
    console.warn('[PortalApp] iframe 不可用，忽略 message 事件')
    return
  }
  if (event.source !== iframe.contentWindow) {
    console.warn('[PortalApp] event.source 与当前 iframe.contentWindow 不一致，忽略 message 事件')
    return
  }
  if (event.data && event.data.type === 'PORTAL_AUTH_REQUEST') {
    console.log('[PortalApp] 收到 PORTAL_AUTH_REQUEST，重新发送 PORTAL_AUTH')
    sendAuthToIframe()
  } else {
    console.log('[PortalApp] 收到非 PORTAL_AUTH_REQUEST 消息，已忽略')
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
  redirectToLogin({ reason: 'user_logout' })
}

/**
 * 处理导航项切换
 * @param {string} key - 被点击的导航项 key
 */
function handleNavClick(key) {
  activeNav.value = key
}

onMounted(() => {
  checkAuth()
  document.addEventListener('click', handleClickOutside)
  document.addEventListener('keydown', handleKeydown)
  window.addEventListener('message', handlePortalMessage)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
  document.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('message', handlePortalMessage)
})
</script>

<template>
  <!-- 认证状态检查中 / 未登录跳转前：仅显示占位符，不渲染 LoginView
       原因：避免在 /portal 短暂渲染 LoginView 后又被浏览器卸载（造成"登录页闪烁两次"），
            以及避免 LoginView.onMounted 触发的 /api/auth/captcha 请求被取消（造成"captcha 调两次，第一次失败"）。
       跳转目标：redirectToLogin() 会跳到 /login?redirect=/portal，由 /login 入口统一渲染登录页 -->
  <div v-if="!isLoggedIn" class="auth-loading-screen">
    <div class="auth-loading-spinner"></div>
    <div class="auth-loading-text">正在验证登录状态...</div>
  </div>

  <!-- 已登录：显示导航栏 + 主内容区 -->
  <div v-else class="portal-wrapper">
    <!-- 顶部蓝色导航栏 -->
    <nav class="top-nav" :style="{ height: `${NAV_HEIGHT}px` }">
      <!-- 左侧：系统标题 -->
      <div class="nav-left">
        <span class="system-title">{{ appConfig.brandTitle }}</span>
      </div>

      <!-- 中间：导航项 -->
      <div class="nav-center">
        <button
          v-for="item in navItems"
          :key="item.key"
          class="nav-item"
          :class="{ active: activeNav === item.key }"
          @click="handleNavClick(item.key)"
        >
          {{ item.label }}
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
      <!-- 当前激活项为 iframe：在主内容区嵌入 iframe，并在加载完成时推送 PORTAL_AUTH -->
      <template v-if="getActiveItem() && getActiveItem().type === 'iframe'">
        <iframe
          ref="iframeRef"
          :src="getActiveItem().url"
          width="100%"
          height="100%"
          frameborder="0"
          :title="getActiveItem().label"
          @load="onIframeLoad"
        ></iframe>
      </template>

      <!-- 当前激活项为 placeholder：显示占位提示 -->
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
/* 认证状态检查中的全屏 loading 占位
   用途：在 checkAuth 还未完成时显示，避免先渲染 LoginView 再被替换造成的视觉闪烁
   设计：与主应用色调保持一致，居中显示旋转动画和提示文字 */
.auth-loading-screen {
  position: fixed;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-base);
  background: linear-gradient(135deg, #EBF4FF 0%, #F0F7FF 40%, #FFFFFF 100%);
  z-index: 9999;
}

.auth-loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid rgba(30, 90, 168, 0.15);
  border-top-color: #1E5AA8;
  border-radius: 50%;
  animation: auth-loading-spin 0.8s linear infinite;
}

.auth-loading-text {
  font-size: var(--font-size-base);
  color: var(--color-text-secondary);
  letter-spacing: 0.5px;
}

@keyframes auth-loading-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

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
