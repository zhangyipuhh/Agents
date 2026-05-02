<script setup>
import { ref } from 'vue'

// Props
const props = defineProps({
  title: {
    type: String,
    default: '新对话'
  }
})

// 状态
const isShareDropdownOpen = ref(false)

// 事件
const emit = defineEmits(['new-chat', 'share'])

// 处理新建聊天
const handleNewChat = () => {
  emit('new-chat')
}

// 处理分享
const handleShare = () => {
  isShareDropdownOpen.value = !isShareDropdownOpen.value
  if (isShareDropdownOpen.value) {
    emit('share')
  }
}
</script>

<template>
  <header class="topbar">
    <div class="topbar-left">
      <h1 class="topbar-title">{{ title }}</h1>
    </div>

    <div class="topbar-right">
      <!-- 新建按钮 -->
      <button class="topbar-btn topbar-btn-primary" @click="handleNewChat">
        <svg class="btn-icon" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" clip-rule="evenodd"/>
        </svg>
        <span>新建</span>
      </button>

      <!-- 分享按钮 -->
      <div class="dropdown-wrapper">
        <button class="topbar-btn" @click="handleShare">
          <svg class="btn-icon" viewBox="0 0 20 20" fill="currentColor">
            <path d="M15 8a3 3 0 10-2.977-2.63l-4.94 2.47a3 3 0 100 4.319l4.94 2.47a3 3 0 10.895-1.789l-4.94-2.47a3.027 3.027 0 000-.74l4.94-2.47C13.456 7.68 14.19 8 15 8z"/>
          </svg>
          <span>分享</span>
        </button>

        <!-- 分享下拉菜单（可选） -->
        <transition name="dropdown">
          <div v-if="isShareDropdownOpen" class="dropdown-menu">
            <button class="dropdown-item">复制链接</button>
            <button class="dropdown-item">生成二维码</button>
            <button class="dropdown-item">导出对话</button>
          </div>
        </transition>
      </div>
    </div>
  </header>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--topbar-height);
  padding: 0 24px;
  background-color: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border);
  position: relative;
  z-index: var(--z-sticky);
}

/* 左侧区域 */
.topbar-left {
  display: flex;
  align-items: center;
  gap: 16px;
  min-width: 0;
}

.topbar-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 右侧区域 */
.topbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* 按钮通用样式 */
.topbar-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  background-color: transparent;
  border-radius: var(--radius-sm);
  transition: var(--transition-colors), var(--transition-transform), var(--transition-shadow);
  position: relative;
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

  &:active:not(:disabled) {
    transform: scale(var(--scale-active));
  }

  /* Ensure content is above pseudo-element */
  > * {
    position: relative;
    z-index: 1;
  }
}

/* 主要按钮样式 */
.topbar-btn-primary {
  background-color: var(--color-accent);
  color: white;

  &:hover {
    background-color: var(--color-accent-hover);
    color: white;
  }
}

.btn-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}

/* 下拉菜单容器 */
.dropdown-wrapper {
  position: relative;
}

.dropdown-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  min-width: 160px;
  padding: 6px;
  background-color: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  z-index: var(--z-dropdown);
  transform-origin: top right;
  contain: layout style paint;
}

.dropdown-item {
  display: block;
  width: 100%;
  padding: 10px 14px;
  text-align: left;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  border-radius: var(--radius-sm);
  transition: var(--transition-colors), var(--transition-transform);
  position: relative;

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

  &:active:not(:disabled) {
    transform: scale(var(--scale-active));
  }

  /* Ensure text is above pseudo-element */
  > span,
  & {
    position: relative;
    z-index: 1;
  }
}

/* 下拉动画 */
.dropdown-enter-active {
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.dropdown-leave-active {
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.dropdown-enter-from {
  opacity: 0;
  transform: translateY(-8px) scale(0.95);
}

.dropdown-enter-to {
  opacity: 1;
  transform: translateY(0) scale(1);
}

.dropdown-leave-from {
  opacity: 1;
  transform: translateY(0) scale(1);
}

.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-4px) scale(0.98);
}

/* 响应式调整 */
@media (max-width: 768px) {
  .topbar {
    padding: 0 16px;
  }

  .topbar-btn span {
    display: none;
  }

  .topbar-btn {
    padding: 8px;
  }
}
</style>
