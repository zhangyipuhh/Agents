<script setup>
import { ref } from 'vue'

const emit = defineEmits(['toggle-sidebar', 'new-chat'])

const isSidebarCollapsed = ref(false)
const isHistoryCollapsed = ref(false)
const isLabCollapsed = ref(false)
const isExpertCollapsed = ref(false)
const activeMenu = ref('new-task')

const historySessions = ref([
  { id: 1, title: '数据分析报告生成', time: '10:30', active: true },
  { id: 2, title: '地图操作自动化', time: '昨天', active: false },
  { id: 3, title: '客户信息整理', time: '3天前', active: false },
])

const handleMenuClick = (menuId) => {
  activeMenu.value = menuId
  if (menuId === 'new-task') {
    emit('new-chat')
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

const toggleExpert = () => {
  isExpertCollapsed.value = !isExpertCollapsed.value
}
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
        <span v-show="!isSidebarCollapsed" class="logo-text">ZYP</span>
      </div>
      <button class="sidebar-toggle" @click="toggleSidebar" :title="isSidebarCollapsed ? '展开侧栏' : '收起侧栏'">
        <svg viewBox="0 0 20 20" fill="currentColor" class="toggle-icon" :class="{ rotated: isSidebarCollapsed }">
          <path fill-rule="evenodd" d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z" clip-rule="evenodd"/>
        </svg>
      </button>
    </div>

    <!-- 主导航区域 -->
    <nav class="sidebar-nav">
      <!-- 新建任务 -->
      <button
        class="menu-item menu-item-primary"
        :class="{ active: activeMenu === 'new-task' }"
        @click="handleMenuClick('new-task')"
      >
        <svg class="menu-icon" viewBox="0 0 20 20" fill="currentColor">
          <path d="M10 5a1 1 0 011 1v3h3a1 1 0 110 2h-3v3a1 1 0 11-2 0v-3H6a1 1 0 110-2h3V6a1 1 0 011-1z"/>
        </svg>
        <span v-show="!isSidebarCollapsed" class="menu-text">新建任务</span>
        <kbd v-show="!isSidebarCollapsed" class="shortcut">Ctrl+K</kbd>
      </button>

      <!-- 搜索 -->
      <button
        class="menu-item"
        :class="{ active: activeMenu === 'search' }"
        @click="handleMenuClick('search')"
      >
        <svg class="menu-icon" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clip-rule="evenodd"/>
        </svg>
        <span v-show="!isSidebarCollapsed" class="menu-text">搜索</span>
      </button>

      <!-- 资产 -->
      <button
        class="menu-item"
        :class="{ active: activeMenu === 'assets' }"
        @click="handleMenuClick('assets')"
      >
        <svg class="menu-icon" viewBox="0 0 20 20" fill="currentColor">
          <path d="M3 4a1 1 0 011-1h12a1 1 0 011 1v2a1 1 0 01-1 1H4a1 1 0 01-1-1V4zM3 10a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H4a1 1 0 01-1-1v-6zM14 9a1 1 0 00-1 1v6a1 1 0 001 1h2a1 1 0 001-1v-6a1 1 0 00-1-1h-2z"/>
        </svg>
        <span v-show="!isSidebarCollapsed" class="menu-text">资产</span>
      </button>
    </nav>

    <template v-if="!isSidebarCollapsed">

    <!-- 分组：ZYP实验室 -->
    <div class="sidebar-group">
      <button class="group-header" @click="toggleLab">
        <svg
          class="group-collapse-icon"
          :class="{ collapsed: isLabCollapsed }"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path fill-rule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clip-rule="evenodd"/>
        </svg>
        <span class="group-title">ZYP实验室</span>
      </button>
      <transition name="slide">
        <div v-show="!isLabCollapsed" class="group-items">
          <!-- 地图操作 (Beta) -->
          <button
            class="menu-item menu-item-sm"
            :class="{ active: activeMenu === 'map' }"
            @click="handleMenuClick('map')"
          >
            <svg class="menu-icon" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M12 1.586l-4 4v12.828l4-4V1.586zM3.707 3.293A1 1 0 002 4v10a1 1 0 00.293.707L6 18.414V5.586L3.707 3.293zM17.707 5.293L14 1.586v12.828l2.293 2.293A1 1 0 0018 16V6a1 1 0 00-.293-.707z" clip-rule="evenodd"/>
            </svg>
            <span class="menu-text">地图操作</span>
            <span class="tag tag-beta">Beta</span>
          </button>

          <!-- 数据分析 -->
          <button
            class="menu-item menu-item-sm"
            :class="{ active: activeMenu === 'analytics' }"
            @click="handleMenuClick('analytics')"
          >
            <svg class="menu-icon" viewBox="0 0 20 20" fill="currentColor">
              <path d="M2 11a1 1 0 011-1h2a1 1 0 011 1v5a1 1 0 01-1 1H3a1 1 0 01-1-1v-5zM8 7a1 1 0 011-1h2a1 1 0 011 1v9a1 1 0 01-1 1H9a1 1 0 01-1-1V7zM14 4a1 1 0 011-1h2a1 1 0 011 1v12a1 1 0 01-1 1h-2a1 1 0 01-1-1V4z"/>
            </svg>
            <span class="menu-text">数据分析</span>
          </button>

          <!-- Skills技能 (New) -->
          <button
            class="menu-item menu-item-sm"
            :class="{ active: activeMenu === 'skills' }"
            @click="handleMenuClick('skills')"
          >
            <svg class="menu-icon" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clip-rule="evenodd"/>
            </svg>
            <span class="menu-text">Skills技能</span>
            <span class="tag tag-new">New</span>
          </button>
        </div>
      </transition>
    </div>

    <!-- 分组：专家 -->
    <div class="sidebar-group">
      <button
        class="group-header"
        @click="toggleExpert"
      >
        <svg
          class="group-collapse-icon"
          :class="{ collapsed: isExpertCollapsed }"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path fill-rule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clip-rule="evenodd"/>
        </svg>
        <span class="group-title">专家</span>
      </button>
      <transition name="slide">
        <div v-show="!isExpertCollapsed" class="group-items">
          <button
            class="menu-item menu-item-sm"
            :class="{ active: activeMenu === 'experts' }"
            @click="handleMenuClick('experts')"
          >
            <svg class="menu-icon" viewBox="0 0 20 20" fill="currentColor">
              <path d="M13 6a3 3 0 11-6 0 3 3 0 016 0zM18 8a2 2 0 11-4 0 2 2 0 014 0zM14 15a4 4 0 00-8 0v3h8v-3zM6 8a2 2 0 11-4 0 2 2 0 014 0zM16 18v-3a5.972 5.972 0 00-.75-2.906A3.005 3.005 0 0119 15v3h-3zM4.75 12.094A5.973 5.973 0 004 15v3H1v-3a3 3 0 013.75-2.906z"/>
            </svg>
            <span class="menu-text">探索专家</span>
          </button>
        </div>
      </transition>
    </div>

    <!-- 任务记录区（可折叠） -->
    <div class="sidebar-history">
      <button class="history-header" @click="toggleHistory">
        <svg
          class="collapse-icon"
          :class="{ collapsed: isHistoryCollapsed }"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path fill-rule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clip-rule="evenodd"/>
        </svg>
        <span class="history-title">任务记录</span>
      </button>

      <transition name="slide">
        <div v-show="!isHistoryCollapsed" class="history-list">
          <button
            v-for="session in historySessions"
            :key="session.id"
            class="history-item"
            :class="{ active: session.active }"
          >
            <div class="history-content">
              <span class="history-title-text">{{ session.title }}</span>
              <span class="history-time">{{ session.time }}</span>
            </div>
          </button>
        </div>
      </transition>
    </div>
    </template>

    <!-- 底部用户信息 -->
    <div class="sidebar-user">
      <div class="user-avatar">
        <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect width="40" height="40" rx="20" fill="var(--color-accent-light)"/>
          <path d="M20 20C23.866 20 27 16.866 27 13C27 9.13401 23.866 6 20 6C16.134 6 13 9.13401 13 13C13 16.866 16.134 20 20 20Z" fill="var(--color-accent)"/>
          <path d="M20 22C14.477 22 10 26.477 10 32V34H30V32C30 26.477 25.523 22 20 22Z" fill="var(--color-accent)"/>
        </svg>
      </div>
      <div v-show="!isSidebarCollapsed" class="user-info">
        <span class="user-name">用户名</span>
        <span class="user-tag tag-free">免费</span>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: var(--sidebar-width);
  min-width: var(--sidebar-width);
  height: 100%;
  background-color: var(--color-bg-primary);
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  contain: var(--contain-layout);
  transition: width 0.3s ease, min-width 0.3s ease;

  &.collapsed {
    width: 60px;
    min-width: 60px;

    .sidebar-logo {
      justify-content: center;
      position: relative;
      cursor: pointer;

      .logo-container {
        transition: opacity 0.2s ease;
      }

      .sidebar-toggle {
        position: absolute;
        opacity: 0;
        transition: opacity 0.2s ease;
      }

      &:hover {
        .logo-container {
          opacity: 0;
        }

        .sidebar-toggle {
          opacity: 1;
        }
      }
    }

    .sidebar-nav {
      padding: 12px 6px;
    }

    .menu-item {
      justify-content: center;
      padding: 10px;
    }

    .sidebar-user {
      justify-content: center;
      padding: 6px;
      margin-top: auto;
    }
  }
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

  &:hover {
    background-color: var(--color-accent-hover);
    color: white;
  }

  &.active {
    background-color: var(--color-accent-hover);
    color: white;
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

/* 用户信息区域 */
.sidebar-user {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 12px;
  border-top: 1px solid var(--color-border-light);
  background-color: var(--color-bg-secondary);
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
  font-size: calc(var(--font-size-base) * 0.7);
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
</style>
