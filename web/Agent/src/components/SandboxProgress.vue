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

const progressPercent = computed(() => {
  if (!props.summary) return 0
  return props.summary.progress_pct || 0
})

const currentStep = computed(() => {
  if (!props.summary) return 0
  return props.summary.current_step || 0
})

const totalSteps = computed(() => {
  if (!props.summary) return 5
  return props.summary.total_steps || 5
})

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
    <div class="progress-header">
      <span class="progress-icon">📦</span>
      <span class="progress-title">沙盒执行</span>
      <span class="progress-status" :class="status">{{ statusText }}</span>
    </div>

    <div class="progress-bar-container">
      <div class="progress-bar" :style="{ width: progressPercent + '%' }" :class="{ running: status === 'running' }"></div>
    </div>

    <div class="progress-info">
      <span class="progress-step">当前进度 {{ currentStep }}/{{ totalSteps }}</span>
      <span class="progress-message">{{ statusIcon }} {{ statusMessage }}</span>
      <span v-if="elapsedTime" class="progress-time">{{ elapsedTime }}</span>
    </div>

    <div class="progress-hint">
      <span>点击查看详情</span>
      <svg class="arrow-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="9 18 15 12 9 6" />
      </svg>
    </div>
  </div>
</template>

<style scoped>
.sandbox-progress {
  width: 100%;
  max-width: 480px;
  border: 1px solid #e0e0e0;
  border-radius: 12px;
  padding: 12px 16px;
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
  border-color: #10b981;
  background: linear-gradient(135deg, #f0fdf4 0%, #ffffff 100%);
}

.sandbox-progress.success {
  border-color: #10b981;
  background: linear-gradient(135deg, #f0fdf4 0%, #ffffff 100%);
}

.sandbox-progress.error {
  border-color: #ef4444;
  background: linear-gradient(135deg, #fef2f2 0%, #ffffff 100%);
}

.progress-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.progress-icon {
  font-size: 16px;
}

.progress-title {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.progress-status {
  font-size: 12px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 9999px;
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
}

.progress-status.running {
  background-color: rgba(16, 185, 129, 0.1);
  color: #10b981;
}

.progress-status.success {
  background-color: rgba(16, 185, 129, 0.1);
  color: #10b981;
}

.progress-status.error {
  background-color: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.progress-bar-container {
  height: 6px;
  background: #e0e0e0;
  border-radius: 3px;
  margin: 8px 0;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #10b981, #34d399);
  border-radius: 3px;
  transition: width 0.3s ease;
}

.progress-bar.running {
  animation: progressPulse 1.5s ease-in-out infinite;
}

@keyframes progressPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.progress-info {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.progress-step {
  font-size: 12px;
  color: var(--color-text-secondary);
  font-weight: 500;
}

.progress-message {
  font-size: 12px;
  color: var(--color-text-primary);
}

.progress-time {
  font-size: 12px;
  color: var(--color-text-muted);
  margin-left: auto;
}

.progress-hint {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  margin-top: 8px;
  font-size: 11px;
  color: var(--color-text-muted);
}

.arrow-icon {
  width: 12px;
  height: 12px;
}
</style>
