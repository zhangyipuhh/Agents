<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import SandboxEventItem from './SandboxEventItem.vue'

/**
 * SandboxDrawer - 右侧滑出面板，展示沙盒执行详情
 *
 * Props:
 *   visible: 是否显示面板
 *   events: 沙盒事件列表
 *   summary: 沙盒摘要信息
 *   status: 'running' | 'success' | 'error'，当前执行状态
 *
 * Emits:
 *   close: 关闭面板时触发
 */
const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  events: {
    type: Array,
    default: () => []
  },
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

const emit = defineEmits(['close'])

const timelineRef = ref(null)

function handleClose() {
  emit('close')
}

function handleOverlayClick(event) {
  if (event.target === event.currentTarget) {
    handleClose()
  }
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
  running: '执行中...',
  success: '执行完成',
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

const elapsedTime = computed(() => {
  if (!props.summary) return ''
  return formatTime(props.summary.elapsed_ms)
})

function isCurrentStep(eventStep) {
  if (!props.summary) return false
  return eventStep === props.summary.current_step && props.status === 'running'
}

// 当事件更新时自动滚动到底部
watch(() => props.events.length, async () => {
  if (props.status === 'running') {
    await nextTick()
    if (timelineRef.value) {
      timelineRef.value.scrollTop = timelineRef.value.scrollHeight
    }
  }
})
</script>

<template>
  <Transition name="drawer">
    <div v-if="visible" class="sandbox-drawer-overlay" @click="handleOverlayClick">
      <div class="sandbox-drawer" @click.stop>
        <!-- 头部 -->
        <div class="drawer-header">
          <div class="drawer-title">
            <span class="title-icon">📦</span>
            <span>沙盒执行详情</span>
          </div>
          <button class="close-btn" @click="handleClose">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <!-- 进度摘要 -->
        <div class="drawer-summary">
          <div class="summary-status" :class="status">
            <span class="status-indicator" :class="status"></span>
            <span class="status-text">{{ statusText }}</span>
          </div>
          <div class="summary-progress">
            <div class="progress-track">
              <div class="progress-fill" :style="{ width: progressPercent + '%' }" :class="{ running: status === 'running' }"></div>
            </div>
            <span class="progress-text">{{ currentStep }}/{{ totalSteps }}</span>
          </div>
          <div v-if="elapsedTime" class="summary-time">
            耗时: {{ elapsedTime }}
          </div>
        </div>

        <!-- 事件时间线 -->
        <div class="drawer-timeline" ref="timelineRef">
          <div v-if="events.length === 0" class="timeline-empty">
            <span class="empty-icon">⏳</span>
            <span class="empty-text">等待执行事件...</span>
          </div>

          <template v-else>
            <SandboxEventItem
              v-for="(event, index) in events"
              :key="event.timestamp + '-' + index"
              :event="event"
              :is-active="isCurrentStep(event.step)"
            />
          </template>

          <!-- 实时输出区域 -->
          <div v-if="status === 'running'" class="live-output">
            <span class="live-indicator">●</span>
            <span>执行中...</span>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.sandbox-drawer-overlay {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  background: rgba(0, 0, 0, 0.3);
  z-index: 1000;
  display: flex;
  justify-content: flex-end;
}

.sandbox-drawer {
  width: 480px;
  max-width: 90vw;
  height: 100%;
  background: #ffffff;
  box-shadow: -4px 0 20px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
}

.drawer-header {
  padding: 16px 20px;
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
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.title-icon {
  font-size: 18px;
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

/* 进度摘要 */
.drawer-summary {
  padding: 16px 20px;
  border-bottom: 1px solid #e8e8e8;
  background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%);
  flex-shrink: 0;
}

.summary-status {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #10b981;
}

.status-indicator.running {
  background-color: #f59e0b;
  animation: statusBlink 1.5s ease-in-out infinite;
}

.status-indicator.error {
  background-color: #ef4444;
}

@keyframes statusBlink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.status-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-primary);
}

.summary-progress {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.progress-track {
  flex: 1;
  height: 6px;
  background-color: #e0e0e0;
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #10b981, #34d399);
  border-radius: 3px;
  transition: width 0.3s ease;
}

.progress-fill.running {
  animation: progressPulse 1.5s ease-in-out infinite;
}

@keyframes progressPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.progress-text {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-secondary);
  min-width: 36px;
  text-align: right;
}

.summary-time {
  font-size: 12px;
  color: var(--color-text-muted);
}

/* 时间线 */
.drawer-timeline {
  flex: 1;
  overflow-y: auto;
  padding: 0 20px 20px;
  position: relative;
}

/* 时间线竖线 */
.drawer-timeline::before {
  content: '';
  position: absolute;
  left: 30px;
  top: 0;
  bottom: 0;
  width: 2px;
  background: linear-gradient(to bottom, #e8e8e8 0%, #e8e8e8 100%);
  z-index: 0;
}

.timeline-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 20px;
  gap: 8px;
}

.empty-icon {
  font-size: 32px;
  opacity: 0.5;
}

.empty-text {
  font-size: 14px;
  color: var(--color-text-muted);
}

/* 实时输出指示器 */
.live-output {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px 0 0 32px;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.live-indicator {
  color: #10b981;
  animation: liveBlink 1.5s ease-in-out infinite;
}

@keyframes liveBlink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* 滑入动画 */
.drawer-enter-active,
.drawer-leave-active {
  transition: all 0.3s ease;
}

.drawer-enter-active .sandbox-drawer,
.drawer-leave-active .sandbox-drawer {
  transition: transform 0.3s ease;
}

.drawer-enter-from .sandbox-drawer,
.drawer-leave-to .sandbox-drawer {
  transform: translateX(100%);
}

.drawer-enter-from,
.drawer-leave-to {
  opacity: 0;
}

.drawer-enter-to,
.drawer-leave-from {
  opacity: 1;
}
</style>
