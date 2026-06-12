<script setup>
/**
 * SandboxProgress - 聊天气泡中展示沙盒执行进度摘要的组件
 *
 * Props:
 *   summary: SandboxSummary 对象，包含当前步骤、总步骤、进度百分比、状态消息等
 *   status: 'running' | 'success' | 'error'，当前执行状态
 *
 * Emits:
 *   click: 用户点击组件时触发，用于展开右侧详情面板
 */
const props = defineProps({
  summary: {
    type: Object,
    default: null
  },
  status: {
    type: String,
    default: 'running',
    validator: (value) => ['running', 'success', 'error'].includes(value)
  }
})

const emit = defineEmits(['click'])

function handleClick() {
  emit('click')
}

function formatTime(ms) {
  if (!ms || ms < 0) return ''
  if (ms < 1000) {
    return ms + 'ms'
  }
  if (ms < 60000) {
    return (ms / 1000).toFixed(1) + 's'
  }
  const minutes = Math.floor(ms / 60000)
  const seconds = ((ms % 60000) / 1000).toFixed(0)
  return minutes + '分' + seconds + '秒'
}

const statusTextMap = {
  running: '执行中',
  success: '已完成',
  error: '执行失败'
}

const statusText = computed(() => statusTextMap[props.status] || '执行中')

const statusMessage = computed(() => {
  if (!props.summary) return '准备执行...'
  return props.summary.status_message || '准备执行...'
})

const statusIcon = computed(() => {
  if (!props.summary) return '⏳'
  return props.summary.status_icon || '⏳'
})

const elapsedTime = computed(() => {
  if (!props.summary) return ''
  return formatTime(props.summary.elapsed_ms)
})
</script>

<script>
import { computed } from 'vue'
export default {
  name: 'SandboxProgress'
}
</script>

<template>
  <div
    class="sandbox-progress"
    :class="{ clickable: true, running: status === 'running', success: status === 'success', error: status === 'error' }"
    @click="handleClick"
  >
    <div class="progress-row">
      <span class="progress-status" :class="status">{{ statusText }}</span>
      <span class="progress-message">{{ statusIcon }} {{ statusMessage }}</span>
      <span v-if="elapsedTime" class="progress-time">{{ elapsedTime }}</span>
      <span class="progress-hint">
        <span>点击查看详情</span>
        <svg class="arrow-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="9 18 15 12 9 6" />
        </svg>
      </span>
    </div>
  </div>
</template>

<style scoped>
.sandbox-progress {
  width: 100%;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 4px 10px;
  background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%);
  cursor: pointer;
  transition: all 0.2s ease;
  user-select: none;
}

.sandbox-progress:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transform: translateY(-1px);
}

.sandbox-progress.running {
  border-color: var(--color-accent);
  background: linear-gradient(135deg, var(--color-accent-light) 0%, #ffffff 100%);
}

.sandbox-progress.success {
  border-color: var(--color-accent);
  background: linear-gradient(135deg, var(--color-accent-light) 0%, #ffffff 100%);
}

.sandbox-progress.error {
  border-color: #ef4444;
  background: linear-gradient(135deg, #fef2f2 0%, #ffffff 100%);
}

.progress-row {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
}

.progress-status {
  font-size: 11px;
  font-weight: 500;
  padding: 1px 6px;
  border-radius: 9999px;
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  flex-shrink: 0;
}

.progress-status.running {
  background-color: rgba(30, 90, 168, 0.1);
  color: var(--color-accent);
}

.progress-status.success {
  background-color: rgba(30, 90, 168, 0.1);
  color: var(--color-accent);
}

.progress-status.error {
  background-color: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.progress-message {
  font-size: 11px;
  color: var(--color-text-primary);
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.progress-time {
  font-size: 10px;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.progress-hint {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 10px;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.arrow-icon {
  width: 10px;
  height: 10px;
}
</style>
