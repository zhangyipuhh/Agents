<script setup>
/**
 * ProjectDropdown 组件（2026-06-30 新增）
 *
 * 紧挨着 InputBox 上方显示的「项目工作」下拉框。
 * 提供三个动作：
 *   - 新建空白项目
 *   - 使用现有文件夹
 *   - 不使用文件夹
 *
 * 顶部预览当前已选项（只读）。
 * 样式与现有 agent-dropdown 保持一致。
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  currentProject: {
    type: Object,
    default: null
  },
  disabled: {
    type: Boolean,
    default: false
  },
  // 2026-07-01 新增：是否锁定（已发送过消息或历史会话时为 true）
  // 与 disabled（streaming 中）独立：两者任一为 true 都禁用按钮
  locked: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['select-project', 'create-project', 'pick-existing'])

const isOpen = ref(false)
const dropdownRef = ref(null)
const triggerRef = ref(null)
const dropdownStyle = ref({})

// 2026-07-01 新增：effectiveDisabled 统一 disabled（streaming）+ locked（已发送）两个维度，
// 模板和 toggleDropdown 都消费这个计算值，避免散落重复判断。
const effectiveDisabled = computed(() => props.disabled || props.locked)

/**
 * 触发按钮显示文本
 *   - 有项目：项目名
 *   - 无项目：「不使用文件夹」
 */
const triggerLabel = computed(() => {
  if (props.currentProject && props.currentProject.name) {
    return props.currentProject.name
  }
  return '不使用文件夹'
})

function toggleDropdown() {
  // 2026-07-01 修复：locked=true 时（已发送过消息或历史会话）也短路 toggle，
  // 避免下拉菜单通过正常点击路径打开
  if (effectiveDisabled.value) return
  if (isOpen.value) {
    closeDropdown()
  } else {
    openDropdown()
  }
}

function openDropdown() {
  isOpen.value = true
  nextTickPosition()
}

function closeDropdown() {
  isOpen.value = false
}

function nextTickPosition() {
  if (!triggerRef.value) return
  const rect = triggerRef.value.getBoundingClientRect()
  dropdownStyle.value = {
    position: 'fixed',
    top: `${rect.bottom + 4}px`,
    left: `${rect.left}px`,
    minWidth: `${rect.width}px`
  }
}

function handleSelectNone() {
  emit('select-project', null)
  closeDropdown()
}

function handleCreate() {
  emit('create-project')
  closeDropdown()
}

function handlePick() {
  emit('pick-existing')
  closeDropdown()
}

function handleClickOutside(event) {
  if (!isOpen.value) return
  if (triggerRef.value && triggerRef.value.contains(event.target)) return
  if (dropdownRef.value && dropdownRef.value.contains(event.target)) return
  closeDropdown()
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
  window.addEventListener('resize', nextTickPosition)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
  window.removeEventListener('resize', nextTickPosition)
})
</script>

<template>
  <div class="project-dropdown-wrapper">
    <button
      ref="triggerRef"
      class="project-trigger"
      :class="{ disabled: effectiveDisabled, open: isOpen }"
      :disabled="effectiveDisabled"
      @click.stop="toggleDropdown"
    >
      <svg class="project-icon" viewBox="0 0 20 20" fill="currentColor">
        <path d="M2 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
      </svg>
      <span class="project-trigger-label">{{ triggerLabel }}</span>
      <svg
        class="project-chevron"
        :class="{ rotated: isOpen }"
        viewBox="0 0 20 20"
        fill="currentColor"
      >
        <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd" />
      </svg>
    </button>

    <Teleport to="body">
      <div
        v-if="isOpen"
        ref="dropdownRef"
        class="project-dropdown-menu"
        :style="dropdownStyle"
      >
        <!-- 顶部只读预览 -->
        <div class="project-dropdown-header">
          <svg class="header-icon" viewBox="0 0 20 20" fill="currentColor">
            <path d="M2 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
          </svg>
          <span class="header-label">{{ triggerLabel }}</span>
        </div>
        <div class="project-dropdown-divider"></div>
        <div class="project-dropdown-item" @click.stop="handleCreate">
          <svg class="item-icon" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M10 5a1 1 0 011 1v3h3a1 1 0 110 2h-3v3a1 1 0 11-2 0v-3H6a1 1 0 110-2h3V6a1 1 0 011-1z" clip-rule="evenodd" />
          </svg>
          <span>新建空白项目</span>
        </div>
        <div class="project-dropdown-item" @click.stop="handlePick">
          <svg class="item-icon" viewBox="0 0 20 20" fill="currentColor">
            <path d="M2 4a2 2 0 012-2h4.586A2 2 0 0110 2.586L13.414 6H16a2 2 0 012 2v8a2 2 0 01-2 2H4a2 2 0 01-2-2V4z" />
          </svg>
          <span>使用现有文件夹</span>
        </div>
        <div class="project-dropdown-item" @click.stop="handleSelectNone">
          <svg class="item-icon" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h8a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 2v8h8V6H6z" clip-rule="evenodd" />
          </svg>
          <span>不使用文件夹</span>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.project-dropdown-wrapper {
  display: inline-block;
}

.project-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  margin-top: 1px;
  background-color: var(--color-bg-primary);
  border: none;
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: var(--transition-colors), var(--transition-shadow);
  font-family: inherit;
}

.project-trigger:hover:not(.disabled) {
  background-color: var(--color-bg-active);
  color: var(--color-text-primary);
}

.project-trigger.open {
  background-color: var(--color-accent-light);
  color: var(--color-accent);
}

.project-trigger.disabled {
  opacity: var(--opacity-disabled);
  cursor: not-allowed;
}

.project-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  color: var(--color-accent);
}

.project-trigger-label {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-chevron {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  transition: transform 0.2s ease;
}

.project-chevron.rotated {
  transform: rotate(-180deg);
}

.project-dropdown-menu {
  background-color: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12), 0 2px 8px rgba(0, 0, 0, 0.08);
  padding: 6px;
  z-index: 200;
  min-width: 200px;
}

.project-dropdown-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  font-weight: var(--font-weight-semibold);
  background-color: var(--color-accent-light);
  border-radius: var(--radius-sm);
}

.header-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  color: var(--color-accent);
}

.header-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-dropdown-divider {
  height: 1px;
  background-color: var(--color-border-light);
  margin: 6px 4px;
}

.project-dropdown-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: var(--transition-colors);
  font-family: inherit;
}

.project-dropdown-item:hover {
  background-color: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.item-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  opacity: 0.8;
}
</style>
